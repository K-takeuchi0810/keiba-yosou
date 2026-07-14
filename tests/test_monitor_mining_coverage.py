"""weekly_monitor の mining カバレッジ監視テスト (2026-07-14)。

LGBM v6 は gain 67% が mining 依存のため、供給劣化を早期検知する。
measure_mining_coverage は「直近 days 日の JRA 確定馬のうち mining_predictions が
付いている割合」を返す。DB 書き込みを伴うので open_db をテスト DB に差し替える。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from db import SCHEMA_PATH


@pytest.fixture
def patched_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))

    from contextlib import contextmanager

    @contextmanager
    def _open_db(*a, **k):
        yield conn  # close しない (テスト内で再利用)

    import scripts.monitor as mon
    monkeypatch.setattr(mon, "open_db", _open_db)
    return conn


def _recent_ymd(days_ago: int) -> tuple[str, str]:
    d = datetime.now().date() - timedelta(days=days_ago)
    return d.strftime("%Y"), d.strftime("%m%d")


def _add_horse(conn, y, md, race_num, horse_num, *, confirmed=1, mining=False):
    conn.execute(
        "INSERT OR REPLACE INTO horse_races (race_year,race_month_day,track_code,kaiji,nichiji,"
        "race_num,horse_num,confirmed_order) VALUES (?,?,'05','01','01',?,?,?)",
        (y, md, race_num, horse_num, confirmed))
    if mining:
        conn.execute(
            "INSERT OR REPLACE INTO mining_predictions (race_year,race_month_day,track_code,"
            "kaiji,nichiji,race_num,horse_num,record_type,predicted_rank) "
            "VALUES (?,?,'05','01','01',?,?,'TM',1)",
            (y, md, race_num, horse_num))


def test_mining_coverage_ratio(patched_db):
    from scripts.monitor import measure_mining_coverage
    y, md = _recent_ymd(3)
    # 4頭中3頭に mining → 75%
    _add_horse(patched_db, y, md, "11", "01", mining=True)
    _add_horse(patched_db, y, md, "11", "02", mining=True)
    _add_horse(patched_db, y, md, "11", "03", mining=True)
    _add_horse(patched_db, y, md, "11", "04", mining=False)
    patched_db.commit()
    r = measure_mining_coverage(days=30)
    assert r["n_horses"] == 4 and r["n_with_mining"] == 3
    assert abs(r["coverage"] - 0.75) < 1e-9


def test_mining_coverage_excludes_unconfirmed_and_nonjra(patched_db):
    from scripts.monitor import measure_mining_coverage
    y, md = _recent_ymd(3)
    _add_horse(patched_db, y, md, "11", "01", confirmed=1, mining=True)
    _add_horse(patched_db, y, md, "11", "02", confirmed=0, mining=False)  # 未確定→除外
    # 非JRA (track 30)
    patched_db.execute(
        "INSERT INTO horse_races (race_year,race_month_day,track_code,kaiji,nichiji,race_num,"
        "horse_num,confirmed_order) VALUES (?,?,'30','01','01','11','09',1)", (y, md))
    patched_db.commit()
    r = measure_mining_coverage(days=30)
    assert r["n_horses"] == 1 and r["coverage"] == 1.0, "未確定/非JRAは母数から除外"


def test_mining_coverage_none_when_empty(patched_db):
    from scripts.monitor import measure_mining_coverage
    r = measure_mining_coverage(days=30)
    assert r["n_horses"] == 0 and r["coverage"] is None
