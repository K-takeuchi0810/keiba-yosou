"""predictor.pit_market — PIT 市場再構成の契約テスト (改革 R1-1)。

固定する不変条件:
  1. cutoff (発走 T−n) より後のスナップショットは使わない
  2. cutoff 以前の**最新**を採る
  3. PIT スナップが無い馬は fail-closed (オッズ None、確定オッズへ落ちない)
  4. 実行時刻に依存しない (cutoff は発走時刻から逆算)
  5. 入力 horses を破壊しない
"""
from __future__ import annotations

import sqlite3

import pytest

from predictor.pit_market import apply_pit_odds, latest_pit_odds, summarize_coverage

RACE = {
    "race_year": "2026", "race_month_day": "0822", "track_code": "05",
    "kaiji": "01", "nichiji": "01", "race_num": "01", "start_time": "1500",
}


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE odds_snapshots (race_year TEXT, race_month_day TEXT,"
        " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT,"
        " fetched_at TEXT, win_odds INTEGER, win_popularity INTEGER, source TEXT)"
    )
    return c


def _snap(conn, horse_num, fetched_at, odds, pop=1, source="0B31"):
    conn.execute(
        "INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026", "0822", "05", "01", "01", "01", horse_num, fetched_at, odds, pop, source),
    )


def _horses(nums=("01", "02")):
    # 確定オッズ (発走後) が入っている状態を模す。fail-closed ならこの値は使われない。
    return [
        {"horse_num": n, "win_odds": 999, "win_popularity": 9,
         "odds_fetched_at": None, "odds_dataspec": "RACE", "horse_name": f"H{n}"}
        for n in nums
    ]


def test_uses_latest_snapshot_at_or_before_cutoff(conn):
    """T−10 (=14:50) 以前の最新を採り、それより後は使わない。"""
    _snap(conn, "01", "2026-08-22T14:00:00", 300)
    _snap(conn, "01", "2026-08-22T14:49:00", 250)   # 採用されるべき
    _snap(conn, "01", "2026-08-22T14:55:00", 180)   # cutoff 後 → 除外
    conn.commit()

    got = latest_pit_odds(conn, RACE)

    assert got["01"]["win_odds"] == 250
    assert got["01"]["fetched_at"] == "2026-08-22T14:49:00"


def test_cutoff_boundary_is_inclusive(conn):
    """ちょうど T−10 のスナップは使える (境界を含む)。"""
    _snap(conn, "01", "2026-08-22T14:50:00", 210)
    conn.commit()

    assert latest_pit_odds(conn, RACE)["01"]["win_odds"] == 210


def test_fail_closed_when_no_pit_snapshot(conn):
    """PIT スナップが無い馬は確定オッズに落ちず None になる。"""
    _snap(conn, "01", "2026-08-22T14:30:00", 320)
    conn.commit()

    horses, meta = apply_pit_odds(conn, RACE, _horses(("01", "02")))

    h1, h2 = horses
    assert h1["win_odds"] == 320 and h1["odds_fetched_at"] == "2026-08-22T14:30:00"
    assert h2["win_odds"] is None, "確定オッズ 999 に落ちてはいけない (fail-closed)"
    assert h2["win_popularity"] is None
    assert h2["odds_fetched_at"] is None
    assert meta["horses_total"] == 2
    assert meta["horses_with_pit_odds"] == 1
    assert meta["coverage"] == 0.5
    assert meta["has_market"] is True
    assert meta["pit_cutoff"] == "2026-08-22T14:50:00"


def test_no_snapshots_at_all_means_no_market(conn):
    horses, meta = apply_pit_odds(conn, RACE, _horses())

    assert all(h["win_odds"] is None for h in horses)
    assert meta["has_market"] is False
    assert meta["coverage"] == 0.0


def test_does_not_mutate_input(conn):
    _snap(conn, "01", "2026-08-22T14:30:00", 320)
    conn.commit()
    src = _horses(("01",))

    apply_pit_odds(conn, RACE, src)

    assert src[0]["win_odds"] == 999, "入力を破壊しない"


def test_unknown_start_time_yields_no_market(conn):
    """start_time 不明は安全側 (市場情報なし)。空文字を 0 時と誤解しない。"""
    _snap(conn, "01", "2026-08-22T14:30:00", 320)
    conn.commit()
    race = {**RACE, "start_time": ""}

    horses, meta = apply_pit_odds(conn, race, _horses(("01",)))

    assert meta["pit_cutoff"] is None
    assert meta["has_market"] is False
    assert horses[0]["win_odds"] is None


def test_zero_odds_snapshot_is_treated_as_missing(conn):
    """win_odds=0 の欠損スナップは「観測できた」に数えない。"""
    _snap(conn, "01", "2026-08-22T14:30:00", 0)
    conn.commit()

    horses, meta = apply_pit_odds(conn, RACE, _horses(("01",)))

    assert horses[0]["win_odds"] is None
    assert meta["horses_with_pit_odds"] == 0


def test_gate_minutes_override(conn):
    """gate を 60 分にすると 14:30 のスナップも cutoff 後になり使えない。"""
    _snap(conn, "01", "2026-08-22T14:30:00", 320)
    conn.commit()

    _, meta60 = apply_pit_odds(conn, RACE, _horses(("01",)), gate_minutes=60)
    _, meta10 = apply_pit_odds(conn, RACE, _horses(("01",)), gate_minutes=10)

    assert meta60["pit_cutoff"] == "2026-08-22T14:00:00"
    assert meta60["has_market"] is False
    assert meta10["has_market"] is True


def test_summarize_coverage():
    metas = [
        {"has_market": True, "horses_total": 10, "horses_with_pit_odds": 8},
        {"has_market": False, "horses_total": 12, "horses_with_pit_odds": 0},
    ]
    s = summarize_coverage(metas)
    assert s["races"] == 2
    assert s["races_with_market"] == 1
    assert s["races_market_rate"] == 0.5
    assert s["horses_coverage"] == round(8 / 22, 4)
