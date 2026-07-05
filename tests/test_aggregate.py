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
    conn.execute("INSERT INTO horse_masters VALUES ('B1','ディープインパクト','S1','タイキシャトル')")
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
    # 単勝配当300円 × 40勝 / (40*100) = 300% (全馬1着なので分散ゼロ→CIも300)
    assert deep["return_pct"] == 300.0
    assert deep["return_ci_lo"] == 300.0 and deep["return_ci_hi"] == 300.0
    assert deep["payout_missing"] == 0
    # キンカメ産駒(B2)は2-4着 → 勝率0・回収0
    king = by_value["キングカメハメハ"]
    assert king["wins"] == 0 and king["return_pct"] == 0.0
    assert king["return_ci_lo"] == 0.0


def test_aggregate_sire_line_classifies_and_colors():
    conn = _db()
    r = agg.aggregate_course(conn, "05", "turf", 1600, "sire_line", "20240101", "20241231", min_n=10)
    by_value = {c["value"]: c for c in r["cells"]}
    assert "sunday" in by_value and by_value["sunday"]["label"] == "サンデーサイレンス系"
    assert by_value["sunday"]["color"] == "#8bc34a"
    assert "kingmambo" in by_value


def test_aggregate_dam_sire_line_old_schema_fallback():
    """母父系統軸。fixture の horse_masters は dam_sire_breeding_num 列なし
    (旧スキーマ) なので、縮退 SELECT (名前照合のみ) の経路を実際に通す。"""
    conn = _db()
    r = agg.aggregate_course(conn, "05", "turf", 1600, "dam_sire_line",
                             "20240101", "20241231", min_n=10)
    by_value = {c["value"]: c for c in r["cells"]}
    # B1 (勝ち馬) の母父タイキシャトル → ターントゥ系 (辞書照合のみで分類)
    assert by_value["turnto"]["n"] == 40
    assert by_value["turnto"]["label"] == "ターントゥ系(ヘイロー等)"
    assert by_value["turnto"]["color"] == "#7986cb"
    # B2 の母父Y は辞書外 + 遡上不能 → unknown
    assert by_value["unknown"]["n"] == 120
    # 縮退フラグが立ち、テンプレートで「簡易分類」チップが出る
    assert r["dam_bn_degraded"] is True


def test_aggregate_dam_sire_line_new_schema_traversal():
    """新スキーマ (dam_sire_breeding_num あり) では母父の血統遡上が実際に効く。

    縮退側テストと対になる非縮退経路の regression (2026-07-05 validation 監査 #2)。
    """
    conn = _db()
    conn.execute("ALTER TABLE horse_masters ADD COLUMN dam_sire_breeding_num TEXT")
    # B1 の母父を辞書外の名前にし、breeding_horses 遡上でのみ分類可能にする
    conn.execute("UPDATE horse_masters SET dam_sire_name='無名母父', dam_sire_breeding_num='D1' "
                 "WHERE blood_register_num='B1'")
    conn.execute("INSERT INTO breeding_horses VALUES ('D1','無名母父','サンデーサイレンス','D2')")
    conn.commit()
    r = agg.aggregate_course(conn, "05", "turf", 1600, "dam_sire_line",
                             "20240101", "20241231", min_n=10)
    by_value = {c["value"]: c for c in r["cells"]}
    assert by_value["sunday"]["n"] == 40      # 遡上で父=サンデーサイレンス → sunday
    assert r["dam_bn_degraded"] is False      # 非縮退


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
