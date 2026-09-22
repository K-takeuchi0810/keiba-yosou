"""確定払戻の滞留を検知する (2026-09-23)。

## なぜ要るか

2026-09-19 から 4 開催日ぶんの確定払戻 (`payouts.data_div='2'`) が届かないまま
3 日以上経過していたのに、**誰も気付かなかった**。気付いたのは、評価から速報
払戻を除外する改修を入れて「9/21 の答え合わせが 0 件になる」と分かったとき。

評価側は「データが不完全なら評価しない」という安全側の設計にした。だが黙って
評価を止めるだけだと、**永久に「一時状態」のまま落ち続けて何も鳴らない**。
これはその鳴らす側。

## 3 つの状態を混同しない

    データが遅れている        ← 供給側。JV-Link の last_timestamp が進まない
    取得が失敗している        ← 取り込み側。timestamp は進むのに DB に入らない
    取得は成功したが集計だけ失敗 ← 後段。2026-09-21 に外部バッチで実際に起きた

このスクリプトは 1 つ目と 2 つ目を区別できるよう、DB の状態と
**JV-Link 側の last_timestamp** の両方を出す。

## 判定

    pending = 実施済み AND 着順確定済み AND 払戻が最終確定でない

**中止レースは絶対に pending へ入れない** (永久に届かないので鳴らし続ける)。
経過時間で深刻度を上げる:

    当日中     INFO
    翌日       WARN
    48 時間超  ERROR

到着したら **自動で解消**する。手動でフラグを消す設計にはしない。

## 使い方

    python -m scripts.payout_finality_monitor            # 直近 14 日
    python -m scripts.payout_finality_monitor --days 30
    python -m scripts.payout_finality_monitor --json     # 1 行 JSON

exit code: 0=OK/INFO, 1=WARN, 2=ERROR (Task Scheduler から検知できるように)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import DB_PATH  # noqa: E402
from db import (  # noqa: E402
    FINAL_PAYOUT_DATA_DIV, expects_a_finishing_order, is_evaluable_race,
)

JST = timezone(timedelta(hours=9), "JST")

#: 経過時間ごとの深刻度。開催日の 24:00 (JST) を起点に数える。
INFO_UNTIL_HOURS = 24      # 当日中
WARN_UNTIL_HOURS = 48      # 翌日
# それ以降は ERROR

STATUS_ORDER = {"OK": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
EXIT_CODES = {"OK": 0, "INFO": 0, "WARN": 1, "ERROR": 2}

PENDING_REASON = "payout_not_yet_final"


def _severity(age_hours: float) -> str:
    if age_hours <= INFO_UNTIL_HOURS:
        return "INFO"
    if age_hours <= WARN_UNTIL_HOURS:
        return "WARN"
    return "ERROR"


def latest_race_source_timestamp() -> str | None:
    """JV-Link が返した RACE の last_timestamp。

    これが進んでいないなら供給側の遅れ、進んでいるのに DB に入らないなら
    取り込み側の障害。両者を取り違えないために出す。
    """
    try:
        from jvlink_client.state import load_state

        return load_state().get("RACE")
    except Exception:                                      # noqa: BLE001
        return None


def race_day_counts(conn: sqlite3.Connection, day: str) -> dict:
    """1 開催日ぶんの内訳。

    `executed` は「中止でない」。`result_final` は着順が付くはずの馬が全員
    そろったレース。`payout_final` は確定払戻が届いたレース。
    """
    rows = conn.execute(
        """
        SELECT r.track_code, r.race_num, r.data_div AS race_div,
               h.abnormal_code, h.confirmed_order
          FROM races r
          LEFT JOIN horse_races h
            ON r.race_year=h.race_year AND r.race_month_day=h.race_month_day
           AND r.track_code=h.track_code AND r.kaiji=h.kaiji
           AND r.nichiji=h.nichiji AND r.race_num=h.race_num
         WHERE r.race_year=? AND r.race_month_day=?
           AND CAST(r.track_code AS INTEGER) BETWEEN 1 AND 10
        """,
        (day[:4], day[4:]),
    ).fetchall()

    scheduled: set[tuple] = set()
    cancelled: set[tuple] = set()
    expected: dict[tuple, int] = {}
    finished: dict[tuple, int] = {}
    for r in rows:
        key = (r["track_code"], r["race_num"])
        scheduled.add(key)
        if not is_evaluable_race(r["race_div"]):
            cancelled.add(key)
            continue
        if r["abnormal_code"] is None and r["confirmed_order"] is None:
            continue                                   # LEFT JOIN の空行
        if not expects_a_finishing_order(r["abnormal_code"]):
            continue
        expected[key] = expected.get(key, 0) + 1
        if (r["confirmed_order"] or 0) > 0:
            finished[key] = finished.get(key, 0) + 1

    executed = scheduled - cancelled
    result_final = {k for k in executed
                    if expected.get(k, 0) > 0 and finished.get(k, 0) == expected[k]}

    pay = conn.execute(
        """
        SELECT track_code, race_num, data_div
          FROM payouts
         WHERE race_year=? AND race_month_day=?
        """,
        (day[:4], day[4:]),
    ).fetchall()
    payout_final = {(p["track_code"], p["race_num"]) for p in pay
                    if str(p["data_div"] or "").strip() == FINAL_PAYOUT_DATA_DIV}
    payout_prelim = {(p["track_code"], p["race_num"]) for p in pay} - payout_final

    # ★ 中止は絶対に pending へ入れない (永久に届かないので鳴らし続ける)
    pending = sorted(result_final - payout_final)

    return {
        "date": day,
        "scheduled": len(scheduled),
        "cancelled": len(cancelled),
        "executed": len(executed),
        "result_final": len(result_final),
        "payout_preliminary": len(payout_prelim),
        "payout_final": len(payout_final),
        "evaluable": len(result_final & payout_final),
        "pending_race_ids": [f"{day}-{t}-{n}" for t, n in pending],
    }


def build(days: int = 14, db_path: str | None = None, now: datetime | None = None
          ) -> dict:
    now = (now or datetime.now(JST)).astimezone(JST)
    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        since = (now - timedelta(days=days)).strftime("%Y%m%d")
        race_days = [r[0] + r[1] for r in conn.execute(
            """SELECT DISTINCT race_year, race_month_day FROM races
                WHERE (race_year || race_month_day) BETWEEN ? AND ?
                  AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
                ORDER BY 1, 2""",
            (since, now.strftime("%Y%m%d")))]
        per_day = [race_day_counts(conn, d) for d in race_days]
    finally:
        conn.close()

    pending_days = [d for d in per_day if d["pending_race_ids"]]
    status, oldest, age_hours = "OK", None, 0.0
    if pending_days:
        oldest = min(d["date"] for d in pending_days)
        # 開催日の 24:00 (JST) を起点に数える。当日中はまだ届いていなくて当然。
        base = datetime.strptime(oldest, "%Y%m%d").replace(tzinfo=JST) \
            + timedelta(days=1)
        age_hours = max(0.0, (now - base).total_seconds() / 3600.0)
        status = _severity(age_hours)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "status": status,
        "oldest_pending_race_date": oldest,
        "pending_race_count": sum(len(d["pending_race_ids"]) for d in pending_days),
        "pending_race_ids": [r for d in pending_days for r in d["pending_race_ids"]],
        "pending_reason": PENDING_REASON if pending_days else None,
        "age_hours": round(age_hours, 1),
        "latest_race_source_timestamp": latest_race_source_timestamp(),
        "days": per_day,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--json", action="store_true", help="1 行 JSON で出力")
    args = ap.parse_args()

    report = build(days=args.days)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return EXIT_CODES[report["status"]]

    print(f"payout finality: {report['status']}")
    for d in report["days"]:
        mark = " ←滞留" if d["pending_race_ids"] else ""
        print(f"  {d['date']}  予定{d['scheduled']:3d} 中止{d['cancelled']:3d}"
              f" 実施{d['executed']:3d} 着順確定{d['result_final']:3d}"
              f" 払戻速報{d['payout_preliminary']:3d} 払戻確定{d['payout_final']:3d}"
              f" 評価可{d['evaluable']:3d}{mark}")
    if report["oldest_pending_race_date"]:
        print(f"  最古の滞留: {report['oldest_pending_race_date']} 開催分から "
              f"{report['pending_reason']}、{report['age_hours']:.0f} 時間経過 "
              f"({report['pending_race_count']} レース)")
    print(f"  JV-Link RACE last_timestamp: "
          f"{report['latest_race_source_timestamp']}")
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
