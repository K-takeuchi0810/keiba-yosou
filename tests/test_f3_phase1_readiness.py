from __future__ import annotations

import sqlite3

import pytest

from scripts.f3_phase1_readiness import (
    _build_summary,
    _validate_window,
    analyze_race,
)


RACE = {
    "race_year": "2026",
    "race_month_day": "0718",
    "track_code": "01",
    "kaiji": "01",
    "nichiji": "01",
    "race_num": "01",
    "start_time": "1300",
    "has_entries": 1,
}


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE odds_snapshots (
            race_year TEXT, race_month_day TEXT, track_code TEXT,
            kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT,
            fetched_at TEXT, win_odds INTEGER, win_popularity INTEGER,
            source TEXT
        )
        """
    )
    return conn


def _insert(conn: sqlite3.Connection, fetched_at: str | None, horse_num: str) -> None:
    conn.execute(
        "INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026", "0718", "01", "01", "01", "01", horse_num,
         fetched_at, 50, 1, "test"),
    )


def test_analyze_race_counts_distinct_pit_timestamps() -> None:
    conn = _connection()
    for fetched_at in ("2026-07-18T11:30:00", "2026-07-18T12:40:00"):
        _insert(conn, fetched_at, "01")
        _insert(conn, fetched_at, "02")
    _insert(conn, "2026-07-18T12:55:00", "01")
    _insert(conn, None, "01")

    result = analyze_race(conn, RACE)

    assert result["n_usable"] == 2
    assert result["earliest_lead_min"] == 90.0
    assert result["latest_lead_min"] == 20.0
    assert result["drift_computable"] is True
    assert result["wide_drift"] is True
    assert result["post_time_band"] == "afternoon"


def test_analyze_race_requires_two_different_times() -> None:
    conn = _connection()
    _insert(conn, "2026-07-18T11:30:00", "01")
    _insert(conn, "2026-07-18T11:30:00", "02")

    result = analyze_race(conn, RACE)

    assert result["n_usable"] == 1
    assert result["drift_computable"] is False
    assert result["wide_drift"] is False


def test_sealed_window_is_rejected_before_query() -> None:
    _validate_window("20260704", "20260930")
    with pytest.raises(ValueError, match="must remain fixed"):
        _validate_window("20260703", "20260930")
    with pytest.raises(ValueError, match="sealed holdout access denied"):
        _validate_window("20260704", "20261001")


def test_summary_uses_races_with_entries_as_rate_denominator() -> None:
    all_races = [dict(RACE), dict(RACE, race_num="02", has_entries=0)]
    measurements = [{
        "race_id": "one",
        "race_date": "20260718",
        "post_time_band": "afternoon",
        "track_scope": "jra_central",
        "n_usable": 2,
        "earliest_lead_min": 90.0,
        "drift_computable": True,
        "wide_drift": True,
    }]

    daily, summary = _build_summary(all_races, measurements)

    assert summary["total_races"] == 2
    assert summary["races_with_entries"] == 1
    assert summary["drift_computable_rate"] == 1.0
    assert daily[0]["total_races"] == 2
    assert daily[0]["races_with_entries"] == 1
    assert summary["by_track_scope"]["jra_central"]["drift_computable"] == 1
    assert summary["by_track_scope"]["other"]["races_with_entries"] == 0


def test_audit_script_source_is_ascii() -> None:
    from scripts import f3_phase1_readiness as module

    source = open(module.__file__, "rb").read()
    source.decode("ascii")
