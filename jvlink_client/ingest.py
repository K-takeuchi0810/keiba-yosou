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
    upsert_breeding_horse,
    upsert_horse_race,
    upsert_horse_master,
    upsert_mining_prediction,
    upsert_offspring_master,
    upsert_payout,
    upsert_race,
    upsert_special_entry,
    upsert_jockey_master,
    upsert_owner_master,
    upsert_producer_master,
    upsert_trainer_master,
    upsert_training_time,
    update_win_odds,
)
from jvlink_client.parser import (
    HR_LENGTH,
    RA_LENGTH,
    SE_LENGTH,
    parse_bn,
    parse_br,
    parse_ch,
    parse_ks,
    parse_dm,
    parse_hc,
    parse_hn,
    parse_hr,
    parse_hs,
    parse_o1,
    parse_ra,
    parse_se,
    parse_sk,
    parse_tk,
    parse_tm,
    parse_um,
    parse_wc,
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

    戻り値: (ra_count, se_count, hr_count, o1_count, um_count, skipped)。
    Phase 1 新規 dataspec (DM/TM/HN/SK/HC/WC/TK) は本戻り値タプルに含めない
    (互換維持)。代わりに ingest_all の summary 辞書に extra カウンタを集計。
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
            # === Phase 1 新規 dataspec (2026-05-13) ===
            elif rec_type == "DM":
                for mp in parse_dm(rec):
                    upsert_mining_prediction(conn, mp)
            elif rec_type == "TM":
                for mp in parse_tm(rec):
                    upsert_mining_prediction(conn, mp)
            elif rec_type == "HN":
                hn = parse_hn(rec)
                upsert_breeding_horse(conn, hn)
            elif rec_type == "SK":
                sk = parse_sk(rec)
                upsert_offspring_master(conn, sk)
            elif rec_type == "HC":
                hc = parse_hc(rec)
                upsert_training_time(conn, hc)
            elif rec_type == "WC":
                wc = parse_wc(rec)
                upsert_training_time(conn, wc)
            elif rec_type == "TK":
                for se_ in parse_tk(rec):
                    upsert_special_entry(conn, se_)
            # === マスタ系 (2026-06-28 追加: DIFN/HOSE) ===
            elif rec_type == "KS":
                upsert_jockey_master(conn, parse_ks(rec))
            elif rec_type == "CH":
                upsert_trainer_master(conn, parse_ch(rec))
            elif rec_type == "BR":
                upsert_producer_master(conn, parse_br(rec))
            elif rec_type == "BN":
                upsert_owner_master(conn, parse_bn(rec))
            else:
                # 未対応レコード種別 (BN/KS/CH/CK/RC/HY/YS/JG/WH/WE/AV/JC/CC 等)
                skipped += 1
        except Exception:
            skipped += 1

    return ra_count, se_count, hr_count, o1_count, um_count, skipped


def ingest_all(
    force: bool = False,
    dataspecs: list[str] | None = None,
    only_files: set[str] | None = None,
    modified_since: float | None = None,
    raw_dir: Path | None = None,
) -> dict:
    """`raw_dir` (省略時は data/raw/) 配下の全ファイルを取り込む。

    既に取り込み済みのファイルはスキップ（force=True で再取り込み）。
    1 ファイルでエラーが出ても残りに影響させない。

    JV-Link は **同名ファイル名のまま内容を更新** する運用 (週次 RACE 等) のため、
    is_file_ingested による「ファイル名ベース重複判定」だけでは新着内容を取り
    こぼす。fetch 直後の取り込みでは `only_files` に fetch が返した filenames を
    渡すこと (該当ファイルは ingest 済みでも強制再取込)。

    only_files の指定外ファイルは「通常判定」(未取り込みなら処理) に落ちる。
    旧仕様 (指定外を全 skip) は、fetch 後・ingest 前にクラッシュした取り残し
    ファイルが永久に未取込になる回復性の穴があった (2026-06-13 v2 監査指摘)。
    `modified_since` (Unix epoch 秒) は従来どおり「それ以降の変更だけに絞る」
    制限フィルタとして機能する。

    過去バルクデータ (data/raw_old_bstr/) のような別ディレクトリから読み込みたい
    ときは `raw_dir` を渡す。
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
    root = raw_dir or RAW_DIR
    if not root.exists():
        return summary

    # 処理順: RACE (レース/出走馬の基礎行) → その他マスタ → 0B* (リアルタイム系)。
    # update_win_odds 等の 0B* 取り込みは horse_races 行への UPDATE-only で、
    # 行が無ければ黙って 0 件になる。素朴な辞書順 ("0B14" < "RACE") だと
    # 空 DB からの raw 全量再構築でリアルタイムオッズが全損していた
    # (2026-06-13 v2 監査指摘)。
    def _dir_priority(name: str) -> tuple:
        if name == "RACE":
            return (0, name)
        if name.startswith("0B"):
            return (2, name)
        return (1, name)

    with open_db() as conn:
        for ds_dir in sorted(root.iterdir(), key=lambda p: _dir_priority(p.name)):
            if not ds_dir.is_dir():
                continue
            if dataspecs is not None and ds_dir.name not in dataspecs:
                continue
            for f in sorted(ds_dir.iterdir()):
                if not f.suffix == ".jvd":
                    continue
                # only_files に該当 → ingest 済みでも強制再取込 (同名更新対応)。
                # modified_since 該当も同様。それ以外は通常判定に落ちる
                # (未取り込みなら処理 = クラッシュ取り残しの回復性を維持)。
                fresh = False
                if only_files is not None and f.name in only_files:
                    fresh = True
                if modified_since is not None and f.stat().st_mtime >= modified_since:
                    fresh = True
                if modified_since is not None and only_files is None and not fresh:
                    # modified_since 単独指定は従来互換の「制限フィルタ」
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
