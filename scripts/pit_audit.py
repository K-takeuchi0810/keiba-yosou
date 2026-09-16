"""T−10 の PIT 監査 (憲法 Phase 0.5-1)。

対象レースを 1 本ずつ `predictor.pit_t10.t10_market` に通し、
**当時の観測可能情報だけで再現できるか** を検査して数字を出す。

> 937件すべて使える前提で先へ進まないことが重要です。正しい処理をした結果、
> 実際には850件しか残らないのであれば850件が正しい母集団です。

出す数字:
  - PIT 監査合格レース数 / 失敗レース数
  - T−10 オッズ取得成功率
  - T−10 以前にオッズが 1 件も無かったレース数
  - 発走時刻変更があったレース数 / うち T−10 判定に影響した件数
  - 発走後取得データが混入していた件数

usage:
    .venv64/Scripts/python.exe -m scripts.pit_audit [--from YYYYMMDD] [--to YYYYMMDD] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, PIT_GATE_MINUTES  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.pit_t10 import (  # noqa: E402
    RACE_KEYS,
    decision_time,
    start_time_history,
    t10_market,
)
from predictor.provenance import snapshot  # noqa: E402


def audit(from_date: str, to_date: str, db_path: str | None = None) -> dict:
    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = conn.execute(
        """SELECT * FROM races
            WHERE (race_year || race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
            ORDER BY race_year, race_month_day, track_code, race_num""",
        (from_date, to_date)).fetchall()

    c = Counter()
    violations: list[dict] = []
    for r in races:
        race = dict(r)
        c["races_total"] += 1

        hist = start_time_history(conn, race)
        if hist.changes:
            c["races_with_start_time_change"] += 1
        if hist.scheduled is None:
            c["no_start_time"] += 1
            continue

        target, start_used = decision_time(conn, race)
        if target is None:
            c["no_start_time"] += 1
            continue

        # 発走時刻変更が T−10 判定に影響したか (当初予定との差)
        naive_target = hist.scheduled - timedelta(minutes=PIT_GATE_MINUTES)
        if target != naive_target:
            c["change_moved_decision_time"] += 1

        m = t10_market(conn, race)
        if m is None:
            c["no_odds_before_t10"] += 1
            continue

        c["t10_available"] += 1
        if m.ok:
            c["pit_pass"] += 1
        else:
            c["pit_fail"] += 1
            for v in m.violations:
                c[f"violation::{v.split(' ')[0]}"] += 1
            if len(violations) < 20:
                violations.append({"race_id": m.race_id,
                                   "decision_time": m.decision_time,
                                   "violations": m.violations})

        # 発走後に取得したデータが混入していないか (受信が発走時刻以降)
        if start_used is not None and m.odds_received_at >= start_used.isoformat(
                timespec="seconds"):
            c["post_start_data_used"] += 1

    conn.close()
    total = c["races_total"] or 1
    return {
        "meta": {**snapshot(), "from_date": from_date, "to_date": to_date,
                 "gate_minutes": PIT_GATE_MINUTES},
        "races_total": c["races_total"],
        "no_start_time": c["no_start_time"],
        "no_odds_before_t10": c["no_odds_before_t10"],
        "t10_available": c["t10_available"],
        "t10_available_rate": round(c["t10_available"] / total, 4),
        "pit_pass": c["pit_pass"],
        "pit_fail": c["pit_fail"],
        "races_with_start_time_change": c["races_with_start_time_change"],
        "change_moved_decision_time": c["change_moved_decision_time"],
        "post_start_data_used": c["post_start_data_used"],
        "violation_kinds": {k.split("::", 1)[1]: v for k, v in c.items()
                            if k.startswith("violation::")},
        "violation_examples": violations,
    }


def main() -> int:
    dev_from, dev_to = DATA_SPLIT["strategy_dev"]["from"], DATA_SPLIT["strategy_dev"]["to"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=dev_from)
    ap.add_argument("--to", dest="to_date", default=dev_to)
    ap.add_argument("--db", default=None)
    ap.add_argument("--json", default=None, help="結果をこのパスに保存")
    args = ap.parse_args()

    out = audit(args.from_date, args.to_date, args.db)
    t = out["races_total"] or 1
    print(f"=== PIT 監査 {args.from_date}〜{args.to_date} "
          f"(T−{out['meta']['gate_minutes']} 分) ===")
    print(f"  対象レース総数            {out['races_total']:6,d}")
    print(f"  発走時刻が不明            {out['no_start_time']:6,d}")
    print(f"  T−10 以前にオッズ無し     {out['no_odds_before_t10']:6,d}")
    print(f"  T−10 取得できた           {out['t10_available']:6,d}  "
          f"({out['t10_available_rate'] * 100:.1f}%)")
    print(f"    うち PIT 監査 合格      {out['pit_pass']:6,d}")
    print(f"    うち PIT 監査 失敗      {out['pit_fail']:6,d}")
    print(f"  発走時刻変更があった      {out['races_with_start_time_change']:6,d}")
    print(f"    うち T−10 判定に影響    {out['change_moved_decision_time']:6,d}")
    print(f"  発走後データの混入        {out['post_start_data_used']:6,d}")
    if out["violation_kinds"]:
        print("  違反の内訳:")
        for k, v in out["violation_kinds"].items():
            print(f"    {k}: {v}")
    for ex in out["violation_examples"][:3]:
        print(f"    例 {ex['race_id']} @{ex['decision_time']}: {ex['violations']}")
    print()
    print(f"→ **正しい母集団は {out['pit_pass']:,} レース** "
          f"(総数 {out['races_total']:,} の {out['pit_pass'] / t * 100:.1f}%)")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"saved: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
