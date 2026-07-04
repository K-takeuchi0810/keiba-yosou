"""SE レコードのコーナー通過順位バイト位置の検証プローブ (Phase 4)。

**目的**: `parser.parse_se` に best-known 値で入れた corner_order_1..4 の
バイト位置 (394/396/398/400) が、実際の SE .jvd で正しいかを検証する。
jvdata-record スキルの鉄則「新パーサは実データで一周させる」を満たすための
必須ゲート。**これが緑になるまで本番 backfill / 先行力指標を信用しないこと。**

使い方 (ユーザの Windows 実機、32bit venv):

    .venv32/Scripts/python.exe -m scripts.probe_corner_offsets data/raw/RACE/<SEを含む>.jvd

検証ロジック:
  1. SE レコードを parse し、confirmed_order が確定しているレースを 1 つ選ぶ。
  2. そのレースの全馬の corner_order_4 と confirmed_order を並べる。
  3. 自動サニティ (_verdict が判定):
     - corner_order_4 は 1..出走頭数(+2) の範囲に収まるはず (順位なので)。
     - 同一レース内で corner_order_4 の値がほぼ一意 (同順位が 3 頭以上なら順位でない値の疑い)。
     - 全部 0 なら offset ズレ or 未収録。
  4. 逸脱があれば exit 1 で「offset がズレている可能性大」と警告。
  (補助的な目視確認: 逃げ/先行馬の corner_order_4 が小さく出ているかは出力を見て確認する。
   これは自動判定には含めない。)

出力の順位列が「1,2,3,...」と自然な順位分布になっていれば offset は正しい。
全部 0 や、頭数を超える値ばかりなら parser.py の 394/396/398/400 を仕様書
(docs/JV-Data4901.pdf p.12「馬毎レース情報」) と突き合わせて修正する。
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jvlink_client.parser import parse_se_file


def _verdict(records) -> int:
    # confirmed_order が入っているレース (= 過去レース) を 1 つ選ぶ
    by_race: dict[str, list] = {}
    for r in records:
        by_race.setdefault(r.race_id, []).append(r)

    checked = 0
    problems = 0
    for race_id, horses in by_race.items():
        c4 = [h.corner_order_4 for h in horses]
        orders = [h.confirmed_order for h in horses]
        if not any(orders):  # 未確定レース (出馬表のみ) はスキップ
            continue
        field = len([o for o in orders if o and o > 0])
        checked += 1
        nonzero = [v for v in c4 if v and v > 0]
        print(f"\nrace {race_id}  出走 {field} 頭")
        print("  corner4 :", c4)
        print("  finish  :", orders)
        # サニティ判定
        bad = []
        if not nonzero:
            bad.append("corner_order_4 が全て 0 (offset ズレ or 未収録の可能性)")
        else:
            over = [v for v in nonzero if v > field + 2]
            if over:
                bad.append(f"頭数({field})を超える順位 {over} (offset ズレの可能性大)")
            dup = [v for v, c in Counter(nonzero).items() if c >= 3]
            if dup:
                bad.append(f"同順位が3頭以上重複 {dup} (順位でない値を読んでいる可能性)")
        if bad:
            problems += 1
            for b in bad:
                print("  ⚠", b)
        else:
            print("  ✓ 範囲・分布ともに順位として妥当")
        if checked >= 5:
            break

    print("\n" + "=" * 60)
    if checked == 0:
        print("確定レースが見つからず検証不能。過去レースを含む SE ファイルを指定してください。")
        return 2
    if problems:
        print(f"❌ {checked} レース中 {problems} レースで逸脱。parser.py の corner offset を")
        print("   docs/JV-Data4901.pdf p.12 と突き合わせて修正し、再度このプローブを通すこと。")
        return 1
    print(f"✅ {checked} レース全てで corner_order_4 が順位として妥当。offset は正しいと判断。")
    print("   本番 backfill (再 ingest) と先行力指標の利用を許可してよい。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SE コーナー順位 offset 検証プローブ")
    ap.add_argument("jvd", help="SE レコードを含む .jvd ファイル (data/raw/RACE/...)")
    args = ap.parse_args()
    records = [r for r in parse_se_file(args.jvd) if r.record_type == "SE"]
    print(f"parsed {len(records)} SE records from {args.jvd}")
    if not records:
        print("SE レコードが見つかりません。ファイル種別を確認してください。")
        return 2
    return _verdict(records)


if __name__ == "__main__":
    raise SystemExit(main())
