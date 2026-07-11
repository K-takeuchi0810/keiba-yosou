"""relative_race_metrics の馬固有性と cache key 汚染バグの regression。

2026-07-06 検証監査で検出した cross-horse 汚染: 同一過去レースを走った複数の
出走馬が、レース内共有 feature_cache 経由で 1 頭目の値 (上がり順位/タイム差) に
汚染されるバグ。cache key に馬番を含めることで解消したことを固定する。
波及先は rules.py の上がり順位スコアと LGBM 特徴。
"""

from __future__ import annotations

import sqlite3

from predictor.features import _cached, relative_race_metrics


def _db_with_shared_past_race() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT, "
        "kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT, finish_time INTEGER, "
        "final_3f INTEGER, confirmed_order INTEGER)"
    )
    # 過去レース R: 馬01 が上がり最速 (335)、馬02 が最遅 (350)
    key = ("2024", "0501", "05", "01", "01", "11")
    conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?, '01', 1200, 335, 1)", key)
    conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?, '02', 1210, 350, 2)", key)
    conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?, '03', 1215, 342, 3)", key)
    conn.commit()
    return conn


def _past(horse_num: str) -> dict:
    return {"race_year": "2024", "race_month_day": "0501", "track_code": "05",
            "kaiji": "01", "nichiji": "01", "race_num": "11",
            "horse_num": horse_num, "finish_time": {"01": 1200, "02": 1210, "03": 1215}[horse_num]}


def test_relative_race_metrics_is_horse_specific():
    conn = _db_with_shared_past_race()
    _, rank1 = relative_race_metrics(conn, _past("01"))
    _, rank2 = relative_race_metrics(conn, _past("02"))
    assert rank1 == 1     # 馬01 は上がり最速 → 1 位
    assert rank2 == 3     # 馬02 は上がり最遅 (335<342<350) → 3 位


def test_cache_key_includes_horse_num_no_cross_contamination():
    """レース内共有 cache で、同一過去レースの別馬が 1 頭目の値に汚染されないこと。

    cache key にレース識別 + 馬番を含める現行実装を模す。旧実装 (馬番なしキー) では
    2 頭目が 1 頭目のキャッシュ値を引いて rank1==rank2 になっていた。
    """
    conn = _db_with_shared_past_race()
    cache: dict = {}
    race_id = ("relative_race_metrics", "2024", "0501", "05", "01", "01", "11")

    def fetch(hn):
        return _cached(cache, race_id + (hn,), lambda: relative_race_metrics(conn, _past(hn)))

    r1 = fetch("01")
    r2 = fetch("02")
    assert r1[1] == 1 and r2[1] == 3          # 各馬固有の順位 (汚染なし)
    # 同じ馬を再取得したらキャッシュヒット (同値) — cache が機能していること
    assert fetch("01") == r1
    # 旧バグ再現ガード: 馬番を除いたキーだと 2 頭目が 1 頭目の値に汚染される
    bad: dict = {}
    b1 = _cached(bad, race_id, lambda: relative_race_metrics(conn, _past("01")))
    b2 = _cached(bad, race_id, lambda: relative_race_metrics(conn, _past("02")))
    assert b1 == b2       # 汚染の実証 (馬番なしキーでは 2 頭目が 1 頭目を引く)
    assert b2[1] == 1     # 馬02 なのに馬01 の 1 位が返る = バグ
