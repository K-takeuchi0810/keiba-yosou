"""通過順位の backfill の前の Scratch A: 空の DB に SE を取り込み、被覆率・値域・冪等を確かめる (2026-10-04)。

docs/PHASE05_5_PREREG.md §8-3 の解除の手順の 3 段目 (scratch での再取り込みの検証) の前半。
**本番 DB には触れない** (空の scratch DB を新しく作る)。raw は読むだけ。

- 対象: data/raw/RACE/ の SE* (SEVM / SESW / SEDW / SEBW / SEPW / SEMM) で 2021〜2026 年の名前のもの。
  取り込みは本番と同じ `ingest_file_dispatch(conn, path, dataspec="RACE")` を、ファイル名の順で
- 測るもの (JRA = track_code 01〜10、確定着順 > 0 の行、月ごと):
  行数 / `corner_order_4 > 0` の率 / corner 4 列の NULL の率 / 「4 角の順位 > そのレースの頭数 + 2」の件数 /
  逃げ馬 (脚質コード 1) の 4 角の中央値
- 受理 (事前登録 §8-3): 2021-01〜2026-06 の **月ごと** に `corner_order_4 > 0` が 95% 以上、範囲外 0 件
- 冪等: 同じファイルを 2 回目に取り込んだ後の horse_races の行のチェックサムが 1 回目と一致

usage (worktree の根で):
    .venv64/Scripts/python.exe data/backtest/corner_scratch_20261004/scratch_a.py --db <scratch.db>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WT))

import config  # noqa: E402
from db import SCHEMA_PATH  # noqa: E402
from jvlink_client.ingest import ingest_file_dispatch  # noqa: E402

RAW = Path(r"C:\Users\kizun\dev\keiba-yosou\data\raw\RACE")
PROD_DB = Path(r"C:\Users\kizun\dev\keiba-yosou\data\keiba.db")
FIRST_MONTH, LAST_MONTH = "202101", "202606"
THRESHOLD = 0.95


def target_files() -> list[Path]:
    files = [p for p in RAW.glob("SE*.jvd") if p.name[4:8].isdigit() and 2021 <= int(p.name[4:8]) <= 2026]
    return sorted(files, key=lambda p: p.name)


def ingest_all_files(conn: sqlite3.Connection, files: list[Path]) -> dict:
    total = defaultdict(int)
    for f in files:
        ra, se, hr, o1, um, skipped = ingest_file_dispatch(conn, f, dataspec="RACE")
        conn.commit()
        total["se"] += se
        total["ra"] += ra
        total["hr"] += hr
        total["o1"] += o1
        total["skipped"] += skipped
    return dict(total)


def checksum(conn: sqlite3.Connection) -> str:
    h = hashlib.sha256()
    for row in conn.execute("SELECT * FROM horse_races ORDER BY race_year, race_month_day, track_code, kaiji,"
                            " nichiji, race_num, horse_num"):
        h.update(repr(tuple(row)).encode())
    return h.hexdigest()


def monthly(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT race_year || substr(race_month_day, 1, 2) AS ym, track_code, kaiji, nichiji, race_num, horse_num,
                  corner_order_1, corner_order_2, corner_order_3, corner_order_4, leg_quality_code
             FROM horse_races
            WHERE CAST(track_code AS INTEGER) BETWEEN 1 AND 10
              AND CAST(confirmed_order AS INTEGER) > 0""").fetchall()
    # 頭数 = 出走頭数 (事前登録 §8-3 の「4 角の順位 > 出走頭数」)。取消・除外 (1/2/3) を除く全行で数える。
    # 初版は確定着順のある行だけで数えていたので、競走中止 (4) の馬がいるレースで頭数を少なく数えていた
    field = defaultdict(int)
    for r in conn.execute(
            """SELECT race_year || substr(race_month_day, 1, 2), track_code, kaiji, nichiji, race_num
                 FROM horse_races
                WHERE CAST(track_code AS INTEGER) BETWEEN 1 AND 10
                  AND COALESCE(TRIM(abnormal_code), '') NOT IN ('1', '2', '3')"""):
        field[tuple(r)] += 1
    out: dict[str, dict] = {}
    for r in rows:
        ym = r[0]
        m = out.setdefault(ym, {"ym": ym, "rows": 0, "c4_pos": 0, "null_any": 0, "over_field": 0, "front_c4": []})
        m["rows"] += 1
        cs = r[6:10]
        if r[9] is not None and r[9] > 0:
            m["c4_pos"] += 1
        if any(c is None for c in cs):
            m["null_any"] += 1
        f = field[(r[0], r[1], r[2], r[3], r[4])]
        if any(c is not None and c > f for c in cs):
            m["over_field"] += 1
        if (r[10] or "").strip() == "1" and r[9]:
            m["front_c4"].append(r[9])
    res = []
    for ym in sorted(out):
        m = out[ym]
        res.append({"ym": ym, "rows": m["rows"], "c4_pos_rate": m["c4_pos"] / m["rows"],
                    "null_any_rate": m["null_any"] / m["rows"], "over_field": m["over_field"],
                    "front_runner_c4_median": statistics.median(m["front_c4"]) if m["front_c4"] else None,
                    "in_target": FIRST_MONTH <= ym <= LAST_MONTH})
    return res


def reanalyze(db: Path, out_path: Path) -> int:
    prev = json.loads(Path(__file__).with_name("scratch_a_result.json").read_text(encoding="utf-8"))
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    months = monthly(conn)
    target = [m for m in months if m["in_target"]]
    fails = [m["ym"] for m in target if m["c4_pos_rate"] < THRESHOLD or m["over_field"] > 0]
    out = {**{k: prev[k] for k in ("n_files", "files_first", "files_last", "ingest_first", "ingest_second",
                                   "checksum_first", "checksum_second", "idempotent", "seconds", "missing_months")},
           "reanalyzed_from": "scratch_a_result.json (v1: 頭数を確定着順のある行で数えた誤り)",
           "field_definition": "出走頭数 = 取消・除外 (1/2/3) を除く行数。判定は 4 角などの順位 > 出走頭数",
           "threshold": THRESHOLD, "failed_months": fails,
           "accepted": prev["idempotent"] and not prev["missing_months"] and not fails, "months": months}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"failed {fails} / accepted {out['accepted']} / min c4>0 in target "
          f"{min(m['c4_pos_rate'] for m in target):.4f} / over_field total in target {sum(m['over_field'] for m in target)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default=str(Path(__file__).with_name("scratch_a_result.json")))
    ap.add_argument("--reanalyze", action="store_true",
                    help="取り込み済みの scratch DB で判定だけをやり直す (取り込みと冪等の結果は前回の JSON から引き継ぐ)")
    args = ap.parse_args()
    config.require_corner_bytes_verified("scratch_a")
    db = Path(args.db).resolve()
    if args.reanalyze:
        return reanalyze(db, Path(args.out))
    if db == PROD_DB.resolve() or db.exists():
        raise SystemExit(f"scratch の DB は新しいパスにする (本番・既存のファイルは使わない): {db}")
    conn = sqlite3.connect(db)
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    files = target_files()
    t0 = time.time()
    first = ingest_all_files(conn, files)
    sum1 = checksum(conn)
    t1 = time.time()
    second = ingest_all_files(conn, files)
    sum2 = checksum(conn)
    t2 = time.time()
    months = monthly(conn)
    target = [m for m in months if m["in_target"]]
    expected_months = {f"{y}{mm:02d}" for y in range(2021, 2027) for mm in range(1, 13)
                       if f"{y}{mm:02d}" <= LAST_MONTH}
    missing = sorted(expected_months - {m["ym"] for m in target})
    fails = [m["ym"] for m in target if m["c4_pos_rate"] < THRESHOLD or m["over_field"] > 0]
    out = {
        "code": "worktree corner-scratch (d4d87fc 以降)", "db": str(db), "n_files": len(files),
        "files_first": files[0].name, "files_last": files[-1].name,
        "ingest_first": first, "ingest_second": second,
        "checksum_first": sum1, "checksum_second": sum2, "idempotent": sum1 == sum2,
        "seconds": {"first": round(t1 - t0, 1), "second": round(t2 - t1, 1)},
        "threshold": THRESHOLD, "target_months": [FIRST_MONTH, LAST_MONTH],
        "missing_months": missing, "failed_months": fails,
        "accepted": sum1 == sum2 and not missing and not fails,
        "months": months,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"files {len(files)} / idempotent {sum1 == sum2} / missing {missing} / failed {fails} / accepted {out['accepted']}")
    for m in months:
        print(f"{m['ym']} rows {m['rows']:6d} c4>0 {m['c4_pos_rate']:.4f} null {m['null_any_rate']:.4f} "
              f"over {m['over_field']} front_med {m['front_runner_c4_median']} {'*' if m['in_target'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
