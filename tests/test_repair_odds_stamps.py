"""scripts.repair_odds_stamps の分岐と境界の回帰テスト。

一括 UPDATE を含む修復スクリプトなので、
  (a) 発走時刻ちょうど (>=) が post-start 扱いになること
  (b) 発走前 snapshot あり → 復元 / 無し → 刻印 NULL 化
  (c) 復元しても odds_dataspec のドメインが壊れないこと
を固定する (2026-08-22 コード品質監査で「テストゼロ」を指摘された)。
"""
from __future__ import annotations

import sqlite3

from scripts.repair_odds_stamps import find_post_start_rows, repair

KEYS = ("2026", "0816", "05", "01", "01", "01")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT, start_time TEXT)"
    )
    conn.execute(
        "CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT, win_odds INTEGER,"
        " win_popularity INTEGER, odds_fetched_at TEXT, odds_dataspec TEXT)"
    )
    conn.execute(
        "CREATE TABLE odds_snapshots (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT, fetched_at TEXT,"
        " win_odds INTEGER, win_popularity INTEGER, source TEXT)"
    )
    conn.execute("INSERT INTO races VALUES (?,?,?,?,?,?, '1500')", KEYS)
    return conn


def _add_horse(conn, horse_num, fetched_at, *, odds=500, pop=4, dataspec="0B31"):
    conn.execute(
        "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (*KEYS, horse_num, odds, pop, fetched_at, dataspec),
    )


def _add_snapshot(conn, horse_num, fetched_at, *, odds=300, pop=2, source="morning"):
    conn.execute(
        "INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (*KEYS, horse_num, fetched_at, odds, pop, source),
    )


def test_start_time_boundary_counts_as_post_start():
    """発走時刻ちょうど (15:00:00) は post-start 側。締切済みで値は動かない。"""
    conn = _conn()
    _add_horse(conn, "01", "2026-08-16T15:00:00")   # ちょうど
    _add_horse(conn, "02", "2026-08-16T14:59:00")   # 発走前
    conn.commit()

    rows = find_post_start_rows(conn, "20260816", "20260816", True)

    assert [r["horse_num"] for r in rows] == ["01"]


def test_restores_newest_pre_start_snapshot_and_keeps_dataspec():
    conn = _conn()
    _add_horse(conn, "01", "2026-08-16T15:20:00", odds=500, pop=4, dataspec="0B31")
    _add_snapshot(conn, "01", "2026-08-16T14:10:00", odds=800, pop=6, source="morning")
    _add_snapshot(conn, "01", "2026-08-16T14:50:00", odds=310, pop=2, source="0B31")
    _add_snapshot(conn, "01", "2026-08-16T15:30:00", odds=999, pop=9, source="0B30")
    conn.commit()

    summary = repair(conn, "20260816", "20260816", apply=True)
    row = conn.execute("SELECT * FROM horse_races").fetchone()

    assert summary["restored_from_snapshot"] == 1
    assert summary["cleared_to_null"] == 0
    assert row["win_odds"] == 310, "発走前で最新の snapshot (14:50) を採る"
    assert row["win_popularity"] == 2
    assert row["odds_fetched_at"] == "2026-08-16T14:50:00"
    assert row["odds_dataspec"] == "0B31", "source ラベルを dataspec 欄に混ぜない"


def test_clears_stamp_when_no_pre_start_snapshot():
    """発走前 snapshot が無ければ確定オッズ相当として刻印だけ外す (値は残す)。"""
    conn = _conn()
    _add_horse(conn, "01", "2026-08-16T15:20:00", odds=500, pop=4)
    _add_snapshot(conn, "01", "2026-08-16T15:40:00", odds=999, pop=9)  # 発走後のみ
    conn.commit()

    summary = repair(conn, "20260816", "20260816", apply=True)
    row = conn.execute("SELECT * FROM horse_races").fetchone()

    assert summary["cleared_to_null"] == 1
    assert row["odds_fetched_at"] is None
    assert row["win_odds"] == 500, "オッズ値自体は保持する"


def test_dry_run_does_not_write_but_reports():
    conn = _conn()
    _add_horse(conn, "01", "2026-08-16T15:20:00")
    conn.commit()

    summary = repair(conn, "20260816", "20260816", apply=False)
    row = conn.execute("SELECT odds_fetched_at FROM horse_races").fetchone()

    assert summary["post_start_rows"] == 1
    assert summary["applied"] is False
    assert row["odds_fetched_at"] == "2026-08-16T15:20:00", "dry-run は書かない"
    assert summary["before_rows"][0]["action"] == "clear"
