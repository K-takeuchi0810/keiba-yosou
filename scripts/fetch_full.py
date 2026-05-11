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
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jvlink_client.client import JVLinkClient


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

    return 0


if __name__ == "__main__":
    sys.exit(main())
