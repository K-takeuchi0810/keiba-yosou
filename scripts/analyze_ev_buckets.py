"""EV帯別 OOS 分析: Blend#2 の EV が anti-predictive から脱したかを判定する。

設計: docs/SECOND_LOGIT_BLEND_DESIGN.md / 背景: memory/project_p24_pred_accuracy
      (EV信号が anti-predictive)、project_roi_research_2026_06_28 (Benter補正)。

目的:
    現行の pop1-3 フィルタは EV を使わないため、Blend#2 の置換で pop1-3 ROI は
    ほぼ動かない。本分析の狙いは ROI を動かすことではなく、
    「Blend#2 が作る EV が価値指標として復活したか」を EV帯別で見ること。

方針 (固定条件):
    - 係数は 2025 fit 済み second_blend.json を固定 (2026 では再学習しない)
    - 同一の◎集合 (rank==1, skip_tentative, JRA, 払戻行あり) に対し
      linear_EV と logit_EV を両方計算
    - EV帯ごとに 件数 / 的中率 / 回収率 / 平均EV / 払戻合計 を出す
    - linear と logit の EV帯別単調性を比較
    - pop1-3 ◎ の ROI を回帰チェックとして併記
    - max_predicted_p=0.40 ゲートが mode 間で何件動くか記録
    - 方向性は paired 指標 (AUC[EV,的中] / Spearman[EV,払戻倍率]) でも見る

linear_EV はproduction の Blend#2 線形 (discount込み) = 実際に anti-predictive だった指標。
logit_EV は提案版 (sigmoid(z), discount無し) = second_blend.json の係数で計算。

使い方:
    .venv64/Scripts/python.exe -m scripts.analyze_ev_buckets --from 20260101 --to 20260614
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from predictor.rules import (
    RULES_VERSION,
    SECOND_BLEND_PATH,
    _apply_calibrator,
    _market_probabilities,
    _w,
    is_tentative,
    predict_race,
)
from scripts.backtest import (
    get_payout_row,
    horses_for_race,
    list_races,
    open_db,
    payout_from_row,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest"
EV_EDGES = [0.0, 0.8, 1.0, 1.2, 1.5, float("inf")]
MAX_PREDICTED_P_GATE = 0.40
ENV_KEYS = {
    "PRED_BLEND_MODE",
    "PRED_DISABLE_BLEND",
    "PRED_DISABLE_SECOND_BLEND",
    "PRED_DISABLE_DISCOUNT",
    "PRED_PROB_TEMPERATURE",
    "PRED_BLEND_W_RULE",
    "PRED_DISABLE_CALIBRATOR",
    "PRED_DISABLE_LGBM",
}


def _bucket_label(ev: float) -> str:
    for lo, hi in zip(EV_EDGES, EV_EDGES[1:]):
        if lo <= ev < hi:
            return f"[{lo:.1f},{hi:.1f})" if hi != float("inf") else f"[{lo:.1f},inf)"
    return "[?]"


def _summarize_buckets(rows: list[dict], ev_key: str) -> list[dict]:
    """rows を ev_key (linear_ev / logit_ev) で帯別集計。各 bet=100円賭けと仮定。"""
    buckets: dict[str, dict] = {}
    for lo, hi in zip(EV_EDGES, EV_EDGES[1:]):
        lab = f"[{lo:.1f},{hi:.1f})" if hi != float("inf") else f"[{lo:.1f},inf)"
        buckets[lab] = {"bucket": lab, "count": 0, "hits": 0, "payout_total": 0, "ev_sum": 0.0}
    for r in rows:
        lab = _bucket_label(r[ev_key])
        b = buckets[lab]
        b["count"] += 1
        b["hits"] += 1 if r["won"] else 0
        b["payout_total"] += r["payout"]
        b["ev_sum"] += r[ev_key]
    out = []
    for lab, b in buckets.items():
        n = b["count"]
        out.append({
            "bucket": lab,
            "count": n,
            "hit_rate": round(b["hits"] / n, 4) if n else 0.0,
            "return_rate": round(b["payout_total"] / (100 * n), 4) if n else 0.0,
            "mean_ev": round(b["ev_sum"] / n, 4) if n else 0.0,
            "payout_total": b["payout_total"],
        })
    return out


def _linear_probability(
    model_probability: float,
    market_probability: float,
    confidence: str,
    odds: float,
    *,
    disable_discount: bool = False,
) -> float:
    """Production linear Blend#2 を分析用に明示再計算する。"""
    model_weight = {
        "高信頼": _w("model_blend.high", 0.72),
        "標準": _w("model_blend.standard", 0.62),
        "接戦": _w("model_blend.close", 0.50),
        "混戦": _w("model_blend.tight", 0.42),
        "暫定": _w("model_blend.tentative", 0.30),
    }.get(confidence, _w("model_blend.default", 0.55))
    if market_probability <= 0:
        blended = model_probability
    else:
        blended = model_probability * model_weight + market_probability * (1.0 - model_weight)
    if disable_discount:
        return blended
    discount = _w("discount.base", 0.92)
    if odds >= 30.0:
        discount *= _w("discount.over30", 0.72)
    elif odds >= 15.0:
        discount *= _w("discount.over15", 0.82)
    elif odds >= 8.0:
        discount *= _w("discount.over8", 0.90)
    return blended * discount


def _paired_metrics(rows: list[dict], ev_key: str) -> dict:
    """EV が価値指標として機能しているかの paired 方向性指標。"""
    ev = np.array([r[ev_key] for r in rows], dtype=float)
    won = np.array([1 if r["won"] else 0 for r in rows], dtype=int)
    ret = np.array([r["payout"] / 100.0 for r in rows], dtype=float)
    auc = float(roc_auc_score(won, ev)) if won.min() != won.max() else float("nan")
    rho, _ = spearmanr(ev, ret)
    return {"auc_ev_vs_hit": round(auc, 4), "spearman_ev_vs_return": round(float(rho), 4)}


def _paired_metrics_raw(rows: list[dict], ev_key: str) -> dict:
    ev = np.array([r[ev_key] for r in rows], dtype=float)
    won = np.array([1 if r["won"] else 0 for r in rows], dtype=int)
    ret = np.array([r["payout"] / 100.0 for r in rows], dtype=float)
    auc = float(roc_auc_score(won, ev)) if won.min() != won.max() else float("nan")
    rho, _ = spearmanr(ev, ret)
    return {"auc_ev_vs_hit": auc, "spearman_ev_vs_return": float(rho)}


def _return_rate_for_bucket(rows: list[dict], ev_key: str, bucket: str) -> float:
    subset = [r for r in rows if _bucket_label(r[ev_key]) == bucket]
    if not subset:
        return float("nan")
    return sum(r["payout"] for r in subset) / (100 * len(subset))


def _ci(values: list[float]) -> dict:
    clean = np.array([v for v in values if math.isfinite(v)], dtype=float)
    if clean.size == 0:
        return {"n": 0, "p025": None, "p50": None, "p975": None}
    return {
        "n": int(clean.size),
        "p025": round(float(np.percentile(clean, 2.5)), 4),
        "p50": round(float(np.percentile(clean, 50.0)), 4),
        "p975": round(float(np.percentile(clean, 97.5)), 4),
    }


def _cluster_bootstrap(rows: list[dict], *, runs: int, seed: int) -> dict:
    """race_key 単位で再標本化し、AUC差とEV帯別回収率の不確実性を見る。"""
    if runs <= 0:
        return {}
    by_race: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_race[row["race_key"]].append(row)
    race_keys = sorted(by_race)
    rng = np.random.default_rng(seed)
    ev_keys = ["linear_ev", "linear_ev_no_discount", "logit_ev"]
    buckets = [
        f"[{lo:.1f},{hi:.1f})" if hi != float("inf") else f"[{lo:.1f},inf)"
        for lo, hi in zip(EV_EDGES, EV_EDGES[1:])
    ]
    auc_values = {key: [] for key in ev_keys}
    auc_deltas = {"logit_minus_linear": [], "logit_minus_linear_no_discount": []}
    bucket_returns = {key: {bucket: [] for bucket in buckets} for key in ev_keys}
    for _ in range(runs):
        sample_rows: list[dict] = []
        for key in rng.choice(race_keys, size=len(race_keys), replace=True):
            sample_rows.extend(by_race[key])
        raw = {key: _paired_metrics_raw(sample_rows, key) for key in ev_keys}
        for key in ev_keys:
            auc_values[key].append(raw[key]["auc_ev_vs_hit"])
            for bucket in buckets:
                bucket_returns[key][bucket].append(_return_rate_for_bucket(sample_rows, key, bucket))
        auc_deltas["logit_minus_linear"].append(raw["logit_ev"]["auc_ev_vs_hit"] - raw["linear_ev"]["auc_ev_vs_hit"])
        auc_deltas["logit_minus_linear_no_discount"].append(
            raw["logit_ev"]["auc_ev_vs_hit"] - raw["linear_ev_no_discount"]["auc_ev_vs_hit"]
        )
    return {
        "runs": runs,
        "seed": seed,
        "cluster": "race_key",
        "n_clusters": len(race_keys),
        "auc_ci": {key: _ci(vals) for key, vals in auc_values.items()},
        "auc_delta_ci": {key: _ci(vals) for key, vals in auc_deltas.items()},
        "bucket_return_ci": {
            key: {bucket: _ci(vals) for bucket, vals in per_bucket.items()}
            for key, per_bucket in bucket_returns.items()
        },
    }


def _git_meta(root: Path) -> dict:
    def run(args: list[str]) -> str | None:
        try:
            return subprocess.check_output(args, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace").strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return None

    status = run(["git", "-C", str(root), "status", "--short"])
    return {
        "git_sha": run(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "git_dirty": bool(status),
        "git_status_short": status.splitlines() if status else [],
    }


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _env_overrides() -> dict:
    keys = set(ENV_KEYS)
    keys.update(k for k in os.environ if k.startswith("PRED_W_"))
    return {k: os.environ[k] for k in sorted(keys) if k in os.environ}


def _print_bucket_table(title: str, buckets: list[dict]) -> None:
    print(f"\n=== {title} ===")
    print(f"{'EV帯':>12} {'件数':>6} {'的中率':>7} {'回収率':>8} {'平均EV':>7} {'払戻合計':>10}")
    for b in buckets:
        print(
            f"{b['bucket']:>12} {b['count']:>6} "
            f"{b['hit_rate']*100:>6.1f}% {b['return_rate']*100:>7.1f}% "
            f"{b['mean_ev']:>7.3f} {b['payout_total']:>10}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="EV帯別 OOS 分析 (linear vs logit)")
    ap.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    ap.add_argument("--db", default=None, help="SQLite DB path")
    ap.add_argument("--out", default=None, help="出力 JSON path")
    ap.add_argument("--bootstrap-runs", type=int, default=1000, help="race-clustered bootstrap の反復数")
    ap.add_argument("--bootstrap-seed", type=int, default=20260628)
    args = ap.parse_args()

    sb = json.loads(SECOND_BLEND_PATH.read_text(encoding="utf-8"))
    coef = sb["coefficients"]
    b0, b1, b2 = coef["intercept"], coef["log_model"], coef["log_market"]
    print(f"second_blend (固定): trained {sb.get('trained_from')}-{sb.get('trained_to')} "
          f"n={sb.get('source_count')} b0={b0:.4f} b1={b1:.4f} b2={b2:.4f}")

    started = time.time()
    rows: list[dict] = []
    gate_flips = 0
    gate_flips_pop13 = 0
    pop13_count = 0
    pop13_payout = 0
    with (open_db(args.db) if args.db else open_db()) as conn:
        races = list_races(conn, args.from_date, args.to_date, jra_only=True)
        n_total = len(races)
        feature_cache: dict = {}
        for i, race in enumerate(races, 1):
            if i % 200 == 0:
                rate = i / (time.time() - started) if time.time() > started else 0
                print(f"  [{i}/{n_total}] {rate:.1f} races/s ...", file=sys.stderr, flush=True)
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            payout_row = get_payout_row(conn, race)
            if payout_row is None:
                continue
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            if not preds or is_tentative(preds):
                continue
            top = next((p for p in preds if p.rank == 1), None)
            if top is None:
                continue
            hmap = {str(h.get("horse_num") or ""): h for h in horses}
            hd = hmap.get(top.horse_num)
            if hd is None:
                continue
            odds = (hd.get("win_odds") or 0) / 10.0
            if odds <= 1.0:
                continue
            raw = {p.horse_num: p.raw_blended_probability for p in preds}
            model_prob = _apply_calibrator(raw)
            market_prob = _market_probabilities([(h, 0.0, [], 0.0) for h in horses])
            mp = model_prob.get(top.horse_num, 0.0)
            kp = market_prob.get(top.horse_num, 0.0)
            if mp <= 0.0 or kp <= 0.0:
                continue
            # linear: production の Blend#2 (discount込み) 指標
            linear_p = top.win_probability
            linear_ev = top.expected_value
            linear_no_discount_p = _linear_probability(mp, kp, top.confidence, odds, disable_discount=True)
            linear_no_discount_ev = linear_no_discount_p * odds
            # logit: 提案版 sigmoid(z), discount無し
            z = b0 + b1 * math.log(mp) + b2 * math.log(kp)
            z = max(-60.0, min(60.0, z))
            logit_p = 1.0 / (1.0 + math.exp(-z))
            logit_ev = logit_p * odds

            won = payout_from_row(payout_row, top.horse_num, "tan") > 0
            payout = payout_from_row(payout_row, top.horse_num, "tan")
            pop = hd.get("win_popularity")
            is_pop13 = isinstance(pop, int) and 1 <= pop <= 3

            # max_predicted_p ゲートの mode 間差 (買い集合が動きうる箇所)
            lin_gate = linear_p >= MAX_PREDICTED_P_GATE
            log_gate = logit_p >= MAX_PREDICTED_P_GATE
            if lin_gate != log_gate:
                gate_flips += 1
                if is_pop13:
                    gate_flips_pop13 += 1

            if is_pop13:
                pop13_count += 1
                pop13_payout += payout

            rows.append({
                "race_key": (
                    str(race.get("race_year") or "")
                    + str(race.get("race_month_day") or "")
                    + str(race.get("track_code") or "")
                    + str(race.get("race_num") or "")
                ),
                "linear_p": linear_p, "linear_ev": linear_ev,
                "linear_p_no_discount": linear_no_discount_p,
                "linear_ev_no_discount": linear_no_discount_ev,
                "logit_p": logit_p, "logit_ev": logit_ev,
                "odds": odds, "won": won, "payout": payout, "pop13": is_pop13,
            })

    if not rows:
        print("ERROR: 対象◎が0件", file=sys.stderr)
        return 1

    linear_buckets = _summarize_buckets(rows, "linear_ev")
    linear_no_discount_buckets = _summarize_buckets(rows, "linear_ev_no_discount")
    logit_buckets = _summarize_buckets(rows, "logit_ev")
    linear_paired = _paired_metrics(rows, "linear_ev")
    linear_no_discount_paired = _paired_metrics(rows, "linear_ev_no_discount")
    logit_paired = _paired_metrics(rows, "logit_ev")
    bootstrap = _cluster_bootstrap(rows, runs=args.bootstrap_runs, seed=args.bootstrap_seed)

    overall_roi = sum(r["payout"] for r in rows) / (100 * len(rows))
    pop13_roi = (pop13_payout / (100 * pop13_count)) if pop13_count else 0.0

    _print_bucket_table("linear_EV 帯別 (現行・production)", linear_buckets)
    _print_bucket_table("linear_EV 帯別 (discount無し・対称比較)", linear_no_discount_buckets)
    _print_bucket_table("logit_EV 帯別 (提案・second_blend固定)", logit_buckets)
    print("\n=== paired 方向性 (EVが価値指標として機能しているか) ===")
    print(f"  linear: AUC(EV,的中)={linear_paired['auc_ev_vs_hit']}  "
          f"Spearman(EV,払戻倍率)={linear_paired['spearman_ev_vs_return']}")
    print(f"  linear(no discount): AUC(EV,的中)={linear_no_discount_paired['auc_ev_vs_hit']}  "
          f"Spearman(EV,払戻倍率)={linear_no_discount_paired['spearman_ev_vs_return']}")
    print(f"  logit : AUC(EV,的中)={logit_paired['auc_ev_vs_hit']}  "
          f"Spearman(EV,払戻倍率)={logit_paired['spearman_ev_vs_return']}")
    if bootstrap:
        delta = bootstrap["auc_delta_ci"]["logit_minus_linear_no_discount"]
        print(
            "  bootstrap ΔAUC(logit-linear_no_discount) 95%CI="
            f"[{delta['p025']}, {delta['p975']}] median={delta['p50']}"
        )
    print("\n=== 回帰チェック / ゲート ===")
    print(f"  ◎総数={len(rows)}  全体ROI={overall_roi*100:.1f}%")
    print(f"  pop1-3 ◎: 件数={pop13_count}  ROI={pop13_roi*100:.1f}% (mode非依存・賭けは同一)")
    print(f"  max_predicted_p={MAX_PREDICTED_P_GATE} ゲート発火 (linear≠logit): "
          f"{gate_flips}件 (うち pop1-3: {gate_flips_pop13}件)")

    out_path = Path(args.out) if args.out else (
        OUT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_ev_bucket_oos_{args.from_date}_{args.to_date}.json"
    )
    root = Path(__file__).resolve().parent.parent
    payload = {
        "type": "ev_bucket_oos_analysis",
        "rule_version": RULES_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": {"from": args.from_date, "to": args.to_date},
        "meta": {
            **_git_meta(root),
            "env_overrides": _env_overrides(),
            "second_blend_sha256": _sha256(SECOND_BLEND_PATH),
            "analysis_note": (
                "linear_ev is current production with odds discount; "
                "linear_ev_no_discount removes the discount for symmetric comparison with logit_ev."
            ),
        },
        "second_blend": {
            "trained_from": sb.get("trained_from"), "trained_to": sb.get("trained_to"),
            "source_count": sb.get("source_count"), "coefficients": coef,
        },
        "ev_edges": EV_EDGES[:-1] + ["inf"],
        "n_top_picks": len(rows),
        "overall_roi": round(overall_roi, 4),
        "linear_buckets": linear_buckets,
        "linear_no_discount_buckets": linear_no_discount_buckets,
        "logit_buckets": logit_buckets,
        "linear_paired": linear_paired,
        "linear_no_discount_paired": linear_no_discount_paired,
        "logit_paired": logit_paired,
        "bootstrap": bootstrap,
        "pop13": {"count": pop13_count, "roi": round(pop13_roi, 4)},
        "max_predicted_p_gate": MAX_PREDICTED_P_GATE,
        "gate_flips": gate_flips,
        "gate_flips_pop13": gate_flips_pop13,
        "elapsed_sec": round(time.time() - started, 1),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
