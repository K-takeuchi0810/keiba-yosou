"""T−10 取得元の感度分析 (scripts/t10_source_sensitivity.py) の純関数と等価性の契約。

感度分析は「入力の T−10 市場だけを差し替える」ことが前提。raw からの選択が本番の
`t10_market` と違う規則で動いたり、組み立ての写しが本番から黙ってずれたりすると、
取得元の差ではなく実装の差を測ってしまう。ここではその前提を固定する。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from predictor.pit_t10 import t10_market
from scripts import t10_source_sensitivity as tss

RACE = {"race_year": "2026", "race_month_day": "0808", "track_code": "04",
        "kaiji": "02", "nichiji": "05", "race_num": "03", "start_time": "1040"}
CUT = datetime(2026, 8, 8, 10, 30)          # 発走 10:40 − 10 分


def _state(source, received, votes=100, odds=None, announced="08081029", file=None):
    return {"source": source, "received": received, "received_epoch": received,
            "received_origin": "mtime_live", "votes": votes, "announced": announced,
            "odds": odds or {"01": 25, "02": 40}, "file": file or f"{source}_{received:%H%M%S}"}


# --- 選択規則 -------------------------------------------------------------------

def test_pick_includes_exactly_the_cutoff_and_excludes_one_second_after():
    at = _state("0B31", CUT)
    late = _state("0B31", CUT + timedelta(seconds=1), votes=200)
    got, _ = tss.pick([at, late], CUT, ("0B31",))
    assert got is at


def test_pick_does_not_step_back_past_the_latest_state():
    """最新の枚に odds の無い馬がいても、それより前の揃った枚へは遡らない (t10_market と同じ)。"""
    full = _state("0B31", CUT - timedelta(minutes=5), odds={"01": 25, "02": 40, "03": 90})
    partial = _state("0B31", CUT - timedelta(minutes=1), odds={"01": 24, "02": 41})
    got, _ = tss.pick([full, partial], CUT, ("0B31",))
    assert got is partial


@pytest.mark.parametrize("order", [0, 1])
def test_same_second_takes_the_larger_vote_total_regardless_of_input_order(order):
    a = _state("0B30", CUT, votes=300)
    b = _state("0B31", CUT, votes=200)
    states = [a, b] if order == 0 else [b, a]
    got, tie = tss.pick(states, CUT, ("0B30", "0B31"))
    assert got is a and tie


def test_same_second_equal_votes_prefers_0B31_and_missing_votes_lose():
    a = _state("0B30", CUT, votes=200)
    b = _state("0B31", CUT, votes=200)
    assert tss.pick([a, b], CUT, ("0B30", "0B31"))[0] is b
    c = _state("0B30", CUT, votes=None)
    d = _state("0B31", CUT, votes=1)
    assert tss.pick([c, d], CUT, ("0B30", "0B31"))[0] is d


def test_pick_can_use_the_alternative_timestamp():
    s = _state("0B31", CUT + timedelta(seconds=1))
    s["received_epoch"] = CUT
    assert tss.pick([s], CUT, ("0B31",))[0] is None
    assert tss.pick([s], CUT, ("0B31",), key="received_epoch")[0] is s


@pytest.mark.parametrize("b_change,want", [
    ({}, "matched_same_state"),
    ({"odds": {"01": 26, "02": 40}}, "same_total_discordant"),
    ({"votes": 101}, "different_state"),
    ({"announced": "08081028"}, "different_announced"),
])
def test_classify(b_change, want):
    a = _state("0B30", CUT)
    b = dict(_state("0B31", CUT), **b_change)
    assert tss.classify(a, b) == want
    assert tss.classify(a, None) == "one_source_missing"


# --- 受信時刻の由来 ----------------------------------------------------------------

def test_received_origin_matches_the_production_writer():
    epoch = int(datetime(2026, 6, 28, 10, 0, 0).timestamp())
    mtime = epoch + 0.7
    assert tss.raw_received("0B31", "20260628", epoch, mtime) == (
        datetime.fromtimestamp(epoch), "epoch_backfill")
    got, origin = tss.raw_received("0B31", "20260704", epoch, mtime + 1)
    assert origin == "mtime_live" and got == datetime.fromtimestamp(epoch + 1)   # 秒未満切り捨て
    assert tss.raw_received("0B30", "20260628", epoch, mtime)[1] == "mtime_live"


# --- 鮮度の境界 ---------------------------------------------------------------------

def test_freshness_boundary_is_inclusive_like_the_evaluation():
    lim = tss.moe.DEFAULT_MAX_LEAD_MINUTES
    assert tss.is_fresh({"lead_min": lim})
    assert not tss.is_fresh({"lead_min": lim + 0.01})
    rows = [{"lead_min": lim, "p_offset": 0.2, "p_t10": 0.1},
            {"lead_min": lim + 1, "p_offset": 0.9, "p_t10": 0.1}]
    assert tss.ratio_stats(rows)["n"] == 1


# --- 本番との等価性 -------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE start_time_changes (race_year TEXT, race_month_day TEXT,
        track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT, announced_time TEXT,
        new_start_time TEXT, old_start_time TEXT)""")
    conn.execute("""CREATE TABLE odds_snapshots (race_year TEXT, race_month_day TEXT,
        track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT,
        fetched_at TEXT, announced_at TEXT, win_odds INTEGER, win_popularity INTEGER,
        source TEXT)""")
    return conn


def _odds(conn, race, fetched, odds, announced="08081029", source="0B31"):
    for h, o in odds.items():
        conn.execute("INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (*[race[k] for k in ("race_year", "race_month_day", "track_code",
                                          "kaiji", "nichiji", "race_num")],
                      h, fetched, announced, o, None, source))


def _races(conn):
    races = []
    for i, case in enumerate(("normal", "partial_latest", "none", "after_only",
                              "announced_late", "mixed_second", "start_change")):
        race = dict(RACE, race_num=f"{i + 1:02d}")
        if case == "normal":
            _odds(conn, race, "2026-08-08T10:25:00", {"01": 25, "02": 40})
        elif case == "partial_latest":
            _odds(conn, race, "2026-08-08T10:20:00", {"01": 25, "02": 40, "03": 90})
            _odds(conn, race, "2026-08-08T10:29:59", {"01": 24, "02": 41})
        elif case == "after_only":
            _odds(conn, race, "2026-08-08T10:30:01", {"01": 25})
        elif case == "announced_late":
            _odds(conn, race, "2026-08-08T10:29:00", {"01": 25, "02": 40}, announced="08081031")
        elif case == "mixed_second":
            _odds(conn, race, "2026-08-08T10:28:00", {"01": 25}, source="0B30")
            _odds(conn, race, "2026-08-08T10:28:00", {"02": 40}, announced=None)
        elif case == "start_change":
            conn.execute("INSERT INTO start_time_changes VALUES (?,?,?,?,?,?,?,?,?)",
                         (*[race[k] for k in ("race_year", "race_month_day", "track_code",
                                              "kaiji", "nichiji", "race_num")],
                          "08081020", "1045", "1040"))
            race["start_time"] = "1045"
            _odds(conn, race, "2026-08-08T10:34:00", {"01": 25, "02": 40})
        races.append(race)
    return races


def test_db_market_is_equivalent_to_production_on_edge_cases():
    conn = _conn()
    races = _races(conn)
    out = tss.production_equivalence(conn, races)
    assert out["production_equivalence_mismatched_races"] == 0
    assert out["production_equivalence_checked_races"] == len(races)
    # 最新の枚の馬だけで組み立て、揃った前の枚へは遡らない
    prod = t10_market(conn, races[1])
    assert set(prod.odds) == {"01", "02"}
    assert tss.db_market(conn, races[1])[0].odds == prod.odds


def test_equivalence_gate_stops_when_the_copy_drifts(monkeypatch):
    """写しの組み立てが本番からずれたら、感度分析を始めずに止まること。"""
    conn = _conn()
    races = _races(conn)
    real = tss.build_market

    def drifted(*a, **k):
        m = real(*a, **k)
        m.violations = []          # 本番にある違反検査を 1 つ落とした写し
        return m
    monkeypatch.setattr(tss, "build_market", drifted)
    with pytest.raises(SystemExit):
        tss.production_equivalence(conn, races)


# --- coverage 閾値の感度 ------------------------------------------------------------

def _summary(n, primary=False, money=None, ge175=0, rejected=()):
    return {"coverage": {"fresh_le_30m": {"n_races": n}},
            "verdict": {"primary": primary, "money": money, "rejected_by": list(rejected)},
            "p_offset_over_p_market": {"ge_1_75": ge175}}


def test_threshold_table_classifies_a_series_just_below_half():
    s = {"original_mixed": _summary(626),
         "raw_0B30": _summary(300, rejected=("古いオッズにだけ勝っている",))}
    t = tss.threshold_table(s)["by_threshold"]
    assert t["45%"]["raw_0B30"]["judged"] and t["45%"]["raw_0B30"]["same_conclusion"] is False
    assert t["45%"]["raw_0B30"]["differs_in"] == ["rejected_by"]
    assert not t["50%"]["raw_0B30"]["judged"] and t["50%"]["raw_0B30"]["same_conclusion"] is None
