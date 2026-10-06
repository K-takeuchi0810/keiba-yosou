"""研究の窓の関所 (`scripts/research_window.py`、docs/LOCKBOX_GOVERNANCE.md、2026-10-06) の契約。

- 期間は development (〜2024) / consumed (2025〜RESERVED_FROM の前日) / reserved (RESERVED_FROM〜FRESH_FROM の前日) / fresh (FRESH_FROM〜)
- reserved はどの目的でも読まない。FRESH_FROM が未確定の間は RESERVED_FROM 以降すべてが reserved
- 件数の点検の SQL は結果の列を含まず、返る列は allow-list と完全一致
- 研究の読み込み (group_a / c_prime の load_races) は関所を通る。本番の封印 (SEALED_FROM) は変えない
"""
from __future__ import annotations

import sqlite3

import pytest

import config
from scripts import c_prime as cp
from scripts import group_a as ga
from scripts import research_window as rw


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(config, "FRESH_FROM", "20261010")


def test_the_production_seal_is_untouched():
    assert config.SEALED_FROM is None and config.SEALED_UNTIL is None


def test_constants_hold_today():
    rw.check_constants()
    assert config.RESERVED_FROM == config.CONFIRM_FROM == "20260914"
    assert config.RESERVED_FROM > config.consumed_until()
    assert config.FRESH_FROM is None or config.FRESH_FROM >= config.FRESH_FROM_NOT_BEFORE


@pytest.mark.parametrize("frm,to,want", [
    ("20220101", "20241231", {"development"}),
    ("20241231", "20250101", {"development", "consumed"}),
    ("20250601", "20251231", {"consumed"}),
    ("20260913", "20260913", {"consumed"}),
    ("20260914", "20260914", {"reserved"}),
    ("20261009", "20261009", {"reserved"}),
    ("20261010", "20261010", {"fresh"}),
    ("20260913", "20261010", {"consumed", "reserved", "fresh"}),
])
def test_period_boundaries_with_fresh_fixed(fresh, frm, to, want):
    assert rw.periods_spanned(frm, to) == want


def test_everything_from_reserved_is_reserved_while_fresh_is_unfixed():
    assert config.FRESH_FROM is None
    assert rw.periods_spanned("20270101", "20270101") == {"reserved"}
    assert rw.periods_spanned("20260913", "20260913") == {"consumed"}


def test_development_reads_only_development():
    assert rw.check("20210101", "20241231", purpose="development", context="t")["periods"] == ["development"]
    with pytest.raises(rw.ResearchWindowError, match="consumed"):
        rw.check("20220101", "20250101", purpose="development", context="t")


def test_reproduce_consumed_needs_what_it_reproduces_and_stops_before_reserved():
    rw.check("20210101", "20251231", purpose="reproduce_consumed", context="t", reproduces="group_a primary")
    with pytest.raises(rw.ResearchWindowError, match="reproduces"):
        rw.check("20250101", "20251231", purpose="reproduce_consumed", context="t")
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        rw.check("20250101", "20260914", purpose="reproduce_consumed", context="t", reproduces="x")


@pytest.mark.parametrize("purpose", rw.PURPOSES)
def test_reserved_is_refused_for_every_purpose(fresh, purpose):
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        rw.check("20260920", "20260920", purpose=purpose, context="t", reads_outcomes=False, reproduces="x")


def test_count_only_reads_fresh_without_outcomes(fresh):
    rw.check("20261010", "20261231", purpose="lockbox_count_only", context="t", reads_outcomes=False)
    with pytest.raises(rw.ResearchWindowError, match="reads_outcomes"):
        rw.check("20261010", "20261231", purpose="lockbox_count_only", context="t")
    with pytest.raises(rw.ResearchWindowError, match="consumed"):
        rw.check("20250101", "20250102", purpose="lockbox_count_only", context="t", reads_outcomes=False)


def test_fresh_is_refused_for_development_and_reproduction(fresh):
    for purpose in ("development", "reproduce_consumed"):
        with pytest.raises(rw.ResearchWindowError, match="fresh"):
            rw.check("20261010", "20261010", purpose=purpose, context="t", reproduces="x")


def test_primary_after_unlock_is_not_available_yet(fresh):
    with pytest.raises(rw.ResearchWindowError, match="開封の手順"):
        rw.check("20261010", "20261010", purpose="primary_after_unlock", context="t")


def test_unknown_purpose_missing_context_and_bad_dates_stop():
    with pytest.raises(rw.ResearchWindowError, match="purpose"):
        rw.check("20220101", "20220102", purpose="explore", context="t")
    with pytest.raises(rw.ResearchWindowError, match="context"):
        rw.check("20220101", "20220102", purpose="development", context="")
    with pytest.raises(ValueError):
        rw.check("2022-01-01", "20220102", purpose="development", context="t")
    with pytest.raises(rw.ResearchWindowError, match=">"):
        rw.check("20220102", "20220101", purpose="development", context="t")


@pytest.mark.parametrize("attr,value,match", [
    ("FRESH_FROM", "20261006", "下限"),
    ("RESERVED_FROM", "20260913", "消費済み"),
])
def test_broken_constants_stop_every_read(monkeypatch, attr, value, match):
    monkeypatch.setattr(config, attr, value)
    with pytest.raises(rw.ResearchWindowError, match=match):
        rw.check("20220101", "20220102", purpose="development", context="t")


# ------------------------------------------------------------------------------------------------ 研究の読み込みの配線

@pytest.mark.parametrize("load", [ga.load_races, cp.load_races])
def test_loaders_refuse_2026_even_with_the_primary_year_flag(load):
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        load(2026, min_year=2021, db_path="unused.db", allow_primary_year=True, primary_purpose="x")


@pytest.mark.parametrize("load", [ga.load_races, cp.load_races])
def test_loaders_pass_the_purpose_to_the_guard(monkeypatch, load):
    seen = []

    def fake(min_year, max_year, **kw):
        seen.append((min_year, max_year, kw["purpose"], kw.get("reproduces")))
        raise rw.ResearchWindowError("stop here")
    monkeypatch.setattr(rw, "check_years", fake)
    with pytest.raises(rw.ResearchWindowError):
        load(2024, min_year=2021, db_path="unused.db")
    with pytest.raises(rw.ResearchWindowError):
        load(2025, min_year=2021, db_path="unused.db", allow_primary_year=True, primary_purpose="why")
    assert seen == [(2021, 2024, "development", None), (2021, 2025, "reproduce_consumed", "why")]


# ------------------------------------------------------------------------------------------------ 件数の点検

def test_count_sql_has_no_result_columns():
    low = rw.count_sql().lower()
    assert not [f for f in rw.FORBIDDEN_FRAGMENTS if f in low]


def test_a_result_column_in_the_count_sql_stops(monkeypatch):
    monkeypatch.setattr(rw, "COUNT_SELECT", rw.COUNT_SELECT + (("r.win_odds", "win_odds"),))
    with pytest.raises(rw.ResearchWindowError, match="結果の列"):
        rw.count_sql()


def _races_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, nichiji TEXT,"
                 " race_num TEXT, track_type_code TEXT, data_div TEXT, payout_secret TEXT)")
    rows = [("2026", "1010", "05", "4", "1", "01", "17", "7", "x"),   # 芝
            ("2026", "1010", "05", "4", "1", "02", "24", "7", "x"),   # ダート
            ("2026", "1010", "05", "4", "1", "03", "54", "7", "x"),   # 障害 → 数えない
            ("2026", "1010", "05", "4", "1", "04", "17", "9", "x"),   # 中止 → 数えない
            ("2026", "1011", "30", "1", "1", "01", "17", "7", "x"),   # 地方 → 数えない
            ("2026", "1011", "08", "4", "2", "01", "17", "1", "x"),   # 発走前 (データ区分 1) も数える
            ("2026", "1009", "05", "4", "1", "01", "17", "7", "x")]   # reserved → 範囲外
    conn.executemany("INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_count_fresh_races_counts_flat_jra_races_only(fresh, tmp_path):
    db = tmp_path / "k.db"
    _races_db(db)
    out = rw.count_fresh_races(db, "20261010", "20261031", context="t")
    assert out["n_flat_races"] == 3 and out["by_day"] == {"20261010": 2, "20261011": 1}
    assert out["window"]["purpose"] == "lockbox_count_only" and out["window"]["reads_outcomes"] is False


def test_count_fresh_races_refuses_reserved_days(fresh, tmp_path):
    db = tmp_path / "k.db"
    _races_db(db)
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        rw.count_fresh_races(db, "20261009", "20261031", context="t")


def test_returned_columns_must_match_the_allow_list(fresh, tmp_path, monkeypatch):
    db = tmp_path / "k.db"
    _races_db(db)
    monkeypatch.setattr(rw, "COUNT_COLUMNS", rw.COUNT_COLUMNS + ("extra",))
    with pytest.raises(rw.ResearchWindowError, match="allow-list"):
        rw.count_fresh_races(db, "20261010", "20261031", context="t")
