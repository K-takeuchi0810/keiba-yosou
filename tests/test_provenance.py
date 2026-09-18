"""予測の出所記録の契約テスト (憲法 Phase 0.5 項目 0)。

## なぜ要るか

> 予測結果すべてに git SHA を記録する / 使用データのバージョンも記録する
> 以後「どのコードがこの予測を出したのか分からない」状態を禁止します。

2026-09-17 時点で、騎手変更・コース変更・発走時刻変更の取り込みが
**未コミットのまま 1 ヶ月以上本番で稼働**しており、その間に出した予測が
どのコードによるものか git から特定できなかった。同じことを繰り返さないよう、
記録を書き込み経路に埋め込み、テストで固定する。
"""
from __future__ import annotations

import sqlite3

import pytest

from predictor import provenance


def _conn_with_log() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE prediction_log (
            generated_at TEXT, race_year TEXT, race_month_day TEXT,
            track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,
            horse_num TEXT, mark TEXT, rank INTEGER, score REAL,
            win_probability REAL, raw_blended_probability REAL,
            win_odds INTEGER, win_popularity INTEGER, confidence TEXT,
            model_version TEXT, calibrator_version TEXT,
            code_version TEXT, data_version TEXT,
            PRIMARY KEY (generated_at, race_year, race_month_day, track_code,
                         kaiji, nichiji, race_num, horse_num))""")
    conn.execute("""
        CREATE TABLE ingested_files (
            filename TEXT, dataspec TEXT, record_count INTEGER, ingested_at TEXT)""")
    return conn


def test_code_version_is_recorded_on_every_prediction():
    """予測 1 行ごとにコード版が入ること。呼び出し側は指定しない。

    引数にすると渡し忘れが起きるので、書き込み関数の中で取る。
    """
    from db import insert_prediction_log

    conn = _conn_with_log()
    race = {"race_year": "2026", "race_month_day": "0920", "track_code": "05",
            "kaiji": "01", "nichiji": "01", "race_num": "01"}
    n = insert_prediction_log(
        conn, race, [{"horse_num": "01", "mark": "◎", "rank": 1, "score": 80.0}],
        generated_at="2026-09-20T08:00:00", model_version="v6")

    assert n == 1
    row = conn.execute(
        "SELECT code_version, data_version FROM prediction_log").fetchone()
    assert row[0], "コード版が空 = どのコードが出した予測か分からない"
    assert row[1], "データ版が空 = どの状態のデータで出したか分からない"
    conn.close()


def test_dirty_working_tree_is_marked():
    """未コミットの変更があるときは版に印が付くこと。

    印が無いと、その SHA が「実際に動いたコード」だと誤解される。
    1 ヶ月続いた事故がまさにそれ。
    """
    provenance.git_dirty.cache_clear()
    provenance.git_sha.cache_clear()
    try:
        provenance.git_dirty = lambda: True          # type: ignore[assignment]
        assert provenance.code_version().endswith("-dirty")
    finally:
        # 元に戻す (lru_cache 付きの本物を復元)
        import importlib
        importlib.reload(provenance)


def test_data_version_changes_when_data_changes():
    """取り込みが進んだらデータ版が変わること。

    同じ値なら同じデータ状態、という識別子として機能する必要がある。
    """
    conn = _conn_with_log()
    before = provenance.data_version(conn)

    conn.execute(
        "INSERT INTO ingested_files VALUES ('a.jvd','RACE',10,'2026-09-20 10:00:00')")
    after = provenance.data_version(conn)

    assert before != after, "データが増えたのに版が同じ = 識別子として機能しない"
    conn.close()


def test_data_version_is_stable_for_the_same_state():
    conn = _conn_with_log()
    conn.execute(
        "INSERT INTO ingested_files VALUES ('a.jvd','RACE',10,'2026-09-20 10:00:00')")

    assert provenance.data_version(conn) == provenance.data_version(conn)
    conn.close()


def test_missing_ledger_does_not_crash():
    """台帳が無い DB でも落ちないこと (テスト用の最小スキーマ等)。"""
    conn = sqlite3.connect(":memory:")
    assert provenance.data_version(conn) == "nodata"
    conn.close()


def test_snapshot_has_all_required_fields():
    """成果物の meta に入れる辞書が、憲法の要求項目を満たすこと。"""
    conn = _conn_with_log()
    snap = provenance.snapshot(conn)
    conn.close()

    assert {"git_sha", "git_dirty", "code_version", "data_version"} <= set(snap)
    assert isinstance(snap["git_dirty"], bool)
    # dirty のときは理由になったパスも残す。「dirty だった」だけでは
    # 後から何が未コミットだったのか分からず、再現の手掛かりにならない。
    assert ("dirty_paths" in snap) == snap["git_dirty"]


def test_untracked_code_counts_as_dirty():
    """**未追跡のコードも dirty**。

    2026-09-18 の実例: Phase 0.5-3 の生成スクリプト 3 本が丸ごと未追跡のまま
    成果物を作り、`git_dirty=false` と刻んでいた。その commit にスクリプトは
    存在せず、刻んだ出所から成果物を再現できなかった。
    `--untracked-files=no` は、この関数が防ぐべき事故そのものを見逃していた。
    """
    import subprocess

    from config import PROJECT_ROOT

    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=30).stdout
    untracked_code = [ln[3:] for ln in out.splitlines()
                      if ln.startswith("??") and ln[3:].startswith(
                          provenance.CODE_DIRS)]
    if not untracked_code:
        pytest.skip("未追跡のコードが無いので、この状況を再現できない")

    provenance.git_dirty.cache_clear()
    provenance.git_status_lines.cache_clear()
    provenance.dirty_code_paths.cache_clear()
    assert provenance.git_dirty() is True
    assert provenance.code_version().endswith("-dirty")
