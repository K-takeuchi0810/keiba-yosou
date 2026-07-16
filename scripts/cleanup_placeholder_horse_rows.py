"""horse_races の枠順未確定 horse_num='00' 行を安全に掃除する。

既定は dry-run。``--execute`` の場合だけ、事前条件を全件検証し、SQLiteの
online backupを作成してから単一トランザクションで削除する。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

from config import DB_PATH
from db import SQL_VALID_HORSE_NUM, sql_invalid_horse_num


RACE_KEY = (
    "race_year", "race_month_day", "track_code",
    "kaiji", "nichiji", "race_num",
)

# 状態の分類 (db.horse_num_violation_counts / monitor カナリアと同じ日付規律):
#   未来日の単独 '00'      = 枠順確定前の正当な過渡状態 → violation 扱いせず削除もしない
#   正規行と共存する '00'  = 冪等削除の失敗残骸        → 唯一の自動削除対象
#   過去日の単独 '00'      = 取込欠落の疑い            → violation (再取得が正解の可能性が
#                            あるため自動削除せず manual judgment で abort)
def _coexist_exists(outer: str) -> str:
    return f"""EXISTS (
    SELECT 1 FROM horse_races resolved
     WHERE resolved.race_year={outer}.race_year
       AND resolved.race_month_day={outer}.race_month_day
       AND resolved.track_code={outer}.track_code
       AND resolved.kaiji={outer}.kaiji
       AND resolved.nichiji={outer}.nichiji
       AND resolved.race_num={outer}.race_num
       AND {SQL_VALID_HORSE_NUM.replace('horse_num', 'resolved.horse_num')}
)"""


def inspect_placeholders(
    conn: sqlite3.Connection, today: str | None = None
) -> tuple[int, list[sqlite3.Row]]:
    today = today or date.today().strftime("%Y%m%d")
    total = conn.execute(
        f"SELECT COUNT(*) FROM horse_races WHERE {sql_invalid_horse_num()}"
    ).fetchone()[0]
    violations = conn.execute(
        f"""
        SELECT h.race_year, h.race_month_day, h.track_code,
               h.kaiji, h.nichiji, h.race_num,
               h.horse_num, h.confirmed_order, h.win_odds, h.odds_fetched_at
          FROM horse_races h
         WHERE {sql_invalid_horse_num('h.horse_num')}
           AND (
                COALESCE(h.horse_num, '') != '00'
             OR h.confirmed_order IS NULL OR h.confirmed_order != 0
             OR h.win_odds IS NULL OR h.win_odds != 0
             OR h.odds_fetched_at IS NOT NULL
             OR (
                NOT {_coexist_exists('h')}
                AND (h.race_year || h.race_month_day) < ?
             )
           )
         ORDER BY h.race_year, h.race_month_day, h.track_code, h.race_num
        """,
        (today,),
    ).fetchall()
    return total, violations


def count_deletable(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM horse_races h "
        f"WHERE h.horse_num='00' AND {_coexist_exists('h')}"
    ).fetchone()[0]


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
    if args.dry_run or not args.execute:
        print("dry-run mode (default): inspect only; no rows will be deleted")

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
        deletable = count_deletable(conn)
    pending = total - deletable
    print(
        f"placeholder rows: {total} "
        f"(deletable: {deletable}, future pre-draw kept: {pending}); "
        f"violations: {len(violations)}"
    )
    if violations:
        for row in violations[:20]:
            key = "-".join(str(row[k]) for k in RACE_KEY)
            horse_num = row["horse_num"]
            action = (
                "manual judgment required"
                if horse_num != "00"
                else "unsafe placeholder"
            )
            print(
                f"VIOLATION {key}: horse_num={horse_num!r} ({action}) "
                f"confirmed_order={row['confirmed_order']} "
                f"win_odds={row['win_odds']} odds_fetched_at={row['odds_fetched_at']!r}",
                file=sys.stderr,
            )
        print("abort: unsafe placeholder rows found; nothing deleted", file=sys.stderr)
        return 1
    if args.dry_run or not args.execute:
        # --dry-run は --execute より常に優先する (「削除しない」と印字した以上、削除しない)
        print(f"DRY-RUN safe to delete: {deletable} rows")
        return 0
    if deletable == 0:
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
        locked_deletable = count_deletable(conn)
        if locked_total != total or locked_deletable != deletable or locked_violations:
            conn.rollback()
            print(
                "abort: placeholder state changed after backup; nothing deleted",
                file=sys.stderr,
            )
            return 1
        deleted = conn.execute(
            "DELETE FROM horse_races WHERE horse_num='00' "
            f"AND {_coexist_exists('horse_races')}"
        ).rowcount
        remaining = count_deletable(conn)
        if remaining != 0:
            conn.rollback()
            print(f"abort: verification found {remaining} remaining rows", file=sys.stderr)
            return 1
        conn.commit()
    finally:
        conn.close()

    print(f"deleted: {deleted}; future pre-draw kept: {pending}; deletable remaining: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
