"""data/raw/RACE/ の全ファイルを再 dispatch し、新規対応レコードを DB に投入する。

O2-O6 (式別オッズ) / H1・H6 (票数) / JG (除外) / WF (WIN5) は parser 追加前に
取り込んだファイルが ingested_files に「取り込み済み」として記録されているため、
通常の ingest_all (is_file_ingested で skip) では再取得されない。本スクリプトは
RACE 配下を強制的に再 dispatch する一回限りのバックフィル。

設計:
- RA/SE/HR/O1 は INSERT OR REPLACE で冪等なので再処理しても安全 (重複しない)。
- N ファイル毎に commit してクラッシュ一貫性を確保 (open_db の一括 commit だと
  150M 行規模で巨大 WAL になる)。中断しても committed 分は残り、再実行で続行可能。
- 進捗を逐次 print (bg 実行のモニタ用)。

使い方: .venv64/Scripts/python.exe scripts/backfill_race_extras.py
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR
from db import connect, init_db, record_ingested_file
from jvlink_client.ingest import ingest_file_dispatch

COMMIT_EVERY = 50


def main() -> None:
    race_dir = DATA_DIR / "raw" / "RACE"
    files = sorted(p for p in race_dir.iterdir() if p.suffix == ".jvd")
    total = len(files)
    print(f"backfill RACE: {total} files", flush=True)

    conn = connect()
    init_db(conn)
    extras_total: Counter = Counter()
    core_total = Counter()  # RA/SE/HR/O1/UM
    t0 = time.time()
    done = 0
    try:
        for f in files:
            file_extras: dict[str, int] = {}
            ra, se, hr, o1, um, skipped = ingest_file_dispatch(
                conn, f, "RACE", extra_counts=file_extras
            )
            core_total["RA"] += ra
            core_total["SE"] += se
            core_total["HR"] += hr
            core_total["O1"] += o1
            extras_total.update(file_extras)
            record_ingested_file(
                conn, f.name, "RACE",
                ra + se + hr + o1 + um + sum(file_extras.values()),
            )
            done += 1
            if done % COMMIT_EVERY == 0:
                conn.commit()
                el = time.time() - t0
                rate = done / el if el else 0
                eta = (total - done) / rate if rate else 0
                print(
                    f"[{done}/{total}] {el:.0f}s eta={eta:.0f}s "
                    f"extras={dict(extras_total)}",
                    flush=True,
                )
        conn.commit()
    finally:
        conn.close()
    print(
        f"DONE {done}/{total} in {time.time()-t0:.0f}s\n"
        f"  core(re-upsert)={dict(core_total)}\n"
        f"  extras={dict(extras_total)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
