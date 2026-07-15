from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from config import DB_PATH
from scripts import cleanup_placeholder_horse_rows as cleanup


def _make_db(path: Path, *, unsafe: bool = False) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE horse_races (
              race_year TEXT, race_month_day TEXT, track_code TEXT,
              kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT,
              confirmed_order INTEGER, win_odds INTEGER, odds_fetched_at TEXT
            )
            """
        )
        common = ("2026", "0712", "02", "01", "01", "01")
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?)",
            (*common, "00", 1 if unsafe else 0, 0, None),
        )
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?)",
            (*common, "01", 1, 229, "2026-07-12T10:00:00"),
        )


def test_cleanup_dry_run_then_execute_creates_backup(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "keiba.db"
    backup_path = tmp_path / "keiba.db.bak_20260715"
    _make_db(db_path)

    monkeypatch.setattr(sys, "argv", ["cleanup", "--db", str(db_path)])
    assert cleanup.main() == 0
    assert "DRY-RUN safe to delete: 1 rows" in capsys.readouterr().out
    assert not backup_path.exists()

    monkeypatch.setattr(
        sys,
        "argv",
        ["cleanup", "--db", str(db_path), "--execute"],
    )
    assert cleanup.main() == 0
    assert backup_path.exists()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
        ).fetchone()[0] == 0
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
        ).fetchone()[0] == 1


def test_cleanup_aborts_when_placeholder_is_not_safe(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "unsafe.db"
    _make_db(db_path, unsafe=True)
    monkeypatch.setattr(
        sys,
        "argv",
        ["cleanup", "--db", str(db_path), "--execute"],
    )

    assert cleanup.main() == 1
    assert "unsafe placeholder rows" in capsys.readouterr().err
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
        ).fetchone()[0] == 1


def test_live_database_has_no_placeholder_horse_rows():
    db_path = Path(DB_PATH)
    if not db_path.exists():
        pytest.skip("data/keiba.db is not available")
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
        ).fetchone()[0]
    assert count == 0
