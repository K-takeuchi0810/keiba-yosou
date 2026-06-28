"""Fetch finalized race results via realtime 0B12 and ingest them.

Default target is yesterday. 0B12 is the realtime "race information after
result finalization" feed and is available by race key YYYYMMDDJJRR.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from jvlink_client import JVLinkClient
from jvlink_client.ingest import ingest_all


def normalize_date(value: str | None) -> str:
    if not value or value.lower() == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    if value.lower() == "today":
        return datetime.now().strftime("%Y%m%d")
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 8:
        raise SystemExit(f"invalid date: {value!r}")
    return digits


def race_result_key(race: dict) -> str:
    return (
        str(race["race_year"])
        + str(race["race_month_day"])
        + str(race["track_code"])
        + str(race["race_num"])
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch finalized race results (0B12)")
    ap.add_argument("--date", default="yesterday", help="YYYYMMDD / today / yesterday")
    ap.add_argument(
        "--timeout-sec",
        type=int,
        default=3,
        help="JVGets が未配信 (-3) のとき、1レースあたり待つ秒数",
    )
    args = ap.parse_args()

    target_date = normalize_date(args.date)
    os.environ["JVLINK_REALTIME_NO_DATA_SEC"] = str(max(0, args.timeout_sec))

    with open_db() as conn:
        rows = conn.execute(
            """
            SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num
              FROM races
             WHERE race_year || race_month_day = ?
               AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
             ORDER BY track_code, race_num
            """,
            (target_date,),
        ).fetchall()
    races = [dict(row) for row in rows]

    print(
        f"fetch_results date={target_date} races={len(races)} "
        f"timeout_sec={os.environ['JVLINK_REALTIME_NO_DATA_SEC']}",
        flush=True,
    )
    if not races:
        return 0

    fetched = []
    errors = []
    with JVLinkClient() as cli:
        for idx, race in enumerate(races, start=1):
            key = race_result_key(race)
            tc = race.get("track_code")
            rn = int(race.get("race_num") or 0)
            print(f"  fetching {idx}/{len(races)} {tc} {rn:02d}R key={key} ...", end=" ", flush=True)
            try:
                result = cli.fetch_realtime("0B12", key)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {str(exc)[:120]}"
                print(f"error {reason}", flush=True)
                errors.append({"race_key": key, "error": reason})
                continue
            records = int(result.get("records_total") or 0)
            files = int(result.get("files_written") or 0)
            if result.get("timed_out"):
                status = "timeout"
            elif result.get("no_data"):
                status = "no_data"
            elif records > 0:
                status = "ok"
            else:
                status = "empty"
            print(f"{status} records={records} files={files}", flush=True)
            fetched.append(result)

    fetched_files = {
        name
        for result in fetched
        for name in (result.get("filenames") or [])
        if name
    }
    if fetched_files:
        ingest = ingest_all(dataspecs=["0B12"], only_files=fetched_files)
    else:
        ingest = {"skipped": "no result records"}
    print({"races": len(races), "fetched": len(fetched), "errors": errors, "ingest": ingest})
    if errors and not fetched:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
