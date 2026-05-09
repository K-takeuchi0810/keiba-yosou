"""SQLite アクセスレイヤ。

- `init_db(conn)`: schema.sql を流して必要なテーブルを作る
- `upsert_race(conn, RaceInfo)`: RA レコードを INSERT OR REPLACE
- `upsert_horse_race(conn, HorseRaceInfo)`: SE レコードを INSERT OR REPLACE
- `record_ingested_file(...)`: 取り込み済みファイルを記録
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from config import DB_PATH, PROJECT_ROOT
from jvlink_client.parser import HorseMaster, HorseRaceInfo, O1Odds, Payout, RaceInfo

SCHEMA_PATH = PROJECT_ROOT / "data" / "schema.sql"


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def open_db(path: Path | str = DB_PATH):
    conn = connect(path)
    try:
        init_db(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    _ensure_column(conn, "horse_races", "odds_fetched_at", "TEXT")
    _ensure_column(conn, "horse_races", "odds_dataspec", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# 整合性のために RA/SE の主キーを race_id 構成順に揃えて生成する
_RACE_PK = (
    "race_year",
    "race_month_day",
    "track_code",
    "kaiji",
    "nichiji",
    "race_num",
)


def _ra_to_row(ra: RaceInfo) -> dict:
    d = asdict(ra)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)  # 種別 ID は固定なのでテーブルに持たない
    return d


def _se_to_row(se: HorseRaceInfo) -> dict:
    d = asdict(se)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    return d


def upsert_race(conn: sqlite3.Connection, ra: RaceInfo) -> None:
    row = _ra_to_row(ra)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO races ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def upsert_horse_race(conn: sqlite3.Connection, se: HorseRaceInfo) -> None:
    row = _se_to_row(se)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO horse_races ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def _hr_to_row(hr: Payout) -> dict:
    d = asdict(hr)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    return d


def upsert_payout(conn: sqlite3.Connection, hr: Payout) -> None:
    row = _hr_to_row(hr)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO payouts ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def update_win_odds(
    conn: sqlite3.Connection,
    o1: O1Odds,
    fetched_at: str | None = None,
    dataspec: str = "0B31",
) -> int:
    updated = 0
    fetched_at = fetched_at or datetime.now().isoformat(timespec="seconds")
    params_base = (
        o1.year,
        o1.month_day,
        o1.track_code,
        o1.kaiji,
        o1.nichiji,
        o1.race_num,
    )
    for horse_num, odds, popularity in o1.win_odds:
        cur = conn.execute(
            """
            UPDATE horse_races
               SET win_odds = ?, win_popularity = ?,
                   odds_fetched_at = ?, odds_dataspec = ?
             WHERE race_year=? AND race_month_day=? AND track_code=?
               AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=?
            """,
            (odds, popularity, fetched_at, dataspec, *params_base, horse_num),
        )
        updated += cur.rowcount
    return updated


def upsert_horse_master(conn: sqlite3.Connection, um: HorseMaster) -> None:
    row = asdict(um)
    row.pop("record_type", None)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO horse_masters ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def is_file_ingested(conn: sqlite3.Connection, filename: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM ingested_files WHERE filename = ?", (filename,)
    )
    return cur.fetchone() is not None


def record_ingested_file(
    conn: sqlite3.Connection,
    filename: str,
    dataspec: str,
    record_count: int,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ingested_files "
        "(filename, dataspec, record_count) VALUES (?, ?, ?)",
        (filename, dataspec, record_count),
    )
