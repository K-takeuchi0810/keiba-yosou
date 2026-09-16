"""T−10 の選択規則と PIT 監査の契約テスト (憲法 Phase 0.5-1)。

## 合格条件は「T−10 データがある」ではない

> そのT-10が当時の観測可能情報だけで再現できることを合格条件にしてください

結果を知ってから実際の発走時刻で逆算すると PIT 違反になる。ここで固定するのは
**その時点で認識していた情報だけで決定時刻が決まる**ことと、
**違反を黙って除外せず失敗させる**こと。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from predictor.pit_t10 import (
    StartTimeHistory,
    decision_time,
    start_time_history,
    t10_market,
)

RACE = {"race_year": "2026", "race_month_day": "0920", "track_code": "05",
        "kaiji": "01", "nichiji": "01", "race_num": "11"}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE start_time_changes (
            race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
            nichiji TEXT, race_num TEXT, announced_time TEXT,
            new_start_time TEXT, old_start_time TEXT)""")
    conn.execute("""
        CREATE TABLE odds_snapshots (
            race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
            nichiji TEXT, race_num TEXT, horse_num TEXT, fetched_at TEXT,
            announced_at TEXT, win_odds INTEGER, win_popularity INTEGER,
            source TEXT)""")
    return conn


def _add_change(conn, announced: str, new: str, old: str) -> None:
    conn.execute(
        "INSERT INTO start_time_changes VALUES (?,?,?,?,?,?,?,?,?)",
        (*[RACE[k] for k in ("race_year", "race_month_day", "track_code",
                             "kaiji", "nichiji", "race_num")],
         announced, new, old))


def _add_odds(conn, fetched_at: str, odds_map: dict[str, int],
              announced_at: str | None = None) -> None:
    for hn, o in odds_map.items():
        conn.execute(
            "INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (*[RACE[k] for k in ("race_year", "race_month_day", "track_code",
                                 "kaiji", "nichiji", "race_num")],
             hn, fetched_at, announced_at, o, None, "0B31"))


# ---------------------------------------------------------------------------
# 発走時刻変更の履歴
# ---------------------------------------------------------------------------

def test_change_known_before_t10_moves_the_decision_time():
    """変更が T−10 より前に発表されていれば、基準は新しい発走時刻になる。

    ユーザ指示の例: 当初 15:40 (T−10 = 15:30)。15:28 に 15:45 へ変更。
    15:28 ≤ 15:30 なので、15:30 の時点で 15:45 を知っている → 基準は 15:35。
    """
    conn = _conn()
    _add_change(conn, "09201528", "1545", "1540")
    race = dict(RACE, start_time="1545")          # races は変更後の現在値を持つ

    target, start_used = decision_time(conn, race)

    assert start_used == datetime(2026, 9, 20, 15, 45)
    assert target == datetime(2026, 9, 20, 15, 35)
    conn.close()


def test_change_announced_after_t10_does_not_move_it():
    """変更の発表が T−10 より後なら、その時点では知らないので基準は動かない。

    **ここが PIT の核心**。結果データから「実際は 15:45 だった」と知って
    過去の基準を書き換えてはいけない。
    """
    conn = _conn()
    _add_change(conn, "09201538", "1545", "1540")   # 15:38 発表 = T−10 (15:30) より後
    race = dict(RACE, start_time="1545")

    target, start_used = decision_time(conn, race)

    assert start_used == datetime(2026, 9, 20, 15, 40), (
        "発表前の変更を既知として扱っている = PIT 違反")
    assert target == datetime(2026, 9, 20, 15, 30)
    conn.close()


def test_no_change_uses_scheduled_time():
    conn = _conn()
    race = dict(RACE, start_time="1540")

    target, start_used = decision_time(conn, race)

    assert start_used == datetime(2026, 9, 20, 15, 40)
    assert target == datetime(2026, 9, 20, 15, 30)
    conn.close()


def test_history_reconstructs_what_was_known_at_each_moment():
    hist = StartTimeHistory(
        scheduled=datetime(2026, 9, 20, 15, 40),
        changes=[(datetime(2026, 9, 20, 15, 28), datetime(2026, 9, 20, 15, 45)),
                 (datetime(2026, 9, 20, 15, 38), datetime(2026, 9, 20, 15, 50))])

    assert hist.known_at(datetime(2026, 9, 20, 15, 20)) == datetime(2026, 9, 20, 15, 40)
    assert hist.known_at(datetime(2026, 9, 20, 15, 30)) == datetime(2026, 9, 20, 15, 45)
    assert hist.known_at(datetime(2026, 9, 20, 15, 39)) == datetime(2026, 9, 20, 15, 50)


def test_unknown_start_time_is_missing_not_guessed():
    conn = _conn()
    target, start_used = decision_time(conn, dict(RACE, start_time=""))
    assert target is None and start_used is None
    conn.close()


# ---------------------------------------------------------------------------
# オッズの選択規則
# ---------------------------------------------------------------------------

def test_latest_before_decision_time_is_used_not_the_closest():
    """決定時刻「以前で最新」を採る。決定時刻より後を「近いから」で採らない。"""
    conn = _conn()
    race = dict(RACE, start_time="1540")            # 決定時刻 = 15:30
    _add_odds(conn, "2026-09-20T15:20:00", {"01": 25, "02": 40})
    _add_odds(conn, "2026-09-20T15:29:00", {"01": 30, "02": 35})   # 採用
    _add_odds(conn, "2026-09-20T15:31:00", {"01": 20, "02": 50})   # 決定時刻より後

    m = t10_market(conn, race)

    assert m is not None
    assert m.odds_received_at == "2026-09-20T15:29:00"
    assert m.odds["01"] == pytest.approx(3.0), "15:31 の値を採ってはいけない"
    conn.close()


def test_missing_is_missing_not_backfilled():
    """決定時刻以前のオッズが 1 件も無ければ欠損。後続値で埋めない。"""
    conn = _conn()
    race = dict(RACE, start_time="1540")
    _add_odds(conn, "2026-09-20T15:35:00", {"01": 25})   # 決定時刻より後だけ

    assert t10_market(conn, race) is None, "後続値で補完している"
    conn.close()


# ---------------------------------------------------------------------------
# T−10 Market Implied Probability (憲法 Phase 0.5-2)
# ---------------------------------------------------------------------------

def test_implied_probability_is_normalised_within_the_race():
    conn = _conn()
    race = dict(RACE, start_time="1540")
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 20, "02": 40, "03": 100})

    m = t10_market(conn, race)

    assert sum(m.implied.values()) == pytest.approx(1.0)
    assert m.implied["01"] > m.implied["02"] > m.implied["03"]
    conn.close()


def test_overround_before_normalisation_is_kept():
    """正規化前の合計 (控除率の目安) を保存すること。

    パリミュチュエルなので「市場の真の確率」ではない。後から市場状態を
    再現できるよう、正規化前の値も残す。
    """
    conn = _conn()
    race = dict(RACE, start_time="1540")
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 20, "02": 40})   # 1/2 + 1/4

    m = t10_market(conn, race)

    assert m.overround == pytest.approx(0.75)
    conn.close()


def test_market_rank_is_by_odds():
    conn = _conn()
    race = dict(RACE, start_time="1540")
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 100, "02": 20, "03": 40})

    m = t10_market(conn, race)

    assert m.market_rank["02"] == 1 and m.market_rank["03"] == 2
    conn.close()


def test_all_required_fields_are_saved():
    """憲法 Phase 0.5-2 が保存を求める項目が揃っていること。"""
    conn = _conn()
    race = dict(RACE, start_time="1540")
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 20, "02": 40},
              announced_at="09201524")

    m = t10_market(conn, race)

    assert m.odds and m.implied and m.market_rank
    assert m.overround > 0
    assert m.decision_time == "2026-09-20T15:30:00"
    assert m.odds_received_at == "2026-09-20T15:25:00"
    assert m.odds_observed_at == "2026-09-20T15:24"
    conn.close()


# ---------------------------------------------------------------------------
# 監査: 違反は黙って除外せず、見えるようにする
# ---------------------------------------------------------------------------

def test_observation_after_decision_time_is_flagged():
    """提供元の発表時刻が決定時刻より後なら違反として記録すること。

    黙って除外するとデータ品質の問題が見えなくなる。
    """
    conn = _conn()
    race = dict(RACE, start_time="1540")
    # 受信は 15:25 だが、提供元は 15:32 発表と言っている (異常)
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 20}, announced_at="09201532")

    m = t10_market(conn, race)

    assert m is not None, "違反でも None にせず、見えるように返す"
    assert not m.ok
    assert any("発表時刻" in v for v in m.violations)
    conn.close()


def test_clean_sample_has_no_violations():
    conn = _conn()
    race = dict(RACE, start_time="1540")
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 20, "02": 40},
              announced_at="09201524")

    m = t10_market(conn, race)

    assert m.ok and m.violations == []
    conn.close()


# ---------------------------------------------------------------------------
# 監査が空振りしていないかの対照実験
# ---------------------------------------------------------------------------

def test_audit_actually_detects_a_planted_violation():
    """監査が「違反を検出できること」自体を確かめる。

    2026-09-17 に、発表時刻の遡及が (レース, 馬) 単位で埋まっていたため、
    51 枚のスナップ全部に同じ発表時刻 (朝の値) が入り、**監査が自明に通って
    「違反 0 件」という嘘の結果**が出た。検出力ゼロの監査で「合格」と言うのは
    無意味なので、わざと違反を仕込んで落ちることを固定する。
    """
    conn = _conn()
    race = dict(RACE, start_time="1540")            # 決定時刻 = 15:30

    # 正常なサンプル: 発表 15:24 / 受信 15:25 → 違反なし
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 20}, announced_at="09201524")
    clean = t10_market(conn, race)
    assert clean.ok, "正常なサンプルで違反が出ている"

    # 違反を仕込む: 同じ受信時刻の行の発表時刻だけを決定時刻より後にする
    conn.execute("UPDATE odds_snapshots SET announced_at='09201545'")
    planted = t10_market(conn, race)

    assert not planted.ok, "仕込んだ違反を検出できていない = 監査が空振り"
    assert any("発表時刻" in v for v in planted.violations)
    conn.close()


def test_each_snapshot_keeps_its_own_observation_time():
    """スナップショットごとに別々の発表時刻を持てること。

    全部に同じ値を入れると、後のオッズが「朝に発表された」ことになり、
    監査が意味を失う。
    """
    conn = _conn()
    race = dict(RACE, start_time="1540")
    _add_odds(conn, "2026-09-20T08:45:00", {"01": 25}, announced_at="09200843")
    _add_odds(conn, "2026-09-20T15:25:00", {"01": 20}, announced_at="09201524")

    m = t10_market(conn, race)

    assert m.odds_received_at == "2026-09-20T15:25:00"
    assert m.odds_observed_at == "2026-09-20T15:24", (
        "採用したスナップの発表時刻ではなく別の値を拾っている")
    conn.close()
