"""webapp の予想生成非干渉保証 (db.open_db_readonly) のテスト。

保証すること:
  1. readonly 接続からは INSERT/UPDATE/DDL が全て失敗する (書込み構造的不可)。
  2. readonly 接続でも webapp のルーティング/描画は正常動作する。
  3. DB ファイルが無い場合は FileNotFoundError (空ファイルを勝手に作らない)。
  4. open_db (migration あり) と違い、readonly 接続はスキーマに触れない。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db import init_db, open_db_readonly


def _make_db(tmp_path: Path) -> Path:
    p = tmp_path / "ro_test.db"
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO races (race_year, race_month_day, track_code, kaiji, nichiji, race_num,"
        " distance, track_type_code) VALUES ('2025','0518','05','01','01','01',1600,'11')"
    )
    conn.commit()
    conn.close()
    return p


def test_readonly_blocks_all_writes(tmp_path):
    p = _make_db(tmp_path)
    with open_db_readonly(p) as conn:
        # SELECT は通る
        n = conn.execute("SELECT COUNT(*) FROM races").fetchone()[0]
        assert n == 1
        # INSERT / UPDATE / DELETE / DDL は全て拒否される
        for sql in (
            "INSERT INTO races (race_year, race_month_day, track_code, kaiji, nichiji, race_num) "
            "VALUES ('2025','0519','05','01','01','02')",
            "UPDATE races SET distance = 2000",
            "DELETE FROM races",
            "ALTER TABLE races ADD COLUMN hacked INTEGER",
            "CREATE TABLE evil (x)",
        ):
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(sql)
    # 接続を閉じた後も行数不変 (書込みが一切成立していない)
    conn2 = sqlite3.connect(p)
    assert conn2.execute("SELECT COUNT(*) FROM races").fetchone()[0] == 1
    conn2.close()


def test_readonly_missing_db_raises_without_creating(tmp_path):
    p = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        with open_db_readonly(p):
            pass
    assert not p.exists()  # mode=ro は空ファイルを作らない


def test_server_routes_work_on_readonly(tmp_path):
    """server の全ルートが readonly 接続で描画できる (書込み不要の証明)。"""
    import types

    from webapp import server

    p = _make_db(tmp_path)
    handler = types.SimpleNamespace(_route=server.Handler._route.__get__(object()))
    with open_db_readonly(p) as conn:
        assert "開催日一覧" in handler._route(conn, "/", {})
        assert "傾向集計" in handler._route(conn, "/trends", {"factor": "waku"})
        today = handler._route(conn, "/today", {"date": "20250518", "factor": "waku"})
        assert "当日傾向速報" in today
