"""N6: invert observed CI lower bound to back out each strategy's
effective payout std (yen), then recompute strategy-specific required_n
for CI lower >= 0.50.

theoretical_w forward formula:
    mean_on_hit = return_rate * 100 / p_hit                       # yen
    var_x_per_bet = p_hit * std^2 + p_hit * (1 - p_hit) * mean^2  # yen^2
    SE_yen        = sqrt(var_x_per_bet / n_bets)
    ci_lo_yen     = return_rate * 100 - z * SE_yen

Inverse (observed_lo given, solve for std):
    SE_yen_needed^2  = ((return_rate - obs_lo) * 100 / z)^2
    var_x_per_bet    = SE_yen_needed^2 * n_bets
    std^2            = (var_x_per_bet - p_hit*(1-p_hit)*mean^2) / p_hit
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "recent_3fold_ci.csv"

Z = 1.96
FULL_POP_STD = 2090.0  # from theoretical_w.py output

TARGETS = [
    # strategies named in scorecard v2 §1.6 plus a few neighbors
    "dm_rank_1_3",
    "tm_rank_1_3",
    "all",
    "kelly_ge_05",
    "ev_ge_105",
    "wl_pop_1_2",
    "wl_odds_8_20",
]


def back_out_std(p_hit: float, return_rate: float, n_bets: int, obs_lo: float) -> tuple[float, float]:
    """Returns (effective_std_yen, mean_on_hit_yen).

    return_rate and obs_lo in decimal (0.765 etc.). p_hit also decimal.
    """
    mean = return_rate * 100.0 / p_hit  # yen
    se_yen_needed = (return_rate - obs_lo) * 100.0 / Z
    var_x = (se_yen_needed ** 2) * n_bets
    var_std = (var_x - p_hit * (1.0 - p_hit) * mean ** 2) / p_hit
    if var_std < 0:
        return float("nan"), mean
    return math.sqrt(var_std), mean


def required_n(p_hit: float, return_rate: float, payout_std: float, target_lo: float = 0.50) -> int:
    """How many bets to make CI lower >= target_lo given (p_hit, return_rate, std)."""
    if return_rate <= target_lo:
        return -1
    mean = return_rate * 100.0 / p_hit
    var_x = p_hit * payout_std ** 2 + p_hit * (1.0 - p_hit) * mean ** 2
    se_needed = (return_rate - target_lo) * 100.0 / Z
    return math.ceil(var_x / (se_needed ** 2))


def fmt_int(n: int) -> str:
    if n < 0:
        return "unreach"
    return str(n)


def main() -> None:
    print(f"# full-population std = {FULL_POP_STD:.0f} yen (from theoretical_w.py)")
    print()
    header = (
        f"{'strategy':<14} {'fold':<7} {'p_hit%':>6} {'ret%':>6} {'bets':>5} "
        f"{'obs_lo%':>7} {'eff_std':>8} {'std/pop':>7} "
        f"{'req_n(eff)':>10} {'req_n(pop)':>10}"
    )
    print(header)
    print("-" * len(header))

    with CSV_PATH.open(encoding="utf-8") as f:
        rows = {r["filter"]: r for r in csv.DictReader(f)}

    for target in TARGETS:
        row = rows.get(target)
        if row is None:
            print(f"# (missing: {target})")
            continue
        for fold in ("2025H1", "2025H2", "2026P"):
            try:
                p = float(row[f"{fold}_hit_rate"]) / 100
                r = float(row[f"{fold}_return_rate"]) / 100
                nb = int(row[f"{fold}_bets"])
                lo = float(row[f"{fold}_lo"]) / 100
            except (KeyError, ValueError):
                continue
            if p <= 0 or nb <= 0:
                continue
            eff_std, mean = back_out_std(p, r, nb, lo)
            ratio = eff_std / FULL_POP_STD if not math.isnan(eff_std) else float("nan")
            req_eff = required_n(p, r, eff_std) if not math.isnan(eff_std) else -1
            req_pop = required_n(p, r, FULL_POP_STD)
            print(
                f"{target:<14} {fold:<7} {p*100:>6.1f} {r*100:>6.1f} {nb:>5} "
                f"{lo*100:>7.1f} {eff_std:>8.0f} {ratio:>7.2f} "
                f"{fmt_int(req_eff):>10} {fmt_int(req_pop):>10}"
            )
        print()


if __name__ == "__main__":
    main()
