"""Phase H2 N2: dump_predictions の per-pick CSV から、各 fold で
MING (dm_rank_1_3) の odds 分布を計算 → 同オッズ帯の LGBM 戦略 (kelly_ge_05、
ev_ge_105、prob_ge_20) と比較。U2-(d) 「MING の robust 性は favorite-class
効果か」を検証する。

判定ロジック (h2_session_notes.txt 通り):
- MING dm_rank_1_3 picks の odds median + IQR (25-75%) を fold ごとに計算
- その IQR 範囲で LGBM 戦略を絞り、bets / hit_rate / return_rate / lo を計算
- MING と LGBM (同オッズ帯) の min_lo 比較

usage:
    python -m scripts.odds_tier_analyze --in data/dump_picks_h2.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from predictor.stats import bootstrap_return_rate


FOLDS = [
    ("2025H1", "20250101", "20250630"),
    ("2025H2", "20250701", "20251231"),
    ("2026P", "20260101", "20260510"),
]

LGBM_STRATEGIES = {
    "kelly_ge_05": lambda r: float(r["kelly"] or 0) >= 0.05,
    "ev_ge_105": lambda r: float(r["ev"] or 0) >= 1.05,
    "prob_ge_20": lambda r: float(r["p_win"] or 0) >= 0.20,
}


def in_fold(date: str, fr: str, to: str) -> bool:
    return fr <= date <= to


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {"bets": 0, "hit_rate": 0, "return_rate": 0, "lo": 0, "hi": 0}
    payouts = [int(r["tan_payout"] or 0) for r in rows]
    stakes = [100] * len(rows)
    n_wins = sum(1 for p in payouts if p > 0)
    point, lo, hi = bootstrap_return_rate(payouts, stakes, n_resample=1000)
    return {
        "bets": len(rows),
        "hit_rate": n_wins / len(rows),
        "return_rate": point,
        "lo": lo,
        "hi": hi,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    args = ap.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        print(f"ERROR: {in_path} not found", file=sys.stderr)
        return 1

    with in_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"total picks: {len(rows)}")
    print()

    # MING の odds 分布 (fold 別)
    print("=== MING (dm_rank_1_3) odds distribution per fold ===")
    print("fold,bets,odds_p25,odds_median,odds_p75,return_rate,lo")
    ming_iqr: dict[str, tuple[float, float]] = {}
    ming_stats: dict[str, dict] = {}
    for fname, fr, to in FOLDS:
        ming_rows = [
            r for r in rows
            if in_fold(r["date"], fr, to) and 1 <= int(r["dm_rank"] or 0) <= 3
        ]
        odds = sorted(float(r["odds"]) for r in ming_rows if float(r["odds"]) > 0)
        if len(odds) < 4:
            continue
        p25 = odds[int(len(odds) * 0.25)]
        median = odds[int(len(odds) * 0.50)]
        p75 = odds[int(len(odds) * 0.75)]
        ming_iqr[fname] = (p25, p75)
        agg = aggregate(ming_rows)
        ming_stats[fname] = agg
        print(
            f"{fname},{agg['bets']},{p25:.1f},{median:.1f},{p75:.1f},"
            f"{agg['return_rate']*100:.1f},{agg['lo']*100:.1f}"
        )

    print()
    print("=== LGBM strategies in same odds-tier (= MING IQR) per fold ===")
    print("strategy,fold,odds_lo,odds_hi,bets,hit_rate,return_rate,lo,delta_vs_ming")
    for strat_name, strat_filter in LGBM_STRATEGIES.items():
        for fname, fr, to in FOLDS:
            if fname not in ming_iqr:
                continue
            lo_odds, hi_odds = ming_iqr[fname]
            fold_rows = [
                r for r in rows
                if in_fold(r["date"], fr, to)
                and lo_odds <= float(r["odds"]) <= hi_odds
                and strat_filter(r)
            ]
            agg = aggregate(fold_rows)
            ming_lo = ming_stats[fname]["lo"]
            delta = (agg["lo"] - ming_lo) * 100 if agg["bets"] > 0 else None
            delta_str = f"{delta:+.1f}" if delta is not None else "N/A"
            print(
                f"{strat_name},{fname},{lo_odds:.1f},{hi_odds:.1f},{agg['bets']},"
                f"{agg['hit_rate']*100:.1f},{agg['return_rate']*100:.1f},"
                f"{agg['lo']*100:.1f},{delta_str}"
            )

    print()
    print("=== verdict per fold (LGBM same-tier vs MING) ===")
    print("rubric (h2_session_notes.txt N2):")
    print("  same-tier LGBM min_lo within +/- 5pp of MING: U2-(d) weakly-support (class effect)")
    print("  same-tier LGBM min_lo 5-15pp below MING: border zone")
    print("  same-tier LGBM min_lo >= 15pp below MING: U2-(d) weakly-reject (MING has info LGBM lacks)")
    print("  same-tier LGBM bets < 30: undetermined")
    print()
    print("strategy,2025H1_delta,2025H2_delta,2026P_delta,verdict")
    for strat_name, strat_filter in LGBM_STRATEGIES.items():
        deltas = []
        for fname, fr, to in FOLDS:
            if fname not in ming_iqr:
                continue
            lo_odds, hi_odds = ming_iqr[fname]
            fold_rows = [
                r for r in rows
                if in_fold(r["date"], fr, to)
                and lo_odds <= float(r["odds"]) <= hi_odds
                and strat_filter(r)
            ]
            agg = aggregate(fold_rows)
            ming_lo = ming_stats[fname]["lo"]
            if agg["bets"] < 30:
                deltas.append(("N/A", agg["bets"]))
            else:
                delta = (agg["lo"] - ming_lo) * 100
                deltas.append((delta, agg["bets"]))
        # verdict per rubric
        valid_deltas = [d for d, _ in deltas if d != "N/A"]
        if not valid_deltas:
            verdict = "判定不能 (全 fold で bets < 30)"
        else:
            max_below = max(-d for d in valid_deltas)  # 最も MING より下
            if max_below <= 5:
                verdict = "U2-(d) 弱く支持 (class effect within +/-5pp)"
            elif max_below <= 15:
                verdict = "border zone (5-15pp below)"
            else:
                verdict = "U2-(d) 弱く棄却 (>15pp below = LGBM lacks info)"
        delta_strs = ",".join(
            f"{d:+.1f}({n})" if d != "N/A" else f"N/A({n})"
            for d, n in deltas
        )
        print(f"{strat_name},{delta_strs},{verdict}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
