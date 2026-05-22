"""N7: judgment threshold sensitivity on data/recent_3fold_ci.csv.

For each (R, L) threshold pair, count strategies with label Y / hold / n
under the v2 §0 rule:
    point_robust = all(bets >= 10) and all(return_rate >= R)
    ci_robust    = min_lo >= L
    label = Y if point_robust and ci_robust else hold if point_robust else n

CSV columns are in percent (82.8 = 82.8%). Thresholds are also in percent.
"""
from __future__ import annotations

import csv
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "recent_3fold_ci.csv"

# Threshold pairs (R%, L%) requested by scorecard v2 §6 N7 + adjacency neighbors.
THRESHOLDS = [
    (70.0, 40.0),
    (75.0, 45.0),
    (75.0, 50.0),
    (80.0, 40.0),
    (80.0, 50.0),  # current
    (85.0, 55.0),
]

FOLDS = ["2025H1", "2025H2", "2026P"]


def load_rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def classify(row: dict, R: float, L: float) -> str:
    bets = [int(row[f"{fold}_bets"]) for fold in FOLDS]
    rets = [float(row[f"{fold}_return_rate"]) for fold in FOLDS]
    los = [float(row[f"{fold}_lo"]) for fold in FOLDS]
    point_robust = all(b >= 10 for b in bets) and all(r >= R for r in rets)
    ci_robust = min(los) >= L
    if point_robust and ci_robust:
        return "Y"
    if point_robust:
        return "hold"
    return "n"


def main() -> None:
    rows = load_rows()
    print(f"loaded {len(rows)} strategies from {CSV_PATH.name}")
    print()
    print(f"{'R%':>5} {'L%':>5} | {'Y':>3} {'hold':>5} {'n':>4} | Y_strategies")
    print("-" * 70)
    last_y_count = None
    jumps = []
    for R, L in THRESHOLDS:
        counts = {"Y": 0, "hold": 0, "n": 0}
        y_names: list[str] = []
        for row in rows:
            label = classify(row, R, L)
            counts[label] += 1
            if label == "Y":
                y_names.append(row["filter"])
        names_str = ", ".join(y_names[:6]) + (
            f" (+{len(y_names) - 6})" if len(y_names) > 6 else ""
        )
        print(f"{R:>5.1f} {L:>5.1f} | {counts['Y']:>3} {counts['hold']:>5} {counts['n']:>4} | {names_str}")
        if last_y_count is not None:
            jumps.append(abs(counts["Y"] - last_y_count))
        last_y_count = counts["Y"]
    print()
    print("Y-count adjacency jumps (across THRESHOLDS order):", jumps)
    print(f"max adjacency jump = {max(jumps) if jumps else 0}")


if __name__ == "__main__":
    main()
