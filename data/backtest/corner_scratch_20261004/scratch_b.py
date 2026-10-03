"""Scratch B: 本番の対象行だけの縮小 clone に backfill を当て、corner 4 列以外が 1 ビットも変わらないことを確かめる (2026-10-04)。

docs/PHASE05_5_PREREG.md §8-3 の scratch での検証の後半。外部の指示者の要件:
- 本番 DB は mode=ro で開き、1 つの読み取りトランザクションで対象行を取得する (一貫した snapshot)。
  読み取りの開始・終了時刻と本番 DB / WAL の状態を残す
- 書き込みの範囲はコードで確認済み (backfill は horse_races の corner 4 列の UPDATE だけ)。clone には horse_races の対象行と、
  同じ日付の races の行を入れる
- 前後で全列を比較し、「変わったセルの列 ⊆ {corner_order_1..4}」を機械的に assert。win_odds / odds_fetched_at /
  jockey / burden_weight / horse_weight / 着順系 / 主キーは全行が完全一致であることを個別にも出す

usage (worktree の根で):
    .venv64/Scripts/python.exe data/backtest/corner_scratch_20261004/scratch_b.py --clone <新しいパス.db>
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WT))

from scripts import backfill_corner_orders as bf  # noqa: E402

PROD_DB = Path(r"C:\Users\kizun\dev\keiba-yosou\data\keiba.db")
RAW_DIR = Path(r"C:\Users\kizun\dev\keiba-yosou\data\raw\RACE")
HERE = Path(__file__).resolve().parent
WATCH = ["win_odds", "odds_fetched_at", "odds_dataspec", "win_popularity", "jockey_code", "jockey_short_name",
         "burden_weight", "horse_weight", "weight_change_sign", "weight_change_diff", "finish_order",
         "confirmed_order", "finish_time", "abnormal_code", "final_3f", "leg_quality_code", "data_div",
         "blood_register_num"]
WHERE = "(race_year || race_month_day) BETWEEN ? AND ? AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10"


def make_clone(clone: Path) -> dict:
    prod_state_before = bf.db_state(PROD_DB)
    t0 = datetime.now().isoformat(timespec="seconds")
    src = sqlite3.connect(f"file:{PROD_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(clone)
    counts = {}
    src.execute("BEGIN")                      # 1 つの読み取りトランザクション (一貫した snapshot)
    for table in ("horse_races", "races"):
        cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
        ddl = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
        dst.execute(ddl)
        rows = src.execute(f"SELECT {', '.join(cols)} FROM {table} WHERE {WHERE}", (bf.FROM_DATE, bf.TO_DATE)).fetchall()
        dst.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
        counts[table] = len(rows)
    src.execute("COMMIT")
    src.close()
    dst.commit()
    dst.close()
    t1 = datetime.now().isoformat(timespec="seconds")
    return {"prod_read_started": t0, "prod_read_finished": t1, "prod_state_before_read": prod_state_before,
            "prod_state_after_read": bf.db_state(PROD_DB), "clone_rows": counts}


def snapshot(path: Path) -> tuple[list[str], dict]:
    conn = sqlite3.connect(path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(horse_races)")]
    rows = {tuple(r[cols.index(c)] for c in bf.PK): r for r in conn.execute(f"SELECT {', '.join(cols)} FROM horse_races")}
    conn.close()
    return cols, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clone", required=True)
    args = ap.parse_args()
    clone = Path(args.clone).resolve()
    if clone == PROD_DB.resolve() or clone.exists():
        raise SystemExit(f"clone は新しいパスにする: {clone}")
    out = {"clone": str(clone), **make_clone(clone)}
    cols, before = snapshot(clone)
    rc = bf.main(["--db", str(clone), "--raw-dir", str(RAW_DIR), "--apply", "--report", str(HERE / "scratch_b_backfill_report.json")])
    report = json.loads((HERE / "scratch_b_backfill_report.json").read_text(encoding="utf-8"))
    _, after = snapshot(clone)
    changed = Counter()
    for key, row in after.items():
        old = before[key]
        for i, c in enumerate(cols):
            if row[i] != old[i]:
                changed[c] += 1
    watch = {c: changed.get(c, 0) for c in WATCH}
    out.update({
        "backfill_rc": rc, "backfill_result": report.get("result"), "backfill_error": report.get("error"),
        "updated_rows": report.get("updated_rows"), "planned_updates": report.get("planned_updates"),
        "null_remaining_after": report.get("null_remaining_after"), "raw_keys_not_in_db": report.get("raw_keys_not_in_db"),
        "acceptance_after_ok": (report.get("acceptance_after") or {}).get("ok"),
        "min_monthly_c4_rate": min(v for v in (report.get("acceptance_after") or {}).get("monthly_c4_rate", {"x": 0}).values()),
        "same_primary_keys": set(before) == set(after), "rows": len(after),
        "changed_cells_by_column": dict(changed),
        "only_corner_columns_changed": set(changed) <= set(bf.CORNERS),
        "watched_columns_changed_rows": watch,
        "watched_all_identical": all(v == 0 for v in watch.values()),
    })
    out["accepted"] = bool(rc == 0 and out["backfill_result"] == "applied" and out["acceptance_after_ok"]
                           and out["same_primary_keys"] and out["only_corner_columns_changed"] and out["watched_all_identical"])
    (HERE / "scratch_b_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("watched_columns_changed_rows",)}, ensure_ascii=False, indent=1))
    return 0 if out["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
