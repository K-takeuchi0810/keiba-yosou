"""3代血統 (父母父/母母父) + 産地のバイト位置を実 DB で検証する。

UM idx8/idx12 と HN 205-229 は「検証済みアンカーからの導出 = 暫定確定」なので、
実データで並び順を確認して確定に昇格させるための spot-check (docs/OPERATION.md §9-2)。

usage:
    .venv32/Scripts/python.exe -m scripts.verify_pedigree
    .venv32/Scripts/python.exe -m scripts.verify_pedigree --db data/keiba.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db


def main() -> int:
    ap = argparse.ArgumentParser(description="3代血統・産地の実 DB 検証")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    with (open_db(args.db) if args.db else open_db()) as conn:
        print("=" * 64)
        print("1. ディープインパクト産駒の3代血統 (父母父=Alzao が期待値)")
        print("=" * 64)
        rows = conn.execute(
            "SELECT horse_name, sire_dam_sire_name, dam_dam_sire_name "
            "FROM horse_masters WHERE sire_name='ディープインパクト' "
            "AND horse_name!='' LIMIT 6").fetchall()
        for r in rows:
            sds = r["sire_dam_sire_name"]
            dds = r["dam_dam_sire_name"]
            sds_disp = "(NULL=未取込)" if sds is None else (sds or "(空)")
            dds_disp = "(NULL=未取込)" if dds is None else (dds or "(空)")
            print(f"  {r['horse_name']:<16} 父母父={sds_disp:<14} 母母父={dds_disp}")
        if not rows:
            print("  (ディープ産駒が見つからない — sire_name の表記を確認)")
        # 3 代血統の充填状況を先に集計して原因を切り分ける
        row = conn.execute(
            "SELECT COUNT(*) t, "
            "SUM(CASE WHEN sire_dam_sire_name IS NULL THEN 1 ELSE 0 END) nulls, "
            "SUM(CASE WHEN sire_dam_sire_name='' THEN 1 ELSE 0 END) empties, "
            "SUM(CASE WHEN sire_dam_sire_name IS NOT NULL AND sire_dam_sire_name!='' "
            "         THEN 1 ELSE 0 END) filled FROM horse_masters").fetchone()
        print(f"  → 父母父: 全{row['t']} / NULL(未取込){row['nulls']} / 空{row['empties']} / 値あり{row['filled']}")
        if row["filled"] == 0:
            print("  ★ 値ありが 0 = 新パーサで UM 未再取込。git pull 後に")
            print("     ingest_all(force=True, dataspecs=['DIFN']) を実行してください。")

        print("\n" + "=" * 64)
        print("2. 産地 上位15 (安平町/新冠町/米/愛 等の地名・国名か。数字混入は異常)")
        print("=" * 64)
        for r in conn.execute(
            "SELECT birthplace, COUNT(*) n FROM breeding_horses "
            "WHERE birthplace IS NOT NULL AND birthplace!='' "
            "GROUP BY birthplace ORDER BY n DESC LIMIT 15"):
            print(f"  {r['birthplace']:<16} {r['n']}")

        print("\n" + "=" * 64)
        print("3. 数字フィールドの健全性 (mochikomi=小集合 / import_year=4桁年)")
        print("=" * 64)
        moch = [r[0] for r in conn.execute(
            "SELECT DISTINCT mochikomi_kubun FROM breeding_horses "
            "WHERE mochikomi_kubun IS NOT NULL LIMIT 12")]
        print(f"  mochikomi_kubun distinct: {moch}")
        iy = [r[0] for r in conn.execute(
            "SELECT DISTINCT import_year FROM breeding_horses "
            "WHERE import_year NOT IN ('0000','') AND import_year IS NOT NULL LIMIT 12")]
        print(f"  import_year sample (非0000): {iy}")

        print("\n" + "=" * 64)
        print("4. 充填率 (force 再取込後は 9 割超が期待値)")
        print("=" * 64)
        for col, tbl in (("sire_dam_sire_name", "horse_masters"),
                         ("dam_dam_sire_name", "horse_masters"),
                         ("birthplace", "breeding_horses")):
            r = conn.execute(
                f"SELECT COUNT(*) t, SUM(CASE WHEN {col} IS NOT NULL AND {col}!='' "
                f"THEN 1 ELSE 0 END) f FROM {tbl}").fetchone()
            t, f = r["t"] or 0, r["f"] or 0
            pct = 100 * f / t if t else 0.0
            print(f"  {col:<20} {f}/{t} ({pct:.1f}%)")

        print("\n判定: 1 が Alzao 系・2 に数字混入なし・3 が健全・4 が高充填 → 確定。"
              "\n      異常があれば parser のオフセット (UM idx8/12, HN 205-229) を再調査。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
