"""過去走データから 1 頭分の特徴量を引き出すクエリ群。

DB の races / horse_races に対して、各馬の血統登録番号や騎手・調教師コードを
キーに過去レコードを集計する。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


def _cached(cache: dict | None, key: tuple, loader):
    if cache is None:
        return loader()
    if key not in cache:
        cache[key] = loader()
    return cache[key]


def _date_key(year: str, month_day: str) -> str:
    return (year or "0000") + (month_day or "0000")


def _days_between(date_a: str, date_b: str) -> int | None:
    try:
        a = datetime.strptime(date_a, "%Y%m%d")
        b = datetime.strptime(date_b, "%Y%m%d")
    except ValueError:
        return None
    return (b - a).days


def _surface_family(track_type_code: str | None) -> str:
    try:
        n = int((track_type_code or "").strip())
    except ValueError:
        return "other"
    if 10 <= n <= 22:
        return "turf"
    if 23 <= n <= 29:
        return "dirt"
    return "other"


def _race_condition_code(race: dict) -> str:
    family = _surface_family(race.get("track_type_code"))
    key = "turf_condition" if family == "turf" else "dirt_condition"
    code = (race.get(key) or "").strip()
    return code if code and code != "0" else ""


def _distance_bucket(distance: int | None) -> str:
    d = distance or 0
    if d <= 1400:
        return "sprint"
    if d <= 1800:
        return "mile"
    if d <= 2200:
        return "middle"
    return "long"


def _race_level(grade_code: str | None, race_symbol_code: str | None) -> int:
    grade = (grade_code or "").strip()
    if grade == "A":
        return 8
    if grade == "B":
        return 7
    if grade == "C":
        return 6
    if grade in ("D", "F", "G", "H", "I", "L"):
        return 5

    symbol = (race_symbol_code or "").strip()
    prefix = symbol[:1]
    suffix = symbol[-2:] if len(symbol) >= 2 else ""
    if prefix in ("N", "M"):
        return 5
    if suffix in ("24", "04"):
        return 4
    if suffix in ("23", "03"):
        return 3
    if suffix in ("22", "02"):
        return 2
    return 1


def _gate_zone(horse_num: str | int | None, starter_count: int | None) -> str:
    try:
        num = int(str(horse_num or "").strip())
        starters = int(starter_count or 0)
    except ValueError:
        return ""
    if num <= 0 or starters <= 0:
        return ""
    pos = num / starters
    if pos <= 1 / 3:
        return "inner"
    if pos <= 2 / 3:
        return "middle"
    return "outer"


def grade_class_close_loss(
    conn: sqlite3.Connection,
    blood_register_num: str,
    before_date: str,
    current_level: int,
    limit: int = 30,
) -> tuple[int, int]:
    """同格以上 (≥ current_level) のレースで「内容の良い敗戦」を数える。

    重賞では着順 (4 着、6 着など) が悪くても、勝ち馬から **僅差** で敗れていれば
    地力は高い。ルールベース予想で重賞の精度を上げる主要シグナル。

    返値: (close_loss, midfield_close)
        close_loss     : 着外 (≥4 着) かつ winner +0.5 秒以内 → 「展開負け / 不利
                          を受けた可能性」のニュアンス
        midfield_close : 中位 (4-7 着) かつ winner +0.3 秒以内 → 強相手にコンマ差
    """
    if (
        not blood_register_num
        or blood_register_num == "0" * 10
        or current_level < 5
    ):
        return 0, 0

    rows = conn.execute(
        """
        SELECT
            r.grade_code, r.race_symbol_code,
            hr.confirmed_order, hr.finish_time,
            (SELECT MIN(hr2.finish_time)
               FROM horse_races hr2
              WHERE hr2.race_year      = hr.race_year
                AND hr2.race_month_day = hr.race_month_day
                AND hr2.track_code     = hr.track_code
                AND hr2.kaiji          = hr.kaiji
                AND hr2.nichiji        = hr.nichiji
                AND hr2.race_num       = hr.race_num
                AND hr2.confirmed_order = 1
                AND hr2.finish_time    > 0
            ) AS winner_time
        FROM horse_races hr
        JOIN races r
          ON hr.race_year     = r.race_year
         AND hr.race_month_day = r.race_month_day
         AND hr.track_code    = r.track_code
         AND hr.kaiji         = r.kaiji
         AND hr.nichiji       = r.nichiji
         AND hr.race_num      = r.race_num
        WHERE hr.blood_register_num = ?
          AND (hr.race_year || hr.race_month_day) < ?
          AND hr.confirmed_order > 0
          AND hr.finish_time     > 0
        ORDER BY (hr.race_year || hr.race_month_day) DESC
        LIMIT ?
        """,
        (blood_register_num, before_date, limit),
    ).fetchall()

    close_loss = 0
    midfield_close = 0
    for r in rows:
        past_level = _race_level(r["grade_code"], r["race_symbol_code"])
        if past_level < current_level:
            continue
        finish_time = r["finish_time"] or 0
        winner_time = r["winner_time"] or 0
        if not winner_time:
            continue
        margin = finish_time - winner_time  # 0.1 秒単位
        order = r["confirmed_order"]
        if order >= 4 and 0 < margin <= 5:
            close_loss += 1
        if 4 <= order <= 7 and 0 < margin <= 3:
            midfield_close += 1
    return close_loss, midfield_close


def horse_past_runs(
    conn: sqlite3.Connection,
    blood_register_num: str,
    before_date: str,
    limit: int = 12,
) -> list[dict]:
    """指定馬の過去走（指定日より前、最新順）。confirmed_order > 0 に絞る。"""
    if not blood_register_num or blood_register_num == "0" * 10:
        return []
    rows = conn.execute(
        """
        SELECT
            hr.confirmed_order, hr.finish_time, hr.final_3f,
            hr.win_popularity, hr.win_odds,
            hr.leg_quality_code,
            hr.burden_weight, hr.horse_weight, hr.weight_change_diff,
            r.distance, r.track_code, r.track_type_code,
            r.race_year, r.race_month_day, r.grade_code, r.race_symbol_code,
            r.starter_count, r.weather_code, r.turf_condition, r.dirt_condition
        FROM horse_races hr
        JOIN races r
          ON hr.race_year = r.race_year
         AND hr.race_month_day = r.race_month_day
         AND hr.track_code = r.track_code
         AND hr.kaiji = r.kaiji
         AND hr.nichiji = r.nichiji
         AND hr.race_num = r.race_num
        WHERE hr.blood_register_num = ?
          AND (hr.race_year || hr.race_month_day) < ?
          AND hr.confirmed_order > 0
        ORDER BY (hr.race_year || hr.race_month_day) DESC
        LIMIT ?
        """,
        (blood_register_num, before_date, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def estimate_leg_code(past: list[dict], limit: int = 5) -> tuple[str, int]:
    counts: dict[str, int] = {}
    for p in past[:limit]:
        leg = (p.get("leg_quality_code") or "").strip()
        if leg in ("1", "2", "3", "4"):
            counts[leg] = counts.get(leg, 0) + 1
    if not counts:
        return "", 0
    return max(counts.items(), key=lambda x: (x[1], -int(x[0])))[0], sum(counts.values())


def jockey_winrate(
    conn: sqlite3.Connection,
    jockey_code: str,
    before_date: str,
    sample: int = 100,
) -> tuple[float | None, int]:
    """直近 sample 騎乗の勝率（confirmed_order=1 比率）。"""
    if not jockey_code or jockey_code == "0" * 5:
        return None, 0
    rows = conn.execute(
        """
        SELECT confirmed_order FROM horse_races
        WHERE jockey_code = ?
          AND (race_year || race_month_day) < ?
          AND confirmed_order > 0
        ORDER BY (race_year || race_month_day) DESC
        LIMIT ?
        """,
        (jockey_code, before_date, sample),
    ).fetchall()
    if not rows:
        return None, 0
    wins = sum(1 for r in rows if r[0] == 1)
    return wins / len(rows), len(rows)


def trainer_winrate(
    conn: sqlite3.Connection,
    trainer_code: str,
    before_date: str,
    sample: int = 100,
) -> tuple[float | None, int]:
    if not trainer_code or trainer_code == "0" * 5:
        return None, 0
    rows = conn.execute(
        """
        SELECT confirmed_order FROM horse_races
        WHERE trainer_code = ?
          AND (race_year || race_month_day) < ?
          AND confirmed_order > 0
        ORDER BY (race_year || race_month_day) DESC
        LIMIT ?
        """,
        (trainer_code, before_date, sample),
    ).fetchall()
    if not rows:
        return None, 0
    wins = sum(1 for r in rows if r[0] == 1)
    return wins / len(rows), len(rows)


def same_day_track_bias(conn: sqlite3.Connection, horse: dict, race: dict) -> tuple[bool, int]:
    leg = (horse.get("leg_quality_code") or "").strip()
    if not leg or not race.get("start_time"):
        return False, 0
    rows = conn.execute(
        """
        SELECT hr.leg_quality_code
        FROM horse_races hr
        JOIN races r
          ON hr.race_year = r.race_year
         AND hr.race_month_day = r.race_month_day
         AND hr.track_code = r.track_code
         AND hr.kaiji = r.kaiji
         AND hr.nichiji = r.nichiji
         AND hr.race_num = r.race_num
        WHERE hr.race_year=? AND hr.race_month_day=? AND hr.track_code=?
          AND r.track_type_code=? AND r.start_time < ?
          AND hr.confirmed_order BETWEEN 1 AND 3
        """,
        (
            race.get("race_year"), race.get("race_month_day"), race.get("track_code"),
            race.get("track_type_code"), race.get("start_time"),
        ),
    ).fetchall()
    if len(rows) < 6:
        return False, len(rows)
    hits = sum(1 for r in rows if (r[0] or "").strip() == leg)
    return hits / len(rows) >= 0.45, len(rows)


def same_day_track_bias_detail(conn: sqlite3.Connection, horse: dict, race: dict) -> tuple[int, int, str]:
    leg = (horse.get("leg_quality_code") or "").strip()
    if not leg or not race.get("start_time"):
        return 0, 0, ""
    family = _surface_family(race.get("track_type_code"))
    if family == "turf":
        surface_sql = "CAST(r.track_type_code AS INTEGER) BETWEEN 10 AND 22"
    elif family == "dirt":
        surface_sql = "CAST(r.track_type_code AS INTEGER) BETWEEN 23 AND 29"
    else:
        surface_sql = "r.track_type_code = ?"
    params = [
        race.get("race_year"), race.get("race_month_day"), race.get("track_code"),
        race.get("start_time"),
    ]
    if family == "other":
        params.insert(3, race.get("track_type_code"))
    rows = conn.execute(
        f"""
        SELECT hr.leg_quality_code
        FROM horse_races hr
        JOIN races r
          ON hr.race_year = r.race_year
         AND hr.race_month_day = r.race_month_day
         AND hr.track_code = r.track_code
         AND hr.kaiji = r.kaiji
         AND hr.nichiji = r.nichiji
         AND hr.race_num = r.race_num
        WHERE hr.race_year=? AND hr.race_month_day=? AND hr.track_code=?
          AND {surface_sql} AND r.start_time < ?
          AND hr.confirmed_order BETWEEN 1 AND 3
        """,
        tuple(params),
    ).fetchall()
    n = len(rows)
    if n < 12:
        return 0, n, ""
    hits = sum(1 for r in rows if (r[0] or "").strip() == leg)
    hit_rate = hits / n
    counts: dict[str, int] = {}
    for r in rows:
        k = (r[0] or "").strip()
        if k:
            counts[k] = counts.get(k, 0) + 1
    leader_rate = max(counts.values()) / n if counts else 0
    score = 0
    if hit_rate >= 0.50:
        score = 5
    elif hit_rate >= 0.30:
        score = 2
    elif leader_rate >= 0.50 and hit_rate <= 0.15:
        score = -3
    note = f"当日脚質傾向{hit_rate * 100:.0f}%({n}件)" if score else ""
    return score, n, note


def same_day_gate_bias_detail(conn: sqlite3.Connection, horse: dict, race: dict) -> tuple[int, int, str]:
    current_zone = _gate_zone(horse.get("horse_num"), race.get("starter_count"))
    if not current_zone or not race.get("start_time"):
        return 0, 0, ""
    family = _surface_family(race.get("track_type_code"))
    if family == "turf":
        surface_sql = "CAST(r.track_type_code AS INTEGER) BETWEEN 10 AND 22"
    elif family == "dirt":
        surface_sql = "CAST(r.track_type_code AS INTEGER) BETWEEN 23 AND 29"
    else:
        surface_sql = "r.track_type_code = ?"
    params = [
        race.get("race_year"), race.get("race_month_day"), race.get("track_code"),
        race.get("start_time"),
    ]
    if family == "other":
        params.insert(3, race.get("track_type_code"))
    rows = conn.execute(
        f"""
        SELECT hr.horse_num, r.starter_count
        FROM horse_races hr
        JOIN races r
          ON hr.race_year = r.race_year
         AND hr.race_month_day = r.race_month_day
         AND hr.track_code = r.track_code
         AND hr.kaiji = r.kaiji
         AND hr.nichiji = r.nichiji
         AND hr.race_num = r.race_num
        WHERE hr.race_year=? AND hr.race_month_day=? AND hr.track_code=?
          AND {surface_sql} AND r.start_time < ?
          AND hr.confirmed_order BETWEEN 1 AND 3
        """,
        tuple(params),
    ).fetchall()
    zones = [_gate_zone(r[0], r[1]) for r in rows]
    zones = [z for z in zones if z]
    n = len(zones)
    if n < 9:
        return 0, n, ""
    hits = sum(1 for z in zones if z == current_zone)
    hit_rate = hits / n
    counts: dict[str, int] = {}
    for z in zones:
        counts[z] = counts.get(z, 0) + 1
    leader_rate = max(counts.values()) / n if counts else 0
    score = 0
    if hit_rate >= 0.55:
        score = 3
    elif hit_rate >= 0.42:
        score = 1
    elif leader_rate >= 0.58 and hit_rate <= 0.12:
        score = -2
    names = {"inner": "内", "middle": "中", "outer": "外"}
    note = f"当日{names.get(current_zone, current_zone)}有利{hit_rate * 100:.0f}%({n}件)" if score else ""
    return score, n, note


def sire_surface_stats(conn: sqlite3.Connection, horse: dict, race: dict, before_date: str) -> tuple[float | None, int]:
    blood = horse.get("blood_register_num", "")
    if not blood:
        return None, 0
    sire = conn.execute(
        "SELECT sire_breeding_num FROM horse_masters WHERE blood_register_num=?",
        (blood,),
    ).fetchone()
    if not sire or not sire[0]:
        return None, 0
    family = _surface_family(race.get("track_type_code"))
    if family == "turf":
        surface_sql = "CAST(r.track_type_code AS INTEGER) BETWEEN 10 AND 22"
        params = (sire[0], blood, before_date)
    elif family == "dirt":
        surface_sql = "CAST(r.track_type_code AS INTEGER) BETWEEN 23 AND 29"
        params = (sire[0], blood, before_date)
    else:
        surface_sql = "r.track_type_code = ?"
        params = (sire[0], blood, before_date, race.get("track_type_code"))
    rows = conn.execute(
        """
        SELECT hr.confirmed_order
        FROM horse_races hr
        JOIN horse_masters hm ON hm.blood_register_num = hr.blood_register_num
        JOIN races r
          ON hr.race_year = r.race_year
         AND hr.race_month_day = r.race_month_day
         AND hr.track_code = r.track_code
         AND hr.kaiji = r.kaiji
         AND hr.nichiji = r.nichiji
         AND hr.race_num = r.race_num
        WHERE hm.sire_breeding_num = ?
          AND hr.blood_register_num != ?
          AND (hr.race_year || hr.race_month_day) < ?
          AND """ + surface_sql + """
          AND hr.confirmed_order > 0
        ORDER BY (hr.race_year || hr.race_month_day) DESC
        LIMIT 120
        """,
        params,
    ).fetchall()
    if not rows:
        return None, 0
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    return top3 / len(rows), len(rows)


def bloodline_stats(
    conn: sqlite3.Connection,
    horse: dict,
    race: dict,
    before_date: str,
    ancestor_column: str,
    scope: str,
    cache: dict | None = None,
) -> tuple[float | None, int]:
    blood = horse.get("blood_register_num", "")
    if not blood:
        return None, 0
    if ancestor_column not in ("sire_breeding_num", "dam_sire_breeding_num"):
        return None, 0
    ancestor = _cached(
        cache,
        ("ancestor", ancestor_column, blood),
        lambda: conn.execute(
            f"SELECT {ancestor_column} FROM horse_masters WHERE blood_register_num=?",
            (blood,),
        ).fetchone(),
    )
    if not ancestor or not ancestor[0]:
        return None, 0
    ancestor_id = ancestor[0]

    family = _surface_family(race.get("track_type_code"))
    bucket = _distance_bucket(race.get("distance"))
    exact_type = race.get("track_type_code") if family == "other" else ""
    stat_key = ("bloodline_stats", ancestor_column, ancestor_id, before_date, scope, family, bucket, exact_type)

    def load_stat() -> tuple[float | None, int]:
        return _bloodline_stats_uncached(
            conn,
            ancestor_id,
            race,
            before_date,
            ancestor_column,
            scope,
        )

    return _cached(cache, stat_key, load_stat)


def _bloodline_stats_uncached(
    conn: sqlite3.Connection,
    ancestor_id: str,
    race: dict,
    before_date: str,
    ancestor_column: str,
    scope: str,
) -> tuple[float | None, int]:
    clauses = [
        f"hm.{ancestor_column} = ?",
        "(hr.race_year || hr.race_month_day) < ?",
        "hr.confirmed_order > 0",
    ]
    params: list[object] = [ancestor_id, before_date]

    family = _surface_family(race.get("track_type_code"))
    if family == "turf":
        clauses.append("CAST(r.track_type_code AS INTEGER) BETWEEN 10 AND 22")
    elif family == "dirt":
        clauses.append("CAST(r.track_type_code AS INTEGER) BETWEEN 23 AND 29")
    else:
        clauses.append("r.track_type_code = ?")
        params.append(race.get("track_type_code"))

    if scope == "distance":
        bucket = _distance_bucket(race.get("distance"))
        if bucket == "sprint":
            clauses.append("r.distance <= 1400")
        elif bucket == "mile":
            clauses.append("r.distance BETWEEN 1401 AND 1800")
        elif bucket == "middle":
            clauses.append("r.distance BETWEEN 1801 AND 2200")
        else:
            clauses.append("r.distance >= 2201")
    elif scope == "going":
        going = _race_condition_code(race)
        if not going:
            return None, 0
        if family == "turf":
            clauses.append("r.turf_condition = ?")
        else:
            clauses.append("r.dirt_condition = ?")
        params.append(going)

    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT hr.confirmed_order
        FROM horse_races hr
        JOIN horse_masters hm ON hm.blood_register_num = hr.blood_register_num
        JOIN races r
          ON hr.race_year = r.race_year
         AND hr.race_month_day = r.race_month_day
         AND hr.track_code = r.track_code
         AND hr.kaiji = r.kaiji
         AND hr.nichiji = r.nichiji
         AND hr.race_num = r.race_num
        WHERE {where}
        ORDER BY (hr.race_year || hr.race_month_day) DESC
        LIMIT 160
        """,
        tuple(params),
    ).fetchall()
    if not rows:
        return None, 0
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    return top3 / len(rows), len(rows)


def compute_features(
    conn: sqlite3.Connection,
    horse: dict,
    race: dict,
    cache: dict | None = None,
) -> dict:
    """1 頭・1 レース分の特徴量を計算。"""
    before = _date_key(race.get("race_year"), race.get("race_month_day"))
    blood = horse.get("blood_register_num", "")
    past = _cached(
        cache,
        ("past", blood, before, 12),
        lambda: horse_past_runs(conn, blood, before),
    )

    feat: dict = {
        "past_count": len(past),
        "recent_avg_finish": None,
        "recent_avg_finish_rate": None,
        "recent_avg_starters": None,
        "recent_best_finish": None,
        "recent_top3_count": 0,
        "recent_win_count": 0,
        "last_finish": None,
        "days_since_last": None,
        "burden_delta": None,
        "current_starter_count": int(race.get("starter_count") or 0),
        "current_race_level": _race_level(race.get("grade_code"), race.get("race_symbol_code")),
        "current_distance": int(race.get("distance") or 0),
        "current_bucket": _distance_bucket(race.get("distance") or 0),
        "current_surface_family": _surface_family(race.get("track_type_code")),
        "current_going": _race_condition_code(race),
        "best_top3_race_level": 0,
        "same_bucket_runs": 0,
        "same_bucket_top3": 0,
        "same_bucket_wins": 0,
        "leg_code": (horse.get("leg_quality_code") or "").strip(),
        "raw_leg_code": (horse.get("leg_quality_code") or "").strip(),
        "estimated_leg_code": "",
        "estimated_leg_samples": 0,
        "leg_quality_available": bool((horse.get("leg_quality_code") or "").strip()),
        "same_day_bias_available": False,
        "class_level_runs": 0,
        "class_level_wins": 0,
        "class_level_top3": 0,
        "class_condition_top3": 0,
        "class_rise_points": 0,
        "class_drop_points": 0,
        "high_grade_close_loss": 0,
        "high_grade_midfield_close": 0,
        "recent_trend_delta": None,
        "same_track_type_runs": 0,
        "same_track_type_wins": 0,
        "same_track_type_top3": 0,
        "same_distance_runs": 0,
        "same_distance_top3": 0,
        "same_course_runs": 0,
        "same_course_wins": 0,
        "same_course_top3": 0,
        "same_course_distance_runs": 0,
        "same_course_distance_top3": 0,
        "same_going_runs": 0,
        "same_going_top3": 0,
        "best_final_3f": None,
        "avg_final_3f": None,
        "best_time_per_100m": None,
        "had_grade_run": False,
        "jockey_win_rate": None,
        "jockey_rides": 0,
        "trainer_win_rate": None,
        "trainer_runs": 0,
        "weight_trend": None,
        "same_day_leg_bias": False,
        "same_day_leg_samples": 0,
        "same_day_bias_score": 0,
        "same_day_bias_note": "",
        "same_day_gate_bias_score": 0,
        "same_day_gate_bias_note": "",
        "sire_surface_top3_rate": None,
        "sire_surface_samples": 0,
        "sire_distance_top3_rate": None,
        "sire_distance_samples": 0,
        "dam_sire_surface_top3_rate": None,
        "dam_sire_surface_samples": 0,
        "dam_sire_distance_top3_rate": None,
        "dam_sire_distance_samples": 0,
        "sire_going_top3_rate": None,
        "sire_going_samples": 0,
        "dam_sire_going_top3_rate": None,
        "dam_sire_going_samples": 0,
        "bloodline_data_available": False,
    }

    if past:
        estimated_leg, estimated_leg_samples = estimate_leg_code(past)
        feat["estimated_leg_code"] = estimated_leg
        feat["estimated_leg_samples"] = estimated_leg_samples
        if not feat["leg_code"] and estimated_leg:
            feat["leg_code"] = estimated_leg
        recent3 = [p for p in past[:3] if p["confirmed_order"] > 0]
        if recent3:
            finishes = [p["confirmed_order"] for p in recent3]
            feat["recent_avg_finish"] = sum(finishes) / len(finishes)
            rates = []
            starters = []
            for p in recent3:
                sc = int(p.get("starter_count") or 0)
                if sc > 1 and p["confirmed_order"] > 0:
                    rates.append((p["confirmed_order"] - 1) / (sc - 1))
                    starters.append(sc)
            if rates:
                feat["recent_avg_finish_rate"] = sum(rates) / len(rates)
                feat["recent_avg_starters"] = sum(starters) / len(starters)
            feat["recent_best_finish"] = min(finishes)
            feat["recent_top3_count"] = sum(1 for f in finishes if f in (1, 2, 3))
            feat["recent_win_count"] = sum(1 for f in finishes if f == 1)
            feat["last_finish"] = finishes[0]
            if len(finishes) >= 2:
                feat["recent_trend_delta"] = finishes[0] - finishes[-1]

        last = past[0]
        last_date = (last.get("race_year") or "") + (last.get("race_month_day") or "")
        feat["days_since_last"] = _days_between(last_date, before)
        try:
            current_burden = int(horse.get("burden_weight") or 0)
            last_burden = int(last.get("burden_weight") or 0)
        except (TypeError, ValueError):
            current_burden = 0
            last_burden = 0
        if current_burden and last_burden:
            feat["burden_delta"] = current_burden - last_burden

        race_track_type = (race.get("track_type_code") or "").strip()
        race_distance = race.get("distance") or 0
        race_track = (race.get("track_code") or "").strip()
        race_family = _surface_family(race_track_type)
        race_bucket = _distance_bucket(race_distance)
        race_going = feat["current_going"]
        final3f_values = []
        time_per_100_values = []

        for p in past:
            past_level = _race_level(p.get("grade_code"), p.get("race_symbol_code"))
            if past_level >= feat["current_race_level"]:
                feat["class_level_runs"] += 1
                if p["confirmed_order"] == 1:
                    feat["class_level_wins"] += 1
                if p["confirmed_order"] in (1, 2, 3):
                    feat["class_level_top3"] += 1
                    if (
                        feat["current_race_level"] >= 5
                        and _surface_family(p.get("track_type_code")) == race_family
                        and _distance_bucket(p.get("distance") or 0) == race_bucket
                    ):
                        feat["class_condition_top3"] += 1
            if p["confirmed_order"] in (1, 2, 3):
                feat["best_top3_race_level"] = max(feat["best_top3_race_level"], past_level)
            ptype = (p.get("track_type_code") or "").strip()
            pfamily = _surface_family(ptype)
            if ptype and race_track_type and ptype == race_track_type:
                feat["same_track_type_runs"] += 1
                if p["confirmed_order"] == 1:
                    feat["same_track_type_wins"] += 1
                if p["confirmed_order"] in (1, 2, 3):
                    feat["same_track_type_top3"] += 1

            pdist = p.get("distance") or 0
            if pdist and race_distance and abs(pdist - race_distance) <= 100:
                feat["same_distance_runs"] += 1
                if p["confirmed_order"] in (1, 2, 3):
                    feat["same_distance_top3"] += 1

            # 距離バケット (sprint/mile/middle/long) で同一なら集計。
            # ±100m より広く取れるので、長距離 (2400/2500/3000) のように
            # サンプルが散らばる馬でも適性を捉えやすい。
            if pdist and race_bucket and _distance_bucket(pdist) == race_bucket:
                feat["same_bucket_runs"] += 1
                if p["confirmed_order"] == 1:
                    feat["same_bucket_wins"] += 1
                if p["confirmed_order"] in (1, 2, 3):
                    feat["same_bucket_top3"] += 1

            if (
                race_track
                and (p.get("track_code") or "").strip() == race_track
                and pfamily == race_family
            ):
                feat["same_course_runs"] += 1
                if p["confirmed_order"] == 1:
                    feat["same_course_wins"] += 1
                if p["confirmed_order"] in (1, 2, 3):
                    feat["same_course_top3"] += 1
                if _distance_bucket(pdist) == race_bucket:
                    feat["same_course_distance_runs"] += 1
                    if p["confirmed_order"] in (1, 2, 3):
                        feat["same_course_distance_top3"] += 1

            p_going = _race_condition_code(p)
            if race_going and p_going == race_going and pfamily == race_family:
                feat["same_going_runs"] += 1
                if p["confirmed_order"] in (1, 2, 3):
                    feat["same_going_top3"] += 1

            if pfamily == race_family and _distance_bucket(pdist) == race_bucket:
                if p.get("final_3f"):
                    final3f_values.append(int(p["final_3f"]))
                if p.get("finish_time") and pdist:
                    time_per_100_values.append(float(p["finish_time"]) / float(pdist) * 100.0)

            if (p.get("grade_code") or "").strip() in ("A", "B", "C", "G", "H", "I"):
                feat["had_grade_run"] = True

        if final3f_values:
            feat["best_final_3f"] = min(final3f_values)
            feat["avg_final_3f"] = sum(final3f_values) / len(final3f_values)
        if time_per_100_values:
            feat["best_time_per_100m"] = min(time_per_100_values)

        if feat["best_top3_race_level"]:
            level_gap = feat["current_race_level"] - feat["best_top3_race_level"]
            feat["class_rise_points"] = max(level_gap, 0)
            feat["class_drop_points"] = max(-level_gap, 0)

        # 馬体重トレンド: 直近 3 走の増減差合計（正なら増加傾向）
        try:
            diffs = []
            for p in past[:3]:
                d = (p.get("weight_change_diff") or "").strip()
                sign_field = ""  # weight_change_sign は別カラムだが過去走では取ってない
                if d.isdigit():
                    diffs.append(int(d))
            if diffs:
                feat["weight_trend"] = sum(diffs)
        except Exception:
            pass

    # OP/重賞時のみ「同格以上の接戦敗」を集計 (高コストなので閾値で守る)
    if feat["current_race_level"] >= 5:
        cl, mc = _cached(
            cache,
            ("grade_close_loss", blood, before, feat["current_race_level"]),
            lambda: grade_class_close_loss(
                conn, blood, before, feat["current_race_level"]
            ),
        )
        feat["high_grade_close_loss"] = cl
        feat["high_grade_midfield_close"] = mc

    jockey_code = horse.get("jockey_code", "")
    rate, n = _cached(
        cache,
        ("jockey", jockey_code, before),
        lambda: jockey_winrate(conn, jockey_code, before),
    )
    feat["jockey_win_rate"] = rate
    feat["jockey_rides"] = n

    trainer_code = horse.get("trainer_code", "")
    rate, n = _cached(
        cache,
        ("trainer", trainer_code, before),
        lambda: trainer_winrate(conn, trainer_code, before),
    )
    feat["trainer_win_rate"] = rate
    feat["trainer_runs"] = n

    leg = (horse.get("leg_quality_code") or "").strip()
    race_bias_key = (
        "same_day_bias",
        race.get("race_year"), race.get("race_month_day"), race.get("track_code"),
        race.get("track_type_code"), race.get("start_time"), leg,
    )
    bias, n = _cached(
        cache,
        race_bias_key + ("legacy",),
        lambda: same_day_track_bias(conn, horse, race),
    )
    feat["same_day_leg_bias"] = bias
    feat["same_day_leg_samples"] = n
    score, n, note = _cached(
        cache,
        race_bias_key + ("detail",),
        lambda: same_day_track_bias_detail(conn, horse, race),
    )
    feat["same_day_bias_score"] = score
    feat["same_day_leg_samples"] = max(feat["same_day_leg_samples"], n)
    feat["same_day_bias_note"] = note
    feat["same_day_bias_available"] = n > 0

    gate_score, gate_n, gate_note = _cached(
        cache,
        race_bias_key + ("gate", horse.get("horse_num"), race.get("starter_count")),
        lambda: same_day_gate_bias_detail(conn, horse, race),
    )
    feat["same_day_gate_bias_score"] = gate_score
    feat["same_day_leg_samples"] = max(feat["same_day_leg_samples"], gate_n)
    feat["same_day_gate_bias_note"] = gate_note
    feat["same_day_bias_available"] = feat["same_day_bias_available"] or gate_n > 0

    feat["bloodline_data_available"] = _cached(
        cache,
        ("bloodline_data_available",),
        lambda: bool(conn.execute("SELECT 1 FROM horse_masters LIMIT 1").fetchone()),
    )
    rate, n = bloodline_stats(conn, horse, race, before, "sire_breeding_num", "surface", cache)
    feat["sire_surface_top3_rate"] = rate
    feat["sire_surface_samples"] = n
    rate, n = bloodline_stats(conn, horse, race, before, "sire_breeding_num", "distance", cache)
    feat["sire_distance_top3_rate"] = rate
    feat["sire_distance_samples"] = n
    rate, n = bloodline_stats(conn, horse, race, before, "dam_sire_breeding_num", "surface", cache)
    feat["dam_sire_surface_top3_rate"] = rate
    feat["dam_sire_surface_samples"] = n
    rate, n = bloodline_stats(conn, horse, race, before, "dam_sire_breeding_num", "distance", cache)
    feat["dam_sire_distance_top3_rate"] = rate
    feat["dam_sire_distance_samples"] = n
    rate, n = bloodline_stats(conn, horse, race, before, "sire_breeding_num", "going", cache)
    feat["sire_going_top3_rate"] = rate
    feat["sire_going_samples"] = n
    rate, n = bloodline_stats(conn, horse, race, before, "dam_sire_breeding_num", "going", cache)
    feat["dam_sire_going_top3_rate"] = rate
    feat["dam_sire_going_samples"] = n

    return feat
