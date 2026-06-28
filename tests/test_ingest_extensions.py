from __future__ import annotations

import sqlite3

import db
from jvlink_client.parser import HorseRaceInfo, MiningPrediction


def _memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def _horse_race_info(**overrides):
    values = dict(
        record_type="SE",
        data_div="1",
        data_created="20260621",
        year="2026",
        month_day="0621",
        track_code="05",
        kaiji="03",
        nichiji="04",
        race_num="01",
        waku_num="1",
        horse_num="01",
        blood_register_num="2020100001",
        horse_name="テストホース",
        horse_symbol_code="",
        sex_code="",
        breed_code="",
        coat_code="",
        age=3,
        east_west_code="",
        trainer_code="",
        trainer_short_name="",
        owner_code="",
        owner_name="",
        burden_weight=560,
        blinker="",
        jockey_code="",
        jockey_short_name="",
        jockey_apprentice_code="",
        horse_weight="480",
        weight_change_sign="+",
        weight_change_diff="004",
        abnormal_code="0",
        finish_order=0,
        confirmed_order=0,
        same_finish="",
        finish_time=0,
        win_odds=0,
        win_popularity=0,
        final_3f=0,
        mining_time=0,
        mining_predicted_order=0,
        leg_quality_code="",
    )
    values.update(overrides)
    return HorseRaceInfo(**values)


def test_init_db_adds_training_metadata_columns():
    conn = _memory_db()
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(training_times)")}
        assert "data_div" in cols
        assert "data_created" in cols
    finally:
        conn.close()


def test_upsert_mining_prediction_updates_horse_race_dm_rank():
    conn = _memory_db()
    try:
        conn.execute(
            """
            INSERT INTO horse_races
                (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num)
            VALUES
                ('2026', '0621', '05', '03', '04', '11', '07')
            """
        )
        db.upsert_mining_prediction(
            conn,
            MiningPrediction(
                record_type="DM",
                data_div="1",
                data_created="20260621",
                year="2026",
                month_day="0621",
                track_code="05",
                kaiji="03",
                nichiji="04",
                race_num="11",
                horse_num="07",
                predicted_rank=2,
            ),
        )
        rank = conn.execute(
            """
            SELECT mining_predicted_order
              FROM horse_races
             WHERE race_year='2026'
               AND race_month_day='0621'
               AND track_code='05'
               AND kaiji='03'
               AND nichiji='04'
               AND race_num='11'
               AND horse_num='07'
            """
        ).fetchone()[0]
        assert rank == 2
    finally:
        conn.close()


def test_result_upsert_does_not_clear_existing_mining_or_odds():
    conn = _memory_db()
    try:
        db.upsert_horse_race(
            conn,
            _horse_race_info(
                mining_time=712,
                mining_predicted_order=2,
                win_odds=48,
                win_popularity=3,
            ),
        )
        db.upsert_horse_race(
            conn,
            _horse_race_info(
                finish_order=1,
                confirmed_order=1,
                final_3f=349,
                mining_time=0,
                mining_predicted_order=0,
                win_odds=0,
                win_popularity=0,
            ),
        )
        row = conn.execute(
            """
            SELECT mining_time, mining_predicted_order, win_odds, win_popularity,
                   finish_order, confirmed_order, final_3f
              FROM horse_races
             WHERE race_year='2026'
               AND race_month_day='0621'
               AND track_code='05'
               AND kaiji='03'
               AND nichiji='04'
               AND race_num='01'
               AND horse_num='01'
            """
        ).fetchone()
        assert dict(row) == {
            "mining_time": 712,
            "mining_predicted_order": 2,
            "win_odds": 48,
            "win_popularity": 3,
            "finish_order": 1,
            "confirmed_order": 1,
            "final_3f": 349,
        }
    finally:
        conn.close()
