"""Fundamental Model を T−10 市場と同一レース集合で比較する (憲法 Phase 0.5-3)。

**Fundamental が市場より悪くても問題ない**。ここで確定させたいのは
「市場情報なしで AI がどの程度の確率推定能力を持つか」と、
**市場とは別の情報を持っているか**。

## 2 つの「市場」の扱い (2026-09-18 の専門家レビューで是正)

**T−10 市場**: `odds_snapshots` から決定時刻以前の最新値。規則は 0.5-1 のまま
だが、**採用したスナップが古い場合がある**。実測で 32.8% が発走 30 分超前、
最大 964 分 (前夜) だった。その時刻に本当に持っていた最新値なので規則違反では
ないが、「市場の T−10 の姿」ではない。古い値を基準線にすると市場を不当に低く
見積もるので、**主分析は鮮度で絞った集合**で行い、全体は参考として併記する。

**最終市場**: `horse_races.win_odds` は確定オッズ **ではない**。確定単勝払戻
(`payouts`, data_div=2) と照合すると勝ち馬 1,178 頭中 563 頭 (47.8%) で
一致しない (5 月 67% / 6 月 92% / 7 月 0% / 8 月 39%)。全頭ぶんの確定オッズは
DB のどこにも無いので、**最終市場の確率ベクトルは一致したレースでしか作れない**。
金額 (回収率) は確定払戻から正確に出せるので、そちらを本命の指標にする。

usage:
    .venv64/Scripts/python.exe -m scripts.fundamental_eval [--max-lead 30]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, guard_analysis_window, sealed_notice  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.eval_stats import (  # noqa: E402
    BANDS,
    N_BOOT,
    SEED,
    band_calibration,
    block_boot,
    coefficient_ci,
    conditional_logit,
    flat_bet_roi,
    logit,
    metrics,
    normalise,
)
from predictor.feature_manifest import assert_no_market_features  # noqa: E402
from predictor.pit_t10 import RACE_KEYS, decision_time, t10_market  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402
from scripts.fundamental_model import FEATURES, MODEL_PATH, build_dataset  # noqa: E402
from scripts.market_data_audit import confirmed_win_payouts  # noqa: E402

# T−10 スナップが発走の何分前までなら「T−10 の市場」と呼んでよいか。
# 決定時刻は発走 10 分前なので理想は 10 分ちょうど。実データのばらつきを
# 見込んで 30 分を既定にする。
DEFAULT_MAX_LEAD_MINUTES = 30

# 統計部品は predictor/eval_stats.py に移した (0.5-4A 以降 消費者が複数)。
_logit = logit
_normalise = normalise
_block_boot = block_boot

__all__ = ["BANDS", "N_BOOT", "SEED", "DEFAULT_MAX_LEAD_MINUTES",
           "band_calibration", "block_boot", "coefficient_ci",
           "conditional_logit", "flat_bet_roi", "logit", "metrics",
           "normalise", "collect", "run"]


def _final_market_odds(conn, race) -> dict[str, float]:
    """`horse_races.win_odds` の全頭ぶん。

    **2021-2025 では確定オッズそのもの** (勝ち馬で確定払戻と 99.5%+ 一致、
    不一致は全件が同着による払戻半減)。一方 **2026 は 77.4% しか一致しない**。
    fresh odds 取得 (0B30/0B31) が発走前の値を後から書いているため。
    評価窓 (2026-05〜08) では 40.8% しか一致しないので、この列を
    「最終市場」として使えるのは `final_odds_confirmed` が立つレースだけ。
    """
    rows = conn.execute(
        """SELECT horse_num, win_odds FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND horse_num NOT IN ('', '00') AND win_odds > 0""",
        tuple(race.get(k) for k in RACE_KEYS)).fetchall()
    return {str(r[0]).strip(): r[1] / 10.0 for r in rows}


def delta_distribution(samples: list[dict]) -> dict:
    """P_fundamental − P_market_T10 の分布。**市場と別の情報を持っているか**。

    平均は載せない。両方ともレース内で和 1 に正規化してあるので **恒等的に 0**
    になり、「AI は市場に対して無偏」と誤読される (実測 1.9e-18)。
    """
    d = np.array([s["delta_ai"] for s in samples])
    pct = {f"p{q}": float(np.percentile(d, q))
           for q in (1, 5, 25, 50, 75, 95, 99)}
    return {
        "n": len(d), "sd": float(d.std(ddof=1)),
        "mean_abs": float(np.abs(d).mean()), **pct,
        "share_abs_gt_0.02": float((np.abs(d) > 0.02).mean()),
        "share_abs_gt_0.05": float((np.abs(d) > 0.05).mean()),
        "share_abs_gt_0.10": float((np.abs(d) > 0.10).mean()),
        "share_ai_higher": float((d > 0).mean()),
    }


def collect(from_date: str, to_date: str) -> tuple[list[dict], Counter]:
    """特徴を作り、T−10 市場・最終オッズ・確定払戻を突き合わせる。"""
    import lightgbm as lgb

    assert_no_market_features(
        FEATURES, source_module=Path(__file__).parent / "fundamental_model.py")
    print("評価期間の特徴を構築中 ...", flush=True)
    data, _ = build_dataset(from_date, to_date)
    booster = lgb.Booster(model_file=str(MODEL_PATH))
    X = np.array([[d[c] for c in FEATURES] for d in data], dtype=float)
    for d, p in zip(data, booster.predict(X), strict=True):
        d["p_raw"] = float(p)

    by_race: dict[str, list[dict]] = defaultdict(list)
    for d in data:
        by_race[d["race_id"]].append(d)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = {r["race_id"]: dict(r) for r in conn.execute(
        """SELECT *, (race_year||'-'||race_month_day||'-'||track_code||'-'||kaiji
                      ||'-'||nichiji||'-'||race_num) AS race_id
             FROM races
            WHERE (race_year||race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""",
        (from_date, to_date))}

    c: Counter = Counter()
    samples: list[dict] = []
    for rid, rows in by_race.items():
        race = races.get(rid)
        if race is None:
            c["no_race"] += 1
            continue
        m10 = t10_market(conn, race)
        _, start = decision_time(conn, race)
        if m10 is None or not m10.ok or start is None:
            c["no_t10"] += 1
            continue
        final_odds = _final_market_odds(conn, race)
        payouts = confirmed_win_payouts(conn, race)
        if not final_odds:
            c["no_final"] += 1
            continue
        if (set(m10.odds) != set(final_odds)
                or set(m10.odds) != {r["horse_num"] for r in rows}):
            c["runner_set_mismatch"] += 1
            continue
        c["analysed"] += 1

        lead = ((start - datetime.fromisoformat(m10.odds_received_at))
                .total_seconds() / 60.0)
        p_final = _normalise({h: 1.0 / o for h, o in final_odds.items()})
        p_fund = _normalise({r["horse_num"]: r["p_raw"] for r in rows})
        # 最終オッズが確定払戻と一致しているレースだけ、最終市場の確率を信じる。
        winners = [r["horse_num"] for r in rows if r["won"] == 1]
        confirmed = bool(winners) and all(
            h.zfill(2) in payouts
            and abs(payouts[h.zfill(2)] - final_odds[h]) < 1e-6 for h in winners)
        if confirmed:
            c["final_confirmed"] += 1
        if lead <= DEFAULT_MAX_LEAD_MINUTES:
            c["t10_fresh"] += 1

        for r in rows:
            h = r["horse_num"]
            samples.append({
                "race_id": rid, "horse_num": h, "date": r["date"],
                "won": r["won"], "lead_min": round(lead, 2),
                "final_odds_confirmed": int(confirmed),
                "p_t10": m10.implied[h], "p_fund": p_fund[h], "p_final": p_final[h],
                "delta_ai": p_fund[h] - m10.implied[h],
                "delta_market": p_final[h] - m10.implied[h],
                "odds_t10": m10.odds[h], "odds_final": final_odds[h],
                "payout_odds": payouts.get(h.zfill(2), 0.0),
            })
    conn.close()
    return samples, c


def run(from_date: str, to_date: str, max_lead: int) -> dict:
    from_date, to_date, sealed = guard_analysis_window(
        from_date, to_date, context="fundamental_eval")
    notice = sealed_notice(sealed)
    if notice:
        print(notice, file=sys.stderr)

    samples, counts = collect(from_date, to_date)
    fresh = [s for s in samples if s["lead_min"] <= max_lead]
    confirmed = [s for s in fresh if s["final_odds_confirmed"]]

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    meta_snapshot = snapshot(conn)
    conn.close()

    out: dict = {
        "meta": {**meta_snapshot, "from_date": from_date, "to_date": to_date,
                 "odds_source": "T-10", "max_lead_minutes": max_lead,
                 "market_features": 0},
        "counts": dict(counts),
        "sets": {
            "all": {"n_races": len({s["race_id"] for s in samples}),
                    "n_horses": len(samples)},
            "fresh_t10": {"n_races": len({s["race_id"] for s in fresh}),
                          "n_horses": len(fresh)},
            "fresh_and_confirmed_final": {
                "n_races": len({s["race_id"] for s in confirmed}),
                "n_horses": len(confirmed)},
        },
    }
    for label, rows in (("all", samples), ("fresh_t10", fresh)):
        if not rows:
            continue
        out[f"t10_market_{label}"] = metrics(rows, "p_t10")
        out[f"fundamental_{label}"] = metrics(rows, "p_fund")

    if fresh:
        for s in fresh:
            s["z_t10"] = float(_logit(s["p_t10"]))
            s["z_fund"] = float(_logit(s["p_fund"]))
        beta = conditional_logit(fresh, ["z_t10", "z_fund"])
        lo, hi = _block_boot(
            fresh, lambda d: conditional_logit(d, ["z_t10", "z_fund"])[1],
            n_boot=300)
        out["conditional_logit_vs_t10"] = {
            "coef_market": beta[0], "coef_fundamental": beta[1],
            "coef_fundamental_ci95": [lo, hi]}
        out["delta_distribution"] = delta_distribution(fresh)
        out["band_calibration_fundamental"] = band_calibration(fresh, "p_fund")
        out["band_calibration_t10"] = band_calibration(fresh, "p_t10")

    if confirmed:
        for s in confirmed:
            s["z_final"] = float(_logit(s["p_final"]))
        beta = conditional_logit(confirmed, ["z_final", "z_fund"])
        lo, hi = _block_boot(
            confirmed, lambda d: conditional_logit(d, ["z_final", "z_fund"])[1],
            n_boot=300)
        out["conditional_logit_vs_final"] = {
            "coef_market": beta[0], "coef_fundamental": beta[1],
            "coef_fundamental_ci95": [lo, hi]}

    top = [s for s in fresh if s["delta_ai"] > 0.05]
    out["flat_bet_all"] = flat_bet_roi(fresh)
    out["flat_bet_ai_over_market_5pt"] = flat_bet_roi(top) if top else None
    out["_samples"] = samples
    return out


def main() -> int:
    dev = DATA_SPLIT["strategy_dev"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=dev["from"])
    ap.add_argument("--to", dest="to_date", default=dev["to"])
    ap.add_argument("--max-lead", type=int, default=DEFAULT_MAX_LEAD_MINUTES)
    ap.add_argument("--json", default=None)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    out = run(args.from_date, args.to_date, args.max_lead)
    s = out["sets"]
    print(f"\n=== 集合 (市場由来特徴量数 {out['meta']['market_features']}) ===")
    print(f"  全体                       {s['all']['n_races']:4,d} レース / "
          f"{s['all']['n_horses']:6,d} 頭")
    print(f"  T−10 が鮮度 {args.max_lead} 分以内      "
          f"{s['fresh_t10']['n_races']:4,d} レース / "
          f"{s['fresh_t10']['n_horses']:6,d} 頭  ← 主分析")
    print(f"  さらに最終オッズが確定値   "
          f"{s['fresh_and_confirmed_final']['n_races']:4,d} レース / "
          f"{s['fresh_and_confirmed_final']['n_horses']:6,d} 頭")

    for label, title in (("fresh_t10", "主分析 (鮮度内)"), ("all", "参考 (全体)")):
        if f"t10_market_{label}" not in out:
            continue
        print(f"\n=== {title} ===")
        hdr = f"{'指標':>20} {'T−10 市場':>12} {'Fundamental':>13} {'差':>10}"
        print(hdr)
        print("-" * len(hdr))
        for k, name in (("log_loss", "LogLoss"), ("brier", "Brier"),
                        ("calibration_error", "Calibration Error")):
            a = out[f"t10_market_{label}"][k]
            b = out[f"fundamental_{label}"][k]
            print(f"{name:>20} {a:12.5f} {b:13.5f} {b - a:+10.5f}")

    for key, title in (("conditional_logit_vs_t10", "T−10 市場を与えた上で"),
                       ("conditional_logit_vs_final", "最終市場を与えた上で")):
        if key not in out:
            continue
        r = out[key]
        lo, hi = r["coef_fundamental_ci95"]
        print(f"\n=== 条件付きロジット: {title} Fundamental に価値はあるか ===")
        print(f"  市場の係数         {r['coef_market']:+.4f}")
        print(f"  Fundamental の係数 {r['coef_fundamental']:+.4f} "
              f"95% 区間 [{lo:+.4f}, {hi:+.4f}]"
              f"  {'← 0 をまたぐ' if lo <= 0 <= hi else '← 0 をまたがない'}")

    if "delta_distribution" in out:
        d = out["delta_distribution"]
        print("\n=== P_fundamental − P_market_T10 の分布 ===")
        print(f"  標準偏差 {d['sd']:.5f} / 平均絶対値 {d['mean_abs']:.5f}")
        print("  " + "  ".join(
            f"{k} {d[k]:+.4f}"
            for k in ("p1", "p5", "p25", "p50", "p75", "p95", "p99")))
        print(f"  |Δ|>0.05 {d['share_abs_gt_0.05'] * 100:.1f}% / "
              f"|Δ|>0.10 {d['share_abs_gt_0.10'] * 100:.1f}%")

    if "band_calibration_fundamental" in out:
        print("\n=== 確率帯ごとの較正 (AI の 20% は本当に 20% か) ===")
        mkt = {r["band"]: r for r in out["band_calibration_t10"]}
        print(f"{'帯':>8} {'頭数':>7} {'予測':>7} {'実際':>7} {'ずれ':>8} "
              f"{'95% 区間':>22} | {'市場 予測':>10} {'実際':>7}")
        for r in out["band_calibration_fundamental"]:
            m = mkt.get(r["band"])
            lo, hi = r["gap_ci95"]
            mm = (f"{m['predicted'] * 100:9.2f}% {m['actual'] * 100:6.2f}%"
                  if m else "")
            print(f"{r['band']:>8} {r['n']:7,d} {r['predicted'] * 100:6.2f}% "
                  f"{r['actual'] * 100:6.2f}% {r['gap'] * 100:+7.2f}pt "
                  f"[{lo * 100:+6.2f}, {hi * 100:+6.2f}]pt | {mm}")

    print("\n=== 100 円均等で買ったときの回収率 (払戻は確定値) ===")
    for key, title in (("flat_bet_all", "鮮度内の全頭"),
                       ("flat_bet_ai_over_market_5pt",
                        "AI が市場より 5pt 以上高い馬")):
        r = out.get(key)
        if not r:
            continue
        lo, hi = r["roi_ci95"]
        print(f"  {title:>26} {r['n_bets']:6,d} 点 "
              f"{r['roi'] * 100:6.1f}% 95% 区間 [{lo * 100:.1f}, {hi * 100:.1f}]%")

    samples = out.pop("_samples")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    if args.csv and samples:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        # 行ごとに鍵が違う (条件付きロジット用の列は部分集合にしか付かない)。
        # 先頭行だけ見ると落ちるので、全行の和を取る。
        fields = list(samples[0])
        for s_ in samples:
            fields += [k for k in s_ if k not in fields]
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, restval="")
            w.writeheader()
            w.writerows(samples)
        print(f"saved: {args.csv} ({len(samples):,} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
