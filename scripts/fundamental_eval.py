"""Fundamental Model を T−10 市場と同一レース集合で比較する (憲法 Phase 0.5-3)。

**Fundamental が市場より悪くても問題ない**。ここで確定させたいのは
「市場情報なしで AI がどの程度の確率推定能力を持つか」と、
**市場とは別の情報を持っているか**。

出すもの:
  ② 同一 933 レースでの LogLoss / Brier / Calibration の比較
  ③ P_fundamental − P_market_T10 の分布
  ④ ΔAI = P_fund − P_T10 と ΔMarket = P_final − P_T10 の関係
     (AI が終盤市場を先読みしているか)

最終市場は **ベンチマークと分析対象** にのみ使う。教師にも特徴にもしない。

usage:
    .venv64/Scripts/python.exe -m scripts.fundamental_eval [--json out.json] [--csv out.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, guard_analysis_window, sealed_notice  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.evaluation import (  # noqa: E402
    brier,
    calibration_table,
    expected_calibration_error,
    log_loss,
)
from predictor.feature_manifest import assert_no_market_features  # noqa: E402
from predictor.pit_t10 import RACE_KEYS, t10_market  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402
from scripts.fundamental_model import FEATURES, MODEL_PATH, build_dataset  # noqa: E402


def _final_market(conn: sqlite3.Connection, race: dict) -> dict[str, float]:
    rows = conn.execute(
        """SELECT horse_num, win_odds FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND horse_num NOT IN ('', '00') AND win_odds > 0""",
        tuple(race.get(k) for k in RACE_KEYS)).fetchall()
    return {str(r[0]).strip(): r[1] / 10.0 for r in rows}


def _normalise(d: dict[str, float]) -> dict[str, float]:
    tot = sum(d.values())
    return {k: v / tot for k, v in d.items()} if tot > 0 else {}


# 「市場 10%、AI 20% だから買う」と判断するには、**AI の 20% が信用できないと
# 意味がない**。分位ではなく確率の固定帯で較正を見る (憲法 Phase 0.5-3)。
BANDS: tuple[tuple[float, float, str], ...] = (
    (0.00, 0.05, "0-5%"), (0.05, 0.10, "5-10%"), (0.10, 0.20, "10-20%"),
    (0.20, 0.30, "20-30%"), (0.30, 1.01, "30%+"),
)


def band_calibration(samples: list[dict], key: str,
                     n_boot: int = 1000, seed: int = 20260918) -> list[dict]:
    """固定帯ごとの予測確率 vs 実勝率。区間はレース単位ブートストラップ。

    同一レースの馬は「1 頭しか勝たない」ので独立ではない。馬単位の二項区間だと
    狭すぎる区間が出るため、レースを塊として再抽出する。
    """
    blocks: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(samples):
        blocks[s["race_id"]].append(i)
    block_list = list(blocks.values())
    rng = random.Random(seed)
    boot_gaps: list[list[float]] = [[] for _ in BANDS]
    for _ in range(n_boot):
        idx: list[int] = []
        for _ in range(len(block_list)):
            idx.extend(block_list[rng.randrange(len(block_list))])
        rows = [samples[i] for i in idx]
        for b, (lo, hi, _label) in enumerate(BANDS):
            sel = [r for r in rows if lo <= r[key] < hi]
            if len(sel) < 20:
                continue
            boot_gaps[b].append(
                sum(r["won"] for r in sel) / len(sel)
                - sum(r[key] for r in sel) / len(sel))

    out: list[dict] = []
    for b, (lo, hi, label) in enumerate(BANDS):
        sel = [s for s in samples if lo <= s[key] < hi]
        if not sel:
            continue
        pred = sum(s[key] for s in sel) / len(sel)
        act = sum(s["won"] for s in sel) / len(sel)
        g = sorted(boot_gaps[b])
        ci = ([g[int(0.025 * len(g))], g[int(0.975 * len(g))]]
              if len(g) >= 100 else [float("nan"), float("nan")])
        out.append({"band": label, "n": len(sel), "predicted": pred,
                    "actual": act, "gap": act - pred, "gap_ci95": ci})
    return out


def delta_distribution(samples: list[dict]) -> dict:
    """P_fundamental − P_market_T10 の分布。**市場と別の情報を持っているか**。

    全部 0 に近ければ市場を言い換えているだけ。散らばっていても勝率が
    伴わなければただの雑音。両方見る。
    """
    d = np.array([s["delta_ai"] for s in samples])
    pct = {f"p{q}": float(np.percentile(d, q))
           for q in (1, 5, 10, 25, 50, 75, 90, 95, 99)}
    return {
        "n": len(d), "mean": float(d.mean()), "sd": float(d.std(ddof=1)),
        "mean_abs": float(np.abs(d).mean()), **pct,
        "share_abs_gt_0.02": float((np.abs(d) > 0.02).mean()),
        "share_abs_gt_0.05": float((np.abs(d) > 0.05).mean()),
        "share_abs_gt_0.10": float((np.abs(d) > 0.10).mean()),
        # AI の方が市場より高く見ている = 買い候補になりうる側
        "share_ai_higher": float((d > 0).mean()),
    }


def run(from_date: str, to_date: str) -> dict:
    import lightgbm as lgb

    assert_no_market_features(FEATURES)
    from_date, to_date, sealed = guard_analysis_window(
        from_date, to_date, context="fundamental_eval")
    notice = sealed_notice(sealed)
    if notice:
        print(notice, file=sys.stderr)

    print("評価期間の特徴を構築中 ...", flush=True)
    data, _ = build_dataset(from_date, to_date)
    booster = lgb.Booster(model_file=str(MODEL_PATH))
    X = np.array([[d[c] for c in FEATURES] for d in data], dtype=float)
    raw = booster.predict(X)
    for d, p in zip(data, raw):
        d["p_raw"] = float(p)

    # レース内で正規化して確率にする (市場と同じ土俵にするため)
    by_race: dict[str, list[dict]] = defaultdict(list)
    for d in data:
        by_race[d["race_id"]].append(d)
    for rid, rows in by_race.items():
        tot = sum(r["p_raw"] for r in rows)
        for r in rows:
            r["p_fund"] = r["p_raw"] / tot if tot > 0 else 0.0

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = {r["race_id"]: r for r in conn.execute(
        """SELECT *, (race_year||'-'||race_month_day||'-'||track_code||'-'||kaiji
                      ||'-'||nichiji||'-'||race_num) AS race_id
             FROM races
            WHERE (race_year||race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""",
        (from_date, to_date)).fetchall()}

    c = Counter()
    samples: list[dict] = []
    for rid, rows in by_race.items():
        race_row = races.get(rid)
        if race_row is None:
            c["no_race"] += 1
            continue
        race = dict(race_row)
        m10 = t10_market(conn, race)
        if m10 is None or not m10.ok:
            c["no_t10"] += 1
            continue
        final_odds = _final_market(conn, race)
        if not final_odds:
            c["no_final"] += 1
            continue
        set_model = {r["horse_num"] for r in rows}
        if set(m10.odds) != set(final_odds) or set(m10.odds) != set_model:
            c["runner_set_mismatch"] += 1
            continue
        c["analysed"] += 1
        p_final = _normalise({h: 1.0 / o for h, o in final_odds.items()})
        p_fund = _normalise({r["horse_num"]: r["p_fund"] for r in rows})
        for r in rows:
            h = r["horse_num"]
            samples.append({
                "race_id": rid, "horse_num": h, "date": r["date"],
                "won": r["won"],
                "p_t10": m10.implied[h], "p_fund": p_fund[h],
                "p_final": p_final[h],
                "delta_ai": p_fund[h] - m10.implied[h],
                "delta_market": p_final[h] - m10.implied[h],
                "odds_t10": m10.odds[h], "odds_final": final_odds[h],
            })
    conn.close()

    y = [s["won"] for s in samples]
    p10 = [s["p_t10"] for s in samples]
    pf = [s["p_fund"] for s in samples]

    def metrics(p):
        return {"log_loss": log_loss(y, p), "brier": brier(y, p),
                "calibration_error": expected_calibration_error(y, p)}

    m_mkt, m_fund = metrics(p10), metrics(pf)

    # ΔAI の分位別に ΔMarket の平均 (AI が終盤市場を先読みしているか)
    order = sorted(samples, key=lambda s: s["delta_ai"])
    q = max(len(order) // 5, 1)
    quintiles = []
    for i in range(5):
        chunk = order[i * q: (i + 1) * q] if i < 4 else order[4 * q:]
        if not chunk:
            continue
        quintiles.append({
            "quintile": i + 1, "n": len(chunk),
            "delta_ai_mean": sum(s["delta_ai"] for s in chunk) / len(chunk),
            "delta_market_mean": sum(s["delta_market"] for s in chunk) / len(chunk),
            "actual_win_rate": sum(s["won"] for s in chunk) / len(chunk),
            "p_t10_mean": sum(s["p_t10"] for s in chunk) / len(chunk),
            "p_fund_mean": sum(s["p_fund"] for s in chunk) / len(chunk),
        })

    da = np.array([s["delta_ai"] for s in samples])
    dm = np.array([s["delta_market"] for s in samples])
    corr = float(np.corrcoef(da, dm)[0, 1]) if len(da) > 2 else float("nan")

    # レース単位ブートストラップで相関の区間
    by_r: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(samples):
        by_r[s["race_id"]].append(i)
    blocks = list(by_r.values())
    rng = random.Random(20260918)
    boot = []
    for _ in range(1000):
        idx: list[int] = []
        for _ in range(len(blocks)):
            idx.extend(blocks[rng.randrange(len(blocks))])
        boot.append(float(np.corrcoef(da[idx], dm[idx])[0, 1]))
    boot.sort()

    meta = json.loads((MODEL_PATH.with_suffix(".meta.json")).read_text(
        encoding="utf-8")) if MODEL_PATH.with_suffix(".meta.json").exists() else {}
    return {
        "meta": {**snapshot(), "from_date": from_date, "to_date": to_date,
                 "odds_source": "T-10", "model_meta": meta,
                 "market_features": 0},
        "counts": dict(c),
        "n_races": c["analysed"], "n_horses": len(samples),
        "t10_market": m_mkt, "fundamental": m_fund,
        "delta_log_loss_fund_minus_market": m_fund["log_loss"] - m_mkt["log_loss"],
        "delta_ai_quintiles": quintiles,
        "corr_delta_ai_vs_delta_market": corr,
        "corr_ci95": [boot[25], boot[974]],
        "calibration_fundamental": calibration_table(y, pf, bins=10),
        "band_calibration_fundamental": band_calibration(samples, "p_fund"),
        "band_calibration_t10": band_calibration(samples, "p_t10"),
        "delta_distribution": delta_distribution(samples),
        "_samples": samples,
    }


def main() -> int:
    dev = DATA_SPLIT["strategy_dev"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=dev["from"])
    ap.add_argument("--to", dest="to_date", default=dev["to"])
    ap.add_argument("--json", default=None)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    out = run(args.from_date, args.to_date)
    print(f"\n=== Fundamental vs T−10 市場 ({out['n_races']:,} レース / "
          f"{out['n_horses']:,} 頭) ===")
    print(f"市場由来特徴量数: {out['meta']['market_features']}")
    print()
    hdr = f"{'指標':>20} {'T−10 市場':>12} {'Fundamental':>13} {'差':>10}"
    print(hdr); print("-" * len(hdr))
    for k, name in (("log_loss", "LogLoss"), ("brier", "Brier"),
                    ("calibration_error", "Calibration Error")):
        a, b = out["t10_market"][k], out["fundamental"][k]
        print(f"{name:>20} {a:12.5f} {b:13.5f} {b - a:+10.5f}")

    print()
    print("=== ΔAI (P_fund − P_T10) の分位別に ΔMarket (P_final − P_T10) を見る ===")
    print(f"{'分位':>4} {'頭数':>6} {'ΔAI 平均':>11} {'ΔMarket 平均':>13} "
          f"{'実勝率':>8} {'T−10 の含意':>11}")
    for q in out["delta_ai_quintiles"]:
        print(f"{q['quintile']:>4} {q['n']:6,d} {q['delta_ai_mean']:+11.5f} "
              f"{q['delta_market_mean']:+13.5f} {q['actual_win_rate'] * 100:7.2f}% "
              f"{q['p_t10_mean'] * 100:10.2f}%")
    lo, hi = out["corr_ci95"]
    print(f"\n相関 (ΔAI, ΔMarket) = {out['corr_delta_ai_vs_delta_market']:+.4f} "
          f"95%区間 [{lo:+.4f}, {hi:+.4f}]")

    print()
    print("=== ③ P_fundamental − P_market_T10 の分布 ===")
    d = out["delta_distribution"]
    print(f"  平均 {d['mean']:+.5f} / 標準偏差 {d['sd']:.5f} / "
          f"平均絶対値 {d['mean_abs']:.5f}")
    print("  " + "  ".join(f"{k} {d[k]:+.4f}"
                           for k in ("p1", "p5", "p25", "p50", "p75", "p95", "p99")))
    print(f"  |Δ|>0.02 {d['share_abs_gt_0.02'] * 100:.1f}% / "
          f"|Δ|>0.05 {d['share_abs_gt_0.05'] * 100:.1f}% / "
          f"|Δ|>0.10 {d['share_abs_gt_0.10'] * 100:.1f}%  "
          f"(AI の方が高い {d['share_ai_higher'] * 100:.1f}%)")

    print()
    print("=== 確率帯ごとの較正 (AI の 20% は本当に 20% か) ===")
    print(f"{'帯':>8} | {'Fundamental':^34} | {'T−10 市場':^22}")
    print(f"{'':>8} | {'頭数':>6} {'予測':>7} {'実際':>7} {'ずれ':>11} | "
          f"{'頭数':>6} {'予測':>7} {'実際':>7}")
    mkt = {r["band"]: r for r in out["band_calibration_t10"]}
    for r in out["band_calibration_fundamental"]:
        m = mkt.get(r["band"])
        lo, hi = r["gap_ci95"]
        mm = (f"{m['n']:6,d} {m['predicted'] * 100:6.2f}% {m['actual'] * 100:6.2f}%"
              if m else " " * 22)
        print(f"{r['band']:>8} | {r['n']:6,d} {r['predicted'] * 100:6.2f}% "
              f"{r['actual'] * 100:6.2f}% {r['gap'] * 100:+6.2f}pt | {mm}")
        print(f"{'':>8} |        95% 区間 [{lo * 100:+.2f}, {hi * 100:+.2f}]pt")

    print()
    print("=== Fundamental の較正 (十分位) ===")
    print(f"{'予測確率':>10} {'頭数':>7} {'実勝率':>8} {'ずれ':>8}")
    for row in out["calibration_fundamental"]:
        print(f"{row['predicted'] * 100:9.2f}% {row['n']:7,d} "
              f"{row['actual'] * 100:7.2f}% {row['gap'] * 100:+7.2f}pt")

    samples = out.pop("_samples")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    if args.csv and samples:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(samples[0]))
            w.writeheader()
            w.writerows(samples)
        print(f"saved: {args.csv} ({len(samples):,} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
