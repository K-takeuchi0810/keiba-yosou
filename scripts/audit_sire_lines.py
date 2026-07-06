"""系統辞書 (LINE_BY_SIRE) の実 DB 突合診断 — 1 回きりのユーザ実機用。

目的 (2026-07-05 validation 監査の HOLD 解除条件 2):
辞書の事実正しさの検証が「コメントとテストの循環」に閉じないよう、
JV-Link 由来の独立データソース (breeding_horses の父系チェーン) と突合する。

  1. 辞書照合を**無視**し、breeding_num の父系遡上のみ (FOUNDERS 停止) で分類
  2. 辞書 (LINE_BY_SIRE) の分類と比較し、不一致を列挙
  3. あわせて unknown 分類率の内訳 (辞書 hit / 遡上 hit / unknown) を報告
     — 「その他だらけ」症状の定量把握 (改修前後比較は HEAD~1 checkout で再実行)

breeding_horses (HN レコード, dataspec=BLOD) が未取込の DB では遡上が効かず
突合になりません。その場合はまず BLOD を取り込んでから実行してください。

usage:
    python -m scripts.audit_sire_lines            # 既定 DB
    python -m scripts.audit_sire_lines --db data/keiba.db
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.sire_lines import FOUNDERS, classify_sire, lookup_line, _normalize

# _normalize は仮名を大書き化するため、生の FOUNDERS (小書きキー) を直接引くと
# 当たらない。独立遡上用に正規化済み FOUNDERS を作る (2026-07-06 code-quality P1)。
_FOUNDERS_N = {_normalize(k): v for k, v in FOUNDERS.items()}


def traversal_only_classify(conn, breeding_num: str | None, max_depth: int = 15) -> str:
    """辞書 (LINE_BY_SIRE) を使わず、父系遡上で FOUNDERS に当たるまで分類する。

    LINE_BY_SIRE と独立の判定 (循環検証の回避が目的) なので、途中世代の
    照合先は FOUNDERS のみ。始祖まで HN が繋がっていなければ unknown。
    """
    if not breeding_num:
        return "unknown"
    seen: set[str] = set()
    cur = breeding_num
    for _ in range(max_depth):
        if not cur or cur in seen:
            break
        seen.add(cur)
        row = conn.execute(
            "SELECT horse_name, sire_name, sire_breeding_num "
            "FROM breeding_horses WHERE breeding_num = ?", (cur,)
        ).fetchone()
        if row is None:
            break
        for candidate in (row["horse_name"], row["sire_name"]):
            k = _normalize(candidate)
            if k in _FOUNDERS_N:
                return _FOUNDERS_N[k]
        cur = row["sire_breeding_num"]
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="系統辞書の実 DB 突合診断")
    ap.add_argument("--db", default=None)
    ap.add_argument("--top", type=int, default=30, help="不一致/unknown の表示上限")
    args = ap.parse_args()

    with (open_db(args.db) if args.db else open_db()) as conn:
        n_hn = conn.execute("SELECT COUNT(*) FROM breeding_horses").fetchone()[0]
        if n_hn == 0:
            print("breeding_horses が空です (BLOD 未取込)。突合には HN レコードの取り込みが必要。")
            return 1

        # 父・母父・父母父・母母父の 4 世代を「種牡馬の出現」として集計 (weight=産駒頭数)。
        # gen3 (父母父/母母父) は海外祖先の英語名が多く、英語名辞書の効果測定の主対象
        # (2026-07-06 validation R-1 / data-pipeline P1: gen3 列を未カバーだった)。
        sires: Counter[tuple[str, str]] = Counter()
        for col_name, col_num in (("sire_name", "sire_breeding_num"),
                                  ("dam_sire_name", "dam_sire_breeding_num"),
                                  ("sire_dam_sire_name", "sire_dam_sire_breeding_num"),
                                  ("dam_dam_sire_name", "dam_dam_sire_breeding_num")):
            try:
                rows = conn.execute(
                    f"SELECT {col_name} AS nm, {col_num} AS bn, COUNT(*) AS c "
                    f"FROM horse_masters WHERE nm IS NOT NULL AND nm != '' "
                    f"GROUP BY nm, bn").fetchall()
            except Exception as e:  # noqa: BLE001 — 列欠如等は skip して続行
                print(f"skip {col_name}: {e}")
                continue
            for r in rows:
                sires[(_normalize(r["nm"]), (r["bn"] or "").strip())] += r["c"]

        breakdown = Counter()          # dict_hit / traversal_hit / unknown (weighted)
        mismatches = []                # 辞書と遡上の両方が非 unknown で食い違い
        unknown_top: Counter[str] = Counter()
        for (name, bn), weight in sires.items():
            dict_key = lookup_line(name)   # 正規化照合 (仮名大書き対応)
            trav_key = traversal_only_classify(conn, bn)
            if dict_key:
                breakdown["dict_hit"] += weight
                if trav_key != "unknown" and trav_key != dict_key:
                    mismatches.append((name, dict_key, trav_key, weight))
            elif classify_sire(name, conn=conn, sire_breeding_num=bn) != "unknown":
                breakdown["traversal_hit"] += weight
            else:
                breakdown["unknown"] += weight
                unknown_top[name] += weight

        total = sum(breakdown.values()) or 1
        print("=" * 70)
        print(f"SIRE LINE AUDIT  (種牡馬出現 {total} 件 = 産駒頭数×父/母父)")
        for k in ("dict_hit", "traversal_hit", "unknown"):
            print(f"  {k:<14} {breakdown[k]:>7} ({breakdown[k] / total * 100:.1f}%)")
        print("=" * 70)

        if mismatches:
            print(f"\n### 辞書 vs 独立遡上の不一致 {len(mismatches)} 件 — 要目視確認 (辞書誤り or HN 欠損)")
            for name, dk, tk, w in sorted(mismatches, key=lambda m: -m[3])[:args.top]:
                print(f"  {name}: dict={dk} traversal={tk} (産駒 {w})")
        else:
            print("\n辞書 vs 独立遡上の不一致なし (遡上可能な範囲で辞書は整合)")

        print(f"\n### unknown 上位 (辞書追加候補, 産駒数順)")
        for name, w in unknown_top.most_common(args.top):
            print(f"  {name} (産駒 {w})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
