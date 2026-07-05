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


def test_fallback_path_still_blocks_writes(tmp_path, monkeypatch):
    """F1 (2026-07-05 検証監査): mode=ro が使えない環境 (WAL -shm 制約) の
    フォールバック経路 (rw ハンドル + query_only) でも書込みが拒否されること。"""
    import db as db_mod

    p = _make_db(tmp_path)
    real_connect = sqlite3.connect

    def fake_connect(target, *args, **kwargs):
        # URI mode=ro を強制的に失敗させ、フォールバック分岐へ落とす
        if isinstance(target, str) and target.startswith("file:") and "mode=ro" in target:
            raise sqlite3.OperationalError("simulated -shm readonly failure")
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(db_mod.sqlite3, "connect", fake_connect)
    with db_mod.open_db_readonly(p) as conn:
        assert conn.execute("SELECT COUNT(*) FROM races").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM races")


def test_no_query_only_off_in_observer_code():
    """F2: 観察系コード (webapp/db) に query_only=OFF が混入していないことの不変条件。
    フォールバック経路の保証は SQL 層ガードのみなので、解除文の混入は保証を壊す。"""
    root = Path(__file__).resolve().parent.parent
    targets = list((root / "webapp").rglob("*.py")) + [root / "db.py"]
    for f in targets:
        # 実行文のみ検知 (docstring/コメント内の注意書きは許容)
        src = f.read_text(encoding="utf-8").replace(" ", "").lower()
        for quote in ('"', "'"):
            assert f'execute({quote}pragmaquery_only=off' not in src, \
                f"{f} に query_only=OFF の実行文が混入"
    # server は readonly 経路のみ使用 (migration 付き open_db を import しない)
    server_src = (root / "webapp" / "server.py").read_text(encoding="utf-8")
    assert "open_db_readonly" in server_src
    assert "from db import open_db\n" not in server_src


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
