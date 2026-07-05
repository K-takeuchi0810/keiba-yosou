"""SE レコードのコーナー通過順位バイト位置の検証プローブ (Phase 4)。

**目的**: `parser.parse_se` に best-known 値で入れた corner_order_1..4 の
バイト位置 (394/396/398/400) が、実際の SE .jvd で正しいかを検証する。
jvdata-record スキルの鉄則「新パーサは実データで一周させる」を満たすための
必須ゲート。**これが緑になるまで本番 backfill / 先行力指標を信用しないこと。**

使い方 (ユーザの Windows 実機、32bit venv):

    .venv32/Scripts/python.exe -m scripts.probe_corner_offsets data/raw/RACE/<SEを含む>.jvd

    # golden fixture 突合 (推奨): JRA 公式成績等で既知のコーナー順位を指定して
    # 「範囲としては順位らしいが実は別フィールド」の false-green を排除する。
    # 形式: --expect <race_id>:<馬番2桁>:<corner4期待値> (複数指定可)
    .venv32/Scripts/python.exe -m scripts.probe_corner_offsets <file>.jvd \
        --expect 20250518_05_01_01_11:07:3 --expect 20250518_05_01_01_11:01:1

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


def _check_expectations(records, expects: list[str]) -> int:
    """golden fixture 突合。--expect race_id:馬番:corner4 を実 parse 値と照合する。

    範囲 heuristic は「1..頭数に収まる別の 2 桁フィールド」を誤読しても緑になり得る。
    既知の実測値 (JRA 公式成績のコーナー通過順位) と突合すれば offset の同一性を
    決定的に検証できる。1 件でも不一致なら offset ズレ確定で exit 1。
    """
    by_key = {}
    for r in records:
        by_key[(r.race_id, r.horse_num)] = r
    failures = 0
    for spec in expects:
        try:
            race_id, horse_num, want_s = spec.rsplit(":", 2)
            want = int(want_s)
        except ValueError:
            print(f"⚠ --expect の形式が不正: {spec} (race_id:馬番:corner4)")
            failures += 1
            continue
        rec = by_key.get((race_id, horse_num))
        if rec is None:
            print(f"⚠ 該当レコードなし: {race_id} 馬番{horse_num}")
            failures += 1
            continue
        got = rec.corner_order_4
        mark = "✓" if got == want else "❌"
        print(f"{mark} {race_id} 馬番{horse_num}: corner4 期待={want} 実測={got}")
        if got != want:
            failures += 1
    return failures


def _verdict(records) -> int:
    # confirmed_order が入っているレース (= 過去レース) を 1 つ選ぶ
    by_race: dict[str, list] = {}
    for r in records:
        by_race.setdefault(r.race_id, []).append(r)

    checked = 0
    problems = 0
    for race_id, horses in by_race.items():
        orders = [h.confirmed_order for h in horses]
        if not any(orders):  # 未確定レース (出馬表のみ) はスキップ
            continue
        field = len([o for o in orders if o and o > 0])
        checked += 1
        corners = {i: [getattr(h, f"corner_order_{i}") for h in horses] for i in (1, 2, 3, 4)}
        print(f"\nrace {race_id}  出走 {field} 頭")
        for i in (1, 2, 3, 4):
            print(f"  corner{i} :", corners[i])
        print("  finish  :", orders)
        # サニティ判定。1-2 角は小回り短距離で存在しない (全 0 が正常) ので、
        # 全 0 警告は 4 角のみ。範囲/重複チェックは非ゼロ値に対し全 4 角で行う。
        bad = []
        if not any(v for v in corners[4]):
            bad.append("corner_order_4 が全て 0 (offset ズレ or 未収録の可能性)")
        for i in (1, 2, 3, 4):
            nonzero = [v for v in corners[i] if v and v > 0]
            if not nonzero:
                continue
            over = [v for v in nonzero if v > field + 2]
            if over:
                bad.append(f"corner{i}: 頭数({field})を超える順位 {over} (offset ズレの可能性大)")
            dup = [v for v, c in Counter(nonzero).items() if c >= 3]
            if dup:
                bad.append(f"corner{i}: 同順位が3頭以上重複 {dup} (順位でない値の可能性)")
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
    ap.add_argument("--expect", action="append", default=[],
                    help="golden fixture: race_id:馬番2桁:corner4期待値 (複数可)。"
                         "JRA 公式成績の既知値と突合し false-green を排除する")
    args = ap.parse_args()
    records = [r for r in parse_se_file(args.jvd) if r.record_type == "SE"]
    print(f"parsed {len(records)} SE records from {args.jvd}")
    if not records:
        print("SE レコードが見つかりません。ファイル種別を確認してください。")
        return 2
    rc = _verdict(records)
    if args.expect:
        print("\n=== golden fixture 突合 ===")
        failures = _check_expectations(records, args.expect)
        if failures:
            print(f"❌ golden 突合 {failures} 件不一致。offset ズレ確定 — parser.py を修正せよ。")
            return 1
        print("✅ golden 突合すべて一致。")
    else:
        print("(参考) --expect で公式成績の既知値を与えると決定的検証になります。")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
