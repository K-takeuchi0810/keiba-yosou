"""raw 0B31 の O1 スナップショットを odds_snapshots (F3 時系列) へバックフィルする。

ファイル名 `0B31_<YYYYMMDD><track2><kaiji2><nichiji2><race2>_<unix_epoch>.jvd` の
epoch が取得時刻。冪等 (INSERT OR REPLACE)。既知の在庫は 600 レース / 18 開催日
(2026-05-02〜06-28) で少量だが、F3-a の動作検証と初期分析の素材になる。

使い方: .venv64/Scripts/python.exe -m scripts.backfill_odds_snapshots
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR
from db import insert_odds_snapshot, open_db
from jvlink_client.ingest import _split_records
from jvlink_client.parser import parse_o1

PAT = re.compile(r"0B31_(\d{16})_(\d+)\.jvd$")


def main() -> int:
    src = DATA_DIR / "raw" / "0B31"
    files = sorted(src.glob("*.jvd"))
    rows = 0
    snaps = 0
    with open_db() as conn:
        for f in files:
            m = PAT.search(f.name)
            if not m:
                continue
            fetched_at = datetime.fromtimestamp(int(m.group(2))).isoformat(timespec="seconds")
            for rec in _split_records(f.read_bytes()):
                if rec[:2] != b"O1":
                    continue
                n = insert_odds_snapshot(conn, parse_o1(rec), fetched_at, "backfill_0B31")
                if n:
                    rows += n
                    snaps += 1
    print(f"backfilled: {snaps} snapshots, {rows} rows from {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
