"""真の W: 現実的予測者の理論的 CI 下限。

oracle (勝率 100%) は trivial だったので、本来の問い「現実的勝率 × 平均オッズで
CI 下限 ≥ 0.50 を達成するには何 bets 必要か」に答える。

approach:
  - 単勝 100 円賭けの per-bet return X は「hit (prob=p) なら payout/100、miss なら 0」の混合
  - E[X]   = p × μ_hit_payout / 100 = observed return_rate
  - Var[X] = p × (μ²+ σ²) − (pμ)²   = p×σ² + p(1−p)×μ²        ← μ,σ は yen 単位
  - SE      = sqrt(Var[X] / n_bets)
  - CI 下限 ≈ E[X] − 1.96 × SE   (normal approximation; bootstrap と一致しないが
                                  漸近的には同じ。1000 bets では誤差小)

payout の natural std を実データから取る (oracle で 2025-01〜2026-05 の単勝
払戻分布から推定)。

usage:
    python -m scripts.theoretical_w --db /c/Users/kizun/dev/keiba-yosou/data/keiba.db
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db


def payout_stats(conn) -> tuple[float, float, int]:
    """oracle 全 2025-01〜2026-05 の単勝払戻 (1 着馬) の平均と標準偏差。"""
    rows = conn.execute(
        """
        SELECT p.tan_payout1
        FROM races r
        JOIN payouts p
          ON p.race_year = r.race_year
         AND p.race_month_day = r.race_month_day
         AND p.track_code = r.track_code
         AND p.kaiji = r.kaiji
         AND p.nichiji = r.nichiji
         AND p.race_num = r.race_num
        WHERE (r.race_year || r.race_month_day) BETWEEN '20250101' AND '20260517'
          AND CAST(r.track_code AS INTEGER) BETWEEN 1 AND 10
          AND p.tan_payout1 IS NOT NULL
          AND p.tan_payout1 > 0
        """
    ).fetchall()
    payouts = [r[0] for r in rows]
    n = len(payouts)
    mean = sum(payouts) / n
    var = sum((p - mean) ** 2 for p in payouts) / (n - 1)
    return mean, math.sqrt(var), n


def theoretical_ci_lo(p_hit: float, return_rate: float, n_bets: int, payout_std: float, z: float = 1.96) -> float:
    """理論 CI 下限 (yen を 100 で割った return_rate スケール)。

    p_hit:        hit rate (0 < p < 1)
    return_rate:  observed point estimate (e.g., 0.80 = 80%)
    n_bets:       sample size
    payout_std:   std of winning payouts in yen (from oracle data)
    """
    if p_hit <= 0 or n_bets <= 0:
        return 0.0
    # 100 円賭け前提。observed return_rate から逆算した平均当たり払戻 (yen):
    mean_on_hit = return_rate * 100 / p_hit
    # per-bet Var (yen²):
    var_x = p_hit * payout_std ** 2 + p_hit * (1 - p_hit) * mean_on_hit ** 2
    se_yen = math.sqrt(var_x / n_bets)
    ci_lo_yen = return_rate * 100 - z * se_yen
    return ci_lo_yen / 100  # return_rate スケール


def required_n_for_ci_lo_50(p_hit: float, return_rate: float, payout_std: float, z: float = 1.96) -> int:
    """CI 下限 ≥ 0.50 を達成するために必要な最小 n_bets。

    closed-form 解は normal approx で:
       0.50 = return_rate − z × SE
       SE   = (return_rate − 0.50) / z
       Var/n = SE² × 100²              (yen² スケール)
       n = Var / SE² × 1/100²
    """
    if return_rate <= 0.50:
        return -1  # unreachable
    mean_on_hit = return_rate * 100 / p_hit
    var_x = p_hit * payout_std ** 2 + p_hit * (1 - p_hit) * mean_on_hit ** 2
    se_yen_needed = (return_rate - 0.50) * 100 / z
    return math.ceil(var_x / (se_yen_needed ** 2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument(
        "--csv",
        default=str(Path(__file__).resolve().parent.parent / "data" / "recent_3fold_ci.csv"),
    )
    args = ap.parse_args()

    with open_db(args.db) if args.db else open_db() as conn:
        mean, std, n = payout_stats(conn)

    print(f"# payout stats (2025-01 to 2026-05, JRA 1-10): mean={mean:.0f}yen, std={std:.0f}yen, n={n}")
    print(f"# (CV = std/mean = {std/mean:.2f} → payout 分布の natural spread)")
    print()

    # === Grid 1: 理論 CI lower as function of (hit_rate, return_rate, n_bets) ===
    print("=== Grid: theoretical CI lower bound (% of stake) ===")
    print("# 各セル = CI 下限 (%) at given (hit_rate, point return_rate) and n_bets")
    print("# 「現実的勝率 × point return_rate × bets で CI 下限 ≥ 50 が出るか」の地図")
    print()
    n_values = [200, 355, 525, 1000, 1266, 2000]
    print("hit_rate,return_rate," + ",".join(f"n={n}" for n in n_values))
    for p_hit in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        for r_pt in [0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.20]:
            cells = []
            for nb in n_values:
                lo = theoretical_ci_lo(p_hit, r_pt, nb, std)
                cells.append(f"{lo*100:.0f}")
            print(f"{p_hit:.2f},{r_pt:.2f}," + ",".join(cells))
    print()

    # === Grid 2: required n_bets for CI lower >= 0.50 ===
    print("=== Required n_bets for CI lower >= 0.50 ===")
    print("# 「(hit_rate, return_rate) で CI 下限 50 を出すには何 bets 要るか」")
    print("hit_rate,return_rate,required_n")
    for p_hit in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]:
        for r_pt in [0.55, 0.60, 0.70, 0.80, 0.90, 1.00, 1.10]:
            req = required_n_for_ci_lo_50(p_hit, r_pt, std)
            req_str = "unreachable" if req < 0 else str(req)
            print(f"{p_hit:.2f},{r_pt:.2f},{req_str}")
    print()

    # === Map current strategies onto this grid ===
    print("=== Current strategy mapping (filter_sweep recent_3fold_ci.csv) ===")
    print("# 観察された (hit_rate, return_rate, n_bets) → 理論 CI 下限 vs 観察 CI 下限")
    print("# 大きく乖離していれば、normal approx の前提 (payout 分布が一様) が崩れている")
    print()
    print("strategy,fold,hit_rate,return_rate,bets,observed_lo,theoretical_lo,gap_pp")
    targets = {
        "tm_rank_1_3", "dm_rank_1_3", "kelly_ge_05",
        "s6_kelly_05_mp40", "all", "ev_ge_105",
        "wl_pop_1_2", "wl_odds_8_20",
    }
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"# (recent_3fold_ci.csv not found at {csv_path}, skipping mapping)")
        return 0
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fname = row.get("filter", "")
            if fname not in targets:
                continue
            for fold in ("2025H1", "2025H2", "2026P"):
                try:
                    p = float(row[f"{fold}_hit_rate"]) / 100
                    r = float(row[f"{fold}_return_rate"]) / 100
                    nb = int(row[f"{fold}_bets"])
                    lo_obs = float(row[f"{fold}_lo"]) / 100
                except (KeyError, ValueError):
                    continue
                if nb == 0 or p == 0:
                    continue
                lo_th = theoretical_ci_lo(p, r, nb, std)
                gap = (lo_obs - lo_th) * 100
                print(
                    f"{fname},{fold},{p*100:.1f},{r*100:.1f},{nb},"
                    f"{lo_obs*100:.1f},{lo_th*100:.1f},{gap:+.1f}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
