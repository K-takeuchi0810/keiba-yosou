"""傾向集計 — コース × ファクター別の成績集計 (SmartRC「傾向集計」踏襲)。

指定コース (競馬場 × 芝ダ × 距離帯) の過去 N 年のレース結果を、各ファクター
(枠番 / 騎手 / 調教師 / 種牡馬 / 父系統 / 母父 / 人気帯) で層別し、
出走数・勝率・複勝率・単勝回収率を Wilson CI 付きで集計する。

bias_scan.py の規律を継承:
- min_n サンプル数ゲート (未満は insufficient として ranked から除外)
- Wilson CI (複勝率の区間) で「たまたま」を区別
- 全数 SQL 1 パス + Python 集計 (predict_race は不要なので高速)

回収率は payouts テーブルがあれば単勝配当から算出 (無ければ None)。
"""

from __future__ import annotations

import sqlite3

from predictor.sire_lines import classify_sire, line_color, line_label
from predictor.stats import wilson_ci
from web.codes import track_name

# ファクター定義: key -> (表示名, 集計単位の説明)
FACTORS = {
    "waku": "枠番",
    "jockey": "騎手",
    "trainer": "調教師",
    "sire": "種牡馬",
    "sire_line": "父系統",
    "dam_sire": "母父",
    "popularity": "人気帯",
}


def surface_of(track_type_code: str | None) -> str:
    """トラックコード -> turf/dirt/jump/other。"""
    try:
        n = int((track_type_code or "").strip())
    except ValueError:
        return "other"
    if 10 <= n <= 22:
        return "turf"
    if 23 <= n <= 29:
        return "dirt"
    if 51 <= n <= 59:
        return "jump"
    return "other"


def distance_bucket_of(distance: int | None) -> str:
    d = distance or 0
    if d <= 0:
        return "unknown"
    if d <= 1400:
        return "sprint"
    if d <= 1800:
        return "mile"
    if d <= 2200:
        return "middle"
    return "long"


def popularity_bucket_of(pop: int | None) -> str:
    p = pop or 0
    if p <= 0:
        return "unknown"
    if p <= 3:
        return "1-3"
    if p <= 6:
        return "4-6"
    if p <= 9:
        return "7-9"
    return "10+"


def _pop_sort_key(v: str) -> tuple:
    order = {"1-3": 0, "4-6": 1, "7-9": 2, "10+": 3, "unknown": 9}
    return (order.get(v, 5), v)


def list_courses(conn, from_date: str, to_date: str, min_races: int = 20) -> list[dict]:
    """集計対象になり得るコース一覧 (competition が min_races 以上あるもの)。"""
    rows = conn.execute(
        """
        SELECT track_code, track_type_code, distance, COUNT(*) AS n
        FROM races
        WHERE (race_year || race_month_day) BETWEEN ? AND ?
          AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
          AND distance > 0
        GROUP BY track_code, track_type_code, distance
        """,
        (from_date, to_date),
    ).fetchall()
    agg: dict[tuple, int] = {}
    for r in rows:
        surf = surface_of(r["track_type_code"])
        key = (r["track_code"], surf, int(r["distance"] or 0))
        agg[key] = agg.get(key, 0) + int(r["n"])
    out = []
    for (track, surf, dist), n in agg.items():
        if n >= min_races:
            out.append({
                "track_code": track, "track_name": track_name(track),
                "surface": surf, "distance": dist, "n_races": n,
            })
    out.sort(key=lambda c: (c["track_code"], c["surface"], c["distance"]))
    return out


def _factor_select(factor: str) -> tuple[str, str]:
    """ファクターの SELECT 式と JOIN 句を返す。"""
    if factor == "waku":
        return "h.waku_num", ""
    if factor == "jockey":
        return "COALESCE(NULLIF(h.jockey_short_name,''), h.jockey_code)", ""
    if factor == "trainer":
        return "COALESCE(NULLIF(h.trainer_short_name,''), h.trainer_code)", ""
    if factor in ("sire", "sire_line"):
        return ("hm.sire_name",
                "LEFT JOIN horse_masters hm ON hm.blood_register_num = h.blood_register_num")
    if factor == "dam_sire":
        return ("hm.dam_sire_name",
                "LEFT JOIN horse_masters hm ON hm.blood_register_num = h.blood_register_num")
    if factor == "popularity":
        return "h.win_popularity", ""
    raise ValueError(f"unknown factor: {factor}")


def aggregate_course(conn, track_code: str, surface: str, distance: int, factor: str,
                     from_date: str, to_date: str, min_n: int = 30) -> dict:
    """1 コース × 1 ファクターの傾向集計。

    戻り: {"cells": [...ranked...], "insufficient": [...], "factor": ..., "total": ...}
    各 cell: value/label/n/wins/top3/win_pct/top3_pct/ci_lo/ci_hi/return_pct/color
    """
    if factor not in FACTORS:
        raise ValueError(f"unknown factor: {factor}")
    if surface not in ("turf", "dirt", "jump", "other"):
        raise ValueError(f"unknown surface: {surface}")

    sel, join = _factor_select(factor)

    # surface は race 単位属性 (track_type_code のコード範囲) なので、対象 race を
    # 先に引いて surface 一致の race キー集合を作り、明細行を後段フィルタする。
    # (同一 track×distance に芝/ダート両方が存在しうるため surface で分離する)
    surf_races = conn.execute(
        """
        SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num, track_type_code
        FROM races
        WHERE (race_year || race_month_day) BETWEEN ? AND ?
          AND track_code = ? AND distance = ?
        """,
        (from_date, to_date, track_code, distance),
    ).fetchall()
    ok_surface = {
        (r["race_year"], r["race_month_day"], r["track_code"], r["kaiji"], r["nichiji"], r["race_num"])
        for r in surf_races if surface_of(r["track_type_code"]) == surface
    }
    rows = _rows_with_key(conn, sel, join, from_date, to_date, track_code, distance)
    rows = [r for r in rows if (r["ry"], r["rmd"], r["tc"], r["kj"], r["nj"], r["rn"]) in ok_surface]

    # 集計
    buckets: dict[str, dict] = {}
    total_n = 0
    for r in rows:
        fval = r["fval"]
        if factor == "popularity":
            value = popularity_bucket_of(fval)
        elif factor == "sire_line":
            value = classify_sire(fval, conn=conn, sire_breeding_num=r["sire_bn"])
        else:
            value = (str(fval).replace("　", "").strip() if fval not in (None, "") else "不明")
        b = buckets.setdefault(value, {"n": 0, "wins": 0, "top3": 0, "ret": 0})
        b["n"] += 1
        ordr = r["ord"] or 0
        if ordr == 1:
            b["wins"] += 1
            b["ret"] += r["tan_payout"] or 0
        if 1 <= ordr <= 3:
            b["top3"] += 1
        total_n += 1

    cells, insufficient = [], []
    for value, b in buckets.items():
        n = b["n"]
        top3_rate = b["top3"] / n if n else 0.0
        lo, hi = wilson_ci(b["top3"], n)
        cell = {
            "value": value,
            "label": line_label(value) if factor == "sire_line" else value,
            "color": line_color(value) if factor == "sire_line" else None,
            "n": n,
            "wins": b["wins"],
            "top3": b["top3"],
            "win_pct": round(b["wins"] / n * 100, 1) if n else 0.0,
            "top3_pct": round(top3_rate * 100, 1),
            "ci_lo": round(lo * 100, 1),
            "ci_hi": round(hi * 100, 1),
            "return_pct": round(b["ret"] / (n * 100) * 100, 1) if n else 0.0,
            "status": "ok" if n >= min_n else "insufficient",
        }
        (cells if n >= min_n else insufficient).append(cell)

    if factor == "waku":
        cells.sort(key=lambda c: (c["value"] or "", ))
    elif factor == "popularity":
        cells.sort(key=lambda c: _pop_sort_key(c["value"]))
    else:
        cells.sort(key=lambda c: c["top3_pct"], reverse=True)
    insufficient.sort(key=lambda c: c["n"], reverse=True)

    return {
        "factor": factor,
        "factor_label": FACTORS[factor],
        "track_code": track_code,
        "track_name": track_name(track_code),
        "surface": surface,
        "distance": distance,
        "from_date": from_date,
        "to_date": to_date,
        "min_n": min_n,
        "total": total_n,
        "cells": cells,
        "insufficient": insufficient,
    }


def today_trends(conn, date: str, factor: str = "waku") -> dict:
    """当日傾向速報 (SmartRC 定点観測)。指定日に確定済みの全 JRA レースを、
    枠番 / 父系統 / 脚質 で層別し「今どの枠・系統・脚質が来ているか」を集計する。

    date は YYYYMMDD。予想 (predict_race) は使わず確定結果のみを見る軽量集計。
    """
    if factor not in ("waku", "sire_line", "leg"):
        raise ValueError(f"today factor must be waku/sire_line/leg: {factor}")
    year, md = date[:4], date[4:]
    rows = conn.execute(
        """
        SELECT h.waku_num AS waku, h.confirmed_order AS ord,
               h.leg_quality_code AS leg,
               hm.sire_name AS sire, hm.sire_breeding_num AS sire_bn,
               r.track_code AS tc, r.race_num AS rn
        FROM races r
        JOIN horse_races h
          ON h.race_year=r.race_year AND h.race_month_day=r.race_month_day
         AND h.track_code=r.track_code AND h.kaiji=r.kaiji
         AND h.nichiji=r.nichiji AND h.race_num=r.race_num
        LEFT JOIN horse_masters hm ON hm.blood_register_num = h.blood_register_num
        WHERE r.race_year=? AND r.race_month_day=?
          AND CAST(r.track_code AS INTEGER) BETWEEN 1 AND 10
          AND h.confirmed_order IS NOT NULL AND h.confirmed_order > 0
        """,
        (year, md),
    ).fetchall()

    buckets: dict[str, dict] = {}
    n_races = set()
    for r in rows:
        n_races.add((r["tc"], r["rn"]))
        if factor == "waku":
            value = (r["waku"] or "?")
        elif factor == "leg":
            value = {"1": "逃げ", "2": "先行", "3": "差し", "4": "追込"}.get(
                (r["leg"] or "").strip(), "不明")
        else:  # sire_line
            value = classify_sire(r["sire"], conn=conn, sire_breeding_num=r["sire_bn"])
        b = buckets.setdefault(value, {"n": 0, "wins": 0, "top3": 0})
        b["n"] += 1
        ordr = r["ord"] or 0
        if ordr == 1:
            b["wins"] += 1
        if 1 <= ordr <= 3:
            b["top3"] += 1

    cells = []
    for value, b in buckets.items():
        n = b["n"]
        cells.append({
            "value": value,
            "label": line_label(value) if factor == "sire_line" else str(value),
            "color": line_color(value) if factor == "sire_line" else None,
            "n": n, "wins": b["wins"], "top3": b["top3"],
            "win_pct": round(b["wins"] / n * 100, 1) if n else 0.0,
            "top3_pct": round(b["top3"] / n * 100, 1) if n else 0.0,
        })
    if factor == "waku":
        cells.sort(key=lambda c: str(c["value"]))
    else:
        cells.sort(key=lambda c: c["top3_pct"], reverse=True)
    return {
        "date": date, "factor": factor,
        "factor_label": {"waku": "枠番", "sire_line": "父系統", "leg": "脚質"}[factor],
        "n_races_done": len(n_races), "cells": cells,
    }


def _rows_with_key(conn, sel: str, join: str, from_date: str, to_date: str,
                   track_code: str, distance: int):
    """race キー付きで factor 値・着順・単勝配当を引く (surface 後段フィルタ用)。"""
    sql = f"""
        SELECT r.race_year AS ry, r.race_month_day AS rmd, r.track_code AS tc,
               r.kaiji AS kj, r.nichiji AS nj, r.race_num AS rn,
               {sel} AS fval,
               h.confirmed_order AS ord,
               hm2.sire_breeding_num AS sire_bn,
               CASE
                 WHEN p.tan_horse_num1 = h.horse_num THEN p.tan_payout1
                 WHEN p.tan_horse_num2 = h.horse_num THEN p.tan_payout2
                 WHEN p.tan_horse_num3 = h.horse_num THEN p.tan_payout3
                 ELSE 0
               END AS tan_payout
        FROM races r
        JOIN horse_races h
          ON h.race_year=r.race_year AND h.race_month_day=r.race_month_day
         AND h.track_code=r.track_code AND h.kaiji=r.kaiji
         AND h.nichiji=r.nichiji AND h.race_num=r.race_num
        {join}
        LEFT JOIN horse_masters hm2 ON hm2.blood_register_num = h.blood_register_num
        LEFT JOIN payouts p
          ON p.race_year=r.race_year AND p.race_month_day=r.race_month_day
         AND p.track_code=r.track_code AND p.kaiji=r.kaiji
         AND p.nichiji=r.nichiji AND p.race_num=r.race_num
        WHERE (r.race_year || r.race_month_day) BETWEEN ? AND ?
          AND r.track_code = ? AND r.distance = ?
          AND h.confirmed_order IS NOT NULL AND h.confirmed_order > 0
    """
    return conn.execute(sql, (from_date, to_date, track_code, distance)).fetchall()
