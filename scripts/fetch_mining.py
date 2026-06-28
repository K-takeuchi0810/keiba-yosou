"""Fetch realtime data mining predictions (0B13/0B17) and ingest them."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from jvlink_client import JVLinkClient
from jvlink_client.ingest import ingest_all


def normalize_date(value: str | None) -> str:
    if not value or value.lower() == "today":
        return datetime.now().strftime("%Y%m%d")
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 8:
        raise SystemExit(f"invalid date: {value!r}")
    return digits


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch realtime mining predictions")
    ap.add_argument("--date", default="today", help="YYYYMMDD / today")
    ap.add_argument(
        "--timeout-sec",
        type=int,
        default=3,
        help="JVGets が未配信 (-3) のとき、dataspecごとに待つ秒数",
    )
    args = ap.parse_args()

    target_date = normalize_date(args.date)
    os.environ["JVLINK_REALTIME_NO_DATA_SEC"] = str(max(0, args.timeout_sec))

    with open_db() as conn:
        race_count = conn.execute(
            """
            SELECT COUNT(*)
              FROM races
             WHERE race_year || race_month_day = ?
               AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
            """,
            (target_date,),
        ).fetchone()[0]

    print(
        f"fetch_mining date={target_date} races={race_count} "
        f"timeout_sec={os.environ['JVLINK_REALTIME_NO_DATA_SEC']}",
        flush=True,
    )
    if not race_count:
        return 0

    fetched = []
    errors = []
    with JVLinkClient() as cli:
        for dataspec in ("0B13", "0B17"):
            print(f"  fetching {dataspec} key={target_date} ...", end=" ", flush=True)
            try:
                result = cli.fetch_realtime(dataspec, target_date)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {str(exc)[:120]}"
                print(f"error {reason}", flush=True)
                errors.append({"dataspec": dataspec, "error": reason})
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

    fetched_by_ds: dict[str, set[str]] = {}
    for result in fetched:
        dataspec = result.get("dataspec")
        if not dataspec:
            continue
        files = {name for name in (result.get("filenames") or []) if name}
        if files:
            fetched_by_ds.setdefault(str(dataspec), set()).update(files)

    ingest_results = {}
    for dataspec, filenames in fetched_by_ds.items():
        ingest_results[dataspec] = ingest_all(dataspecs=[dataspec], only_files=filenames)
    if not ingest_results:
        ingest_results = {"skipped": "no mining records"}
    print({"fetched": len(fetched), "errors": errors, "ingest": ingest_results})
    if errors and not fetched:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
