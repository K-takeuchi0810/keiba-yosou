"""JVGets で 1 ファイルだけ取得してバイト整合性を確認するスモークテスト。

確認項目:
- JVGets が rc=0 以外の正常応答を返すか
- 取得した raw ファイル中の SE レコード長が CRLF 分割で 553 byte (本体) で揃うか
  (= BSTR ラウンドトリップで膨らんでいないか)
- parse_se で confirmed_order / win_popularity / win_odds が現実的な値か
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter

from config import DATA_DIR
from jvlink_client.client import JVLinkClient
from jvlink_client.parser import SE_LENGTH, parse_se


SMOKE_RAW_DIR = DATA_DIR / "raw_smoke_jvgets"


def progress(stage: str, info: dict) -> None:
    print(f"  [{stage}] {info}", flush=True)


def main() -> int:
    SMOKE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    # 直近 1 ヶ月の RACE データだけ取得 (ファイル数を抑える)
    fromtime = "20260301000000"

    print(f"=== JVGets smoke test (RACE since {fromtime}) ===")

    # JVLinkClient.fetch は client.py の RAW_DIR に書く実装なので
    # ここでは一時的に RAW_DIR を上書き
    import jvlink_client.client as cli_mod
    orig_dir = cli_mod.RAW_DIR
    cli_mod.RAW_DIR = SMOKE_RAW_DIR
    try:
        with JVLinkClient() as cli:
            summary = cli.fetch(
                "RACE", fromtime=fromtime, option=2, on_progress=progress
            )
    finally:
        cli_mod.RAW_DIR = orig_dir

    print()
    print("=== fetch summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # SE ファイルを 1 つ拾ってレコード長を見る
    se_files = sorted(SMOKE_RAW_DIR.glob("RACE/SE*.jvd"))
    if not se_files:
        print("\nSE files not produced — check fetch summary above")
        return 1

    se_path = se_files[0]
    data = se_path.read_bytes()
    parts = [r for r in data.split(b"\r\n") if r]

    print()
    print(f"=== inspect {se_path.name} ===")
    print(f"file size: {len(data):,}")
    print(f"crlf-split records: {len(parts)}")
    length_dist = Counter(len(r) for r in parts)
    print(f"length distribution (top 5): {length_dist.most_common(5)}")
    print(f"expected body length (spec): {SE_LENGTH - 2}")

    # 最初の data_div=7 (確定) レコードをパースして数値の妥当性確認
    sample = next(
        (rec for rec in parts if len(rec) >= 3 and rec[2:3] == b"7"), None
    )
    if sample is None:
        print("no data_div=7 record found in this sample (may need finished races)")
    else:
        se = parse_se(sample)
        print()
        print("=== sample parse_se (data_div=7) ===")
        print(
            f"race_id={se.race_id} horse={se.horse_num} "
            f"name={se.horse_name!r}"
        )
        print(
            f"pop={se.win_popularity} order={se.confirmed_order} "
            f"odds={se.win_odds} burden={se.burden_weight}"
        )
        # 妥当性チェック
        ok_pop = 0 < se.win_popularity <= 18
        ok_order = 0 < se.confirmed_order <= 18
        ok_odds = 0 < se.win_odds <= 9999
        print(
            f"sanity: pop_ok={ok_pop} order_ok={ok_order} odds_ok={ok_odds}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
