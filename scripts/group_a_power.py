"""Phase 0.5-5 Group A の検出力の固定 (§8-7): **2025 の対象レースの結果を読まない** 経路 (2026-10-05)。

- 対象レースは `load_target_fields` だけで読む。SELECT は `TARGET_SELECT` (allow-list) から組み立て、着順・走破タイム・上がり・
  異常コードの生の値 (中止・失格・降着は結果) などは **SQL に含めない**。返還 (出走取消・発走除外・競走除外) は真偽だけを SQL で作る
- 標本の行は `won` を持たない。β を推定する関数 (条件付きロジット) はこの module から呼ばない (テストで強制)
- 検出力の SE: (1) 2025 の S と市場の確率だけからの解析的な値 (β = 0・β_market = 1 の仮定でのシューア補元の Fisher 情報) と、
  (2) 学習期 2022-2024 のブートストラップの SE を √(N_学習 / N_2025) で換算した値の **大きい方** (§8-7)
- 過去走 (対象日より前) の時計は特徴の履歴として読む (外部の指示者の決定 2026-10-05)。履歴は (日, 評価値) だけを持ち、
  対象の行に着順や勝ちのフラグは付かない
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from scripts import group_a as g

BETA_TARGET = math.log(1.25) / 2.0           # §8-4: 学習期の 1 SD あたり
Z_ALPHA_2SIDED_001 = 2.5758293035489004      # 両側 α = 0.01
Z_POWER_080 = 0.8416212335729143             # 検出力 80%
CRITICAL_MULTIPLIER = Z_ALPHA_2SIDED_001 + Z_POWER_080   # ≈ 3.418

# 対象レースから読んでよい列 (allow-list)。ここに無い列は SQL に現れない
TARGET_SELECT = (
    "h.race_year", "h.race_month_day", "h.track_code", "h.kaiji", "h.nichiji", "h.race_num",
    "r.track_type_code", "r.distance", "h.horse_num", "h.blood_register_num",
    "CASE WHEN h.abnormal_code IN ('1','2','3') THEN 1 ELSE 0 END",   # 返還の真偽だけ (4 / 5 / 7 は出さない)
    "h.win_odds",                                                     # 市場 (§8-5 の主検定の市場)
)
# 対象レースの結果の列。対象レースを読む SQL にこの名前が現れたら止める (テストでも強制)
FORBIDDEN_COLUMNS = ("confirmed_order", "finish_order", "finish_time", "final_3f", "same_finish", "time_diff",
                     "corner_order", "mining", "payout", "refund", "popularity")


class PowerError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetRunner:
    race_id: str
    ymd: str
    horse: str
    horse_num: str
    refunded: bool
    win_odds: float


def target_sql() -> str:
    sql = f"""SELECT {', '.join(TARGET_SELECT)}
                FROM horse_races h
                JOIN races r ON r.race_year = h.race_year AND r.race_month_day = h.race_month_day
                 AND r.track_code = h.track_code AND r.kaiji = h.kaiji AND r.nichiji = h.nichiji AND r.race_num = h.race_num
               WHERE h.race_year = ? AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
                 AND r.data_div = '7' AND h.horse_num NOT IN ('', '00')
               ORDER BY 1, 2, 3, 6, 9"""
    low = sql.lower()
    bad = [c for c in FORBIDDEN_COLUMNS if c in low]
    if bad:
        raise PowerError(f"対象レースの SQL に結果の列が入っている: {bad}")
    return sql


def load_target_fields(year: int, db_path) -> dict[str, list[TargetRunner]]:
    """対象レース (JRA・確定・平地) の選択集合の材料だけを読む。結果の列は読まない。"""
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    rows = conn.execute(target_sql(), (str(year),)).fetchall()
    conn.close()
    out: dict[str, list[TargetRunner]] = defaultdict(list)
    for (ry, rmd, tc, ka, ni, rn, tt, dist, hn, bn, refunded, odds) in rows:
        if g.is_obstacle(tt):
            continue
        if g.surface_of(tt) is None:
            raise PowerError(f"{ry}{rmd}_{tc}_{ka}_{ni}_{rn}: 平地の未知の track_type_code {tt!r}")
        rid = f"{ry}{rmd}_{tc}_{ka}_{ni}_{rn}"
        out[rid].append(TargetRunner(rid, f"{ry}{rmd}", str(bn or "").strip(), str(hn).strip(), bool(refunded),
                                     float(odds or 0) / 10.0))
    return dict(out)


def outcome_blind_rows(targets: dict[str, list[TargetRunner]], ratings: dict, counts) -> list[dict]:
    """選択集合 (返還を除き、残りで市場の確率を再正規化) の行。`won` は持たない。"""
    out = []
    for rid in sorted(targets):
        runners = targets[rid]
        counts["target_races_seen"] += 1
        choice = [x for x in runners if not x.refunded]
        counts["refunded_runners"] += len(runners) - len(choice)
        if not choice or any(x.win_odds <= 0 for x in choice):
            counts["drop_runner_without_price"] += 1
            continue
        inv = [1.0 / x.win_odds for x in choice]
        total = sum(inv)
        t = g.day_ordinal(runners[0].ymd)
        rows = []
        for x, q in zip(choice, inv):
            comp = g.horse_components(ratings.get(x.horse, []) if x.horse else [], t)
            rows.append({"race_id": rid, "year": int(rid[:4]), "horse_num": x.horse_num, "horse": x.horse,
                         "p_market": q / total, **comp})
        for row, rk in zip(rows, g.rank_in_race([row["perf_rating_best3_365"] for row in rows])):
            row["perf_rating_rank_in_race"] = rk
        counts["target_races_used"] += 1
        counts["runners_before_refund"] += len(runners)
        counts["runners_in_choice_set"] += len(choice)
        out.extend(rows)
    return out


def fisher_se_at_null(rows: list[dict], s_col: str = "S", z_col: str = "logit_p_market") -> dict:
    """β_S = 0・β_market = 1 の仮定 (勝つ確率 = 市場の確率) での、S の係数の SE (シューア補元)。

    レースごとに確率 p で重み付けた共分散 V = Σ p x x' − (Σ p x)(Σ p x)' (x = (z, S)) を足し合わせ、
    情報行列 I = Σ V の逆行列の S の対角から SE を出す。勝ち馬の列は使わない (行に無い)。
    """
    if any("won" in r for r in rows):
        raise PowerError("検出力の計算の行に勝ちの列がある (結果を読まない経路のはず)")
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    info = np.zeros((2, 2))
    schur_terms = []
    for rs in by.values():
        p = np.array([r["p_market"] for r in rs])
        p = p / p.sum()
        X = np.array([[r[z_col], r[s_col]] for r in rs], dtype=float)
        m = p @ X
        V = (X * p[:, None]).T @ X - np.outer(m, m)
        info += V
        schur_terms.append(V)
    inv = np.linalg.inv(info)
    se = float(math.sqrt(inv[1, 1]))
    # レース内の市場の確率で重み付けた S の分散 (シューア補元の前と後) を診断として残す
    var_s = float(info[1, 1])
    schur = float(info[1, 1] - info[0, 1] ** 2 / info[0, 0])
    return {"se": se, "n_races": len(by), "info": info.tolist(), "var_s_within": var_s, "schur_complement": schur,
            "assumption": "beta_S=0, beta_market=1 (win probability = renormalised market probability)"}


def mde(se_fixed: float) -> float:
    return CRITICAL_MULTIPLIER * se_fixed


def fixed_power(se_analytic: float, se_train_boot: float, n_train_races: int, n_target_races: int) -> dict:
    """§8-7: 解析の SE と、学習期のブートストラップの SE の換算値の大きい方で MDE を固定し、判定の区分を先に決める。"""
    se_scaled = se_train_boot * math.sqrt(n_train_races / n_target_races)
    se_fixed = max(se_analytic, se_scaled)
    m = mde(se_fixed)
    return {"se_analytic_2025": se_analytic, "se_train_boot": se_train_boot, "n_train_races": n_train_races,
            "n_target_races": n_target_races, "se_train_scaled": se_scaled, "se_fixed": se_fixed,
            "critical_multiplier": CRITICAL_MULTIPLIER, "mde": m, "beta_target": BETA_TARGET,
            "inconclusive_by_power": bool(m > BETA_TARGET),
            "rule": "MDE > beta_target なら、主検定は結果に関係なく PRIMARY_INCONCLUSIVE (§8-4)。主検定は 1 回実行して記録する"}


def purchase_count_at_target(rows: list[dict], s_col: str = "S") -> dict:
    """§8-8: β = β_target・β_market = 1 の仮定値で、比 exp(β·S) ≥ 1.25 (= S ≥ 2) の馬の件数 (2025 の β̂ は使わない)。"""
    thr = math.log(1.25) / BETA_TARGET
    n = sum(r[s_col] >= thr - 1e-12 for r in rows)
    return {"threshold_S": thr, "n_horses": int(n), "n_rows": len(rows)}
