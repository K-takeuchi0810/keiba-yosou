"""N3: same-season permutation test for 2025 vs 2026 oracle return_rate.

Permutes the 10-month labels (2025-01..05 vs 2026-01..05) over all
C(10, 5) = 252 combinations and reports where the observed +63 pp delta
sits in the resulting null distribution.

Data source: data/oracle_diagnose.log (months 202501..202605).
"""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

# Hand-copied from data/oracle_diagnose.log "=== Z'-light: Oracle CI per month ==="
# Same-season window: Jan-May.
M2025 = {
    "01": 1042.2,
    "02": 1011.6,
    "03": 1099.0,
    "04": 1002.7,
    "05": 1078.5,
}
M2026 = {
    "01": 1156.2,
    "02": 972.5,
    "03": 1182.1,
    "04": 1052.1,
    "05": 1185.7,
}


def main() -> None:
    months = sorted(M2025.keys())
    values = [M2025[m] for m in months] + [M2026[m] for m in months]
    n = len(values)  # 10

    avg_25 = sum(M2025.values()) / 5
    avg_26 = sum(M2026.values()) / 5
    observed_delta = avg_26 - avg_25
    observed_abs = abs(observed_delta)

    print(f"observed: 2025 avg = {avg_25:.1f}%, 2026 avg = {avg_26:.1f}%, "
          f"delta = {observed_delta:+.1f} pp")
    print(f"n_total months = {n} (5 + 5)")
    print()

    # All C(10, 5) = 252 ways to assign 5 of the 10 months to "group A"
    null_deltas: list[float] = []
    for idx_a in combinations(range(n), 5):
        a = [values[i] for i in idx_a]
        b = [values[i] for i in range(n) if i not in idx_a]
        null_deltas.append(sum(b) / 5 - sum(a) / 5)

    # Two-sided p-value
    extreme = sum(1 for d in null_deltas if abs(d) >= observed_abs)
    p_two = extreme / len(null_deltas)
    # One-sided (2026 > 2025)
    extreme_one = sum(1 for d in null_deltas if d >= observed_delta)
    p_one = extreme_one / len(null_deltas)

    print(f"permutations enumerated: {len(null_deltas)}")
    print(f"null delta range: [{min(null_deltas):+.1f}, {max(null_deltas):+.1f}] pp")
    print(f"null delta median: {sorted(null_deltas)[len(null_deltas)//2]:+.1f} pp")
    print()
    print(f"two-sided p-value (|delta| >= {observed_abs:.1f}): {p_two:.4f}  ({extreme}/{len(null_deltas)})")
    print(f"one-sided p-value (delta >= {observed_delta:+.1f}): {p_one:.4f}  ({extreme_one}/{len(null_deltas)})")
    print()
    # Show percentile of observed in null distribution
    sorted_null = sorted(null_deltas)
    rank = sum(1 for d in sorted_null if d <= observed_delta)
    print(f"observed at percentile {rank/len(null_deltas)*100:.1f}% of null distribution (one-sided)")


if __name__ == "__main__":
    main()
