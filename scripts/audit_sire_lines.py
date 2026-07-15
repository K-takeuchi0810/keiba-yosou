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
import csv
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db_readonly
from predictor.sire_lines import (
    FOUNDERS, classify_sire, lookup_line, _normalize, _breeding_name_to_num,
)

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
    ap.add_argument("--dump-unknown", default=None,
                    help="「その他」になる全種牡馬を産駒数順 CSV で書き出すパス "
                         "(例: --dump-unknown data/unknown_sires.csv)。全件洗い出し用。")
    ap.add_argument("--since-year", type=int, default=None,
                    help="指定年以降に出走した馬に登場する種牡馬だけを対象にする "
                         "(例: --since-year 2023)。現出馬表で実際に目立つ『その他』に絞る。"
                         "全期間集計では歴史的な母母父が大量に混じるため。")
    args = ap.parse_args()
    # --since-year は 4 桁西暦のみ許可。race_year は "YYYY" 固定長 TEXT で字句比較するため、
    # 非 4 桁入力は silent かつ非直感的な挙動になる (2026-07-16 data-pipeline 監査 D1 実測):
    #   --since-year 23  → 0 件 ("23" > "2024" 等で全 row が falsy)
    #   --since-year 202 → 2024+ のみ (2018-2023 は "202" < "2018" 等で落ちる)
    #   --since-year 2   → 20xx 系すべて (意図より広い)
    # いずれも例外なく silent なため、parse 時点で fail-fast する (範囲は現実的な西暦馬齢)。
    if args.since_year is not None and not (1900 <= args.since_year <= 2100):
        ap.error(f"--since-year は 4 桁西暦 (1900-2100) で指定してください: {args.since_year}")

    # 読み取り専用で開く (診断は観察系。init_db の書込み migration を走らせて
    #  GUI/ingest とロック競合させない — 2026-07-06 data-pipeline 指摘)。
    with (open_db_readonly(args.db) if args.db else open_db_readonly()) as conn:
        n_hn = conn.execute("SELECT COUNT(*) FROM breeding_horses").fetchone()[0]
        if n_hn == 0:
            print("breeding_horses が空です (BLOD 未取込)。突合には HN レコードの取り込みが必要。")
            return 1

        # --since-year: 指定年以降に出走した馬 (horse_races.race_year) に絞る。
        # horse_masters を「その馬が近年走ったか」で filter し、現出馬表で実際に出る
        # 種牡馬だけを対象にする。全期間集計は数十年前の母母父を大量に含み過大評価になる。
        recent_where, recent_params = "", ()
        if args.since_year is not None:
            try:
                n_recent = conn.execute(
                    "SELECT COUNT(DISTINCT blood_register_num) FROM horse_races "
                    "WHERE race_year >= ?", (str(args.since_year),)).fetchone()[0]
            except sqlite3.OperationalError as e:
                print(f"--since-year 使用不可 (horse_races 参照失敗: {e})。全期間で続行します。")
                n_recent = None
            if n_recent is not None:
                # 集計対象 horse_masters を「近年出走馬」に限定する副問い合わせ。
                recent_where = (" AND blood_register_num IN "
                                "(SELECT DISTINCT blood_register_num FROM horse_races "
                                "WHERE race_year >= ?)")
                recent_params = (str(args.since_year),)
                print(f"[--since-year {args.since_year}] {args.since_year} 年以降に出走した "
                      f"{n_recent} 頭に登場する種牡馬に絞って集計します。\n")

        # 父・母父・父母父・母母父の 4 世代を「種牡馬の出現」として集計 (weight=産駒頭数)。
        # gen3 (父母父/母母父) は海外祖先の英語名が多く、英語名辞書の効果測定の主対象
        # (2026-07-06 validation R-1 / data-pipeline P1: gen3 列を未カバーだった)。
        sires: Counter[tuple[str, str]] = Counter()
        # 正規化キー → 生スペルの出現数。unknown 洗い出しで「元の読める名前」を復元する
        # (_normalize は小書き畳み込み+英字小文字化+記号除去で読みにくいため)。列ごとに
        # カナ (母父) と英語 (父母父/母母父) が別スペルで入るので、両方を候補として保持し
        # 代表 = 最頻スペルを表示する。
        raw_names: dict[str, Counter] = {}
        # 各種牡馬がどの世代 (父/母父/父母父/母母父) に出たかも記録 (洗い出しの手がかり)。
        gen_of: dict[str, set[str]] = {}
        _GEN = {"sire_name": "父", "dam_sire_name": "母父",
                "sire_dam_sire_name": "父母父", "dam_dam_sire_name": "母母父"}
        for col_name, col_num in (("sire_name", "sire_breeding_num"),
                                  ("dam_sire_name", "dam_sire_breeding_num"),
                                  ("sire_dam_sire_name", "sire_dam_sire_breeding_num"),
                                  ("dam_dam_sire_name", "dam_dam_sire_breeding_num")):
            try:
                rows = conn.execute(
                    f"SELECT {col_name} AS nm, {col_num} AS bn, COUNT(*) AS c "
                    f"FROM horse_masters WHERE nm IS NOT NULL AND nm != ''"
                    f"{recent_where} "
                    f"GROUP BY nm, bn", recent_params).fetchall()
            except sqlite3.OperationalError as e:  # 旧スキーマの列欠如等は skip して続行
                print(f"skip {col_name}: {e}")
                continue
            for r in rows:
                norm = _normalize(r["nm"])
                sires[(norm, (r["bn"] or "").strip())] += r["c"]
                raw_names.setdefault(norm, Counter())[r["nm"]] += r["c"]
                gen_of.setdefault(norm, set()).add(_GEN[col_name])

        def _raw_of(norm: str) -> str:
            """正規化キーから最頻の生スペル (読める名前) を返す。"""
            c = raw_names.get(norm)
            return c.most_common(1)[0][0] if c else norm

        def _gens_of(norm: str) -> str:
            """出現世代 (父/母父/父母父/母母父) を安定順で "/" 連結。"""
            return "/".join(sorted(gen_of.get(norm, set())))

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
        print(f"  breeding_horses 行数: {n_hn}")
        for k in ("dict_hit", "traversal_hit", "unknown"):
            print(f"  {k:<14} {breakdown[k]:>7} ({breakdown[k] / total * 100:.1f}%)")
        print("=" * 70)

        # 遡上入口の join 健全性診断: horse_masters.sire_breeding_num (UM 由来、遡上の
        # 起点) が breeding_horses.breeding_num (HN の PK) にどれだけ存在するか。
        # traversal_hit=0 の原因が「行数不足/未取込 (=join は成立し得るが対象が居ない)」か
        # 「採番系の不一致 (=そもそも key が噛み合わない)」かを、再取込前に切り分ける。
        try:
            distinct_bn = conn.execute(
                "SELECT COUNT(DISTINCT sire_breeding_num) FROM horse_masters "
                "WHERE sire_breeding_num IS NOT NULL AND sire_breeding_num != ''"
            ).fetchone()[0]
            matched_bn = conn.execute(
                "SELECT COUNT(DISTINCT hm.sire_breeding_num) FROM horse_masters hm "
                "JOIN breeding_horses bh ON hm.sire_breeding_num = bh.breeding_num "
                "WHERE hm.sire_breeding_num IS NOT NULL AND hm.sire_breeding_num != ''"
            ).fetchone()[0]
            # 代替 join: UM.sire_breeding_num が「繁殖登録番号」でなく「血統登録番号」を
            # 格納している可能性を検証する (breeding_horses.blood_register_num と突合)。
            matched_blood = 0
            try:
                matched_blood = conn.execute(
                    "SELECT COUNT(DISTINCT hm.sire_breeding_num) FROM horse_masters hm "
                    "JOIN breeding_horses bh ON hm.sire_breeding_num = bh.blood_register_num "
                    "WHERE hm.sire_breeding_num IS NOT NULL AND hm.sire_breeding_num != ''"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                pass
            um_samples = [r[0] for r in conn.execute(
                "SELECT DISTINCT sire_breeding_num FROM horse_masters "
                "WHERE sire_breeding_num != '' LIMIT 5").fetchall()]
            hn_bn_samples = [r[0] for r in conn.execute(
                "SELECT breeding_num FROM breeding_horses LIMIT 5").fetchall()]
            hn_blood_samples = [r[0] for r in conn.execute(
                "SELECT blood_register_num FROM breeding_horses "
                "WHERE blood_register_num IS NOT NULL AND blood_register_num != '' LIMIT 5").fetchall()]
            print("遡上入口 join 診断 (UM.sire_breeding_num を各 HN 列と突合):")
            print(f"  horse_masters の distinct 父繁殖番号: {distinct_bn}")
            print(f"  ⇔ breeding_horses.breeding_num(PK) 一致: {matched_bn} "
                  f"({(matched_bn / distinct_bn * 100 if distinct_bn else 0):.1f}%)")
            print(f"  ⇔ breeding_horses.blood_register_num 一致: {matched_blood} "
                  f"({(matched_blood / distinct_bn * 100 if distinct_bn else 0):.1f}%)")
            print(f"  UM.sire_breeding_num サンプル: {um_samples}")
            print(f"  HN.breeding_num サンプル:       {hn_bn_samples}")
            print(f"  HN.blood_register_num サンプル: {hn_blood_samples}")
            if distinct_bn and matched_blood > matched_bn and matched_blood > 0:
                print("  → blood_register_num 側で一致が多い。UM 3代血統は『血統登録番号』を格納しており")
                print("    遡上は breeding_num でなく blood_register_num に join すべき (要コード修正)。")
            elif distinct_bn and matched_bn == 0 and matched_blood == 0:
                print("  ⚠ どちらも 0 件。(a) breeding_horses が対象祖先を含まない(=要 BLOD 全取込) か、")
                print("    (b) HN.breeding_num/blood_register_num の parse 位置ずれ。probe_hn_offsets の")
                print("    HEAD ダンプ (breeding_num 12-21) で PK の桁/形式を UM サンプルと比較して切り分ける。")
            elif distinct_bn and matched_bn / distinct_bn < 0.3:
                print("  → 一部一致。key 体系は正しく、未一致分は breeding_horses の不足。")
                print("    `scripts.bootstrap --dataspecs BLOD` で全繁殖馬を取込めば traversal_hit が上がる。")
            # 決定打: 同名の種牡馬が両テーブルに居る場合の breeding_num を並べ、
            # 「同じ馬なのに UM と HN で番号が違う」= parse/format 変換ずれを直接見る。
            try:
                name_matched = conn.execute(
                    "SELECT COUNT(DISTINCT hm.sire_name) FROM horse_masters hm "
                    "JOIN breeding_horses bh ON hm.sire_name = bh.horse_name "
                    "WHERE hm.sire_name != ''"
                ).fetchone()[0]
                distinct_name = conn.execute(
                    "SELECT COUNT(DISTINCT sire_name) FROM horse_masters WHERE sire_name != ''"
                ).fetchone()[0]
                pairs = conn.execute(
                    "SELECT hm.sire_name, hm.sire_breeding_num, bh.breeding_num "
                    "FROM horse_masters hm JOIN breeding_horses bh ON hm.sire_name = bh.horse_name "
                    "WHERE hm.sire_name != '' AND hm.sire_breeding_num != '0000000000' "
                    "GROUP BY hm.sire_name LIMIT 8"
                ).fetchall()
                print("同名突合 (UM.sire_name = breeding_horses.horse_name):")
                print(f"  名前一致する distinct 父: {name_matched} / {distinct_name} "
                      f"({(name_matched / distinct_name * 100 if distinct_name else 0):.1f}%)")
                print("  同じ馬の breeding_num 比較 (UM 側 vs HN 側):")
                for nm, um_bn, hn_bn in pairs:
                    flag = "一致" if um_bn == hn_bn else "★不一致"
                    print(f"    {nm}: UM={um_bn} / HN={hn_bn}  {flag}")
                print("  → 名前一致率が高いのに breeding_num が『★不一致』なら、遡上は breeding_num でなく")
                print("    名前で join すべき (または番号の変換規則を特定)。名前一致も低ければ HN 名の表記揺れ。")
            except sqlite3.OperationalError as e:
                print(f"  (同名突合 skip: {e})")
            # 正規化名での入口一致率 (classify_sire の名前ベース遡上が効くかの実測)。
            # exact SQL 一致が 0% でも _normalize (仮名 fold+空白/記号畳み込み) で拾える。
            try:
                name_idx = _breeding_name_to_num(conn)
                um_names = [r[0] for r in conn.execute(
                    "SELECT DISTINCT sire_name FROM horse_masters WHERE sire_name != ''").fetchall()]
                norm_hit = sum(1 for nm in um_names if _normalize(nm) in name_idx)
                print(f"  正規化名 入口一致 (UM.sire_name → breeding_horses.horse_name): "
                      f"{norm_hit} / {len(um_names)} "
                      f"({(norm_hit / len(um_names) * 100 if um_names else 0):.1f}%)")
                print("  → この率が高ければ classify_sire の名前ベース遡上で traversal_hit が上がる。")
                # なぜ一致しないかを目視するための正規化名サンプル (両テーブル)。
                um_name_s = [f"{nm!r}->{_normalize(nm)!r}" for nm in um_names[:4]]
                hn_name_s = [f"{r[0]!r}->{_normalize(r[0])!r}" for r in conn.execute(
                    "SELECT horse_name FROM breeding_horses WHERE horse_name != '' LIMIT 4").fetchall()]
                print(f"  UM.sire_name 正規化サンプル: {um_name_s}")
                print(f"  HN.horse_name 正規化サンプル: {hn_name_s}")
                # 著名種牡馬が breeding_horses に居るか (exact/正規化)。居なければ HN 名の
                # parse ずれ or 別表記。近い名前も探す。
                for probe in ("ディープインパクト", "サンデーサイレンス", "キングカメハメハ"):
                    exact = conn.execute("SELECT COUNT(*) FROM breeding_horses WHERE horse_name=?",
                                         (probe,)).fetchone()[0]
                    innorm = _normalize(probe) in name_idx
                    like = [r[0] for r in conn.execute(
                        "SELECT horse_name FROM breeding_horses WHERE horse_name LIKE ? LIMIT 3",
                        (probe[:4] + "%",)).fetchall()]
                    print(f"  probe {probe}: exact={exact} 正規化index={innorm} 前方一致例={like}")
            except Exception as e:  # noqa: BLE001
                print(f"  (正規化名一致 skip: {e})")
            print("=" * 70)
        except sqlite3.OperationalError as e:
            print(f"(join 診断 skip: {e})")
        # 「その他が大量に残る」ときの原因切り分け: 辞書追加では届かない long-tail は
        # breeding_horses 遡上で拾うのが前提。traversal_hit がほぼ 0 で unknown が高い場合、
        # BLOD (繁殖馬) の血統木が浅く founder まで遡れていない可能性が高い (辞書追加より
        # まず BLOD 取り込みの確認が必要)。
        if breakdown["unknown"] / total > 0.05 and breakdown["traversal_hit"] / total < 0.01:
            print(f"⚠ unknown が高い一方 traversal_hit がほぼ 0 です (breeding_horses {n_hn} 行)。原因の候補:")
            print("  (i) breeding_horses の行が旧オフセットで取り込まれている or 行数不足。")
            print("      parse_hn は 2026-07-06 に HN の -2 ずれを修正済 (sire_breeding_num=228)。")
            print("      `python -m scripts.bootstrap --dataspecs BLOD` で BLOD を再取込し、")
            print("      新オフセットで breeding_horses を埋め直す (OPERATION.md §9-4)。")
            print("  (ii) 再取込しても 0% のままなら、遡上の入口 = UM(競走馬マスタ)側の")
            print("       sire_breeding_num と HN の breeding_num(PK) の採番系が突合しない疑い。")
            print("       UM gen3 の breeding_num フィールド位置 / 採番系を確認する。")
            print("  (iii) 遡上は届くが FOUNDERS 辞書に停止点が不足 → founder 追加で traversal_hit が上がる。")
            print("  いずれも個別種牡馬の辞書追加 (whack-a-mole) では long-tail に届きません。")
            print("=" * 70)

        if mismatches:
            print(f"\n### 辞書 vs 独立遡上の不一致 {len(mismatches)} 件 — 要目視確認 (辞書誤り or HN 欠損)")
            for name, dk, tk, w in sorted(mismatches, key=lambda m: -m[3])[:args.top]:
                print(f"  {name}: dict={dk} traversal={tk} (産駒 {w})")
        else:
            print("\n辞書 vs 独立遡上の不一致なし (遡上可能な範囲で辞書は整合)")

        distinct_unknown = len(unknown_top)
        print(f"\n### unknown (=「その他」) 種牡馬: distinct {distinct_unknown} 件 / 産駒延べ "
              f"{breakdown['unknown']} 件。上位 {min(args.top, distinct_unknown)} 件 (産駒数順):")
        for norm, w in unknown_top.most_common(args.top):
            print(f"  {_raw_of(norm)} (産駒 {w}, 出現世代 {_gens_of(norm)})")

        # 全件洗い出し: --dump-unknown で「その他」になる全種牡馬を産駒数順 CSV に書き出す。
        # 読める生スペル + 産駒数 + 出現世代 + 正規化キーを出力し、そのまま貼れば辞書追加
        # 対象を一望できる (top 打ち切りなし)。
        if args.dump_unknown:
            out = Path(args.dump_unknown)
            out.parent.mkdir(parents=True, exist_ok=True)  # 親ディレクトリを用意 (診断中断防止)
            # csv.writer で quoting/エスケープを一任 (手組み連結の破損リスク回避)。
            # Excel で直接開いてもカナが化けないよう BOM 付き UTF-8。
            with out.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["raw_name", "occurrences", "generations", "normalized_key"])
                for norm, w in unknown_top.most_common():
                    writer.writerow([_raw_of(norm), w, _gens_of(norm), norm])
            print(f"\n→ 「その他」全 {distinct_unknown} 件を {out} に産駒数順 CSV で書き出しました。")
            print("  この CSV を貼るか添付すれば、確度の高いものからまとめて系統分類します。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
