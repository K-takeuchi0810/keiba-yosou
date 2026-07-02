"""feature cache キー衝突の回帰テスト (2026-07-02 忠実性監査で発見)。

walk-forward ハーネスと production 経路の確率突合で max 2.8e-2 の差が出た根因:
1. relative_race_metrics のキーに馬識別が無く、過去に対戦した 2 頭が同じ過去レースを
   共有すると先勝ちの値を使い回していた (best_relative_time_diff / best_final_3f_rank)。
2. bloodline_stats scope="going" のキーに馬場状態が無く、同日同 family/bucket の
   別馬場レースで衝突していた (sire_going / dam_sire_going)。

どちらも走査順で dataset の値が変わる = build ごとに再現しないノイズ源だった。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from db import SCHEMA_PATH
from predictor.features import bloodline_stats, compute_features


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    return conn


def _insert_race(conn, ymd: str, race_num: str = "01", track: str = "05",
                 track_type: str = "11", distance: int = 1600) -> dict:
    row = {
        "race_year": ymd[:4], "race_month_day": ymd[4:], "track_code": track,
        "kaiji": "01", "nichiji": "01", "race_num": race_num,
        "track_type_code": track_type, "distance": distance,
        "starter_count": 2, "turf_condition": "1", "dirt_condition": "0",
    }
    conn.execute(
        "INSERT INTO races (race_year, race_month_day, track_code, kaiji, nichiji, race_num,"
        " track_type_code, distance, starter_count, turf_condition, dirt_condition)"
        " VALUES (:race_year,:race_month_day,:track_code,:kaiji,:nichiji,:race_num,"
        ":track_type_code,:distance,:starter_count,:turf_condition,:dirt_condition)", row)
    return row


def _insert_run(conn, race: dict, horse_num: str, blood: str,
                order: int, finish_time: int, final_3f: int) -> None:
    conn.execute(
        "INSERT INTO horse_races (race_year, race_month_day, track_code, kaiji, nichiji,"
        " race_num, horse_num, blood_register_num, confirmed_order, finish_time, final_3f)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (race["race_year"], race["race_month_day"], race["track_code"], race["kaiji"],
         race["nichiji"], race["race_num"], horse_num, blood, order, finish_time, final_3f))


def test_relative_race_metrics_cache_key_includes_horse():
    """同じ過去レースを共有する 2 頭が、共有 cache 下でも各自の相対値を得る。"""
    conn = _conn()
    past = _insert_race(conn, "20240107")
    _insert_run(conn, past, "01", "A000000001", order=1, finish_time=960, final_3f=340)
    _insert_run(conn, past, "02", "B000000002", order=2, finish_time=972, final_3f=355)
    current = _insert_race(conn, "20240601")

    shared: dict = {}
    feat_a = compute_features(conn, {"horse_num": "01", "blood_register_num": "A000000001"},
                              current, cache=shared)
    feat_b = compute_features(conn, {"horse_num": "02", "blood_register_num": "B000000002"},
                              current, cache=shared)
    # A は上位平均に近い側、B は +12。衝突バグ時は B が A の値 (と rank 1) を使い回す
    assert feat_a["best_relative_time_diff"] != feat_b["best_relative_time_diff"], \
        "同一過去レース共有の 2 頭が同じ相対値 = cache キー衝突"
    assert feat_a["best_final_3f_rank"] == 1
    assert feat_b["best_final_3f_rank"] == 2


def test_bloodline_going_cache_key_includes_going():
    """同日同 family/bucket で馬場だけ違う 2 レースが別キーになる。"""
    conn = _conn()
    conn.execute(
        "INSERT INTO horse_masters (blood_register_num, sire_breeding_num) VALUES (?,?)",
        ("A000000001", "S000000001"))
    horse = {"blood_register_num": "A000000001"}
    race_good = {"track_type_code": "11", "distance": 1600,
                 "turf_condition": "1", "dirt_condition": "0"}
    race_heavy = {"track_type_code": "11", "distance": 1600,
                  "turf_condition": "3", "dirt_condition": "0"}
    shared: dict = {}
    bloodline_stats(conn, horse, race_good, "20240601", "sire_breeding_num", "going", cache=shared)
    bloodline_stats(conn, horse, race_heavy, "20240601", "sire_breeding_num", "going", cache=shared)
    going_keys = [k for k in shared if k[0] == "bloodline_stats" and k[4] == "going"]
    assert len(going_keys) == 2, \
        f"良/重 の別馬場が同一キーに衝突している: {going_keys}"
