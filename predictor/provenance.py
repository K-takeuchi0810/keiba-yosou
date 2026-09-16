"""予測の出所 (どのコードが、どの状態のデータで出したか) を記録する。

## なぜ要るか

憲法 (docs/CHARTER_2026_09_17.md) Phase 0.5 項目 0:

> 予測結果すべてに git SHA を記録する / 使用データのバージョンも記録する
> 以後「どのコードがこの予測を出したのか分からない」状態を禁止します。

実際 2026-09-17 時点で、騎手変更・コース変更・発走時刻変更の取り込みが
**未コミットのまま 1 ヶ月以上本番で稼働**していた。その間に出した予測が
どのコードによるものかは、後から git からは分からなかった。

同じことは予測だけでなく **データの状態** にも当てはまる。同じコードでも、
取り込み済みのデータが違えば違う予測になる。だから両方を記録する。

## 何を記録するか

| 項目 | 意味 |
|---|---|
| `git_sha` | 予測を出したコードの commit |
| `git_dirty` | 未コミットの変更があったか (True なら SHA は正確でない) |
| `data_version` | 取り込み済みデータの状態を表す短い指紋 |

`data_version` は `ingested_files` (取り込み台帳) の件数と最終取り込み時刻から
作る。同じ値なら同じデータ状態、違えば違う、という識別子であって、
人が読んで意味が分かるものではない。
"""
from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from functools import lru_cache

from config import PROJECT_ROOT

UNKNOWN = "unknown"


@lru_cache(maxsize=1)
def git_sha() -> str:
    """HEAD の commit SHA。取れなければ "unknown"。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=PROJECT_ROOT, check=True, timeout=10).stdout.strip()
        return out or UNKNOWN
    except Exception:
        return UNKNOWN


@lru_cache(maxsize=1)
def git_dirty() -> bool:
    """tracked ファイルに未コミットの変更があるか。

    True なら git_sha は「実際に動いたコード」を指していない。
    2026-09-17 まで 1 ヶ月続いた状態がまさにこれ。
    """
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
            check=True, timeout=10).stdout.strip()
        return bool(out)
    except Exception:
        return False


def code_version() -> str:
    """予測に刻む版文字列。dirty なら末尾に印を付けて区別できるようにする。"""
    sha = git_sha()
    return f"{sha[:12]}-dirty" if git_dirty() else sha[:12]


def data_version(conn: sqlite3.Connection) -> str:
    """取り込み済みデータの状態を表す短い指紋。

    `ingested_files` の件数と最終取り込み時刻から作る。同じ値なら同じ状態。
    台帳が無い DB (テスト用の最小スキーマ等) では "nodata" を返す。
    """
    try:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(ingested_at), '')"
            " FROM ingested_files").fetchone()
    except sqlite3.Error:
        return "nodata"
    if row is None:
        return "nodata"
    n, last = int(row[0] or 0), str(row[1] or "")
    digest = hashlib.sha256(f"{n}|{last}".encode()).hexdigest()[:10]
    return f"{n}:{digest}"


def snapshot(conn: sqlite3.Connection | None = None) -> dict:
    """成果物の meta にそのまま入れる辞書。"""
    return {
        "git_sha": git_sha(),
        "git_dirty": git_dirty(),
        "code_version": code_version(),
        "data_version": data_version(conn) if conn is not None else None,
    }
