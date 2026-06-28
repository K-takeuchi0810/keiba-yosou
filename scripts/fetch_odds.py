"""Fetch realtime win/place odds (O1 via 0B31) and update horse_races."""

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from jvlink_client import JVLinkClient
from jvlink_client.ingest import ingest_all
from scripts.backtest import list_races

ROOT_DIR = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT_DIR / "data" / "logs" / "fetch_odds.lock"


@contextmanager
def single_run_lock(max_age_sec: int = 60 * 60):
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - LOCK_PATH.stat().st_mtime
        except OSError:
            age = 0
        if age > max_age_sec:
            try:
                LOCK_PATH.unlink()
                fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except OSError:
                print(f"another fetch_odds run is active: {LOCK_PATH}", flush=True)
                yield False
                return
        else:
            print(f"another fetch_odds run is active: {LOCK_PATH}", flush=True)
            yield False
            return
    try:
        os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode("ascii"))
        os.close(fd)
        yield True
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def race_key(race: dict) -> str:
    return (
        race["race_year"]
        + race["race_month_day"]
        + race["track_code"]
        + race["kaiji"]
        + race["nichiji"]
        + race["race_num"]
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD")
    ap.add_argument("--from", dest="from_date")
    ap.add_argument("--to", dest="to_date")
    ap.add_argument(
        "--timeout-sec",
        type=int,
        default=None,
        help="JVGets が未配信 (-3) のとき、1レースあたり待つ秒数",
    )
    args = ap.parse_args()

    if args.timeout_sec is not None:
        os.environ["JVLINK_REALTIME_NO_DATA_SEC"] = str(max(0, args.timeout_sec))

    if args.date:
        from_date = to_date = args.date
    elif args.from_date and args.to_date:
        from_date, to_date = args.from_date, args.to_date
    else:
        with open_db() as conn:
            row = conn.execute("SELECT MAX(race_year || race_month_day) FROM races").fetchone()
            from_date = to_date = row[0]

    with open_db() as conn:
        races = list_races(conn, from_date, to_date, jra_only=True)

    print(
        f"fetch_odds date={from_date}-{to_date} races={len(races)} "
        f"timeout_sec={os.environ.get('JVLINK_REALTIME_NO_DATA_SEC', '30')}",
        flush=True,
    )
    if not races:
        return 0

    summaries = []
    errors = []
    with single_run_lock() as acquired:
        if not acquired:
            return 0
        with JVLinkClient() as cli:
            for idx, race in enumerate(races, start=1):
                key = race_key(race)
                tc = race.get("track_code")
                rn = int(race.get("race_num") or 0)
                print(f"  fetching {idx}/{len(races)} {tc} {rn:02d}R ...", end=" ", flush=True)
                try:
                    result = cli.fetch_realtime("0B31", key)
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
                summaries.append(result)

    fetched_files = {
        name
        for result in summaries
        for name in (result.get("filenames") or [])
        if name
    }
    if fetched_files:
        ingest = ingest_all(dataspecs=["0B31"], only_files=fetched_files)
    else:
        ingest = {"skipped": "no odds records"}
    print({"races": len(races), "fetched": len(summaries), "errors": errors, "ingest": ingest})
    if errors and not summaries:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
