"""通過順位 (corner_order_1〜4) の backfill — raw の SE から、horse_races の **corner 4 列だけ** を UPDATE する (2026-10-04)。

docs/PHASE05_5_PREREG.md §8-3 の解除の手順の backfill。`ingest_all` / `upsert_horse_race` は **使わない**:
SE を再び upsert すると、`win_odds` を確定値で上書きする一方で `odds_fetched_at` の刻印が残り、
「発走前の刻印 + 確定オッズ」という PIT の汚染行ができる (2026-10-04 data-pipeline レビュー)。この処理は
主キーを指定した `UPDATE horse_races SET corner_order_1..4` だけなので、ほかの列は構造的に変わらない。

契約 (外部の指示者と 3 名のレビューで固定):
- `config.CORNER_BYTES_VERIFIED` が False なら **DB を開く前に** 止まる
- 対象は JRA (track 01〜10)、レースの日付が 2021-01-01〜2026-06-30。値の出どころは raw の SE* の `data_div = 7`
  (確定成績) のレコードだけ。使ったファイルの一覧・件数・sha256 を manifest に残す
- 同じ主キーに raw の値が複数あって corner が食い違えば止める (どちらが正しいか推測しない)
- raw に無い DB の行は推測で埋めず、NULL のまま件数を数える
- 既定は dry-run。`--apply` が無ければ書かない。`--apply` は 1 トランザクションで、検収
  (月ごとの `corner_order_4 > 0` ≥ 95%、順位 > 出走頭数が 0 件、更新件数 = 予定件数) が不合格なら rollback
- 今日 (JST) が JRA の開催日 (races にその日の JRA のレースがある) なら `--apply` を拒否する。
  これは安全装置の 1 つにすぎず、本番での実行には書き手の停止の確認とユーザーの明示の承認が別に要る
- 前後の DB / WAL / SHM の大きさ・更新時刻、対象の行数、月ごとの被覆率を記録する
- (v2) `--apply` は計画・更新・検収を 1 つの書き込みトランザクション (BEGIN IMMEDIATE) で行う。対象の行に corner が
  すでに入っている件数が `--expected-nonnull-before` (既定 0 = 全行 NULL) と違えば止める。対象外の行の行数とチェックサム、
  この接続の総変更件数 (= 更新件数) を前後で検査する。COMMIT 直後 (checkpoint の前) の状態を記録してから
  `wal_checkpoint(TRUNCATE)` を打つ (成功時の戻り値は (0, 0, 0) なので、WAL の規模の証拠は COMMIT 直後の状態で見る)
- dry-run は読み取り専用 (mode=ro) で開く

usage:
    .venv64/Scripts/python.exe -m scripts.backfill_corner_orders --db <db> [--apply] --report <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

# 対象の終端は 2026-06-30 (事前登録 §8-3。2026-07 以降は offset 修正後の取り込みで値が入っている)
FROM_DATE, TO_DATE = "20210101", "20260630"
JRA_TRACKS = (1, 10)                     # JRA の track_code の範囲 (01〜10)
GUARD_CONTEXT = "scripts.backfill_corner_orders"
DEFAULT_EXPECTED_NONNULL_BEFORE = 0      # --apply の前に corner が入っている対象の行の件数の想定 (全行 NULL)
THRESHOLD = 0.95
REFUNDED = ("1", "2", "3")
PK = ("race_year", "race_month_day", "track_code", "kaiji", "nichiji", "race_num", "horse_num")
CORNERS = ("corner_order_1", "corner_order_2", "corner_order_3", "corner_order_4")
JST = timezone(timedelta(hours=9))


class BackfillError(RuntimeError):
    """backfill を止める条件 (raw の食い違い・検収の不合格・開催日など)。"""


@dataclass
class Plan:
    updates: dict[tuple, tuple] = field(default_factory=dict)    # 主キー → (c1, c2, c3, c4)
    db_rows: int = 0
    missing_in_raw: int = 0
    raw_keys: int = 0
    raw_records_used: int = 0
    raw_outside_db: int = 0


def is_jra(track_code: str) -> bool:
    return str(track_code).isdigit() and JRA_TRACKS[0] <= int(track_code) <= JRA_TRACKS[1]


def in_range(ymd: str) -> bool:
    return FROM_DATE <= ymd <= TO_DATE


def raw_corner_map(records: Iterable) -> tuple[dict[tuple, tuple], int]:
    """SE レコードから {主キー: corner 4 つ}。対象は JRA・data_div 7・日付の範囲内。食い違いは止める。"""
    out: dict[tuple, tuple] = {}
    used = 0
    for r in records:
        if getattr(r, "record_type", "SE") != "SE" or str(r.data_div).strip() != "7":
            continue
        if not is_jra(r.track_code) or not in_range(f"{r.year}{r.month_day}"):
            continue
        key = (r.year, r.month_day, r.track_code, r.kaiji, r.nichiji, r.race_num, r.horse_num)
        val = (int(r.corner_order_1), int(r.corner_order_2), int(r.corner_order_3), int(r.corner_order_4))
        used += 1
        if key in out and out[key] != val:
            raise BackfillError(f"raw の通過順位が食い違う: {key} {out[key]} vs {val}")
        out[key] = val
    return out, used


def target_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        f"""SELECT {', '.join(PK)}, {', '.join(CORNERS)}, abnormal_code, confirmed_order
              FROM horse_races
             WHERE (race_year || race_month_day) BETWEEN ? AND ?
               AND CAST(track_code AS INTEGER) BETWEEN ? AND ?""", (FROM_DATE, TO_DATE, *JRA_TRACKS)).fetchall()


def make_plan(rows: list, raw: dict[tuple, tuple], raw_used: int) -> Plan:
    plan = Plan(db_rows=len(rows), raw_keys=len(raw), raw_records_used=raw_used)
    db_keys = set()
    for row in rows:
        key = tuple(row[c] for c in PK)
        db_keys.add(key)
        if key in raw:
            plan.updates[key] = raw[key]
        else:
            plan.missing_in_raw += 1
    plan.raw_outside_db = len(set(raw) - db_keys)
    return plan


def acceptance(rows: list, values: dict[tuple, tuple]) -> dict:
    """月ごとの被覆率 (確定着順のある行の corner_order_4 > 0) と、順位 > 出走頭数 の件数。

    `values` は主キー → corner 4 つ (検収する状態の値。適用前は計画の値、適用後は DB の値)。
    """
    field_n: dict[tuple, int] = defaultdict(int)
    for row in rows:
        if str(row["abnormal_code"] or "").strip() not in REFUNDED:
            field_n[tuple(row[c] for c in PK[:6])] += 1
    months: dict[str, dict] = {}
    over = []
    for row in rows:
        key = tuple(row[c] for c in PK)
        cs = values.get(key)
        ym = row["race_year"] + row["race_month_day"][:2]
        m = months.setdefault(ym, {"rows": 0, "c4_pos": 0})
        if cs is not None and any(c and c > field_n[key[:6]] for c in cs):
            over.append(key)
        try:
            confirmed = int(row["confirmed_order"] or 0) > 0
        except ValueError:
            confirmed = False
        if confirmed:
            m["rows"] += 1
            if cs is not None and cs[3] and cs[3] > 0:
                m["c4_pos"] += 1
    expected = {f"{y}{mm:02d}" for y in range(int(FROM_DATE[:4]), int(TO_DATE[:4]) + 1) for mm in range(1, 13)
                if FROM_DATE[:6] <= f"{y}{mm:02d}" <= TO_DATE[:6]}
    rates = {ym: (m["c4_pos"] / m["rows"] if m["rows"] else None) for ym, m in sorted(months.items())}
    failed = sorted(ym for ym, r in rates.items() if r is None or r < THRESHOLD)
    missing = sorted(expected - set(rates))
    return {"monthly_c4_rate": rates, "failed_months": failed, "missing_months": missing,
            "over_field": len(over), "over_field_examples": [list(k) for k in over[:5]],
            "ok": not failed and not missing and not over}


def db_state(path: Path) -> dict:
    out = {}
    for p in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if p.exists():
            st = p.stat()
            out[p.name] = {"bytes": st.st_size,
                           "mtime": datetime.fromtimestamp(st.st_mtime, JST).isoformat(timespec="seconds")}
        else:
            out[p.name] = None
    return out


def is_race_day(conn: sqlite3.Connection, today: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM races WHERE (race_year || race_month_day) = ? AND CAST(track_code AS INTEGER) BETWEEN ? AND ?"
        " LIMIT 1", (today, *JRA_TRACKS)).fetchone() is not None


def current_values(conn: sqlite3.Connection) -> dict[tuple, tuple]:
    return {tuple(r[c] for c in PK): tuple(r[c] for c in CORNERS) for r in target_rows(conn)}


def outside_digest(conn: sqlite3.Connection) -> dict:
    """対象外の horse_races の行 (地方・範囲外の日付) の行数とチェックサム。前後で同一であることを示す。"""
    h = hashlib.sha256()
    n = 0
    for row in conn.execute(
            f"""SELECT * FROM horse_races
                 WHERE NOT ((race_year || race_month_day) BETWEEN ? AND ?
                            AND CAST(track_code AS INTEGER) BETWEEN {JRA_TRACKS[0]} AND {JRA_TRACKS[1]})
                 ORDER BY {', '.join(PK)}""", (FROM_DATE, TO_DATE)):
        h.update(repr(tuple(row)).encode())
        n += 1
    return {"rows": n, "sha256": h.hexdigest()}


def nonnull_corners(rows: list) -> int:
    return sum(1 for r in rows if any(r[c] is not None for c in CORNERS))


def run(db_path: Path, records: Iterable, apply: bool, today: str | None = None, manifest: list | None = None,
        expected_nonnull_before: int = DEFAULT_EXPECTED_NONNULL_BEFORE) -> dict:
    """本体。`records` は SE レコードの列 (テストでは合成した値を渡す)。

    `--apply` のときは、計画・更新・検収を **1 つの書き込みトランザクション** (BEGIN IMMEDIATE) の中で行う
    (計画と適用が同じ snapshot になり、ほかの書き手が割り込めない)。対象の行の corner がすでに入っている件数が
    `expected_nonnull_before` (既定 0 = 全行 NULL) と違えば止める (別の経路で入った値を黙って上書きしない)。
    """
    config.require_corner_bytes_verified(GUARD_CONTEXT)
    raw, used = raw_corner_map(records)          # raw の食い違いは DB を開く前に止める
    if not Path(db_path).exists():
        raise BackfillError(f"DB が無い: {db_path}")
    report: dict = {"db": str(db_path), "apply": apply, "range": [FROM_DATE, TO_DATE], "threshold": THRESHOLD,
                    "raw_files": manifest or [], "state_before": db_state(Path(db_path))}
    if apply:
        conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    else:                                         # dry-run は構造的に書けないように読み取り専用で開く
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    in_tx = False
    try:
        today = today or datetime.now(JST).strftime("%Y%m%d")
        if apply:
            if is_race_day(conn, today):
                raise BackfillError(f"今日 {today} は JRA の開催日なので --apply を拒否する")
            conn.execute("BEGIN IMMEDIATE")
            in_tx = True
            report["outside_before"] = outside_digest(conn)
        rows = target_rows(conn)
        plan = make_plan(rows, raw, used)
        planned = acceptance(rows, plan.updates)
        report.update({"db_rows": plan.db_rows, "nonnull_before": nonnull_corners(rows),
                       "planned_updates": len(plan.updates), "null_remaining_after": plan.missing_in_raw,
                       "raw_keys": plan.raw_keys, "raw_records_used": plan.raw_records_used,
                       "raw_keys_not_in_db": plan.raw_outside_db, "acceptance_planned": planned})
        if not apply:
            report["result"] = "dry_run"
            return report
        if report["nonnull_before"] != expected_nonnull_before:
            raise BackfillError(f"前の状態が想定と違う: corner が入っている対象の行 {report['nonnull_before']} "
                                f"(想定 {expected_nonnull_before})")
        if not planned["ok"]:
            raise BackfillError(f"検収 (計画の値) が不合格: {planned['failed_months']} {planned['missing_months']} "
                                f"over={planned['over_field']}")
        changes_before = conn.total_changes
        changed = 0
        for key, values in plan.updates.items():
            cur = conn.execute(
                f"UPDATE horse_races SET {', '.join(f'{c} = ?' for c in CORNERS)}"
                f" WHERE {' AND '.join(f'{c} = ?' for c in PK)}", (*values, *key))
            changed += cur.rowcount
        if changed != len(plan.updates):
            raise BackfillError(f"更新件数 {changed} が予定 {len(plan.updates)} と違う")
        if conn.total_changes - changes_before != changed:
            raise BackfillError("この接続の変更件数が更新件数と違う (想定外の書き込み)")
        after = acceptance(target_rows(conn), current_values(conn))
        if not after["ok"]:
            raise BackfillError(f"検収 (適用後) が不合格: {after['failed_months']} over={after['over_field']}")
        report["outside_after"] = outside_digest(conn)
        if report["outside_after"] != report["outside_before"]:
            raise BackfillError("対象外の行が変わった")
        conn.execute("COMMIT")
        in_tx = False
        report["state_after_commit"] = db_state(Path(db_path))     # checkpoint の前 (WAL の規模の証拠)
        report.update({"updated_rows": changed, "acceptance_after": after, "result": "applied"})
        busy, log, ckpt = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        report["wal_checkpoint"] = {"busy": busy, "log_frames": log, "checkpointed_frames": ckpt}
    except BaseException as e:                    # Ctrl-C でもレポートを残す
        if in_tx:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error as rb:              # 元の例外を隠さない
                report["rollback_error"] = str(rb)
        report.setdefault("result", "error")
        report["error"] = f"{type(e).__name__}: {e}"
        try:
            e.report = report                       # main() が失敗の内訳もレポートに書けるように
        except AttributeError:
            pass
        raise
    finally:
        conn.close()
        report["state_after"] = db_state(Path(db_path))
    return report


def raw_files(raw_dir: Path) -> list[Path]:
    """対象期間の年の名前を持つ SE* のファイル (日付の絞り込みはレコード単位でも行う)。"""
    return sorted((p for p in raw_dir.glob("SE*.jvd")
                   if p.name[4:8].isdigit() and int(FROM_DATE[:4]) <= int(p.name[4:8]) <= int(TO_DATE[:4])),
                  key=lambda p: p.name)


def load_records(files: list[Path]) -> tuple[list, list[dict]]:
    from jvlink_client.parser import parse_se_file

    records, manifest = [], []
    for f in files:
        recs = [r for r in parse_se_file(str(f)) if r.record_type == "SE"]
        records.extend(recs)
        manifest.append({"file": f.name, "bytes": f.stat().st_size,
                         "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "se_records": len(recs)})
    return records, manifest


def _write_report(path: str, report: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="対象の DB (既定値は持たない。本番に当てるときも明示する)")
    ap.add_argument("--raw-dir", default=str(Path(config.PROJECT_ROOT) / "data" / "raw" / "RACE"))
    ap.add_argument("--apply", action="store_true", help="書き込む (無ければ dry-run)")
    ap.add_argument("--expected-nonnull-before", type=int, default=DEFAULT_EXPECTED_NONNULL_BEFORE,
                    help="--apply の前に corner が入っている対象の行の件数の想定 "
                         f"(既定 {DEFAULT_EXPECTED_NONNULL_BEFORE} = 全行 NULL)")
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    config.require_corner_bytes_verified(GUARD_CONTEXT)   # raw を読む前にも止める
    files = raw_files(Path(args.raw_dir))
    report: dict
    try:
        if not files:
            raise BackfillError(f"raw の SE ファイルが無い: {args.raw_dir}")
        records, manifest = load_records(files)
        report = run(Path(args.db), records, args.apply, manifest=manifest,
                     expected_nonnull_before=args.expected_nonnull_before)
        rc = 0 if (report["result"] == "applied" or report["acceptance_planned"]["ok"]) else 1
    except BaseException as e:                   # Ctrl-C を含め、想定外の例外もレポートを書いてから再送出
        report = getattr(e, "report", None) or {"db": args.db, "apply": args.apply, "raw_dir": args.raw_dir,
                                                "result": "error", "error": f"{type(e).__name__}: {e}"}
        rc = 1
        if not isinstance(e, (BackfillError, sqlite3.Error)):
            _write_report(args.report, report)
            raise
    _write_report(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("raw_files", "acceptance_planned", "acceptance_after")},
                     ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
