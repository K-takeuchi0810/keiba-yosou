"""Phase 0.5-5 Group D — クラス昇降 × 能力 (前走でのクラスに対する余裕) の計算 (2026-10-06)。

仕様: `docs/PHASE05_5_PREREG.md` §8-4d、`docs/PHASE05_5_EXPLORATION.md` の D-0〜D-3。ここにあるのは計算の部品だけで、どの年を読むかは
呼び出し側 (`scripts/group_d_explore.py` / `scripts/group_d_run.py`) が決める。

- 1 走の評価値は Group A の部品 (`scripts/group_a.py` の `fit_tables` / `bounded_residual`、S1V1W0、P3 の改訂 B) をそのまま使う。
  Group A の市場の関数・合成の部品は使わない
- 使う前走: 対象日の 365 日前から **前日まで** の、評価値のある最も新しい 1 走。S と class_move は同じ前走から作る
- 要求水準: 同じ canonical class × 芝ダの、**前走の日の** 365 日前から前日までのレースの勝ち馬の評価値の中央値 (1 レース 1 観測、20 レース未満は欠損)
- S_raw = 前走の評価値 − 要求水準。class_move = level(今回) − level(前走)
- 今回のクラスの要求水準を引いた量 (`gap_to_current_class`) は、レース内で定数を引くだけなので条件付きロジットでは前走の評価値と同値 (§8-4d)。診断だけ
- 市場の列は `predictor.market_clogit` / `predictor.race_market.market_feature` (log) だけ
"""
from __future__ import annotations

import math
from bisect import bisect_left
from collections import Counter, defaultdict

import numpy as np

from predictor import race_market as rm
from scripts import c_prime as cp            # 標準化・診断の汎用の部品 (pooled within-race SD など、§8-4c-2)
from scripts import group_a as ga            # 1 走の評価値の部品だけ (市場・合成の部品は使わない)

PRIMARY_YEAR = 2025
WINDOW_DAYS = 365
MIN_REQUIREMENT_RACES = 20
LEVEL = {"701": 0, "703": 0, "005": 1, "010": 2, "016": 3, "999": 4}
SPEC = ga.Spec("S1", "V1", "W0")             # Group A の凍結した評価値の仕様 (§8-4d)
EXCLUDE_ALL_MISSING = "all_runners_missing_previous_surplus"


class GroupDError(RuntimeError):
    pass


def check_est_years(years) -> None:
    if any(int(y) >= PRIMARY_YEAR for y in years):
        raise GroupDError(f"推定に {PRIMARY_YEAR} 年以降を渡した: {sorted(set(years))}")


# ---------------------------------------------------------------------------------------------------- 評価値

def run_ratings(races: dict, tables) -> dict[str, list[tuple[int, str, float]]]:
    """{馬: [(日の序数, race_id, 評価値)] (日付順)}。Group A の `rate_runs` と同じ値 (S1: 尺度なし) に race_id を付けたもの。"""
    if tables.scales is not None:
        raise GroupDError("D は S1 (尺度なし) の評価値だけを使う")
    out: dict[str, list[tuple[int, str, float]]] = defaultdict(list)
    for r in sorted(races.values(), key=lambda x: x.ymd):
        for run in r.runs:
            if run.abnormal in ga.REFUNDED or not run.horse:
                continue
            res, _state = ga.bounded_residual(run, r, tables.par, tables.variants, tables.w)
            if not math.isnan(res):
                out[run.horse].append((run.ordinal, r.race_id, -res))
    for h in out.values():
        h.sort()
    return out


def winner_ratings(races: dict, history: dict) -> dict[str, float]:
    """{race_id: 勝ち馬の評価値の中央値} (確定着順 1 の走で評価値があるもの。同着は中央値で 1 観測)。"""
    by_run = {(rid, h): v for h, entries in history.items() for _, rid, v in entries}
    out = {}
    for r in races.values():
        vals = [by_run[(r.race_id, x.horse)] for x in r.runs if x.finish == 1 and (r.race_id, x.horse) in by_run]
        if vals:
            out[r.race_id] = float(np.median(vals))
    return out


class Requirements:
    """要求水準 `requirement(class, surface, day)`: 同じ class × 芝ダの [day − 365, day − 1] のレースの勝ち馬の評価値の中央値 (20 レース未満は NaN)。"""

    def __init__(self, races: dict, winners: dict[str, float]):
        self.days: dict[tuple, list[int]] = defaultdict(list)
        self.vals: dict[tuple, list[float]] = defaultdict(list)
        rows = sorted((r.ordinal_day, r.race_id) for r in _with_day(races.values()) if r.race_id in winners and r.cls)
        for day, rid in rows:
            r = races[rid]
            key = (r.cls, r.surface)
            self.days[key].append(day)
            self.vals[key].append(winners[rid])
        self.cache: dict[tuple, float] = {}

    def __call__(self, cls: str | None, surface: str | None, day: int) -> float:
        if not cls or not surface:
            return math.nan
        k = (cls, surface, day)
        if k not in self.cache:
            days = self.days.get((cls, surface), [])
            lo, hi = bisect_left(days, day - WINDOW_DAYS), bisect_left(days, day)
            self.cache[k] = float(np.median(self.vals[(cls, surface)][lo:hi])) if hi - lo >= MIN_REQUIREMENT_RACES else math.nan
        return self.cache[k]


def _with_day(races):
    for r in races:
        if not hasattr(r, "ordinal_day"):
            r.ordinal_day = ga.day_ordinal(r.ymd)
        yield r


def previous_run(history: list[tuple[int, str, float]], target_ordinal: int):
    """対象日の 365 日前から前日までで最も新しい評価値のある走 (日の序数, race_id, 評価値)。無ければ None。"""
    lo = bisect_left(history, (target_ordinal - WINDOW_DAYS, "", -math.inf))
    hi = bisect_left(history, (target_ordinal, "", -math.inf))
    return history[hi - 1] if hi > lo else None


# ---------------------------------------------------------------------------------------------------- 標本

def target_rows(races: dict, years: tuple[int, ...], history: dict, req: Requirements,
                counts: Counter, exclusions: list[dict]) -> list[dict]:
    """対象レースの標本 (§8-6 の選択集合の馬ごとに 1 行)。S_raw / class_move は観測がなければ NaN (埋めるのは `standardize_and_fill`)。"""
    out = []
    for race in sorted(_with_day(races.values()), key=lambda r: r.race_id):
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
        if race.cls not in LEVEL:
            raise GroupDError(f"{race.race_id}: 想定外の canonical class {race.cls!r}")
        by_num = {x.horse_num: x for x in race.runs}
        rows = []
        for h in cs.choice:
            run = by_num[h]
            prev = previous_run(history.get(run.horse, []), race.ordinal_day) if run.horse else None
            row = {"race_id": race.race_id, "year": year, "horse_num": h, "horse": run.horse, "won": int(run.finish == 1),
                   "p_market": cs.implied["final"][h], "S_raw": math.nan, "class_move": math.nan, "prev_rating": math.nan,
                   "gap_to_current_class": math.nan, "has_prev": prev is not None}
            if prev is not None:
                pday, prid, prating = prev
                prace = races[prid]
                if prace.cls not in LEVEL:
                    raise GroupDError(f"{prid}: 想定外の canonical class {prace.cls!r}")
                requirement = req(prace.cls, prace.surface, pday)
                row["prev_rating"] = prating
                row["gap_to_current_class"] = prating - req(race.cls, race.surface, race.ordinal_day)
                if not math.isnan(requirement):
                    row["S_raw"] = prating - requirement
                    row["class_move"] = float(LEVEL[race.cls] - LEVEL[prace.cls])
                else:
                    counts["requirement_missing_rows"] += 1
            counts["observed_rows" if not math.isnan(row["S_raw"]) else "missing_rows"] += 1
            rows.append(row)
        if not any(not math.isnan(r["S_raw"]) for r in rows):
            counts[f"excluded:{EXCLUDE_ALL_MISSING}"] += 1
            exclusions.append({"race_id": race.race_id, "reason": EXCLUDE_ALL_MISSING, "horses": [r["horse_num"] for r in rows]})
            continue
        if cs.refunded:
            counts["refunded_runners_excluded"] += len(cs.refunded)
        counts["target_races_used"] += 1
        out.extend(rows)
    return out


def standardize_and_fill(rows: list[dict], s_sd: float) -> list[dict]:
    """S_std = S_raw / σ_within。欠損の馬は S_std と class_move をレース内の観測のある馬の平均で埋める (全馬が欠損のレースは target_rows で除外済み)。"""
    out = [dict(r) for r in rows]
    by: dict[str, list[dict]] = defaultdict(list)
    for r in out:
        by[r["race_id"]].append(r)
    for rid, rs in by.items():
        obs = [r for r in rs if not math.isnan(r["S_raw"])]
        if not obs:
            raise GroupDError(f"{rid}: 観測のある馬がいない (target_rows で除くはず)")
        s_fill = sum(r["S_raw"] for r in obs) / len(obs) / s_sd
        m_fill = sum(r["class_move"] for r in obs) / len(obs)
        for r in rs:
            observed = not math.isnan(r["S_raw"])
            r["S_std"] = r["S_raw"] / s_sd if observed else s_fill
            r["class_move_filled"] = r["class_move"] if observed else m_fill
    return out


def fit_scale(fit_rows: list[dict]) -> dict:
    """推定期間の観測のある行で、S_raw の pooled within-race SD (§8-4c-2)。"""
    check_est_years({r["year"] for r in fit_rows})
    return cp.within_sd(fit_rows, "S_raw")


def clogit(rows: list[dict], s_col: str = "S_std") -> dict:
    """主検定のモデル `[market_feature, class_move, S]` の係数と SE (`c_prime.clogit_with_se` は市場の列を market_clogit で足す)。"""
    return cp.clogit_with_se(rows, ["class_move_filled", s_col])


def gap_equivalence(rows: list[dict], s_sd: float) -> dict:
    """診断 (§8-4d): 今回のクラスの要求水準を引いた量と前走の評価値の、条件付きロジットの係数 (レース内の全馬で両方が定義されるレースだけ)。"""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    keep = [r for rs in by.values() if all(not math.isnan(x["gap_to_current_class"]) and not math.isnan(x["S_raw"]) for x in rs)
            for r in rs]
    if not keep:
        return {"n_races": 0}
    data = [{**r, "class_move_filled": r["class_move"], "gap_std": r["gap_to_current_class"] / s_sd,
             "prev_std": r["prev_rating"] / s_sd} for r in keep]
    g = cp.clogit_with_se(data, ["class_move_filled", "gap_std"])
    p = cp.clogit_with_se(data, ["class_move_filled", "prev_std"])
    return {"n_races": len({r["race_id"] for r in keep}), "beta_gap": g["beta"][2], "beta_prev": p["beta"][2],
            "abs_diff": abs(g["beta"][2] - p["beta"][2]),
            "note": "今回のクラスの要求水準はレース内で定数なので、前走の評価値と同じ係数になる (§8-4d、主検定に採らない理由)"}

