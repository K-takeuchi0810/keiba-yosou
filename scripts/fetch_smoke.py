"""フェッチャ動作確認用スクリプト（軽負荷の差分取得 1 件）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jvlink_client import JVLinkClient


def main() -> None:
    fromtime = "20260501000000"
    with JVLinkClient() as cli:
        summary = cli.fetch(
            "RACE",
            fromtime,
            option=4,
            on_progress=lambda s, i: print(s, i),
        )
        print("DONE:", summary)


if __name__ == "__main__":
    main()
