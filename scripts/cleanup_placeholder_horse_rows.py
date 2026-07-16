"""horse_races の枠順未確定 horse_num='00' 行を安全に掃除する。

既定は dry-run。``--execute`` の場合だけ、事前条件を全件検証し、SQLiteの
online backupを作成してから単一トランザクションで削除する。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from config import DB_PATH
from db import SQL_VALID_HORSE_NUM


RACE_KEY = (
    "race_year", "race_month_day", "track_code",
    "kaiji", "nichiji", "race_num",
)


def inspect_placeholders(conn: sqlite3.Connection) -> tuple[int, list[sqlite3.Row]]:
    total = conn.execute(
        "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
    ).fetchone()[0]
    violations = conn.execute(
        f"""
        SELECT h.race_year, h.race_month_day, h.track_code,
               h.kaiji, h.nichiji, h.race_num,
               h.confirmed_order, h.win_odds, h.odds_fetched_at
          FROM horse_races h
         WHERE h.horse_num='00'
           AND (
                h.confirmed_order IS NULL OR h.confirmed_order != 0
             OR h.win_odds IS NULL OR h.win_odds != 0
             OR h.odds_fetched_at IS NOT NULL
             OR NOT EXISTS (
                    SELECT 1 FROM horse_races resolved
                     WHERE resolved.race_year=h.race_year
                       AND resolved.race_month_day=h.race_month_day
                       AND resolved.track_code=h.track_code
                       AND resolved.kaiji=h.kaiji
                       AND resolved.nichiji=h.nichiji
                       AND resolved.race_num=h.race_num
                       AND {SQL_VALID_HORSE_NUM}
                )
           )
         ORDER BY h.race_year, h.race_month_day, h.track_code, h.race_num
        """
    ).fetchall()
    return total, violations


def create_backup(db_path: Path, backup_path: Path, expected_rows: int) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        with sqlite3.connect(backup_path) as existing:
            existing_count = existing.execute(
                "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
            ).fetchone()[0]
        if existing_count != expected_rows:
            raise RuntimeError(
                f"existing backup has {existing_count} placeholders; "
                f"expected {expected_rows}: {backup_path}"
            )
        print(f"backup already exists and matches pre-delete count: {backup_path}")
        return

    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as dest:
        source.backup(dest)
    print(f"backup created: {backup_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=Path(DB_PATH))
    ap.add_argument("--backup", type=Path, default=None)
    ap.add_argument("--execute", action="store_true", help="バックアップ後に削除を実行")
    ap.add_argument("--dry-run", action="store_true", help="明示的にdry-runを選択 (既定動作)")
    args = ap.parse_args()

    db_path = args.db.resolve()
    backup_path = (
        args.backup.resolve()
        if args.backup
        else db_path.with_name(f"{db_path.name}.bak_20260715")
    )
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        total, violations = inspect_placeholders(conn)
    print(f"placeholder rows: {total}; violations: {len(violations)}")
    if violations:
        for row in violations[:20]:
            key = "-".join(str(row[k]) for k in RACE_KEY)
            print(
                f"VIOLATION {key}: confirmed_order={row['confirmed_order']} "
                f"win_odds={row['win_odds']} odds_fetched_at={row['odds_fetched_at']!r}",
                file=sys.stderr,
            )
        print("abort: unsafe placeholder rows found; nothing deleted", file=sys.stderr)
        return 1
    if not args.execute:
        print(f"DRY-RUN safe to delete: {total} rows")
        return 0
    if total == 0:
        print("nothing to delete")
        return 0

    try:
        create_backup(db_path, backup_path, total)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        locked_total, locked_violations = inspect_placeholders(conn)
        if locked_total != total or locked_violations:
            conn.rollback()
            print(
                "abort: placeholder state changed after backup; nothing deleted",
                file=sys.stderr,
            )
            return 1
        deleted = conn.execute(
            "DELETE FROM horse_races WHERE horse_num='00'"
        ).rowcount
        remaining = conn.execute(
            "SELECT COUNT(*) FROM horse_races WHERE horse_num='00'"
        ).fetchone()[0]
        if remaining != 0:
            conn.rollback()
            print(f"abort: verification found {remaining} remaining rows", file=sys.stderr)
            return 1
        conn.commit()
    finally:
        conn.close()

    print(f"deleted: {deleted}; remaining: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
