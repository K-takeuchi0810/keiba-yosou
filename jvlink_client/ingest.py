"""data/raw/ 配下の生 JV-Data ファイルを SQLite に取り込む。

設計方針:
- ファイル名先頭 2 文字がレコード種別とは限らない（"RAMM" のように
  サマリ系ファイルが他種レコードを持つ場合がある）。レコードを CRLF で
  分割して中身の先頭 2 バイトで dispatch する方が頑健。
- BSTR ラウンドトリップでレコード長が ±数バイトずれることがあるので、
  parse_xx 側でパディング/切詰しているのに合わせ、ここでは長さチェックしない。
- 1 ファイル中の 1 レコードがおかしくても全体を止めない（try-except per record）。
- 1 ファイルが致命的におかしくても次のファイルに進む（log + skip）。
"""

from __future__ import annotations

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

from config import DATA_DIR
from db import (
    is_file_ingested,
    open_db,
    record_ingested_file,
    upsert_horse_race,
    upsert_payout,
    upsert_race,
    update_win_odds,
    upsert_horse_master,
)
from jvlink_client.parser import (
    HR_LENGTH,
    RA_LENGTH,
    SE_LENGTH,
    parse_hr,
    parse_o1,
    parse_ra,
    parse_se,
    parse_hs,
    parse_um,
)

RAW_DIR = DATA_DIR / "raw"


def _split_records(data: bytes) -> list[bytes]:
    """JV-Data のレコード区切りで分割。

    JVGets で取得した raw は各レコード末尾が `\\r\\n\\x00` (3 byte) になっている
    ため、 `\\r\\n` で素朴に split すると次レコード先頭に `\\x00` がぶら下がり、
    `record_type` (先頭 2 byte) が `\\x00\\x00` になって全レコードが種別不明で
    スキップされる。`\\r\\n` 直後の `\\x00` も除去する。
    """
    if b"\r\n" not in data:
        return [data] if data else []
    raw_parts = data.split(b"\r\n")
    out: list[bytes] = []
    for p in raw_parts:
        # 区切りの直後にある制御 NUL を 1 つだけ落とす
        if p.startswith(b"\x00"):
            p = p[1:]
        if p:
            out.append(p)
    return out


def ingest_file_dispatch(conn, path: Path, dataspec: str = "") -> tuple[int, int, int, int, int, int]:
    """ファイルを開き、レコード単位に分割 → 種別別に DB へ。

    戻り値: (ra_count, se_count, hr_count, o1_count, skipped)
    """
    data = path.read_bytes()
    records = _split_records(data)
    fetched_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    ra_count = 0
    se_count = 0
    hr_count = 0
    o1_count = 0
    um_count = 0
    skipped = 0

    for rec in records:
        if len(rec) < 2:
            skipped += 1
            continue
        rec_type = rec[:2].decode("latin-1", errors="replace")
        try:
            if rec_type == "RA":
                ra = parse_ra(rec)
                upsert_race(conn, ra)
                ra_count += 1
            elif rec_type == "SE":
                se = parse_se(rec)
                upsert_horse_race(conn, se)
                se_count += 1
            elif rec_type == "HR":
                hr = parse_hr(rec)
                upsert_payout(conn, hr)
                hr_count += 1
            elif rec_type == "O1":
                o1 = parse_o1(rec)
                update_win_odds(conn, o1, fetched_at=fetched_at, dataspec=dataspec or "0B31")
                o1_count += 1
            elif rec_type == "UM":
                um = parse_um(rec)
                upsert_horse_master(conn, um)
                um_count += 1
            elif rec_type == "HS":
                hs = parse_hs(rec)
                upsert_horse_master(conn, hs)
                um_count += 1
            else:
                # 未対応レコード種別。後段で他テーブル実装するまでスキップ。
                skipped += 1
        except Exception:
            skipped += 1

    return ra_count, se_count, hr_count, o1_count, um_count, skipped


def ingest_all(
    force: bool = False,
    dataspecs: list[str] | None = None,
    only_files: set[str] | None = None,
    modified_since: float | None = None,
) -> dict:
    """data/raw/ 配下の全ファイルを取り込む。

    既に取り込み済みのファイルはスキップ（force=True で再取り込み）。
    1 ファイルでエラーが出ても残りに影響させない。

    JV-Link は **同名ファイル名のまま内容を更新** する運用 (週次 RACE 等) のため、
    is_file_ingested による「ファイル名ベース重複判定」だけでは新着内容を取り
    こぼす。直近の取得で書き出されたファイルだけ再 ingest したい場合は、
    `only_files` (ファイル名 set) または `modified_since` (Unix epoch 秒) で
    対象を絞ってください。これらが指定されれば force=False でも処理されます。
    """
    summary = {
        "files_processed": 0,
        "files_skipped": 0,
        "files_errored": 0,
        "RA": 0,
        "SE": 0,
        "HR": 0,
        "O1": 0,
        "UM": 0,
        "records_skipped": 0,
        "errors": [],
    }
    if not RAW_DIR.exists():
        return summary

    with open_db() as conn:
        for ds_dir in sorted(RAW_DIR.iterdir()):
            if not ds_dir.is_dir():
                continue
            if dataspecs is not None and ds_dir.name not in dataspecs:
                continue
            for f in sorted(ds_dir.iterdir()):
                if not f.suffix == ".jvd":
                    continue
                # only_files / modified_since が指定されたら、それに該当する
                # ファイルは強制的に再 ingest (force 相当)。指定外はスキップ。
                fresh = False
                if only_files is not None and f.name in only_files:
                    fresh = True
                if modified_since is not None and f.stat().st_mtime >= modified_since:
                    fresh = True
                if (only_files is not None or modified_since is not None) and not fresh:
                    summary["files_skipped"] += 1
                    continue
                if not fresh and not force and is_file_ingested(conn, f.name):
                    summary["files_skipped"] += 1
                    continue
                try:
                    ra_n, se_n, hr_n, o1_n, um_n, skipped = ingest_file_dispatch(conn, f, ds_dir.name)
                    summary["RA"] += ra_n
                    summary["SE"] += se_n
                    summary["HR"] += hr_n
                    summary["O1"] += o1_n
                    summary["UM"] += um_n
                    summary["records_skipped"] += skipped
                    summary["files_processed"] += 1
                    record_ingested_file(conn, f.name, ds_dir.name, ra_n + se_n + hr_n + o1_n + um_n)
                except Exception as e:
                    summary["files_errored"] += 1
                    summary["errors"].append(
                        {"file": f.name, "error": f"{type(e).__name__}: {e}"}
                    )
                    # スタックトレースを残しつつ次ファイルへ続行
                    logger.error("ingest failed: %s", f.name, exc_info=True)

    return summary


if __name__ == "__main__":
    print(ingest_all())
