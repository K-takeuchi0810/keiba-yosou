"""F4 予想ロギング (prediction_log) のテスト。

発行時点の予想を追記し、後で結果と突合できることを検証する。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from db import SCHEMA_PATH, insert_prediction_log


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    return conn


RACE = {"race_year": "2026", "race_month_day": "0712", "track_code": "05",
        "kaiji": "01", "nichiji": "01", "race_num": "11"}


def _rows():
    return [
        {"horse_num": "05", "mark": "◎", "rank": 1, "score": 110.0,
         "win_probability": 0.30, "raw_blended_probability": 0.28,
         "win_odds": 320, "win_popularity": 1, "confidence": "高信頼"},
        {"horse_num": "07", "mark": "○", "rank": 2, "score": 90.0,
         "win_probability": 0.18, "raw_blended_probability": 0.16,
         "win_odds": 550, "win_popularity": 2, "confidence": "標準"},
    ]


def test_insert_and_readback():
    conn = _conn()
    n = insert_prediction_log(conn, RACE, _rows(), "2026-07-12T09:30:00",
                              model_version="lgbm-v6", calibrator_version="p26")
    assert n == 2
    row = conn.execute(
        "SELECT mark, win_probability, win_odds, model_version FROM prediction_log "
        "WHERE horse_num='05'").fetchone()
    assert row["mark"] == "◎" and abs(row["win_probability"] - 0.30) < 1e-9
    assert row["win_odds"] == 320 and row["model_version"] == "lgbm-v6"


def test_append_only_keeps_multiple_generated_at():
    """同一レースを別時刻に再生成すると別スナップとして両方残る (発行時系列)。"""
    conn = _conn()
    insert_prediction_log(conn, RACE, _rows(), "2026-07-12T09:30:00")
    # 発走直前に◎が変わった想定
    later = [dict(_rows()[0], mark="○"), dict(_rows()[1], mark="◎")]
    insert_prediction_log(conn, RACE, later, "2026-07-12T15:20:00")
    snaps = conn.execute(
        "SELECT DISTINCT generated_at FROM prediction_log ORDER BY generated_at").fetchall()
    assert len(snaps) == 2, "異なる generated_at は別スナップとして追記される"


def test_same_generated_at_is_idempotent():
    conn = _conn()
    insert_prediction_log(conn, RACE, _rows(), "2026-07-12T09:30:00")
    insert_prediction_log(conn, RACE, _rows(), "2026-07-12T09:30:00")
    assert conn.execute("SELECT COUNT(*) FROM prediction_log").fetchone()[0] == 2


def test_join_with_results_for_accuracy():
    """prediction_log ⋈ horse_races (confirmed_order) で ◎ 的中が測れる。"""
    conn = _conn()
    insert_prediction_log(conn, RACE, _rows(), "2026-07-12T09:30:00")
    # ◎馬(05)が1着で確定
    conn.execute(
        "INSERT INTO horse_races (race_year,race_month_day,track_code,kaiji,nichiji,"
        "race_num,horse_num,confirmed_order) VALUES ('2026','0712','05','01','01','11','05',1)")
    conn.commit()
    hit = conn.execute(
        """
        SELECT hr.confirmed_order FROM prediction_log pl
          JOIN horse_races hr USING (race_year,race_month_day,track_code,kaiji,nichiji,race_num,horse_num)
         WHERE pl.mark='◎'
        """).fetchone()
    assert hit["confirmed_order"] == 1
