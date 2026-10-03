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
- 前後の DB / WAL の大きさ・更新時刻、対象の行数、月ごとの被覆率を記録する

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

FROM_DATE, TO_DATE = "20210101", "20260630"
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
    return str(track_code).isdigit() and 1 <= int(track_code) <= 10


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
               AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""", (FROM_DATE, TO_DATE)).fetchall()


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
    for p in (path, Path(str(path) + "-wal")):
        if p.exists():
            st = p.stat()
            out[p.name] = {"bytes": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
        else:
            out[p.name] = None
    return out


def is_race_day(conn: sqlite3.Connection, today: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM races WHERE (race_year || race_month_day) = ? AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10"
        " LIMIT 1", (today,)).fetchone() is not None


def current_values(conn: sqlite3.Connection) -> dict[tuple, tuple]:
    return {tuple(r[c] for c in PK): tuple(r[c] for c in CORNERS) for r in target_rows(conn)}


def run(db_path: Path, records: Iterable, apply: bool, today: str | None = None, manifest: list | None = None) -> dict:
    """本体。`records` は SE レコードの列 (テストでは合成した値を渡す)。"""
    config.require_corner_bytes_verified("scripts.backfill_corner_orders")
    raw, used = raw_corner_map(records)          # raw の食い違いは DB を開く前に止める
    if not Path(db_path).exists():
        raise BackfillError(f"DB が無い: {db_path}")
    report: dict = {"db": str(db_path), "apply": apply, "range": [FROM_DATE, TO_DATE], "threshold": THRESHOLD,
                    "raw_files": manifest or [], "state_before": db_state(Path(db_path))}
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        today = today or datetime.now(JST).strftime("%Y%m%d")
        if apply and is_race_day(conn, today):
            raise BackfillError(f"今日 {today} は JRA の開催日なので --apply を拒否する")
        rows = target_rows(conn)
        plan = make_plan(rows, raw, used)
        planned = acceptance(rows, {**{tuple(r[c] for c in PK): None for r in rows}, **plan.updates})
        report.update({"db_rows": plan.db_rows, "planned_updates": len(plan.updates),
                       "null_remaining_after": plan.missing_in_raw, "raw_keys": plan.raw_keys,
                       "raw_records_used": plan.raw_records_used, "raw_keys_not_in_db": plan.raw_outside_db,
                       "acceptance_planned": planned})
        if not apply:
            report["result"] = "dry_run"
            return report
        if not planned["ok"]:
            raise BackfillError(f"検収 (計画の値) が不合格: {planned['failed_months']} {planned['missing_months']} "
                                f"over={planned['over_field']}")
        conn.execute("BEGIN IMMEDIATE")
        try:
            changed = 0
            for key, (c1, c2, c3, c4) in plan.updates.items():
                cur = conn.execute(
                    "UPDATE horse_races SET corner_order_1 = ?, corner_order_2 = ?, corner_order_3 = ?, corner_order_4 = ?"
                    " WHERE race_year = ? AND race_month_day = ? AND track_code = ? AND kaiji = ? AND nichiji = ?"
                    " AND race_num = ? AND horse_num = ?", (c1, c2, c3, c4, *key))
                changed += cur.rowcount
            if changed != len(plan.updates):
                raise BackfillError(f"更新件数 {changed} が予定 {len(plan.updates)} と違う")
            after = acceptance(target_rows(conn), current_values(conn))
            if not after["ok"]:
                raise BackfillError(f"検収 (適用後) が不合格: {after['failed_months']} over={after['over_field']}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        report.update({"updated_rows": changed, "acceptance_after": after, "result": "applied"})
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="対象の DB (既定値は持たない。本番に当てるときも明示する)")
    ap.add_argument("--raw-dir", default=str(Path(config.PROJECT_ROOT) / "data" / "raw" / "RACE"))
    ap.add_argument("--apply", action="store_true", help="書き込む (無ければ dry-run)")
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    config.require_corner_bytes_verified("scripts.backfill_corner_orders")   # raw を読む前にも止める
    files = raw_files(Path(args.raw_dir))
    records, manifest = load_records(files)
    try:
        report = run(Path(args.db), records, args.apply, manifest=manifest)
        rc = 0 if (report["result"] == "applied" or report["acceptance_planned"]["ok"]) else 1
    except BackfillError as e:
        report, rc = {"db": args.db, "apply": args.apply, "error": str(e), "raw_files": manifest}, 1
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("raw_files", "acceptance_planned", "acceptance_after")},
                     ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
