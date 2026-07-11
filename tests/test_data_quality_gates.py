"""Step1 データ品質ゲートのテスト。

対象:
- list_races(require_confirmed=True): 確定勝ち馬を持つレースのみ返す (完全性ゲート)
- update_win_odds: 古い snapshot で新しい snapshot を上書きしない (1c)
"""
from __future__ import annotations

import sqlite3

from db import update_win_odds
from jvlink_client.parser import O1Odds
from scripts.backtest import list_races


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE races (
            race_year TEXT, race_month_day TEXT, track_code TEXT,
            kaiji TEXT, nichiji TEXT, race_num TEXT, distance INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE horse_races (
            race_year TEXT, race_month_day TEXT, track_code TEXT,
            kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT,
            confirmed_order INTEGER, win_odds INTEGER, win_popularity INTEGER,
            odds_fetched_at TEXT, odds_dataspec TEXT
        )
        """
    )
    return conn


def _add_race(conn, race_num, *, confirmed: int) -> None:
    keys = ("2026", "0607", "05", "01", "01", race_num)
    conn.execute(
        "INSERT INTO races (race_year,race_month_day,track_code,kaiji,nichiji,race_num,distance)"
        " VALUES (?,?,?,?,?,?,1600)",
        keys,
    )
    conn.execute(
        "INSERT INTO horse_races (race_year,race_month_day,track_code,kaiji,nichiji,race_num,"
        "horse_num,confirmed_order,win_odds,win_popularity) VALUES (?,?,?,?,?,?, '01', ?, 30, 1)",
        (*keys, confirmed),
    )


def test_list_races_require_confirmed_excludes_unconfirmed():
    conn = _conn()
    _add_race(conn, "01", confirmed=1)   # 確定済
    _add_race(conn, "02", confirmed=0)   # 着順未確定 (払戻だけ先行等)
    _add_race(conn, "03", confirmed=2)   # 部分結果: 勝ち馬が未確定
    conn.commit()

    all_races = list_races(conn, "20260607", "20260607", require_confirmed=False)
    confirmed = list_races(conn, "20260607", "20260607", require_confirmed=True)

    assert {r["race_num"] for r in all_races} == {"01", "02", "03"}
    assert {r["race_num"] for r in confirmed} == {"01"}, "確定勝ち馬のないレースは除外される"


def _o1(fetched_horse_odds, race_num="01") -> O1Odds:
    return O1Odds(
        record_type="O1", data_div="1", data_created="20260607",
        year="2026", month_day="0607", track_code="05",
        kaiji="01", nichiji="01", race_num=race_num,
        announced_at="", registered_count=1, starter_count=1,
        win_odds=fetched_horse_odds,
    )


def test_update_win_odds_does_not_overwrite_newer_snapshot():
    conn = _conn()
    _add_race(conn, "01", confirmed=0)
    conn.commit()

    # 新しい snapshot を先に書く (12:10)
    update_win_odds(conn, _o1([("01", 50, 2)]), fetched_at="2026-06-07T12:10:00", dataspec="0B31")
    # 古い snapshot (12:00) を後から取り込む → 上書きしないはず
    n = update_win_odds(conn, _o1([("01", 999, 9)]), fetched_at="2026-06-07T12:00:00", dataspec="0B31")

    row = conn.execute("SELECT win_odds, odds_fetched_at FROM horse_races").fetchone()
    assert n == 0, "古い fetched_at では rowcount=0 (更新されない)"
    assert row["win_odds"] == 50, "新しい snapshot が古いもので上書きされない"
    assert row["odds_fetched_at"] == "2026-06-07T12:10:00"


def test_update_win_odds_applies_newer_snapshot_and_null():
    conn = _conn()
    _add_race(conn, "01", confirmed=0)
    conn.commit()

    # 既存 NULL → 更新可
    n1 = update_win_odds(conn, _o1([("01", 80, 3)]), fetched_at="2026-06-07T12:00:00")
    assert n1 == 1
    # より新しい snapshot → 更新可
    n2 = update_win_odds(conn, _o1([("01", 60, 2)]), fetched_at="2026-06-07T12:20:00")
    assert n2 == 1
    row = conn.execute("SELECT win_odds, odds_fetched_at FROM horse_races").fetchone()
    assert row["win_odds"] == 60
    assert row["odds_fetched_at"] == "2026-06-07T12:20:00"


def test_update_win_odds_historical_keeps_null_fetched_at():
    """RACE dataspec の確定オッズは odds_fetched_at=NULL (信頼) を維持する。

    2026-06-30 バックフィルが確定オッズ行にファイル mtime (発走後) を刻印し、
    Step1 odds ゲートが 2021-2026 の全 261k 行を post-start 扱いにした事故の回帰。
    """
    conn = _conn()
    _add_race(conn, "01", confirmed=1)
    conn.commit()

    n = update_win_odds(conn, _o1([("01", 45, 1)]), fetched_at="2026-06-30T18:00:00",
                        dataspec="RACE", historical=True)
    assert n == 1
    row = conn.execute("SELECT win_odds, odds_fetched_at, odds_dataspec FROM horse_races").fetchone()
    assert row["win_odds"] == 45
    assert row["odds_fetched_at"] is None, "確定オッズに発走後 mtime を刻印しない"
    assert row["odds_dataspec"] == "RACE"


def test_update_win_odds_historical_does_not_clobber_realtime_snapshot():
    """historical はリアルタイム PIT snapshot (odds_fetched_at 非NULL) を上書きしない。"""
    conn = _conn()
    _add_race(conn, "01", confirmed=0)
    conn.commit()

    # 発走前スナップショット (mining) が先にある
    update_win_odds(conn, _o1([("01", 80, 3)]), fetched_at="2026-06-07T12:00:00", dataspec="0B31")
    # 後から確定オッズを historical 取り込み → スキップされる
    n = update_win_odds(conn, _o1([("01", 45, 1)]), dataspec="RACE", historical=True)
    assert n == 0
    row = conn.execute("SELECT win_odds, odds_fetched_at FROM horse_races").fetchone()
    assert row["win_odds"] == 80, "PIT snapshot が確定オッズで潰されない"
    assert row["odds_fetched_at"] == "2026-06-07T12:00:00"
