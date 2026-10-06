"""次の世代の候補 A″ の計算の部品 (docs/A_DOUBLE_PRIME_PREREG.md、2026-10-06)。

Group A の 1 走の評価値 (S1V1W0) と 4 成分をそのまま使い、標準化だけを pooled within-race SD (§8-4c-2) に、欠損をレース内の平均に、
市場の項を log P_market (§8-6b) にする。選択集合は §8-6 (`predictor.race_market.choice_rows`)。
読み込みは `scripts.group_a.load_races` (研究の窓の関所を通る、2024 まで)。Group A の凍結物・2025 の成果物は読まない。

構造の量 (結果の列を使わない、E1 の前に測る): S と前走の着順の分位・log P_market のレース内の相関、S を [着順の分位, log P_market] で
レース内に回帰した決定係数 (Group D の教訓)。
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np

from predictor import market_clogit as mc
from predictor import race_market as rm
from scripts import c_prime as cp            # 標準化・診断の汎用の部品 (pooled within-race SD など、§8-4c-2)
from scripts import group_a as ga            # 1 走の評価値と 4 成分の部品

PRIMARY_YEAR = 2025
SPEC = ga.Spec("S1", "V1", "W0")             # Group A の凍結した評価値の仕様
COMPONENTS = ga.COMPONENTS
STD_SUFFIX = "_wstd"
EXCLUDE_NO_PRICE = "nonrefund_runner_without_price"


class GroupA2Error(RuntimeError):
    pass


def check_est_years(years) -> None:
    if any(int(y) >= PRIMARY_YEAR for y in years):
        raise GroupA2Error(f"推定に {PRIMARY_YEAR} 年以降を渡した: {sorted(set(years))}")


def finish_history(races: dict) -> dict[str, list[tuple[int, float]]]:
    """{馬: [(日の通し番号, 着順の分位)]} (日付順)。分位は (完走頭数 − 着順 + 0.5) / 完走頭数 (良いほど大)。構造の量の診断だけに使う。"""
    out: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for r in sorted(races.values(), key=lambda x: x.ymd):
        finishers = [x for x in r.runs if x.finish > 0 and x.abnormal not in ga.REFUNDED]
        n = len(finishers)
        for x in finishers:
            if x.horse:
                out[x.horse].append((x.ordinal, (n - x.finish + 0.5) / n))
    return out


def last_finish_pct(history: list[tuple[int, float]], target_ordinal: int) -> float:
    """対象日の 365 日前から前日までの最新の走の着順の分位 (無ければ NaN)。"""
    window = [v for d, v in history if target_ordinal - ga.WINDOW_DAYS <= d < target_ordinal]
    return window[-1] if window else math.nan


def target_rows(races: dict, years: tuple[int, ...], ratings: dict, finishes: dict, counts: Counter,
                exclusions: list[dict]) -> list[dict]:
    """対象レースの標本 (§8-6 の選択集合の馬ごとに 1 行)。成分は欠損なら NaN (埋めるのは `fit_composite` / `apply_composite`)。"""
    out = []
    for race in sorted(races.values(), key=lambda r: r.race_id):
        year = int(race.ymd[:4])
        if year not in years:
            continue
        counts["target_races_seen"] += 1
        winners = [x for x in race.runs if x.finish == 1]
        if len(winners) != 1:
            counts["drop_dead_heat_or_no_winner"] += 1
            continue
        abnormal = {x.horse_num: x.abnormal for x in race.runs}
        market = {x.horse_num: x.win_odds for x in race.runs if x.win_odds > 0}
        sel = rm.choice_rows([{"horse_num": x.horse_num, "won": int(x.finish == 1)} for x in race.runs], abnormal, {"final": market})
        if isinstance(sel, rm.Excluded):
            counts[f"excluded:{sel.reason}"] += 1
            exclusions.append({"race_id": race.race_id, "reason": sel.reason, "horses": list(sel.horses)})
            continue
        cs, _ = sel
        by_num = {x.horse_num: x for x in race.runs}
        rows = []
        for h in cs.choice:
            run = by_num[h]
            comp = ga.horse_components(ratings.get(run.horse, []) if run.horse else [], run.ordinal)
            rows.append({"race_id": race.race_id, "year": year, "horse_num": h, "horse": run.horse, "won": int(run.finish == 1),
                         "p_market": cs.implied["final"][h], **comp,
                         "last_finish_pct": last_finish_pct(finishes.get(run.horse, []), run.ordinal) if run.horse else math.nan})
        for row, rk in zip(rows, ga.rank_in_race([row["perf_rating_best3_365"] for row in rows])):
            row["perf_rating_rank_in_race"] = rk
        for row in rows:
            row["all_components_missing"] = all(math.isnan(row[c]) for c in COMPONENTS)
            counts["missing_rows" if row["all_components_missing"] else "observed_rows"] += 1
        if cs.refunded:
            counts["refunded_runners_excluded"] += len(cs.refunded)
        counts["target_races_used"] += 1
        out.extend(rows)
    return out


def fit_composite(fit_rows: list[dict]) -> dict:
    """推定期間の行で、成分の σ_within・合成の重み (逆符号は 0)・S の σ_within を決める (A″ §2)。"""
    check_est_years({r["year"] for r in fit_rows})
    rows = [dict(r) for r in fit_rows]
    comp_sd = {}
    for c in COMPONENTS:
        comp_sd[c] = cp.within_sd(rows, c)
        cp.standardize(rows, c, comp_sd[c]["sd"], c + STD_SUFFIX)
    fit = cp.clogit_with_se(rows, [c + STD_SUFFIX for c in COMPONENTS])
    raw = dict(zip(COMPONENTS, fit["beta"][1:]))
    weights = {c: (b if b > 0 else 0.0) for c, b in raw.items()}          # 期待される符号はすべて正 (§8-4b)
    if not any(w > 0 for w in weights.values()):
        raise GroupA2Error(f"全成分が逆符号 (重みがすべて 0): {raw}。A″ は候補にならない")
    for r in rows:
        r["S_raw"] = sum(weights[c] * r[c + STD_SUFFIX] for c in COMPONENTS)
    s_sd = cp.within_sd(rows, "S_raw")
    return {"years": sorted({r["year"] for r in fit_rows}), "component_sd": comp_sd, "fit": fit, "raw_coefficients": raw,
            "weights": weights, "zeroed": [c for c in COMPONENTS if weights[c] == 0.0], "s_sd": s_sd,
            "n_races": len({r["race_id"] for r in rows}), "n_rows": len(rows)}


def apply_composite(rows: list[dict], comp: dict) -> list[dict]:
    """凍結した σ・重みで S を作った行のコピー (推定し直さない)。成分は σ_within で割り、欠損はレース内の平均で埋める。"""
    out = [dict(r) for r in rows]
    for c in COMPONENTS:
        cp.standardize(out, c, comp["component_sd"][c]["sd"], c + STD_SUFFIX)
    for r in out:
        r["S"] = sum(comp["weights"][c] * r[c + STD_SUFFIX] for c in COMPONENTS) / comp["s_sd"]["sd"]
    return out


def within_r2(rows: list[dict], y: str, xs: list[str]) -> dict:
    """レース内で中心化した y を、レース内で中心化した xs で最小二乗 (等重み)。決定係数と係数。"""
    by = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    Y, X = [], []
    for rs in by.values():
        yy = np.array([r[y] for r in rs], dtype=float)
        xx = np.array([[r[c] for c in xs] for r in rs], dtype=float)
        Y.extend(yy - yy.mean())
        X.extend(xx - xx.mean(axis=0))
    Y, X = np.array(Y), np.array(X)
    if not len(Y) or not (Y @ Y) > 0:
        raise GroupA2Error(f"{y}: レース内の変動が無い")
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ coef
    return {"r2": float(1 - (resid @ resid) / (Y @ Y)), "coef": dict(zip(xs, map(float, coef)))}


def structural(rows: list[dict]) -> dict:
    """構造の量 (結果の列を使わない)。前走の着順が分かる馬が 2 頭以上いるレースの、それらの馬だけで測る。"""
    if any("won" in r for r in rows):
        raise GroupA2Error("構造の量の行に勝ちの列がある (結果を読まない計算のはず)")
    by = defaultdict(list)
    for r in rows:
        if not math.isnan(r["last_finish_pct"]):
            by[r["race_id"]].append({**r, "log_p": rm.market_feature(r["p_market"])})
    obs = [r for rs in by.values() if len(rs) >= 2 for r in rs]
    return {"n_rows": len(obs), "n_races": len({r["race_id"] for r in obs}),
            "within_race_corr_S_last_finish": cp.within_race_corr(obs, "S", "last_finish_pct"),
            "within_race_corr_S_log_p": cp.within_race_corr(obs, "S", "log_p"),
            "within_race_r2_S_on_finish_and_market": within_r2(obs, "S", ["last_finish_pct", "log_p"]),
            "within_race_r2_S_on_finish_only": within_r2(obs, "S", ["last_finish_pct"])}


def rows_without_outcome(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if k != "won"} for r in rows]


def outcome_blind_power(rows: list[dict], beta_target: float, critical: float, se_train_boot: float | None = None,
                        n_train_races: int | None = None) -> dict:
    """MDE <= beta_target に要るレース数 (規則 §4、§8-7b と同じ規則の単一の出典)。

    SE は、結果を読まない Fisher の SE (β_market = 1・β_S = 0) と、学習期のブートストラップの SE を √(N_学習 / N) で換算した値の大きい方。
    σ₁ = その SE × √N (1 レースあたり)、N_primary_required = ceil((critical × σ₁ / β_target)²)。
    """
    fisher = mc.fisher_se_at_null(rows_without_outcome(rows), s_col="S")
    n = fisher["n_races"]
    se_scaled = se_train_boot * math.sqrt(n_train_races / n) if se_train_boot is not None else None
    se_fixed = max(fisher["se"], se_scaled) if se_scaled is not None else fisher["se"]
    sigma1 = se_fixed * math.sqrt(n)
    return {"fisher": fisher, "se_train_boot": se_train_boot, "n_train_races": n_train_races, "se_train_scaled": se_scaled,
            "se_fixed": se_fixed, "sigma_per_race": sigma1, "n_races": n,
            "n_primary_required": math.ceil((critical * sigma1 / beta_target) ** 2)}
