"""Phase H2 N8: dump_predictions の per-pick CSV から、複数の fold 分割で
dm_rank_1_3 (MING)、tm_rank_1_3、kelly_ge_05、ev_ge_105、all 戦略の
return_rate / CI 下限を集計し、「2026P 単独崩壊」パターンが他の分割でも
残るかを判定する (U1-e fold selection bias)。

fold 分割案:
    (i)   current     = 2025H1 / 2025H2 / 2026P
    (ii)  quarterly   = 2025Q1 / Q2 / Q3 / Q4 / 2026Q1 / Q2 (= 2026 春)
    (iii) reverse     = 2026P / 2025H2 / 2025H1 (順序のみ, sanity)
    (iv)  rolling_12m = [2025-01〜2025-12] / [2025-06〜2026-05] (2 fold)

usage:
    python -m scripts.fold_sensitivity_analyze --in data/dump_picks_h2.csv
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


STRATEGIES = {
    "dm_rank_1_3": lambda r: 1 <= int(r["dm_rank"] or 0) <= 3,
    "tm_rank_1_3": lambda r: 1 <= int(r["tm_rank"] or 0) <= 3,
    "kelly_ge_05": lambda r: float(r["kelly"] or 0) >= 0.05,
    "ev_ge_105": lambda r: float(r["ev"] or 0) >= 1.05,
    "all": lambda r: True,
}


def fold_membership(date: str, scheme: str) -> str | None:
    """date yyyymmdd を fold ラベルに mapping。所属しなければ None。"""
    y = date[:4]
    md = date[4:8]
    if scheme == "current":
        if y == "2025" and md <= "0630":
            return "2025H1"
        if y == "2025" and md >= "0701":
            return "2025H2"
        if y == "2026":
            return "2026P"
    elif scheme == "quarterly":
        if y == "2025":
            if md <= "0331": return "2025Q1"
            if md <= "0630": return "2025Q2"
            if md <= "0930": return "2025Q3"
            return "2025Q4"
        if y == "2026":
            if md <= "0331": return "2026Q1"
            return "2026Q2"
    elif scheme == "reverse":
        # same as current, but caller orders display in reverse
        if y == "2025" and md <= "0630":
            return "2025H1"
        if y == "2025" and md >= "0701":
            return "2025H2"
        if y == "2026":
            return "2026P"
    elif scheme == "rolling_12m":
        # 各 pick が複数 fold に属する可能性 (overlap)
        return None  # handle specially
    return None


def fold_membership_rolling(date: str) -> list[str]:
    """rolling_12m: 1 pick が overlap で複数 fold に入る。"""
    folds = []
    if "20250101" <= date <= "20251231":
        folds.append("2025_all")
    if "20250601" <= date <= "20260510":
        folds.append("2025-06_to_2026-05")
    return folds


def aggregate_strategy(rows: list[dict], strat_filter) -> dict:
    selected = [r for r in rows if strat_filter(r)]
    if not selected:
        return {"bets": 0, "hit_rate": 0, "return_rate": 0, "lo": 0, "hi": 0, "n_wins": 0}
    payouts = [int(r["tan_payout"] or 0) for r in selected]
    stakes = [100] * len(selected)
    n_wins = sum(1 for p in payouts if p > 0)
    if len(selected) >= 1:
        point, lo, hi = bootstrap_return_rate(payouts, stakes, n_resample=1000)
    else:
        point, lo, hi = 0, 0, 0
    return {
        "bets": len(selected),
        "hit_rate": n_wins / len(selected) if selected else 0,
        "return_rate": point,
        "lo": lo,
        "hi": hi,
        "n_wins": n_wins,
    }


def evaluate_scheme(rows: list[dict], scheme: str, fold_order: list[str]) -> dict:
    """各 fold で各戦略を集計し、robust=Y 件数を返す。"""
    result = {}
    for strat_name, strat_filter in STRATEGIES.items():
        fold_results = []
        for fold_label in fold_order:
            fold_rows = [r for r in rows if fold_membership(r["date"], scheme) == fold_label]
            agg = aggregate_strategy(fold_rows, strat_filter)
            fold_results.append((fold_label, agg))
        # robust=Y 判定 (= 各 fold で >= 80% かつ CI 下限 >= 50%)
        point_robust = all(
            agg["bets"] >= 10 and agg["return_rate"] >= 0.80
            for _, agg in fold_results
        )
        ci_robust = all(agg["lo"] >= 0.50 for _, agg in fold_results)
        min_ret = min((agg["return_rate"] for _, agg in fold_results), default=0)
        min_lo = min((agg["lo"] for _, agg in fold_results), default=0)
        if point_robust and ci_robust:
            label = "Y"
        elif point_robust:
            label = "hold"
        else:
            label = "n"
        result[strat_name] = {
            "fold_results": fold_results,
            "min_return": min_ret,
            "min_lo": min_lo,
            "label": label,
        }
    return result


def evaluate_rolling(rows: list[dict]) -> dict:
    """rolling_12m: overlap fold での 2-fold robust 判定。"""
    fold_labels = ["2025_all", "2025-06_to_2026-05"]
    result = {}
    for strat_name, strat_filter in STRATEGIES.items():
        fold_results = []
        for fold_label in fold_labels:
            fold_rows = [r for r in rows if fold_label in fold_membership_rolling(r["date"])]
            agg = aggregate_strategy(fold_rows, strat_filter)
            fold_results.append((fold_label, agg))
        point_robust = all(
            agg["bets"] >= 10 and agg["return_rate"] >= 0.80
            for _, agg in fold_results
        )
        ci_robust = all(agg["lo"] >= 0.50 for _, agg in fold_results)
        min_ret = min((agg["return_rate"] for _, agg in fold_results), default=0)
        min_lo = min((agg["lo"] for _, agg in fold_results), default=0)
        if point_robust and ci_robust:
            label = "Y"
        elif point_robust:
            label = "hold"
        else:
            label = "n"
        result[strat_name] = {
            "fold_results": fold_results,
            "min_return": min_ret,
            "min_lo": min_lo,
            "label": label,
        }
    return result


def print_scheme(scheme_name: str, scheme_results: dict):
    print(f"=== scheme: {scheme_name} ===")
    print("strategy,", end="")
    # column headers: fold-specific values
    first_strat = list(scheme_results.keys())[0]
    fold_labels = [fl for fl, _ in scheme_results[first_strat]["fold_results"]]
    cols = []
    for fl in fold_labels:
        cols.extend([f"{fl}_bets", f"{fl}_ret%", f"{fl}_lo%"])
    cols.extend(["min_ret%", "min_lo%", "robust"])
    print(",".join(cols))
    for strat_name, info in scheme_results.items():
        parts = [strat_name]
        for fl, agg in info["fold_results"]:
            parts.append(str(agg["bets"]))
            parts.append(f"{agg['return_rate']*100:.1f}")
            parts.append(f"{agg['lo']*100:.1f}")
        parts.append(f"{info['min_return']*100:.1f}")
        parts.append(f"{info['min_lo']*100:.1f}")
        parts.append(info["label"])
        print(",".join(parts))
    print()


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

    print(f"total picks loaded: {len(rows)}")
    print()

    # (i) current
    res_cur = evaluate_scheme(rows, "current", ["2025H1", "2025H2", "2026P"])
    print_scheme("(i) current (2025H1 / 2025H2 / 2026P)", res_cur)

    # (ii) quarterly
    res_q = evaluate_scheme(
        rows, "quarterly",
        ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"],
    )
    print_scheme("(ii) quarterly (2025Q1-Q4 / 2026Q1-Q2)", res_q)

    # (iii) reverse - same data, only display reversed
    res_r = evaluate_scheme(rows, "reverse", ["2026P", "2025H2", "2025H1"])
    print_scheme("(iii) reverse order (sanity check)", res_r)

    # (iv) rolling
    res_roll = evaluate_rolling(rows)
    print_scheme("(iv) rolling_12m", res_roll)

    # Summary verdict for U1-e
    print("=== U1-e (fold selection bias) verdict per N8 rubric ===")
    # Check if "2026P/2026 春 単独崩壊" persists across schemes
    # dm_rank_1_3 is the most relevant strategy (53.4% in 2026P originally)
    strat = "dm_rank_1_3"
    print(f"strategy: {strat}")
    cur_2026p_ret = next(
        (agg["return_rate"] for fl, agg in res_cur[strat]["fold_results"] if fl == "2026P"),
        None,
    )
    print(f"  current scheme 2026P return_rate: {cur_2026p_ret*100:.1f}%" if cur_2026p_ret else "N/A")

    # Quarterly: pick 2026Q2 (最近春) ret
    q_2026q2_ret = next(
        (agg["return_rate"] for fl, agg in res_q[strat]["fold_results"] if fl == "2026Q2"),
        None,
    )
    q_2025_rets = [
        agg["return_rate"] for fl, agg in res_q[strat]["fold_results"]
        if fl.startswith("2025")
    ]
    q_2025_mean = statistics.mean(q_2025_rets) if q_2025_rets else 0
    if q_2026q2_ret is not None and q_2025_rets:
        print(f"  quarterly 2026Q2: {q_2026q2_ret*100:.1f}%, 2025Q1-Q4 mean: {q_2025_mean*100:.1f}%")
    # Rolling
    roll_2025_ret = res_roll[strat]["fold_results"][0][1]["return_rate"]
    roll_recent_ret = res_roll[strat]["fold_results"][1][1]["return_rate"]
    print(f"  rolling 2025_all: {roll_2025_ret*100:.1f}%, 2025-06_to_2026-05: {roll_recent_ret*100:.1f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
