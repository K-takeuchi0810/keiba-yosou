"""Fetch realtime win/place odds (O1 via 0B31) and update horse_races."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from jvlink_client import JVLinkClient
from jvlink_client.ingest import ingest_all
from scripts.backtest import list_races


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
    args = ap.parse_args()

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

    summaries = []
    with JVLinkClient() as cli:
        for race in races:
            key = race_key(race)
            summaries.append(cli.fetch_realtime("0B31", key))

    ingest = ingest_all(force=True, dataspecs=["0B31"])
    print({"races": len(races), "fetch": summaries, "ingest": ingest})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
