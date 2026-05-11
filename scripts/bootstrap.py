"""一回限りの過去データセットアップ取得（option=4）。

中長期予想に必要な過去データを dataspec ごとに一括ダウンロードし、
raw 保存 → 取り込み可能なものは SQLite に投入する。

所要時間: 回線にもよるが 数時間〜半日。
ディスク使用量: 5〜15 GB（dataspec の組合せにより）。
途中で止まっても JV-Link のローカルキャッシュにより再実行で再開可能。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jvlink_client import JVLinkClient
from jvlink_client.ingest import ingest_all

DEFAULT_FROMTIME = "20200101000000"  # 過去 5 年

# 過去データを取りに行く dataspec（option=4 で取得可能なもの）
BOOTSTRAP_DATASPECS = [
    "RACE",   # 競走情報（最重要、レース・出走馬・払戻 等）
    "DIFN",   # 競走馬マスタ（UM。血統特徴量の父系/母父系に使用）
    "HOSE",   # 競走馬マスタ
    "BLOD",   # 血統
    "SLOP",   # 坂路調教
    "WOOD",   # ウッドチップ調教
    "HOYU",   # 馬主
    "YSCH",   # 開催スケジュール
    "TOKU",   # 特別登録馬
    "COMM",   # コメント
    "MING",   # マイニング予想（過去レース分のみ）
]


def progress(stage: str, info: dict) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {stage}: {info}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fromtime",
        default=DEFAULT_FROMTIME,
        help=f"YYYYMMDDhhmmss (default: {DEFAULT_FROMTIME})",
    )
    args = parser.parse_args()
    fromtime = args.fromtime

    started = time.time()

    print("=" * 60)
    print("bootstrap: 過去データ一括取得")
    print(f"対象 dataspec: {', '.join(BOOTSTRAP_DATASPECS)}")
    print("option = 4 (ダイアログなしセットアップ)")
    print(f"fromtime = {fromtime}")
    print("=" * 60)
    print()

    with JVLinkClient() as cli:
        summaries = cli.fetch_all(
            fromtime=fromtime,
            option=4,
            dataspecs=BOOTSTRAP_DATASPECS,
            on_progress=progress,
        )

    print()
    print("=== fetch summaries ===")
    for s in summaries:
        print(f"  {s}")

    print()
    print("=== ingest into SQLite ===")
    print("（現状 RA / SE のみ DB 投入。他の dataspec は raw のみ保存）")
    ingest_summary = ingest_all()
    print(f"  {ingest_summary}")

    elapsed = time.time() - started
    h, rem = divmod(int(elapsed), 3600)
    m, s = divmod(rem, 60)
    print()
    print(f"=== bootstrap 完了: 所要 {h:02d}:{m:02d}:{s:02d} ===")


if __name__ == "__main__":
    main()
