"""F3 PIT ゲートのガードテスト (docs/F3_MARKET_RESIDUAL_DESIGN.md D1: n=10)。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from db import SCHEMA_PATH, insert_odds_snapshot
from jvlink_client.parser import O1Odds
from predictor.pit_gate import pit_cutoff, usable_snapshots


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    return conn


def _o1(odds_list):
    return O1Odds(record_type="O1", data_div="1", data_created="20260704",
                  year="2026", month_day="0704", track_code="05", kaiji="01",
                  nichiji="01", race_num="11", announced_at="",
                  registered_count=2, starter_count=2, win_odds=odds_list)


RACE = {"race_year": "2026", "race_month_day": "0704", "track_code": "05",
        "kaiji": "01", "nichiji": "01", "race_num": "11", "start_time": "1540"}


def test_pit_cutoff_is_start_minus_gate():
    assert pit_cutoff("20260704", "1540", 10) == "2026-07-04T15:30:00"
    assert pit_cutoff("20260704", "", 10) is None  # start 不明 → 使用不可


def test_usable_snapshots_excludes_post_gate_and_null():
    conn = _conn()
    # T-70分 (朝寄り) と T-11分 → 適格
    insert_odds_snapshot(conn, _o1([("01", 50, 1)]), "2026-07-04T14:30:00", "morning")
    insert_odds_snapshot(conn, _o1([("01", 45, 1)]), "2026-07-04T15:29:00", "0B31")
    # T-5分 → ゲート違反 (n=10)
    insert_odds_snapshot(conn, _o1([("01", 40, 1)]), "2026-07-04T15:35:00", "0B31")
    # 発走後 → 違反
    insert_odds_snapshot(conn, _o1([("01", 38, 1)]), "2026-07-04T15:45:00", "0B31")
    conn.commit()

    snaps = usable_snapshots(conn, RACE, gate_minutes=10)
    assert [s["fetched_at"] for s in snaps] == [
        "2026-07-04T14:30:00", "2026-07-04T15:29:00",
    ], "T−10 より後・発走後のスナップは特徴に流れない"
    # ドリフトの素材: 朝 50 → 直前 45
    assert (snaps[0]["win_odds"], snaps[-1]["win_odds"]) == (50, 45)


def test_usable_snapshots_empty_when_start_time_missing():
    conn = _conn()
    insert_odds_snapshot(conn, _o1([("01", 50, 1)]), "2026-07-04T09:30:00", "morning")
    conn.commit()
    race = dict(RACE, start_time="")
    assert usable_snapshots(conn, race) == [], "発走時刻不明レースは安全側で空"


def test_insert_odds_snapshot_idempotent():
    conn = _conn()
    n1 = insert_odds_snapshot(conn, _o1([("01", 50, 1), ("02", 30, 2)]),
                              "2026-07-04T09:30:00", "morning")
    n2 = insert_odds_snapshot(conn, _o1([("01", 50, 1), ("02", 30, 2)]),
                              "2026-07-04T09:30:00", "morning")
    assert n1 == n2 == 2
    assert conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0] == 2
