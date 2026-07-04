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


def recent_corner_stats(
    conn: sqlite3.Connection,
    blood_register_num: str,
    before_date: str,
    limit: int = 6,
) -> tuple[float | None, float | None, int]:
    """直近レースのコーナー通過順位から先行力/差し脚力の代理指標を出す (Phase 4)。

    テンP (SmartRC の先行力指標) に相当する自前シグナル。リーク防止のため
    ``before_date`` 未満の確定レースのみ参照する。

    返値: (avg_4corner_position, avg_position_change, samples)
      - avg_4corner_position : 直近の 4 角通過順位の平均。小さいほど前で運ぶ (先行力)。
      - avg_position_change  : (4角順位 − 確定着順) の平均。正なら 4 角から順位を上げる
                               = 差し脚 (末脚) が効くタイプ。
      - samples              : 有効サンプル数 (corner_order_4 > 0 の過去走数)。

    corner_order_4 が未 ingest (全て 0/NULL) の環境では samples=0, 指標 None を返し、
    呼び出し側は「データ無し」として扱えるので後方互換。
    """
    if not blood_register_num or blood_register_num == "0" * 10:
        return None, None, 0
    rows = conn.execute(
        """
        SELECT corner_order_4, confirmed_order
        FROM horse_races
        WHERE blood_register_num = ?
          AND (race_year || race_month_day) < ?
          AND corner_order_4 IS NOT NULL AND corner_order_4 > 0
          AND confirmed_order IS NOT NULL AND confirmed_order > 0
        ORDER BY (race_year || race_month_day) DESC
        LIMIT ?
        """,
        (blood_register_num, before_date, limit),
    ).fetchall()
    if not rows:
        return None, None, 0
    positions = [r["corner_order_4"] for r in rows]
    changes = [r["corner_order_4"] - r["confirmed_order"] for r in rows]
    n = len(positions)
    return (round(sum(positions) / n, 2), round(sum(changes) / n, 2), n)


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
            hr.horse_num, hr.confirmed_order, hr.finish_time, hr.final_3f,
            hr.win_popularity, hr.win_odds,
            hr.leg_quality_code,
            hr.burden_weight, hr.horse_weight, hr.weight_change_diff,
            r.distance, r.track_code, r.track_type_code,
            r.race_year, r.race_month_day, r.grade_code, r.race_symbol_code,
            r.kaiji, r.nichiji, r.race_num,
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


def relative_race_metrics(conn: sqlite3.Connection, past_run: dict) -> tuple[float | None, int | None]:
    keys = (
        past_run.get("race_year"), past_run.get("race_month_day"), past_run.get("track_code"),
        past_run.get("kaiji"), past_run.get("nichiji"), past_run.get("race_num"),
    )
    if not all(keys):
        return None, None
    rows = conn.execute(
        """
        SELECT horse_num, finish_time, final_3f
        FROM horse_races
        WHERE race_year=? AND race_month_day=? AND track_code=?
          AND kaiji=? AND nichiji=? AND race_num=?
          AND confirmed_order > 0
        """,
        keys,
    ).fetchall()
    finish_times = sorted([r["finish_time"] for r in rows if r["finish_time"]])
    avg_top5 = sum(finish_times[:5]) / min(5, len(finish_times)) if finish_times else None
    time_diff = None
    if avg_top5 and past_run.get("finish_time"):
        time_diff = float(past_run["finish_time"]) - avg_top5
    final3 = [(r["horse_num"], r["final_3f"]) for r in rows if r["final_3f"]]
    final3.sort(key=lambda x: x[1])
    final3_rank = None
    for idx, (num, _value) in enumerate(final3, start=1):
        if str(num) == str(past_run.get("horse_num", "")):
            final3_rank = idx
            break
    return time_diff, final3_rank


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


def _date_minus_days(date_str: str, days: int) -> str:
    """YYYYMMDD 文字列を days 日前にスライド (純 Python、leak 防止用)。"""
    from datetime import datetime, timedelta
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return date_str
    return (dt - timedelta(days=days)).strftime("%Y%m%d")


def _track_recent_stats(
    conn: sqlite3.Connection,
    track_code: str,
    before_date: str,
    days: int,
    cache: dict | None = None,
) -> tuple[float | None, int, float | None]:
    """場の直近 N 日 (race-level) 統計。

    Phase 6 Tier 2.3 (2026-05-16):
    馬場改修 / 開催プロモーション変動に追従するための「直近の場の傾向」を
    captre。同じレース内のすべての horse で同じ値になる (race-level prior)。

    戻り: (top3_rate, sample_count, avg_winning_popularity)
    - top3_rate は 1-3 着の頻度 / 出走馬総数。常に ~3/N ≈ 21%% 付近で固定値
      ぽいが、過去走で着外多発時に値が下がる (= レース荒れている場)
    - avg_winning_popularity は 1 着馬の平均人気。低い = 本命堅め、高い = 荒れ気味
    """
    if not track_code:
        return None, 0, None
    key = ("track_recent", track_code, before_date, days)
    if cache is not None and key in cache:
        return cache[key]
    since_date = _date_minus_days(before_date, days)
    rows = conn.execute(
        """
        SELECT confirmed_order, win_popularity FROM horse_races
         WHERE track_code = ?
           AND (race_year || race_month_day) < ?
           AND (race_year || race_month_day) >= ?
           AND confirmed_order > 0
        """,
        (track_code, before_date, since_date),
    ).fetchall()
    if not rows:
        result = (None, 0, None)
    else:
        n = len(rows)
        top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
        winning_pops = [r[1] for r in rows if r[0] == 1 and r[1] and r[1] > 0]
        avg_win_pop = sum(winning_pops) / len(winning_pops) if winning_pops else None
        result = (top3 / n, n, avg_win_pop)
    if cache is not None:
        cache[key] = result
    return result


def _entity_recent_stats(
    conn: sqlite3.Connection,
    entity_col: str,
    entity_value: str,
    before_date: str,
    days: int,
    cache: dict | None = None,
) -> tuple[float | None, int]:
    """騎手 / 厩舎 / 馬 の直近 N 日 top3 率 (entity-level)。

    entity_col: 'jockey_code' / 'trainer_code' / 'blood_register_num'
    Phase 6 Tier 2.3 (2026-05-16):
    場特性は変動するが、「個人の調子」も時系列的に変動する。
    直近 N 日の成績が現在の調子を最も反映する。
    """
    if not entity_value:
        return None, 0
    # SQL injection safety: entity_col must be from known whitelist
    if entity_col not in ("jockey_code", "trainer_code", "blood_register_num"):
        return None, 0
    key = ("entity_recent", entity_col, entity_value, before_date, days)
    if cache is not None and key in cache:
        return cache[key]
    since_date = _date_minus_days(before_date, days)
    rows = conn.execute(
        f"""
        SELECT confirmed_order FROM horse_races
         WHERE {entity_col} = ?
           AND (race_year || race_month_day) < ?
           AND (race_year || race_month_day) >= ?
           AND confirmed_order > 0
        """,
        (entity_value, before_date, since_date),
    ).fetchall()
    if not rows:
        result = (None, 0)
    else:
        top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
        result = (top3 / len(rows), len(rows))
    if cache is not None:
        cache[key] = result
    return result


def _jockey_track_stats(
    conn: sqlite3.Connection,
    jockey_code: str,
    track_code: str,
    before_date: str,
    cache: dict | None = None,
    limit: int = 300,
) -> tuple[float | None, int]:
    """騎手 × 場 の past 着順 top3 rate と sample 数を返す (Phase 6 Tier 1)。

    リーク防止: race_date < before_date のみ集計。
    """
    if not jockey_code or not track_code:
        return None, 0
    key = ("jockey_track", jockey_code, track_code, before_date, limit)
    if cache is not None and key in cache:
        return cache[key]
    rows = conn.execute(
        """
        SELECT confirmed_order FROM horse_races
         WHERE jockey_code = ? AND track_code = ?
           AND (race_year || race_month_day) < ?
           AND confirmed_order > 0
         ORDER BY (race_year || race_month_day) DESC
         LIMIT ?
        """,
        (jockey_code, track_code, before_date, limit),
    ).fetchall()
    if not rows:
        result = (None, 0)
    else:
        top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
        result = (top3 / len(rows), len(rows))
    if cache is not None:
        cache[key] = result
    return result


def _trainer_track_stats(
    conn: sqlite3.Connection,
    trainer_code: str,
    track_code: str,
    before_date: str,
    cache: dict | None = None,
    limit: int = 300,
) -> tuple[float | None, int]:
    """厩舎 × 場 の past 着順 top3 rate と sample 数 (Phase 6 Tier 1)。"""
    if not trainer_code or not track_code:
        return None, 0
    key = ("trainer_track", trainer_code, track_code, before_date, limit)
    if cache is not None and key in cache:
        return cache[key]
    rows = conn.execute(
        """
        SELECT confirmed_order FROM horse_races
         WHERE trainer_code = ? AND track_code = ?
           AND (race_year || race_month_day) < ?
           AND confirmed_order > 0
         ORDER BY (race_year || race_month_day) DESC
         LIMIT ?
        """,
        (trainer_code, track_code, before_date, limit),
    ).fetchall()
    if not rows:
        result = (None, 0)
    else:
        top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
        result = (top3 / len(rows), len(rows))
    if cache is not None:
        cache[key] = result
    return result


def _horse_track_stats(
    conn: sqlite3.Connection,
    blood_register_num: str,
    track_code: str,
    before_date: str,
    cache: dict | None = None,
    limit: int = 50,
) -> tuple[float | None, int]:
    """馬 × 場 の past 着順 top3 rate と sample 数 (Phase 6 Tier 1)。

    `same_course_*` は同芝・同ダートかつ track 一致時のみカウント。これは
    芝/ダート問わず純粋に「この場経験」全数で集計。
    """
    if not blood_register_num or not track_code:
        return None, 0
    key = ("horse_track", blood_register_num, track_code, before_date, limit)
    if cache is not None and key in cache:
        return cache[key]
    rows = conn.execute(
        """
        SELECT confirmed_order FROM horse_races
         WHERE blood_register_num = ? AND track_code = ?
           AND (race_year || race_month_day) < ?
           AND confirmed_order > 0
         ORDER BY (race_year || race_month_day) DESC
         LIMIT ?
        """,
        (blood_register_num, track_code, before_date, limit),
    ).fetchall()
    if not rows:
        result = (None, 0)
    else:
        top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
        result = (top3 / len(rows), len(rows))
    if cache is not None:
        cache[key] = result
    return result


def _sire_track_stats(
    conn: sqlite3.Connection,
    horse: dict,
    track_code: str,
    before_date: str,
    cache: dict | None = None,
    limit: int = 200,
) -> tuple[float | None, int]:
    """父 × 場 の産駒過去 top3 rate と sample 数 (Phase 6 Tier 1)。"""
    if not track_code:
        return None, 0
    blood = horse.get("blood_register_num", "") or ""
    # 父の breeding_num を horse_masters から
    sire_row = conn.execute(
        "SELECT sire_breeding_num FROM horse_masters WHERE blood_register_num = ?",
        (blood,),
    ).fetchone()
    sire_num = sire_row[0] if sire_row else None
    if not sire_num:
        return None, 0
    key = ("sire_track", sire_num, track_code, before_date, limit)
    if cache is not None and key in cache:
        return cache[key]
    rows = conn.execute(
        """
        SELECT hr.confirmed_order
          FROM horse_races hr
          JOIN horse_masters hm ON hm.blood_register_num = hr.blood_register_num
         WHERE hm.sire_breeding_num = ? AND hr.track_code = ?
           AND (hr.race_year || hr.race_month_day) < ?
           AND hr.confirmed_order > 0
         ORDER BY (hr.race_year || hr.race_month_day) DESC
         LIMIT ?
        """,
        (sire_num, track_code, before_date, limit),
    ).fetchall()
    if not rows:
        result = (None, 0)
    else:
        top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
        result = (top3 / len(rows), len(rows))
    if cache is not None:
        cache[key] = result
    return result


def compute_race_relative_features(
    conn: sqlite3.Connection,
    horses: list[dict],
    race: dict,
    cache: dict | None = None,
) -> dict[str, dict]:
    """Phase 6 Tier 2.4 (2026-05-16): race-internal な相対 features を一括算出。

    各 horse の (個別 value - race 内平均) を計算し、horse_num → {feature: value}
    の dict を返す。compute_features の呼び出しの中で個別に集計するよりも、
    レース全体を見渡してから差分を計算するほうが SQL 1 回で済むので効率的。

    呼び出し側 (predict_race or build_dataset) が:
      rel_map = compute_race_relative_features(conn, horses, race, cache)
      feat = compute_features(...)
      feat.update(rel_map.get(horse_num, {}))

    狙い: SHAP v4 で判明した「馬個体シグナルが弱い」問題に対し、
    既存の absolute 値 (recent_avg_finish_rate 等) と独立な「同レース内
    偏差」を提供。jockey_win_rate との相関が低い純粋な horse signal。
    """
    before = _date_key(race.get("race_year"), race.get("race_month_day"))

    # 各 horse の絶対値を取得 → race 内平均を計算 → 偏差を返す
    horse_recent_top3: list[tuple[str, float | None]] = []
    horse_recent_avg_finish: list[tuple[str, float | None]] = []
    jockey_recent_top3: list[tuple[str, float | None]] = []
    for h in horses:
        hn = h.get("horse_num") or ""
        # 馬の直近 90 日 top3 率
        ht_rate, _ = _entity_recent_stats(
            conn, "blood_register_num",
            h.get("blood_register_num", "") or "",
            before, 90, cache=cache,
        )
        horse_recent_top3.append((hn, ht_rate))
        # 馬の通算 recent_avg_finish_rate 風 (5 走平均)
        blood = h.get("blood_register_num", "") or ""
        if blood:
            past_rows = conn.execute(
                """
                SELECT confirmed_order FROM horse_races
                 WHERE blood_register_num = ?
                   AND (race_year || race_month_day) < ?
                   AND confirmed_order > 0
                 ORDER BY (race_year || race_month_day) DESC LIMIT 5
                """,
                (blood, before),
            ).fetchall()
            if past_rows:
                avg_fin = sum(r[0] for r in past_rows) / len(past_rows)
            else:
                avg_fin = None
        else:
            avg_fin = None
        horse_recent_avg_finish.append((hn, avg_fin))
        # 騎手の直近 90 日 top3 率
        jr_rate, _ = _entity_recent_stats(
            conn, "jockey_code",
            h.get("jockey_code", "") or "",
            before, 90, cache=cache,
        )
        jockey_recent_top3.append((hn, jr_rate))

    def _race_mean(items: list[tuple[str, float | None]]) -> float | None:
        vals = [v for _, v in items if v is not None]
        return (sum(vals) / len(vals)) if vals else None

    h_rt_mean = _race_mean(horse_recent_top3)
    h_af_mean = _race_mean(horse_recent_avg_finish)
    j_rt_mean = _race_mean(jockey_recent_top3)

    result: dict[str, dict] = {}
    for hn, v in horse_recent_top3:
        diff = (v - h_rt_mean) if (v is not None and h_rt_mean is not None) else None
        result.setdefault(hn, {})["horse_recent_top3_rel"] = diff
    for hn, v in horse_recent_avg_finish:
        diff = (v - h_af_mean) if (v is not None and h_af_mean is not None) else None
        result.setdefault(hn, {})["horse_recent_avg_finish_rel"] = diff
    for hn, v in jockey_recent_top3:
        diff = (v - j_rt_mean) if (v is not None and j_rt_mean is not None) else None
        result.setdefault(hn, {})["jockey_recent_top3_rel"] = diff

    return result


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
        "recent_best_finish": None,
        "recent_top3_count": 0,
        "recent_win_count": 0,
        "last_finish": None,
        "days_since_last": None,
        "burden_delta": None,
        "current_race_date": before,
        "current_start_time": (race.get("start_time") or "").strip(),
        "current_starter_count": int(race.get("starter_count") or 0),
        "current_race_level": _race_level(race.get("grade_code"), race.get("race_symbol_code")),
        "current_distance": int(race.get("distance") or 0),
        "current_bucket": _distance_bucket(race.get("distance") or 0),
        "current_track_code": (race.get("track_code") or "").strip(),
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
        "needs_post_race_data": [],
        "class_level_runs": 0,
        "class_level_wins": 0,
        "class_level_top3": 0,
        "class_condition_top3": 0,
        "class_rise_points": 0,
        "class_drop_points": 0,
        "high_grade_close_loss": 0,
        "high_grade_midfield_close": 0,
        "recent_trend_delta": None,
        "recent_4corner_avg_position": None,   # Phase 4: 先行力 (小=前)
        "recent_4corner_position_change": None,  # Phase 4: 4角→着で上げた順位 (正=差し脚)
        "recent_4corner_samples": 0,
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
        "best_relative_time_diff": None,
        "best_final_3f_rank": None,
        "had_grade_run": False,
        "jockey_win_rate": None,
        "jockey_rides": 0,
        "trainer_win_rate": None,
        "trainer_runs": 0,
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
        relative_diffs = []
        final3f_ranks = []

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
                rel_diff, rel_rank = _cached(
                    cache,
                    ("relative_race_metrics", p.get("race_year"), p.get("race_month_day"), p.get("track_code"), p.get("kaiji"), p.get("nichiji"), p.get("race_num")),
                    lambda p=p: relative_race_metrics(conn, p),
                )
                if rel_diff is not None:
                    relative_diffs.append(rel_diff)
                if rel_rank is not None:
                    final3f_ranks.append(rel_rank)

            if (p.get("grade_code") or "").strip() in ("A", "B", "C", "G", "H", "I"):
                feat["had_grade_run"] = True

        if final3f_values:
            feat["best_final_3f"] = min(final3f_values)
            feat["avg_final_3f"] = sum(final3f_values) / len(final3f_values)
        if time_per_100_values:
            feat["best_time_per_100m"] = min(time_per_100_values)
        if relative_diffs:
            feat["best_relative_time_diff"] = min(relative_diffs)
        if final3f_ranks:
            feat["best_final_3f_rank"] = min(final3f_ranks)

        if feat["best_top3_race_level"]:
            level_gap = feat["current_race_level"] - feat["best_top3_race_level"]
            feat["class_rise_points"] = max(level_gap, 0)
            feat["class_drop_points"] = max(-level_gap, 0)

        # weight_trend (馬体重トレンド) は過去計算していたが rules.py で
        # 一度も使われていない dead feature だったため P1-1 で削除済み。
        # 復活させるなら過去走の weight_change_sign を取得する経路から作り直し。
    if not feat["leg_quality_available"] and feat["estimated_leg_code"]:
        feat["needs_post_race_data"].append("leg_quality_code")

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

    # Phase 4: コーナー通過順位ベースの先行力/差し脚指標 (現状 scoring 未配線の dormant)。
    # corner 未 ingest の DB では全馬 samples=0 なので、ホットループで無償 SQL を
    # 毎頭発行しないよう「corner データが 1 件でも存在するか」を run 単位で 1 回だけ判定し、
    # 不在なら以降スキップする (backfill 前の backtest 実行時間を無駄にしない)。
    corner_present = cache.get("_corner_data_present")
    if corner_present is None:
        row = conn.execute(
            "SELECT 1 FROM horse_races WHERE corner_order_4 IS NOT NULL "
            "AND corner_order_4 > 0 LIMIT 1"
        ).fetchone()
        corner_present = row is not None
        cache["_corner_data_present"] = corner_present
    if corner_present:
        c_avg, c_chg, c_n = _cached(
            cache,
            ("corner_stats", blood, before),
            lambda: recent_corner_stats(conn, blood, before),
        )
        feat["recent_4corner_avg_position"] = c_avg
        feat["recent_4corner_position_change"] = c_chg
        feat["recent_4corner_samples"] = c_n

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
    # legacy 呼び出しはサンプル数 (= same_day_bias_available 判定) のため
    # だけに残す。bias / samples は dead feature だったので feat に格納しない。
    _legacy_bias, legacy_n = _cached(
        cache,
        race_bias_key + ("legacy",),
        lambda: same_day_track_bias(conn, horse, race),
    )
    score, n, note = _cached(
        cache,
        race_bias_key + ("detail",),
        lambda: same_day_track_bias_detail(conn, horse, race),
    )
    feat["same_day_bias_score"] = score
    feat["same_day_bias_note"] = note
    feat["same_day_bias_available"] = max(legacy_n, n) > 0

    gate_score, gate_n, gate_note = _cached(
        cache,
        race_bias_key + ("gate", horse.get("horse_num"), race.get("starter_count")),
        lambda: same_day_gate_bias_detail(conn, horse, race),
    )
    feat["same_day_gate_bias_score"] = gate_score
    feat["same_day_gate_bias_note"] = gate_note
    feat["same_day_bias_available"] = feat["same_day_bias_available"] or gate_n > 0
    if not feat["same_day_bias_available"]:
        feat["needs_post_race_data"].append("same_day_bias")

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

    # Phase 1 (2026-05-13): JRA-VAN マイニング予想 (DM/TM) を feature 化。
    # mining_predictions テーブルに record_type='DM' と 'TM' の per-horse 行が
    # 入っている (Phase 1 ingest)。predict 時に当該レース×馬の予測順位 / score
    # を取り出し LightGBM の feature として渡す。SE.mining_predicted_order
    # (既存) は DM の rank と重複だが、SE は 1 値、DM/TM は分離して持つ。
    horse_num = horse.get("horse_num") or ""
    if horse_num and conn is not None:
        rows = conn.execute(
            """
            SELECT record_type, predicted_rank, predicted_time, score
              FROM mining_predictions
             WHERE race_year=? AND race_month_day=? AND track_code=?
               AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=?
            """,
            (
                race.get("race_year"), race.get("race_month_day"), race.get("track_code"),
                race.get("kaiji"), race.get("nichiji"), race.get("race_num"), horse_num,
            ),
        ).fetchall()
        dm_rank = None
        dm_time = None
        tm_rank = None
        tm_score = None
        for r in rows:
            rt = r[0]
            if rt == "DM":
                dm_rank = r[1] if r[1] else None
                dm_time = r[2] if r[2] else None
            elif rt == "TM":
                tm_rank = r[1] if r[1] else None
                tm_score = r[3] if r[3] else None
        feat["mining_dm_rank"] = dm_rank
        feat["mining_dm_time"] = dm_time
        feat["mining_tm_rank"] = tm_rank
        feat["mining_tm_score"] = tm_score
    else:
        feat["mining_dm_rank"] = None
        feat["mining_dm_time"] = None
        feat["mining_tm_rank"] = None
        feat["mining_tm_score"] = None

    # Phase 6 Tier 1 (2026-05-14): 文脈特徴量 (場 × 各エンティティの相性)
    track_code = (race.get("track_code") or "").strip()
    if track_code and conn is not None:
        # 騎手 × 場
        jt_rate, jt_n = _jockey_track_stats(
            conn, horse.get("jockey_code", "") or "", track_code, before, cache=cache,
        )
        feat["jockey_track_top3_rate"] = jt_rate
        feat["jockey_track_samples"] = jt_n
        # 厩舎 × 場
        tt_rate, tt_n = _trainer_track_stats(
            conn, horse.get("trainer_code", "") or "", track_code, before, cache=cache,
        )
        feat["trainer_track_top3_rate"] = tt_rate
        feat["trainer_track_samples"] = tt_n
        # 馬 × 場 (= 芝/ダート問わずこの場での累積成績)
        ht_rate, ht_n = _horse_track_stats(
            conn, horse.get("blood_register_num", "") or "", track_code, before, cache=cache,
        )
        feat["horse_track_top3_rate"] = ht_rate
        feat["horse_track_samples"] = ht_n
        # 父 × 場 (= 父系のこの場での産駒実績)
        st_rate, st_n = _sire_track_stats(
            conn, horse, track_code, before, cache=cache,
        )
        feat["sire_track_top3_rate"] = st_rate
        feat["sire_track_samples"] = st_n
    else:
        feat["jockey_track_top3_rate"] = None
        feat["jockey_track_samples"] = 0
        feat["trainer_track_top3_rate"] = None
        feat["trainer_track_samples"] = 0
        feat["horse_track_top3_rate"] = None
        feat["horse_track_samples"] = 0
        feat["sire_track_top3_rate"] = None
        feat["sire_track_samples"] = 0

    # 季節シグナル (1-12)。LightGBM で月別バイアスを学習させる。
    md = race.get("race_month_day") or ""
    if md and len(md) >= 2:
        try:
            feat["race_month"] = int(md[:2])
        except ValueError:
            feat["race_month"] = 0
    else:
        feat["race_month"] = 0

    # Phase 6 Tier 2.3 (2026-05-16): rolling 統計 (30/90 日)。
    # 「直近の場の傾向」「直近の調子」を時系列適応的に取得。
    # P14 が「直近 trend で robust」だった事実を支える信号として期待。
    if track_code and conn is not None:
        # 場の直近 30 日 (race-level)
        t30_rate, t30_n, t30_pop = _track_recent_stats(conn, track_code, before, 30, cache=cache)
        feat["track_recent_30d_top3_rate"] = t30_rate
        feat["track_recent_30d_samples"] = t30_n
        feat["track_recent_30d_avg_winning_pop"] = t30_pop
        # 場の直近 90 日 (race-level、安定指標)
        t90_rate, t90_n, t90_pop = _track_recent_stats(conn, track_code, before, 90, cache=cache)
        feat["track_recent_90d_top3_rate"] = t90_rate
        feat["track_recent_90d_samples"] = t90_n
        feat["track_recent_90d_avg_winning_pop"] = t90_pop
    else:
        feat["track_recent_30d_top3_rate"] = None
        feat["track_recent_30d_samples"] = 0
        feat["track_recent_30d_avg_winning_pop"] = None
        feat["track_recent_90d_top3_rate"] = None
        feat["track_recent_90d_samples"] = 0
        feat["track_recent_90d_avg_winning_pop"] = None

    if conn is not None:
        # 騎手の直近調子 (30/90 日)
        jr30_rate, jr30_n = _entity_recent_stats(
            conn, "jockey_code", horse.get("jockey_code", "") or "", before, 30, cache=cache,
        )
        feat["jockey_recent_30d_top3_rate"] = jr30_rate
        feat["jockey_recent_30d_samples"] = jr30_n
        jr90_rate, jr90_n = _entity_recent_stats(
            conn, "jockey_code", horse.get("jockey_code", "") or "", before, 90, cache=cache,
        )
        feat["jockey_recent_90d_top3_rate"] = jr90_rate
        feat["jockey_recent_90d_samples"] = jr90_n
        # 厩舎の直近調子
        tr30_rate, tr30_n = _entity_recent_stats(
            conn, "trainer_code", horse.get("trainer_code", "") or "", before, 30, cache=cache,
        )
        feat["trainer_recent_30d_top3_rate"] = tr30_rate
        feat["trainer_recent_30d_samples"] = tr30_n
        # 馬自身の直近調子 (= 賞味期限の検出)
        hr90_rate, hr90_n = _entity_recent_stats(
            conn, "blood_register_num", horse.get("blood_register_num", "") or "", before, 90, cache=cache,
        )
        feat["horse_recent_90d_top3_rate"] = hr90_rate
        feat["horse_recent_90d_samples"] = hr90_n
    else:
        feat["jockey_recent_30d_top3_rate"] = None
        feat["jockey_recent_30d_samples"] = 0
        feat["jockey_recent_90d_top3_rate"] = None
        feat["jockey_recent_90d_samples"] = 0
        feat["trainer_recent_30d_top3_rate"] = None
        feat["trainer_recent_30d_samples"] = 0
        feat["horse_recent_90d_top3_rate"] = None
        feat["horse_recent_90d_samples"] = 0

    return feat
