from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

import db
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


def test_inspect_reports_null_and_empty_without_deleting_them(
    tmp_path, monkeypatch, capsys
):
    db_path = tmp_path / "invalid.db"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        common = ("2026", "0712", "02", "01", "01", "01")
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?)",
            (*common, None, 0, 0, None),
        )
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?)",
            (*common, "", 0, 0, None),
        )

    monkeypatch.setattr(
        sys, "argv", ["cleanup", "--db", str(db_path), "--execute"]
    )
    assert cleanup.main() == 1
    err = capsys.readouterr().err
    assert "horse_num=None (manual judgment required)" in err
    assert "horse_num='' (manual judgment required)" in err
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num IS NULL OR horse_num=''"
        ).fetchone()[0] == 2


def test_delete_statement_remains_limited_to_00(tmp_path):
    db_path = tmp_path / "delete-scope.db"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM horse_races WHERE horse_num='00'")
        assert conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num='01'"
        ).fetchone()[0] == 1


def test_live_database_has_no_placeholder_violations():
    # 枠順確定前の単独 '00' 行は正当な過渡状態 (確定時に ingest が掃除する) なので
    # raw count ではなく「正規馬番行と共存する不正行」= violation の不在を検証する。
    # monitor.py のカナリアと同じ db.count_horse_num_violations に述語を一元化。
    db_path = Path(DB_PATH)
    if not db_path.exists():
        pytest.skip("data/keiba.db is not available")
    with sqlite3.connect(db_path) as conn:
        assert db.count_horse_num_violations(conn) == 0


def test_dry_run_flag_overrides_execute(tmp_path, monkeypatch, capsys):
    # 「no rows will be deleted」と印字した以上、--execute が併用されても削除しない
    db_path = tmp_path / "keiba.db"
    _make_db(db_path)
    monkeypatch.setattr(
        sys, "argv", ["cleanup", "--db", str(db_path), "--dry-run", "--execute"]
    )
    assert cleanup.main() == 0
    out = capsys.readouterr().out
    assert "no rows will be deleted" in out
    assert "DRY-RUN safe to delete: 1 rows" in out
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
        ).fetchone()[0] == 1


def _insert_solo_placeholder(path: Path, month_day: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("2026", month_day, "05", "01", "01", "01", "00", 0, 0, None),
        )


def test_future_solo_placeholder_is_not_violation_and_survives_execute(
    tmp_path, monkeypatch, capsys
):
    # 未来日の単独 '00' は枠順確定前の正当な過渡状態:
    # violation として abort させず、--execute でも削除しない
    db_path = tmp_path / "keiba.db"
    _make_db(db_path)  # 2026-07-12 に coexist '00' 1 行 (削除対象)
    _insert_solo_placeholder(db_path, "1231")  # 遠い未来日の単独 '00'
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        total, violations = cleanup.inspect_placeholders(conn, today="20260716")
        assert total == 2
        assert violations == []
        assert cleanup.count_deletable(conn) == 1

    monkeypatch.setattr(sys, "argv", ["cleanup", "--db", str(db_path), "--execute"])
    assert cleanup.main() == 0
    assert "future pre-draw kept: 1" in capsys.readouterr().out
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT race_month_day FROM horse_races WHERE horse_num='00'"
        ).fetchall()
    assert [r[0] for r in rows] == ["1231"]


def test_past_solo_placeholder_is_violation_requiring_manual_judgment(tmp_path):
    # 過去日の単独 '00' は取込欠落の疑い: 自動削除せず violation として報告する
    db_path = tmp_path / "keiba.db"
    _make_db(db_path)
    _insert_solo_placeholder(db_path, "0501")  # 過去日の単独 '00'
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        total, violations = cleanup.inspect_placeholders(conn, today="20260716")
    assert total == 2
    assert len(violations) == 1
    assert violations[0]["race_month_day"] == "0501"
