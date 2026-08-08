"""フル再取得スクリプト (1986-現在の RACE + HOSE)。

JVGets 切り替え後の正しい raw を取り直すために使う。
JV-Link ローカルキャッシュにファイルがある分は再 DL されず読み出しのみで済む。

usage:
    python -m scripts.fetch_full
    python -m scripts.fetch_full --dataspecs RACE
    python -m scripts.fetch_full --fromtime 20200101000000

注意: 数十分〜数時間かかる可能性あり。
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jvlink_client.client import JVLinkClient
from jvlink_client.ingest import ingest_all


def _current_week_fromtime(today: date | None = None) -> str:
    """Return Monday 00:00:00 for JVOpen option=2 catch-up."""
    current = today or date.today()
    monday = current - timedelta(days=current.weekday())
    return datetime.combine(monday, datetime.min.time()).strftime("%Y%m%d%H%M%S")


def _is_no_data(summary: dict) -> bool:
    return re.search(r"\brc=-1(?!\d)", str(summary.get("error") or "")) is not None


def _empty_summary(dataspec: str) -> dict:
    return {
        "dataspec": dataspec,
        "no_data": True,
        "files_written": 0,
        "records_total": 0,
        "last_timestamp": None,
        "bad_files": [],
        "filenames": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dataspecs", nargs="+", default=["RACE", "HOSE"],
        help="取得する dataspec (デフォルト: RACE HOSE)",
    )
    ap.add_argument(
        "--fromtime", default=None,
        help="開始タイムスタンプ yyyymmddHHMMSS (省略時はデフォルト 19860101000000)",
    )
    ap.add_argument(
        "--option", type=int, default=1, choices=[1, 2, 3, 4],
        help="JVOpen option (1=通常差分, 2=今週, 3,4=セットアップ)",
    )
    ap.add_argument(
        "--retries", type=int, default=None,
        help="JVOpen の通信系エラー(-413等)をリトライする回数",
    )
    ap.add_argument(
        "--ingest", action="store_true",
        help="取得したファイルを直後にSQLiteへ取り込む（日次運用向け）",
    )
    args = ap.parse_args()

    started = time.time()

    def on_progress(stage: str, info: dict) -> None:
        elapsed = int(time.time() - started)
        print(f"  [{elapsed:>5}s {stage:>8}] {info}", flush=True)

    print(f"=== fetch start: option={args.option} dataspecs={args.dataspecs} ===")
    if args.fromtime:
        print(f"fromtime override: {args.fromtime}")

    with JVLinkClient() as cli:
        summaries = cli.fetch_all(
            fromtime=args.fromtime,
            option=args.option,
            dataspecs=args.dataspecs,
            on_progress=on_progress,
            retry_attempts=args.retries,
        )

        # option=1 can legitimately return rc=-1 when its saved cursor has no
        # newer files even though the current week's race card is absent from
        # SQLite.  Retry RACE with option=2 so a missed/stalled morning run can
        # recover without an operator resetting fetch_state.json.
        race_no_data = next(
            (s for s in summaries if s.get("dataspec") == "RACE" and _is_no_data(s)),
            None,
        )
        if args.option == 1 and args.fromtime is None and race_no_data is not None:
            catchup_from = _current_week_fromtime()
            print(
                f"RACE incremental fetch has no data; retry current week from {catchup_from}",
                flush=True,
            )
            catchup = cli.fetch_all(
                fromtime=catchup_from,
                option=2,
                dataspecs=["RACE"],
                on_progress=on_progress,
                retry_attempts=args.retries,
            )
            summaries = [s for s in summaries if s is not race_no_data] + catchup

    # JVOpen rc=-1 means "no matching data", not an operational failure.
    # RACE has already received the current-week recovery attempt above; other
    # dataspecs (for example HOSE) may normally have no incremental update.
    normalized = []
    for summary in summaries:
        dataspec = str(summary.get("dataspec") or "")
        # A missing RACE card after the current-week retry is actionable on a
        # normal JRA weekend.  Keep it as an error so Discord/watchdog reports
        # the incident.  Weekday and non-RACE no-update responses are normal.
        weekend_race_gap = dataspec == "RACE" and date.today().weekday() >= 5
        if _is_no_data(summary) and not weekend_race_gap:
            normalized.append(_empty_summary(dataspec))
        else:
            normalized.append(summary)
    summaries = normalized

    elapsed = int(time.time() - started)
    print()
    print(f"=== fetch done in {elapsed}s ({elapsed // 60} min) ===")
    for s in summaries:
        ds = s.get("dataspec")
        if "error" in s:
            print(f"  {ds}: ERROR  {s['error']}")
        else:
            print(
                f"  {ds}: files={s.get('files_written'):>5} "
                f"records={s.get('records_total'):>8} "
                f"last_ts={s.get('last_timestamp')} "
                f"bad={len(s.get('bad_files', []))}"
            )

    # -402/-403 の破損ファイルでは client がその dataspec の読み出しを打ち切る。
    # raw が一部書けていても当日RACEが欠け得るため、成功終了にしない。
    fetch_errors = [s for s in summaries if "error" in s or s.get("bad_files")]
    ingest_errors: list[dict] = []
    if args.ingest:
        print()
        print("=== ingest fetched files ===")
        for summary in summaries:
            if "error" in summary:
                continue
            dataspec = str(summary.get("dataspec") or "")
            filenames = set(summary.get("filenames") or [])
            if not dataspec or summary.get("no_data"):
                continue
            got = ingest_all(dataspecs=[dataspec], only_files=filenames)
            print(
                f"  {dataspec}: files={got.get('files_processed', 0)} "
                f"errors={got.get('files_errored', 0)} RA={got.get('RA', 0)} "
                f"SE={got.get('SE', 0)} HR={got.get('HR', 0)}"
            )
            if got.get("files_errored") or got.get("errors"):
                ingest_errors.append({"dataspec": dataspec, "summary": got})

    if fetch_errors:
        print(f"fetch failed for {len(fetch_errors)} dataspec(s)", file=sys.stderr)
        return 1
    if ingest_errors:
        print(f"ingest failed for {len(ingest_errors)} dataspec(s)", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
