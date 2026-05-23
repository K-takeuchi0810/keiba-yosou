"""Phase H2 N1: dump_predictions の per-pick CSV から月次 Brier を計算する。

Brier per-pick = (p_win - y_win)^2 を picks ごとに計算し、月平均を出す。
2026 春の LGBM 確率予測の calibration が drift しているかを月次で観察。

3 つの確率を比較:
- p_win: calibrator 適用後の投資確率 (race 内非正規化、market_blend + odds_discount 適用済)
- p_raw_blended: calibrator 前の LGBM blend 確率 (race 内 Σ=1 正規化済)

usage:
    python -m scripts.monthly_brier_analyze --in data/dump_picks_h2.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# UTF-8 stdout for Windows cp932 console (output may pipe to file too)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    args = ap.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        print(f"ERROR: {in_path} not found", file=sys.stderr)
        return 1

    # Per-month aggregation
    by_month_brier_pwin: dict[str, list[float]] = defaultdict(list)
    by_month_brier_praw: dict[str, list[float]] = defaultdict(list)
    by_month_hit: dict[str, list[int]] = defaultdict(list)
    by_month_p_mean: dict[str, list[float]] = defaultdict(list)

    # Reliability buckets (10 bins of p_win)
    bins = [(i / 10, (i + 1) / 10) for i in range(10)]
    reliability_25: dict[tuple[float, float], list[int]] = defaultdict(list)
    reliability_25_p: dict[tuple[float, float], list[float]] = defaultdict(list)
    reliability_26: dict[tuple[float, float], list[int]] = defaultdict(list)
    reliability_26_p: dict[tuple[float, float], list[float]] = defaultdict(list)

    with in_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yyyymm = row["date"][:6]
            p_win = float(row["p_win"])
            p_raw = float(row["p_raw_blended"])
            y = int(row["y_win"])
            by_month_brier_pwin[yyyymm].append((p_win - y) ** 2)
            by_month_brier_praw[yyyymm].append((p_raw - y) ** 2)
            by_month_hit[yyyymm].append(y)
            by_month_p_mean[yyyymm].append(p_win)
            # reliability bin (only using p_win for now)
            for lo, hi in bins:
                if lo <= p_win < hi or (hi == 1.0 and p_win == 1.0):
                    if yyyymm.startswith("2025"):
                        reliability_25[(lo, hi)].append(y)
                        reliability_25_p[(lo, hi)].append(p_win)
                    elif yyyymm.startswith("2026"):
                        reliability_26[(lo, hi)].append(y)
                        reliability_26_p[(lo, hi)].append(p_win)
                    break

    months = sorted(by_month_brier_pwin.keys())
    print("=== monthly Brier (top-pick, n>=10 only) ===")
    print("yyyymm,n,hit_rate,p_mean,brier_pwin,brier_praw")
    monthly_rows: list[tuple[str, int, float, float, float, float]] = []
    for m in months:
        n = len(by_month_brier_pwin[m])
        if n < 10:
            continue
        hr = sum(by_month_hit[m]) / n
        pmean = sum(by_month_p_mean[m]) / n
        bp = sum(by_month_brier_pwin[m]) / n
        br = sum(by_month_brier_praw[m]) / n
        monthly_rows.append((m, n, hr, pmean, bp, br))
        print(f"{m},{n},{hr*100:.1f},{pmean*100:.1f},{bp:.4f},{br:.4f}")

    # 2025 vs 2026 aggregate
    print()
    print("=== year-aggregate Brier comparison ===")
    print("year,n_months,n_picks,brier_pwin_mean,brier_pwin_std,brier_praw_mean")
    for year in ("2025", "2026"):
        months_year = [r for r in monthly_rows if r[0].startswith(year)]
        if not months_year:
            continue
        bp_values = [r[4] for r in months_year]
        br_values = [r[5] for r in months_year]
        bp_mean = statistics.mean(bp_values)
        bp_std = statistics.stdev(bp_values) if len(bp_values) >= 2 else 0
        br_mean = statistics.mean(br_values)
        total_picks = sum(r[1] for r in months_year)
        print(
            f"{year},{len(months_year)},{total_picks},"
            f"{bp_mean:.4f},{bp_std:.4f},{br_mean:.4f}"
        )

    # 2026 vs 2025 統計判定 (per h2_session_notes.txt N1 判定基準)
    print()
    months_25 = [r for r in monthly_rows if r[0].startswith("2025")]
    months_26 = [r for r in monthly_rows if r[0].startswith("2026")]
    if months_25 and months_26:
        bp25 = [r[4] for r in months_25]
        bp26 = [r[4] for r in months_26]
        mean25 = statistics.mean(bp25)
        std25 = statistics.stdev(bp25) if len(bp25) >= 2 else 0
        mean26 = statistics.mean(bp26)
        delta = mean26 - mean25
        sigma_units = delta / std25 if std25 > 0 else 0
        print(f"=== drift judgment (N1 rubric, p_win Brier) ===")
        print(f"2025 monthly Brier: mean={mean25:.4f}, std={std25:.4f}")
        print(f"2026 monthly Brier: mean={mean26:.4f}")
        print(f"delta = 2026 - 2025 = {delta:+.4f} ({sigma_units:+.2f}sigma)")
        if sigma_units >= 2:
            verdict = "drift 強く支持 (>=+2sigma)"
        elif sigma_units >= 1:
            verdict = "drift 弱く支持 (+1〜+2sigma)"
        elif sigma_units >= -1:
            verdict = "drift 弱く棄却 (-1〜+1sigma)"
        elif sigma_units >= -2:
            verdict = "drift 強く棄却 (-1〜-2sigma、LGBM 改善)"
        else:
            verdict = "drift 確定的に棄却 (<-2sigma)"
        print(f"verdict: {verdict}")

    # reliability
    print()
    print("=== reliability calibration (p_win bins) ===")
    print("bin_lo,bin_hi,n_25,obs_25,n_26,obs_26,gap_25,gap_26")
    for lo, hi in bins:
        n25 = len(reliability_25[(lo, hi)])
        n26 = len(reliability_26[(lo, hi)])
        if n25 + n26 == 0:
            continue
        obs25 = sum(reliability_25[(lo, hi)]) / n25 if n25 else 0
        obs26 = sum(reliability_26[(lo, hi)]) / n26 if n26 else 0
        # gap = observed - predicted (predicted ≈ mean p in bin)
        p25_mean = sum(reliability_25_p[(lo, hi)]) / n25 if n25 else 0
        p26_mean = sum(reliability_26_p[(lo, hi)]) / n26 if n26 else 0
        gap25 = obs25 - p25_mean
        gap26 = obs26 - p26_mean
        print(
            f"{lo:.1f},{hi:.1f},{n25},{obs25*100:.1f},{n26},{obs26*100:.1f},"
            f"{gap25*100:+.1f},{gap26*100:+.1f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
