"""Phase 0.5-5 Group A — 走破時計の内容で能力を評価する特徴 (Performance Rating) の計算 (2026-10-05)。

仕様: `docs/PHASE05_5_PREREG.md` §8-4 / §8-4b / §8-4b-2、`docs/PHASE05_5_EXPLORATION.md` の A-0〜A-3b。
ここにあるのは計算の部品だけで、どの年を読むか・どの候補を試すかは呼び出し側 (`scripts/group_a_explore.py`) が決める。

- 時計は MSSt を秒に復号し、**秒 / km** で扱う (P1)。0 は NaN。障害 (`track_type_code` 51 以上) は使わない
- 標準タイムの模型 (レース単位、勝ち時計 / km): セル + 芝ダ×馬場状態 + クラス + 年齢の制限の区分。クラスと年齢の区分は
  馬場差の材料 (ε) を作るための局外の補正で、評価値からは引かない (2a)
- 馬ごとの過去走の残差だけを ±3.0 秒 / km で clip する (P3)。clip は残差から局外の補正 (クラス + 年齢の区分) を一度外した値に
  当て、その後に戻す (事前登録 §8-4b-3、2026-10-05 改訂 B。2a を保ったまま、クラス・年齢による系統的な打ち切りを避ける)
- 成分は対象日の 365 日前から前日までの過去走だけで作る
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sqlite3
import subprocess
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np

from config import guard_analysis_window
from db import REFUNDED_ABNORMAL_CODES
from scripts import research_window

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "keiba.db"
CLASS_TABLE = ROOT / "data" / "backtest" / "group_a_class_20261005" / "class_table.csv"

OBSTACLE_FROM = 51                 # track_type_code がこれ以上なら障害 (§8-4b-2)
DIRT_CODES = range(23, 30)         # 23〜29 がダート。10〜22 が芝
REFUNDED = REFUNDED_ABNORMAL_CODES      # 出走取消・発走除外・競走除外 (単一の出典は db)
PRIMARY_YEAR = 2025                # 主検定の年。推定 (fit_*) には渡さない
WINDOW_DAYS = 365
MIN_CELL_RACES = 20
MIN_VARIANT_RACES = 3
CLIP_SEC_PER_KM = 3.0              # P3 (固定)
BASE_WEIGHT_KG = 55.0
HANDICAP = "1"                     # races.weight_type_code: 1 = ハンデ
REF_CLASS, REF_AGE = "005", "3up"  # 標準タイムの模型の基準の水準 (定数のずれはレース内の比較で消える)
COMPONENTS = ("perf_rating_last", "perf_rating_best3_365", "perf_rating_trend_365", "perf_rating_rank_in_race")
DIST_BANDS = (1400, 1800, 2200)    # S2 の帯: 1400 未満 / 1400〜1799 / 1800〜2199 / 2200 以上


class GroupAError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------------- 復号・分類

def decode_msst(value) -> float:
    """MSSt (例 1122 = 1 分 12 秒 2) を秒にする。0・空・不正は NaN。生の値どうしの引き算はしない (§8-4b)。"""
    try:
        t = int(value)
    except (TypeError, ValueError):
        return math.nan
    if t <= 0 or t % 1000 >= 600:          # 秒の欄が 60 以上は MSSt として不正 (2021-2024 の JRA で 0 件)
        return math.nan
    return t // 1000 * 60 + (t % 1000) / 10.0


def is_obstacle(track_type_code) -> bool:
    try:
        return int(track_type_code) >= OBSTACLE_FROM
    except (TypeError, ValueError):
        return False


def surface_of(track_type_code) -> str | None:
    """'T' (芝) / 'D' (ダート) / None (障害・不明)。読み込みでは、障害は飛ばし、平地の未知のコードは止める。"""
    try:
        tt = int(track_type_code)
    except (TypeError, ValueError):
        return None
    if tt >= OBSTACLE_FROM:
        return None
    if tt in DIRT_CODES:
        return "D"
    if 10 <= tt <= 22:
        return "T"
    return None


def age_restriction(c2: str, c3: str, c4: str, c5: str) -> str | None:
    """年齢の制限の区分 (固定の規則、探索台帳 A-1)。000 でない欄の並びで決め、それ以外は None (推測しない)。"""
    pat = tuple(c != "000" for c in (c2, c3, c4, c5))
    return {(True, False, False, False): "2yo", (False, True, False, False): "3yo",
            (False, True, True, True): "3up", (False, False, True, True): "4up"}.get(pat)


def dist_band(distance: int) -> int:
    return sum(distance >= b for b in DIST_BANDS)


def day_ordinal(ymd: str) -> int:
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])).toordinal()


# ---------------------------------------------------------------------------------------------------- 読み込み

@dataclass
class Race:
    race_id: str
    ymd: str
    track: str
    track_type: str
    surface: str
    distance: int
    going: str                 # 芝ダ × 馬場状態 (例 'T1')
    weight_type: str
    cls: str | None
    age: str | None
    runs: list = field(default_factory=list)


@dataclass
class Run:
    race_id: str
    ymd: str
    ordinal: int
    horse: str
    horse_num: str
    abnormal: str
    finish: int
    sec_per_km: float          # NaN なら時計なし
    burden_kg: float
    win_odds: float            # 倍。0 以下は価格なし


def load_class_table(path: Path = CLASS_TABLE) -> dict[str, tuple[str, str | None]]:
    """{race_id: (canonical_class, 年齢の制限の区分)}。"""
    out = {}
    with Path(path).open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["race_id"]] = (r["canonical_class"], age_restriction(r["c2"], r["c3"], r["c4"], r["c5"]))
    return out


def load_races(max_year: int, *, min_year: int = 2021, db_path: Path | str = DB_PATH,
               class_table: dict | None = None, allow_primary_year: bool = False,
               primary_purpose: str | None = None) -> tuple[dict[str, Race], Counter]:
    """JRA・確定 (`data_div = 7`)・平地のレースと走を読む。**探索は 2024 年以前だけ** (2025 は主検定の年)。

    `allow_primary_year` は主検定の年を読むとき (検出力の計算の履歴 / 主検定) だけ True にし、`primary_purpose` に目的を書く
    (成果物の stats に残る監査の記録)。探索のコードからは渡さない。
    """
    if max_year >= PRIMARY_YEAR and not allow_primary_year:
        raise GroupAError(f"探索で 2025 年以降を読もうとした (max_year={max_year})。主検定の年は探索で読まない")
    if allow_primary_year and not primary_purpose:
        raise GroupAError("主検定の年を読むときは primary_purpose (目的) を書く")
    # 研究の窓の関所 (docs/LOCKBOX_GOVERNANCE.md、2026-10-06 追加): 2025 は reproduce_consumed、2026 以降 (RESERVED / fresh) は止まる
    window = research_window.check_years(min_year, max_year, context="group_a.load_races",
                                         purpose="reproduce_consumed" if allow_primary_year else "development",
                                         reproduces=primary_purpose)
    from_date, to_date, _sealed = guard_analysis_window(f"{min_year}0101", f"{max_year}1231",
                                                        context="group_a.load_races")
    classes = class_table if class_table is not None else load_class_table()
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    rows = conn.execute(
        """SELECT h.race_year||h.race_month_day, h.track_code, h.kaiji, h.nichiji, h.race_num,
                  r.track_type_code, r.distance, r.turf_condition, r.dirt_condition, r.weight_type_code,
                  h.horse_num, h.blood_register_num, h.abnormal_code, h.confirmed_order, h.finish_time,
                  h.burden_weight, h.win_odds
             FROM horse_races h
             JOIN races r ON r.race_year = h.race_year AND r.race_month_day = h.race_month_day
              AND r.track_code = h.track_code AND r.kaiji = h.kaiji AND r.nichiji = h.nichiji AND r.race_num = h.race_num
            WHERE (h.race_year||h.race_month_day) BETWEEN ? AND ?
              AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
              AND r.data_div = '7' AND h.horse_num NOT IN ('', '00')
            ORDER BY 1, h.track_code, h.race_num, h.horse_num""", (from_date, to_date)).fetchall()
    conn.close()
    stats: Counter = Counter()
    races: dict[str, Race] = {}
    for (ymd, tc, ka, ni, rn, tt, dist, tcond, dcond, wt, hn, bn, abn, fin, ftime, bw, odds) in rows:
        if is_obstacle(tt):
            stats["skip_obstacle_rows"] += 1
            continue
        surf = surface_of(tt)
        if surf is None:
            raise GroupAError(f"{ymd}_{tc}_{ka}_{ni}_{rn}: 平地の未知の track_type_code {tt!r} (黙って落とさない)")
        rid = f"{ymd}_{tc}_{ka}_{ni}_{rn}"
        race = races.get(rid)
        if race is None:
            if rid not in classes:
                raise GroupAError(f"{rid}: クラスの表に無い (表は 2021-2025 の JRA の全レース)")
            cls, age = classes[rid]
            cond = str(dcond if surf == "D" else tcond).strip()
            race = Race(rid, ymd, tc, str(tt).strip(), surf, int(dist or 0), f"{surf}{cond}", str(wt or "").strip(),
                        cls, age)
            races[rid] = race
        km = race.distance / 1000.0
        sec = decode_msst(ftime)
        race.runs.append(Run(rid, ymd, day_ordinal(ymd), str(bn or "").strip(), str(hn).strip(),
                             str(abn or "0").strip(), int(fin or 0), sec / km if km > 0 else math.nan,
                             float(bw or 0) / 10.0, float(odds or 0) / 10.0))
        stats["rows"] += 1
    stats["races"] = len(races)
    stats["guard_from"], stats["guard_to"] = from_date, to_date
    stats["research_window_purpose"] = window["purpose"]
    if allow_primary_year:
        stats["primary_year_purpose"] = primary_purpose
    return races, stats


# ---------------------------------------------------------------------------------------------------- 標準タイム

def check_est_years(est_years) -> None:
    """推定 (補正テーブル・斤量・尺度・合成) に主検定の年を渡したら止める。凍結物は 2022-2024 だけで作る。"""
    bad = [y for y in est_years if int(y) >= PRIMARY_YEAR]
    if bad:
        raise GroupAError(f"推定の年に主検定の年 {bad} が入っている (凍結物は 2022-2024 だけで作る)")


def winner_sec_per_km(race: Race) -> float:
    vals = {r.sec_per_km for r in race.runs if r.finish == 1 and not math.isnan(r.sec_per_km)}
    return vals.pop() if len(vals) == 1 else math.nan     # 同着は同じ値。違う値なら使わない


@dataclass
class ParModel:
    est_years: tuple[int, ...]
    cell_level: dict           # 元のセル → 使う水準 (自身 / 共有 / None)
    coef: dict                 # 列名 → 係数
    columns: list
    counts: dict

    def base(self, race: Race) -> float:
        """評価値の基準 a[セル] + g[芝ダ×馬場状態] (秒 / km)。クラスと年齢の区分は含めない (2a)。"""
        level = self.level_of(race)
        if level is None:
            return math.nan
        return self.coef["intercept"] + self.coef.get(f"cell={level}", 0.0) + self.coef.get(f"going={race.going}", 0.0)

    def fitted(self, race: Race) -> float:
        """局外の補正も含めた期待勝ち時計 (秒 / km)。年齢の区分が欠損なら NaN。"""
        b = self.base(race)
        if math.isnan(b) or race.age is None or race.cls is None:
            return math.nan
        ck, ak = f"class={race.cls}", f"age={race.age}"
        if (race.cls != REF_CLASS and ck not in self.coef) or (race.age != REF_AGE and ak not in self.coef):
            return math.nan          # 推定期間に無かったクラス・年齢の区分は基準扱いにしない (評価値なし)
        return b + self.coef.get(ck, 0.0) + self.coef.get(ak, 0.0)

    def level_of(self, race: Race):
        return self.cell_level.get((race.track, race.track_type, race.distance))


def fit_par_model(races: dict[str, Race], est_years: tuple[int, ...]) -> ParModel:
    """推定期間のレースだけで、勝ち時計 / km の最小二乗を解く (1 レース 1 観測)。疎なセルは探索台帳 A-1 の規則。

    馬場状態のダミーは芝ダの両面で参照を 1 つ (D1) だけ落とすので、セルが芝ダに入れ子になっていることと合わせて
    設計行列の rank が 1 落ちる (2026-10-05 prediction-logic の指摘)。lstsq は最小ノルムの解を返し、個々の係数は
    解釈できないが、`base` (セル + 馬場状態) と `fitted` が使う列の組は零空間と直交するので、評価値と ε は一意に決まる。
    rank を counts に残す。
    """
    check_est_years(est_years)
    est = [r for r in races.values() if int(r.ymd[:4]) in est_years]
    usable = [r for r in est if not math.isnan(winner_sec_per_km(r)) and r.age is not None and r.cls is not None]
    cell_n = Counter((r.track, r.track_type, r.distance) for r in usable)
    sparse_n = Counter(("pooled", r.surface, r.distance) for r in usable if cell_n[(r.track, r.track_type, r.distance)] < MIN_CELL_RACES)
    cell_level: dict = {}
    for cell, n in cell_n.items():
        if n >= MIN_CELL_RACES:
            cell_level[cell] = cell
    surface_of_type = {r.track_type: r.surface for r in usable}
    for cell, n in cell_n.items():
        if n < MIN_CELL_RACES:
            pooled = ("pooled", surface_of_type[cell[1]], cell[2])
            cell_level[cell] = pooled if sparse_n[pooled] >= MIN_CELL_RACES else None
    fit_races = [r for r in usable if cell_level.get((r.track, r.track_type, r.distance)) is not None]
    levels = sorted({cell_level[(r.track, r.track_type, r.distance)] for r in fit_races}, key=str)
    goings = sorted({r.going for r in fit_races})
    classes = sorted({r.cls for r in fit_races} - {REF_CLASS})
    ages = sorted({r.age for r in fit_races} - {REF_AGE})
    columns = (["intercept"] + [f"cell={lv}" for lv in levels[1:]] + [f"going={g}" for g in goings[1:]]
               + [f"class={c}" for c in classes] + [f"age={a}" for a in ages])
    idx = {c: i for i, c in enumerate(columns)}
    X = np.zeros((len(fit_races), len(columns)))
    y = np.zeros(len(fit_races))
    for i, r in enumerate(fit_races):
        X[i, 0] = 1.0
        for key in (f"cell={cell_level[(r.track, r.track_type, r.distance)]}", f"going={r.going}",
                    f"class={r.cls}", f"age={r.age}"):
            if key in idx:
                X[i, idx[key]] = 1.0
        y[i] = winner_sec_per_km(r)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    rank = int(np.linalg.matrix_rank(X))
    coef = dict(zip(columns, (float(b) for b in beta)))
    counts = {"est_races": len(est), "usable_races": len(usable), "fit_races": len(fit_races),
              "cells": len(cell_n), "sparse_cells": sum(n < MIN_CELL_RACES for n in cell_n.values()),
              "races_in_sparse_cells": sum(n for n in cell_n.values() if n < MIN_CELL_RACES),
              "races_unrated_cells": len(usable) - len(fit_races),
              "races_age_unknown": sum(r.age is None for r in est),
              "design_cols": len(columns), "design_rank": rank}
    return ParModel(tuple(est_years), cell_level, coef, columns, counts)


# ---------------------------------------------------------------------------------------------------- 馬場差・斤量・尺度

def day_variants(races: dict[str, Race], par: ParModel, how: str) -> dict[tuple, float]:
    """{(日, 競馬場, 芝ダ): 馬場差 (秒 / km)}。V0 は空。1 レース 1 観測で、自レースを含む。3 未満の区分は 0 (= 載せない)。"""
    if how == "V0":
        return {}
    eps: dict[tuple, list[float]] = defaultdict(list)
    for r in races.values():
        w = winner_sec_per_km(r)
        f = par.fitted(r)
        if not math.isnan(w) and not math.isnan(f):
            eps[(r.ymd, r.track, r.surface)].append(w - f)
    agg = {"V1": lambda v: float(np.mean(v)), "V2": lambda v: float(np.median(v))}[how]
    return {k: agg(v) for k, v in eps.items() if len(v) >= MIN_VARIANT_RACES}


def raw_residual(run: Run, race: Race, par: ParModel, variants: dict, w: float) -> float:
    """馬の 1 走の残差 (秒 / km、clip の前)。遅いほど大。"""
    base = par.base(race)
    if math.isnan(base) or math.isnan(run.sec_per_km):
        return math.nan
    return run.sec_per_km - base - variants.get((race.ymd, race.track, race.surface), 0.0) - w * (run.burden_kg - BASE_WEIGHT_KG)


def fit_weight_effect(races: dict[str, Race], par: ParModel, variants: dict, est_years: tuple[int, ...]) -> dict:
    """W1: 推定期間の走で、同じ馬の中で斤量 1 kg あたりの残差 (秒 / km) を最小二乗で推定する。ハンデ戦は除く。

    係数が 0 以下 (重いほど速い) なら W1 は無効 (`valid` False、呼び出し側は w = 0 = W0 として扱う)。
    """
    check_est_years(est_years)
    by_horse: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in races.values():
        if int(r.ymd[:4]) not in est_years or r.weight_type == HANDICAP:
            continue
        for run in r.runs:
            if run.abnormal in REFUNDED or not run.horse:
                continue
            res = raw_residual(run, r, par, variants, 0.0)
            nu = nuisance(r, par)
            # 外れ値の除外は P3 と同じ座標 (残差 − c − d) で行う (事前登録 §8-4b-3)
            if not (math.isnan(res) or math.isnan(nu)) and abs(res - nu) <= CLIP_SEC_PER_KM:
                by_horse[run.horse].append((run.burden_kg, res))
    xs, ys = [], []
    for obs in by_horse.values():
        if len(obs) < 2:
            continue
        mx = sum(o[0] for o in obs) / len(obs)
        my = sum(o[1] for o in obs) / len(obs)
        xs += [o[0] - mx for o in obs]
        ys += [o[1] - my for o in obs]
    x, y = np.array(xs), np.array(ys)
    w = float(x @ y / (x @ x)) if len(x) and (x @ x) > 0 else math.nan
    return {"w": w, "valid": bool(w > 0), "n_runs": len(x)}


def clip_residual(res: float) -> float:
    if math.isnan(res):
        return res
    return max(-CLIP_SEC_PER_KM, min(CLIP_SEC_PER_KM, res))


def nuisance(race: Race, par: ParModel) -> float:
    """そのレースの局外の補正 c[クラス] + d[年齢の区分] (秒 / km)。年齢の区分が欠損なら NaN。"""
    f = par.fitted(race)
    b = par.base(race)
    return f - b if not (math.isnan(f) or math.isnan(b)) else math.nan


def bounded_residual(run: Run, race: Race, par: ParModel, variants: dict, w: float) -> tuple[float, str]:
    """P3 (改訂 B) を当てた残差と、その状態 ('ok' / 'clipped_slow' / 'clipped_fast' / 'no_time' / 'no_nuisance')。

    残差 − (c + d) を ±3.0 で clip してから (c + d) を戻す。評価値にはクラスの水準が残る (2a)。
    """
    res = raw_residual(run, race, par, variants, w)
    if math.isnan(res):
        return math.nan, "no_time"
    nu = nuisance(race, par)
    if math.isnan(nu):
        return math.nan, "no_nuisance"
    adj = res - nu
    state = "clipped_slow" if adj > CLIP_SEC_PER_KM else ("clipped_fast" if adj < -CLIP_SEC_PER_KM else "ok")
    return clip_residual(adj) + nu, state


def fit_scale(races: dict[str, Race], par: ParModel, variants: dict, w: float, est_years: tuple[int, ...]) -> dict:
    """S2: 推定期間の (芝ダ, 距離の帯) ごとの、馬単位の残差 (clip の後) の SD。"""
    check_est_years(est_years)
    vals: dict[tuple, list[float]] = defaultdict(list)
    for r in races.values():
        if int(r.ymd[:4]) not in est_years:
            continue
        for run in r.runs:
            if run.abnormal in REFUNDED or not run.horse:
                continue
            res, _state = bounded_residual(run, r, par, variants, w)
            if not math.isnan(res):
                vals[(r.surface, dist_band(r.distance))].append(res)
    return {k: float(np.std(v)) for k, v in vals.items() if len(v) >= 2}


@dataclass(frozen=True)
class Spec:
    scale: str      # S1 / S2
    variant: str    # V0 / V1 / V2
    weight: str     # W0 / W1

    @property
    def name(self) -> str:
        return f"{self.scale}{self.variant}{self.weight}"


@dataclass
class RatingTables:
    """ある推定期間で凍結した、評価値の計算に要る物一式。"""
    spec: Spec
    par: ParModel
    variants: dict
    w: float
    weight_fit: dict | None
    scales: dict | None


def fit_tables(races: dict[str, Race], spec: Spec, est_years: tuple[int, ...]) -> RatingTables:
    par = fit_par_model(races, est_years)
    variants = day_variants(races, par, spec.variant)
    weight_fit = None
    w = 0.0
    if spec.weight == "W1":
        weight_fit = fit_weight_effect(races, par, variants, est_years)
        w = weight_fit["w"] if weight_fit["valid"] else 0.0
    scales = fit_scale(races, par, variants, w, est_years) if spec.scale == "S2" else None
    return RatingTables(spec, par, variants, w, weight_fit, scales)


def rate_runs(races: dict[str, Race], tables: RatingTables) -> tuple[dict[str, list[tuple[int, float]]], Counter]:
    """{馬: [(日の通し番号, 評価値)] (日付順)}。評価値は速いほど大。時計・基準の無い走は入れない。

    stats には全体の件数と、clip の監査用の `group|<年>|<クラス>|<年齢の区分>|<rated / clipped_slow / clipped_fast>` を入れる。
    """
    out: dict[str, list[tuple[int, float]]] = defaultdict(list)
    stats: Counter = Counter()
    for r in sorted(races.values(), key=lambda x: x.ymd):
        for run in r.runs:
            if run.abnormal in REFUNDED or not run.horse:
                continue
            res, state = bounded_residual(run, r, tables.par, tables.variants, tables.w)
            if math.isnan(res):
                stats["unrated_runs"] += 1
                if state == "no_nuisance":
                    stats["unrated_no_nuisance"] += 1
                continue
            stats["rated_runs"] += 1
            grp = f"group|{r.ymd[:4]}|{r.cls}|{r.age}"
            stats[f"{grp}|rated"] += 1
            if state != "ok":
                stats[state] += 1
                stats[f"{grp}|{state}"] += 1
            if tables.scales is not None:
                sd = tables.scales.get((r.surface, dist_band(r.distance)))
                if not sd:
                    stats["unrated_no_scale"] += 1
                    continue
                res = res / sd
            out[run.horse].append((run.ordinal, -res))
    return out, stats


# ---------------------------------------------------------------------------------------------------- 成分

def horse_components(history: list[tuple[int, float]], target_ordinal: int) -> dict[str, float]:
    """対象日の 365 日前から前日までの評価値から、last / best3 / trend を作る (rank は別)。"""
    if any(history[i][0] > history[i + 1][0] for i in range(len(history) - 1)):
        raise GroupAError("評価値の履歴が日付順でない (bisect の前提)")
    lo = bisect_left(history, (target_ordinal - WINDOW_DAYS, -math.inf))
    hi = bisect_left(history, (target_ordinal, -math.inf))
    window = history[lo:hi]
    if not window:
        return {"perf_rating_last": math.nan, "perf_rating_best3_365": math.nan, "perf_rating_trend_365": math.nan}
    vals = [v for _, v in window]
    best3 = sorted(vals, reverse=True)[:3]
    trend = math.nan
    if len(window) >= 3:
        x = np.array([d for d, _ in window], dtype=float) / 100.0
        y = np.array(vals)
        x = x - x.mean()
        if (x @ x) > 0:
            trend = float(x @ (y - y.mean()) / (x @ x))
    return {"perf_rating_last": window[-1][1], "perf_rating_best3_365": float(np.mean(best3)),
            "perf_rating_trend_365": trend}


def rank_in_race(values: list[float]) -> list[float]:
    """欠損でない馬だけで順位を付け (1 = 最良、同値は平均順位)、(n − rank + 0.5) / n。欠損は NaN。"""
    valid = [v for v in values if not math.isnan(v)]
    n = len(valid)
    out = []
    for v in values:
        if math.isnan(v):
            out.append(math.nan)
            continue
        better = sum(u > v for u in valid)
        ties = sum(u == v for u in valid)
        rank = better + (ties + 1) / 2.0
        out.append((n - rank + 0.5) / n)
    return out


def target_samples(races: dict[str, Race], years: tuple[int, ...], ratings: dict, counts: Counter) -> list[dict]:
    """対象レースの標本 (選択集合の馬ごとに 1 行)。市場の確率は選択集合の中で正規化し直す (§8-6)。"""
    out = []
    for r in sorted(races.values(), key=lambda x: x.race_id):
        if int(r.ymd[:4]) not in years:
            continue
        counts["target_races_seen"] += 1
        winners = [x for x in r.runs if x.finish == 1]
        if len(winners) != 1:
            counts["drop_dead_heat_or_no_winner"] += 1
            continue
        choice = [x for x in r.runs if x.abnormal not in REFUNDED]
        if any(x.win_odds <= 0 for x in choice):
            counts["drop_runner_without_price"] += 1
            continue
        if not choice or winners[0] not in choice:
            counts["drop_winner_not_in_choice_set"] += 1
            continue
        inv = [1.0 / x.win_odds for x in choice]
        total = sum(inv)
        target_ord = day_ordinal(r.ymd)
        rows = []
        for x, q in zip(choice, inv):
            comp = horse_components(ratings.get(x.horse, []) if x.horse else [], target_ord)
            rows.append({"race_id": r.race_id, "year": int(r.ymd[:4]), "horse_num": x.horse_num, "horse": x.horse,
                         "won": 1 if x.finish == 1 else 0, "p_market": q / total, **comp})
        for row, rk in zip(rows, rank_in_race([row["perf_rating_best3_365"] for row in rows])):
            row["perf_rating_rank_in_race"] = rk
        out.extend(rows)
        counts["target_races_used"] += 1
    return out


# ---------------------------------------------------------------------------------------------------- 標準化・合成・推定

def standardizer(rows: list[dict], cols) -> dict[str, tuple[float, float]]:
    """欠損でない行だけで平均・SD (§8-4 の手順 4)。"""
    out = {}
    for c in cols:
        v = np.array([r[c] for r in rows if not math.isnan(r[c])])
        if len(v) < 2 or not v.std() > 0:
            raise GroupAError(f"{c}: 標準化できない (欠損でない行 {len(v)}、SD {v.std() if len(v) else 'n/a'})")
        out[c] = (float(v.mean()), float(v.std()))
    return out


def apply_standardizer(rows: list[dict], std: dict, suffix: str = "_z") -> None:
    for r in rows:
        for c, (m, s) in std.items():
            r[c + suffix] = 0.0 if math.isnan(r[c]) else (r[c] - m) / s


def clogit_with_se(samples: list[dict], cols: list[str]) -> dict:
    """条件付きロジットの係数と、ヘッセ行列からの SE (選択の基準の z 用。主検定の区間には使わない)。"""
    from predictor.eval_stats import conditional_logit
    beta, ok = conditional_logit(samples, cols, with_status=True)
    if not ok:
        return {"beta": beta, "se": [math.nan] * len(cols), "converged": False, "status": "not_converged"}
    by_race: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_race[s["race_id"]].append(s)
    b = np.array(beta)
    info = np.zeros((len(cols), len(cols)))
    for rows in by_race.values():
        if sum(r["won"] for r in rows) <= 0:
            continue
        X = np.array([[r[c] for c in cols] for r in rows], dtype=float)
        u = X @ b
        u -= u.max()
        p = np.exp(u)
        p /= p.sum()
        info += X.T @ (np.diag(p) - np.outer(p, p)) @ X
    try:
        se = np.sqrt(np.diag(np.linalg.inv(info)))
    except np.linalg.LinAlgError:
        return {"beta": [float(x) for x in b], "se": [math.nan] * len(cols), "converged": True, "status": "singular_information"}
    return {"beta": [float(x) for x in b], "se": [float(x) for x in se], "converged": True, "status": "ok"}


def add_market_logit(rows: list[dict]) -> None:
    for r in rows:
        p = min(max(r["p_market"], 1e-6), 1 - 1e-6)
        r["logit_p_market"] = math.log(p / (1 - p))


def fit_composite(fit_rows: list[dict]) -> dict:
    """学習の行で、市場 + 標準化した 4 成分の条件付きロジットを解き、逆符号の成分は重み 0 (§8-4 の手順 3)。"""
    if any("year" not in r for r in fit_rows):
        raise GroupAError("合成の学習の行に year が無い (主検定の年のガードを通せない)")
    check_est_years(sorted({r["year"] for r in fit_rows}))
    std = standardizer(fit_rows, COMPONENTS)
    apply_standardizer(fit_rows, std)
    cols = ["logit_p_market"] + [c + "_z" for c in COMPONENTS]
    res = clogit_with_se(fit_rows, cols)
    if not res["converged"]:
        raise GroupAError("合成の条件付きロジットが収束しない")
    raw_w = dict(zip(COMPONENTS, res["beta"][1:]))
    weights = {c: (w if (not math.isnan(w) and w > 0) else 0.0) for c, w in raw_w.items()}
    if not any(w > 0 for w in weights.values()):
        raise GroupAError(f"全成分が逆符号 (重みが全部 0): {raw_w}。S は定数になり、主検定の係数は識別できない")
    for r in fit_rows:
        r["S_raw"] = sum(weights[c] * r[c + "_z"] for c in COMPONENTS)
        r["S_missing"] = all(math.isnan(r[c]) for c in COMPONENTS)
    s_vals = np.array([r["S_raw"] for r in fit_rows if not r["S_missing"]])
    if len(s_vals) < 2 or not s_vals.std() > 0:
        raise GroupAError("S を標準化できない (欠損でない行が足りないか SD が 0)")
    s_std = (float(s_vals.mean()), float(s_vals.std()))
    return {"standardizer": std, "raw_weights": raw_w, "weights": weights, "S_standardizer": s_std,
            "fit_clogit": res, "zeroed": [c for c, w in raw_w.items() if weights[c] == 0.0]}


def apply_composite(rows: list[dict], comp: dict) -> None:
    apply_standardizer(rows, comp["standardizer"])
    m, s = comp["S_standardizer"]
    for r in rows:
        missing = all(math.isnan(r[c]) for c in COMPONENTS)
        raw = sum(comp["weights"][c] * r[c + "_z"] for c in COMPONENTS)
        r["S"] = 0.0 if missing else (raw - m) / s


# ---------------------------------------------------------------------------------------------------- 凍結物と来歴

PAYLOAD_VERSION = "group_a_payload_v1"
SPEC_AXES = {"scale": ("S1", "S2"), "variant": ("V0", "V1", "V2"), "weight": ("W0", "W1")}


def current_constants() -> dict:
    return {"WINDOW_DAYS": WINDOW_DAYS, "MIN_CELL_RACES": MIN_CELL_RACES, "MIN_VARIANT_RACES": MIN_VARIANT_RACES,
            "CLIP_SEC_PER_KM": CLIP_SEC_PER_KM, "BASE_WEIGHT_KG": BASE_WEIGHT_KG, "DIST_BANDS": list(DIST_BANDS),
            "REF_CLASS": REF_CLASS, "REF_AGE": REF_AGE, "OBSTACLE_FROM": OBSTACLE_FROM, "REFUNDED": sorted(REFUNDED)}


def freeze_payload(tables: RatingTables, comp: dict) -> dict:
    """評価値と S の計算に要る物を JSON にできる形で書き出す (§8-4 の手順 6)。馬場差は凍結しない (その日のレースから作る)。"""
    par = tables.par
    return {
        "payload_version": PAYLOAD_VERSION, "spec": tables.spec.name, "est_years": list(par.est_years),
        "constants": current_constants(),
        "par": {"cell_level": [[list(c), list(lv) if lv is not None else None] for c, lv in sorted(par.cell_level.items(), key=str)],
                "coef": par.coef, "columns": par.columns, "counts": par.counts},
        "w": tables.w, "weight_fit": tables.weight_fit,
        "scales": [[list(k), v] for k, v in sorted(tables.scales.items())] if tables.scales is not None else None,
        "composite": {"standardizer": {c: list(v) for c, v in comp["standardizer"].items()},
                      "raw_weights": comp["raw_weights"], "weights": comp["weights"], "zeroed": comp["zeroed"],
                      "S_standardizer": list(comp["S_standardizer"])},
    }


def tables_from_payload(payload: dict, races: dict[str, Race]) -> tuple[RatingTables, dict]:
    """凍結物を読み込む。補正テーブル・斤量・尺度・合成は再推定しない。馬場差だけ、読み込んだレースから凍結した模型で作る。"""
    if payload.get("payload_version") != PAYLOAD_VERSION:
        raise GroupAError(f"凍結物の版が違う: {payload.get('payload_version')!r} (この code は {PAYLOAD_VERSION})")
    if payload.get("constants") != current_constants():
        raise GroupAError(f"凍結物の定数が今の code と違う: {payload.get('constants')} vs {current_constants()}")
    spec_name = payload["spec"]
    spec = Spec(spec_name[:2], spec_name[2:4], spec_name[4:6])
    if (len(spec_name) != 6 or spec.scale not in SPEC_AXES["scale"] or spec.variant not in SPEC_AXES["variant"]
            or spec.weight not in SPEC_AXES["weight"]):
        raise GroupAError(f"凍結物の候補の名前が不正: {spec_name!r}")
    p = payload["par"]
    cell_level = {tuple(int(x) if i == 2 else x for i, x in enumerate(c)):
                  (tuple(int(x) if (i == 2 and str(x).isdigit()) else x for i, x in enumerate(lv)) if lv is not None else None)
                  for c, lv in p["cell_level"]}
    par = ParModel(tuple(payload["est_years"]), cell_level, dict(p["coef"]), list(p["columns"]), dict(p["counts"]))
    variants = day_variants(races, par, spec.variant)
    scales = {(k[0], int(k[1])): v for k, v in payload["scales"]} if payload["scales"] is not None else None
    c = payload["composite"]
    comp = {"standardizer": {k: tuple(v) for k, v in c["standardizer"].items()}, "raw_weights": c["raw_weights"],
            "weights": c["weights"], "zeroed": c["zeroed"], "S_standardizer": tuple(c["S_standardizer"])}
    return RatingTables(spec, par, variants, float(payload["w"]), payload["weight_fit"], scales), comp


DEPENDENCIES = ("scripts/group_a.py", "scripts/group_a_explore.py", "scripts/group_a_power.py", "scripts/research_window.py",
                "scripts/group_a_run.py", "scripts/group_a_stats.py",
                "predictor/eval_stats.py", "config.py", "db.py",
                "data/backtest/group_a_class_20261005/class_table.csv", "docs/PHASE05_5_PREREG.md",
                "docs/PHASE05_5_EXPLORATION.md")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _is_own_output(status_line: str, own_output: str | None) -> bool:
    path = status_line[3:].strip().strip('"').replace("\\", "/")
    return bool(own_output) and path.startswith(own_output.rstrip("/") + "/")


def _dependency_hashes(files) -> dict:
    missing = [f for f in files if not (ROOT / f).exists()]
    if missing:
        raise GroupAError(f"来歴の依存ファイルが無い: {missing}")
    return {f: sha256_file(ROOT / f) for f in files}


def provenance(db_path, argv: list[str] | None = None, extra_files: tuple[str, ...] = (),
               own_output: str | None = None) -> dict:
    """成果物の来歴を 1 か所で作る: HEAD・全ツリーの未コミットの変更・依存ファイルの sha256・版・DB の状態・argv。

    `own_output` (その実行が書く出力先、repo からの相対) の未追跡・変更は `git_dirty` の判定から外す (生の一覧は `git_status` に残す)。
    """
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    dbp = Path(db_path)
    st = dbp.stat() if dbp.exists() else None
    return {
        "git_sha": head.stdout.strip() if head.returncode == 0 else "unknown",
        "git_dirty": (any(not _is_own_output(line, own_output) for line in status.stdout.splitlines() if line.strip())
                      if status.returncode == 0 else None),
        "own_output": own_output,
        "git_status": status.stdout.strip().splitlines() if status.returncode == 0 else None,
        "files_sha256": _dependency_hashes(DEPENDENCIES + tuple(extra_files)),
        "python": platform.python_version(), "numpy": np.__version__, "argv": list(argv if argv is not None else sys.argv),
        "db": {"path": str(dbp), "bytes": st.st_size if st else None,
               "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds") if st else None},
    }

