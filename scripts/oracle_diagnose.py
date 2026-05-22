"""Oracle sanity check (W) + monthly regime diagnostic (Z'-light).

W: 完璧予測者 (oracle) が rank=1 = 実勝ち馬を毎回当てた場合の return rate と
   bootstrap CI を fold 別に出す。これが「理論的天井」。もし oracle 自身が
   CI 下限 >= 0.50 を割るなら、filter_sweep の採用基準 (CI 下限 >= 0.50) は
   そもそも achievable でない可能性。

Z'-light: 同じ oracle return を月次に分解して return_rate と CI 下限をプロット。
   - 2026 春で急変 (regime shift) か
   - 2025 H1 が異常に良かったか (= 訓練データ近接)
   - 全体的に drift しているか
   - 2026P は単なるサンプル不足か
   を切り分ける。

oracle は LGBM 不要、payouts.tan_payout1 (= 1 着馬の単勝払戻) を直接拾うだけ
なので SQL 1 本で済む。filter_sweep の 141 分とは別世界の速度。

usage:
    python -m scripts.oracle_diagnose --db /c/Users/kizun/dev/keiba-yosou/data/keiba.db
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.stats import bootstrap_return_rate


FOLD_PERIODS = [
    ("2025H1", "20250101", "20250630"),
    ("2025H2", "20250701", "20251231"),
    ("2026P", "20260101", "20260517"),
]


def collect_oracle_payouts(conn, from_date: str, to_date: str) -> list[tuple[str, int]]:
    """Returns [(yyyymm, tan_payout1), ...] for all JRA races in [from, to].

    payouts.tan_payout1 is the winning horse's tan payout for a 100-yen bet.
    Filtering by races.track_code 01-10 keeps us to central JRA (where payout
    records are populated). Skips races with no winner data (tan_payout1 NULL
    or 0 = unrun / cancelled / no-payout).
    """
    rows = conn.execute(
        """
        SELECT (r.race_year || substr(r.race_month_day, 1, 2)) AS yyyymm,
               p.tan_payout1
        FROM races r
        JOIN payouts p
          ON p.race_year = r.race_year
         AND p.race_month_day = r.race_month_day
         AND p.track_code = r.track_code
         AND p.kaiji = r.kaiji
         AND p.nichiji = r.nichiji
         AND p.race_num = r.race_num
        WHERE (r.race_year || r.race_month_day) BETWEEN ? AND ?
          AND CAST(r.track_code AS INTEGER) BETWEEN 1 AND 10
          AND p.tan_payout1 IS NOT NULL
          AND p.tan_payout1 > 0
        """,
        (from_date, to_date),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    with open_db(args.db) if args.db else open_db() as conn:
        all_rows: list[tuple[str, int]] = []
        for name, fr, to in FOLD_PERIODS:
            rows = collect_oracle_payouts(conn, fr, to)
            all_rows.append((name, fr, to, rows))

    # === W: per-fold oracle CI ===
    print("=== W: Oracle CI per fold (perfect predictor, 100-yen bet on actual winner) ===")
    print("fold,bets,return_rate,lo,hi")
    fold_summary: list[tuple[str, int, float, float, float]] = []
    for name, fr, to, rows in all_rows:
        payouts = [p for _, p in rows]
        stakes = [100] * len(payouts)
        point, lo, hi = bootstrap_return_rate(payouts, stakes, n_resample=1000)
        fold_summary.append((name, len(payouts), point, lo, hi))
        print(f"{name},{len(payouts)},{point*100:.1f},{lo*100:.1f},{hi*100:.1f}")

    # min_lo across folds
    min_lo = min(s[3] for s in fold_summary)
    print(f"min_lo across folds: {min_lo*100:.1f}")
    if min_lo >= 0.50:
        print("verdict: BAR ACHIEVABLE (oracle's worst-fold lo >= 0.50)")
    else:
        print(
            f"verdict: BAR LIKELY UNREALISTIC (oracle's worst-fold lo {min_lo*100:.1f}% "
            f"< 50%); filter_sweep CI-lo >= 0.50 may be impossible to meet"
        )

    # === Z'-light: per-month oracle CI ===
    print()
    print("=== Z'-light: Oracle CI per month (2025-01 to 2026-05) ===")
    print("month,bets,return_rate,lo,hi")
    by_month: dict[str, list[int]] = defaultdict(list)
    for _name, _fr, _to, rows in all_rows:
        for yyyymm, p in rows:
            by_month[yyyymm].append(p)
    months_sorted = sorted(by_month.keys())
    monthly: list[tuple[str, int, float, float, float]] = []
    for month in months_sorted:
        ps = by_month[month]
        if len(ps) < 10:
            continue
        stakes = [100] * len(ps)
        point, lo, hi = bootstrap_return_rate(ps, stakes, n_resample=1000)
        monthly.append((month, len(ps), point, lo, hi))
        print(f"{month},{len(ps)},{point*100:.1f},{lo*100:.1f},{hi*100:.1f}")

    # === diagnostic verdict ===
    print()
    print("=== diagnosis hints ===")
    if monthly:
        rates_2025 = [m[2] for m in monthly if m[0].startswith("2025")]
        rates_2026 = [m[2] for m in monthly if m[0].startswith("2026")]
        if rates_2025 and rates_2026:
            avg_2025 = sum(rates_2025) / len(rates_2025)
            avg_2026 = sum(rates_2026) / len(rates_2026)
            min_2025 = min(rates_2025)
            max_2025 = max(rates_2025)
            print(f"2025 monthly return_rate: avg={avg_2025*100:.1f}%, range=[{min_2025*100:.1f}%, {max_2025*100:.1f}%]")
            print(f"2026 monthly return_rate: avg={avg_2026*100:.1f}%, n_months={len(rates_2026)}")
            print(f"  → 2026 months inside 2025 range? "
                  f"{all(min_2025 <= r <= max_2025 for r in rates_2026)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
