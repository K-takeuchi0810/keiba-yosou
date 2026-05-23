"""N9 (v4 新規): N7 の fine-grained 拡張。R% を 1pp 刻みで 60-90 まで振り、
Y/hold/n 件数を出す。U7 (cliff edge) operational 再評価。

判定 (h2_session_notes.txt U7 operational rule):
- 78-82% で滑らか (各刻みで件数差 <= 2): (b) 「閾値偶然 cliff edge」棄却
- 79% で 5+ 件、80% で 0 件: (b) 採用
- 76% で 10+ 件、80% で 0 件: (c) 「JRA 控除率超え 80% ambitious」採用
- 全 R% で 0 件: (a) 「point 能力構造的問題」採用
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "recent_3fold_ci.csv"
FOLDS = ["2025H1", "2025H2", "2026P"]


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
    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"loaded {len(rows)} strategies from {CSV_PATH.name}")
    print()

    # Fixed L=50, vary R from 60 to 90 in 1pp steps
    L = 50.0
    print(f"=== R% sensitivity (fixed L%={L}) ===")
    print("R%, Y, hold, n, Y_strategies, hold_strategies")
    results = []
    for R_pct in range(60, 91):
        R = float(R_pct)
        counts = {"Y": 0, "hold": 0, "n": 0}
        y_names: list[str] = []
        hold_names: list[str] = []
        for row in rows:
            label = classify(row, R, L)
            counts[label] += 1
            if label == "Y":
                y_names.append(row["filter"])
            elif label == "hold":
                hold_names.append(row["filter"])
        results.append((R_pct, counts, y_names, hold_names))
        y_str = ",".join(y_names[:3]) + (f"+{len(y_names)-3}" if len(y_names) > 3 else "")
        h_str = ",".join(hold_names[:3]) + (f"+{len(hold_names)-3}" if len(hold_names) > 3 else "")
        print(f"{R_pct},{counts['Y']},{counts['hold']},{counts['n']},{y_str},{h_str}")

    print()
    print("=== verdict per U7 operational rubric ===")

    def get_y(R_pct):
        return next(r[1]["Y"] for r in results if r[0] == R_pct)

    def get_hold(R_pct):
        return next(r[1]["hold"] for r in results if r[0] == R_pct)

    y76 = get_y(76)
    y79 = get_y(79)
    y80 = get_y(80)
    hold80 = get_hold(80)
    # Adjacency in 78-82 region
    y_band = [get_y(r) for r in range(78, 83)]  # 78, 79, 80, 81, 82
    hold_band = [get_hold(r) for r in range(78, 83)]
    print(f"Y at R=76,77,78,79,80,81,82,83,84,85:")
    for r in [76, 77, 78, 79, 80, 81, 82, 83, 84, 85]:
        print(f"  R={r}: Y={get_y(r)}, hold={get_hold(r)}")
    smooth_78_82 = all(abs(y_band[i] - y_band[i+1]) <= 2 for i in range(len(y_band)-1))
    print()
    print(f"Y count smooth in 78-82 region (delta <= 2 each step): {smooth_78_82}")
    print(f"Y at R=76: {y76}, R=79: {y79}, R=80: {y80}")

    # Apply rubric
    if y80 == 0 and y79 >= 5:
        verdict = "(b) 採用: 79% で 5+ 件、80% で 0 件 = 閾値偶然 cliff edge"
    elif y80 == 0 and y76 >= 10:
        verdict = "(c) 採用: 76% で 10+ 件、80% で 0 件 = JRA 控除率超え 80% ambitious"
    elif all(get_y(r) == 0 for r in range(60, 91)):
        verdict = "(a) 採用: 全 R% で Y=0 = point 能力構造的問題"
    elif smooth_78_82:
        verdict = "(b) 棄却: 78-82% で滑らか = 閾値偶然性ではない"
    else:
        verdict = "U7 mixed signal (未確定)"
    print(f"verdict: {verdict}")


if __name__ == "__main__":
    main()
