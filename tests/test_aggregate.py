"""webapp/aggregate.py の傾向集計テスト (in-memory DB)。"""

from __future__ import annotations

import sqlite3

import pytest

from webapp import aggregate as agg


def test_surface_and_bucket_helpers():
    assert agg.surface_of("11") == "turf"
    assert agg.surface_of("24") == "dirt"
    assert agg.surface_of("51") == "jump"
    assert agg.surface_of(None) == "other"
    assert agg.distance_bucket_of(1200) == "sprint"
    assert agg.distance_bucket_of(1600) == "mile"
    assert agg.distance_bucket_of(2000) == "middle"
    assert agg.distance_bucket_of(2500) == "long"
    assert agg.popularity_bucket_of(2) == "1-3"
    assert agg.popularity_bucket_of(5) == "4-6"
    assert agg.popularity_bucket_of(12) == "10+"
    assert agg.popularity_bucket_of(0) == "unknown"


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT,
          kaiji TEXT, nichiji TEXT, race_num TEXT, distance INTEGER, track_type_code TEXT);
        CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT,
          kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT, waku_num TEXT,
          blood_register_num TEXT, jockey_short_name TEXT, jockey_code TEXT,
          trainer_short_name TEXT, trainer_code TEXT, confirmed_order INTEGER, win_popularity INTEGER);
        CREATE TABLE horse_masters (blood_register_num TEXT PRIMARY KEY, sire_name TEXT,
          sire_breeding_num TEXT, dam_sire_name TEXT);
        CREATE TABLE payouts (race_year TEXT, race_month_day TEXT, track_code TEXT,
          kaiji TEXT, nichiji TEXT, race_num TEXT,
          tan_horse_num1 TEXT, tan_payout1 INTEGER, tan_horse_num2 TEXT, tan_payout2 INTEGER,
          tan_horse_num3 TEXT, tan_payout3 INTEGER);
        CREATE TABLE breeding_horses (breeding_num TEXT PRIMARY KEY, horse_name TEXT,
          sire_name TEXT, sire_breeding_num TEXT);
        """
    )
    # horse masters: 2 sires
    conn.execute("INSERT INTO horse_masters VALUES ('B1','ディープインパクト','S1','母父X')")
    conn.execute("INSERT INTO horse_masters VALUES ('B2','キングカメハメハ','S2','母父Y')")
    # 40 races, 東京(05) 芝(11) 1600m, 4 horses each; horse 1 (B1) always wins。
    # race キーはユニークにする (race_num を 01..40 の連番に)。
    for i in range(40):
        md = "0115"
        key = ("2024", md, "05", "01", "01", f"{i + 1:02d}")
        conn.execute("INSERT INTO races VALUES (?,?,?,?,?,?,1600,'11')", key)
        for hn in range(1, 5):
            brn = "B1" if hn == 1 else "B2"
            order = 1 if hn == 1 else hn
            conn.execute(
                "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*key, f"{hn:02d}", str(hn), brn, "ルメール" if hn == 1 else "武豊",
                 f"J{hn}", "厩舎A", "T1", order, hn),
            )
        conn.execute("INSERT INTO payouts (race_year,race_month_day,track_code,kaiji,nichiji,race_num,tan_horse_num1,tan_payout1) VALUES (?,?,?,?,?,?, '01', 300)", key)
    conn.commit()
    return conn


def test_list_courses():
    conn = _db()
    courses = agg.list_courses(conn, "20240101", "20241231", min_races=10)
    assert len(courses) == 1
    c = courses[0]
    assert c["track_code"] == "05" and c["surface"] == "turf" and c["distance"] == 1600
    assert c["n_races"] == 40


def test_aggregate_sire_and_return():
    conn = _db()
    r = agg.aggregate_course(conn, "05", "turf", 1600, "sire", "20240101", "20241231", min_n=10)
    assert r["total"] == 160  # 40 races × 4 horses
    by_value = {c["value"]: c for c in r["cells"]}
    # ディープ産駒(B1)は常に1着 → 勝率100%/複勝100%
    deep = by_value["ディープインパクト"]
    assert deep["n"] == 40 and deep["wins"] == 40
    assert deep["win_pct"] == 100.0 and deep["top3_pct"] == 100.0
    # 単勝配当300円 × 40勝 / (40*100) = 300%
    assert deep["return_pct"] == 300.0
    # キンカメ産駒(B2)は2-4着 → 勝率0
    king = by_value["キングカメハメハ"]
    assert king["wins"] == 0 and king["return_pct"] == 0.0


def test_aggregate_sire_line_classifies_and_colors():
    conn = _db()
    r = agg.aggregate_course(conn, "05", "turf", 1600, "sire_line", "20240101", "20241231", min_n=10)
    by_value = {c["value"]: c for c in r["cells"]}
    assert "sunday" in by_value and by_value["sunday"]["label"] == "サンデーサイレンス系"
    assert by_value["sunday"]["color"] == "#8bc34a"
    assert "kingmambo" in by_value


def test_min_n_gate():
    conn = _db()
    # min_n を 200 にすると全 cell が insufficient
    r = agg.aggregate_course(conn, "05", "turf", 1600, "sire", "20240101", "20241231", min_n=200)
    assert r["cells"] == []
    assert len(r["insufficient"]) >= 1


def test_popularity_sorted():
    conn = _db()
    r = agg.aggregate_course(conn, "05", "turf", 1600, "popularity", "20240101", "20241231", min_n=10)
    vals = [c["value"] for c in r["cells"]]
    # 人気帯は昇順 (1-3, 4-6, ...)
    assert vals == sorted(vals, key=agg._pop_sort_key)


def test_surface_filter_excludes_dirt():
    conn = _db()
    # ダートで引くと該当0 (合成データは芝のみ)
    r = agg.aggregate_course(conn, "05", "dirt", 1600, "sire", "20240101", "20241231", min_n=1)
    assert r["total"] == 0


def test_unknown_factor_raises():
    conn = _db()
    with pytest.raises(ValueError):
        agg.aggregate_course(conn, "05", "turf", 1600, "bogus", "20240101", "20241231")
