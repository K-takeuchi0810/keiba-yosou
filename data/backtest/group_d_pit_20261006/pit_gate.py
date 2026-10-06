"""Phase 0.5-5 Group D (クラス昇降 × 能力) の PIT の確認 (2026-10-06)。結果・勝ち馬・払戻には触れない。

事前登録 §8-3: 「Group A の能力値と、当該クラスの要求水準 (当該レースを含めない過去実績) を使う。要求水準の算出が決定時刻までに確定した値だけで
作れることをコードで確認するまで、主検定を走らせない」。外部の指示者の指示 (2026-10-06): 必要な入力が決定時刻に本当に取得できるか /
時刻と来歴を再構成できるか / 対象レース自身や未来の情報の混入がないか / PIT の欠損率 / fail-closed にできるか。

確認すること:
1. クラス (競走条件コード) は発走前に確定しているか: 2026-01〜08 のレース (2025 と封印窓を避ける) で、発走前の RA (データ区分 1 出走馬名表 /
   2 出馬表) と確定の RA (7) の条件コード・距離・コースが一致するか (`group_a_class_table.extract` は食い違いで止まる)
2. 2021-2025 の凍結したクラスの表の各レースの、どのデータ区分の RA から作ったか (確定 7 だけか)
3. 要求水準の材料の件数: 学習期 2022-2024 の対象レースごとに、同じ canonical class × 芝ダの、対象日の 365 日前から前日までのレース数
   (勝ち時計などの結果は数えない。件数だけ)
4. 前走の有無 (前走のクラス・前走の能力値の材料): 学習期の対象の行のうち、365 日以内に JRA・確定・平地の過去走がある割合

usage (worktree の root で):
    .venv64/Scripts/python.exe data/backtest/group_d_pit_20261006/pit_gate.py <out.json> --db <keiba.db> --raw-dir <data/raw/RACE>
"""
import argparse
import csv
import json
import sqlite3
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

from scripts import group_a_class_table as ct  # noqa: E402

CLASS_TABLE = ROOT / "data" / "backtest" / "group_a_class_20261005" / "class_table.csv"
YEARS = (2022, 2023, 2024)


def ordinal(ymd: str) -> int:
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])).toordinal()


def surface(tt) -> str | None:
    tt = int(tt)
    if tt >= 51:
        return None
    if 10 <= tt <= 22:
        return "T"
    if 23 <= tt <= 29:
        return "D"
    raise SystemExit(f"平地の未知の track_type_code {tt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--db", required=True)
    ap.add_argument("--raw-dir", required=True)
    a = ap.parse_args()
    out = {"purpose": "Group D の PIT の確認 (結果・勝ち馬・払戻を読まない)"}

    # 1. 発走前と確定の RA の条件コード
    c = Counter()
    ra = ct.extract(ct.raw_files(Path(a.raw_dir)), "20260101", "20260831", counts=c)
    dd = Counter(tuple(sorted(v["data_divs"])) for v in ra.values())
    both = sum(1 for v in ra.values() if ({"1", "2"} & v["data_divs"]) and "7" in v["data_divs"])
    out["check1_condition_code_pre_vs_final_2026"] = {
        "races": len(ra), "data_div_sets": {"|".join(k): n for k, n in dd.most_common()},
        "races_with_pre_race_and_final_records": both, "mismatches": 0,
        "note": "group_a_class_table.extract は同じレースの条件コード・距離・コースが食い違うと止まる。止まらずに完了 = 食い違い 0",
        "record_counts": dict(c)}

    # 2. 凍結したクラスの表のデータ区分
    table = {}
    with CLASS_TABLE.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            table[r["race_id"]] = r
    cols = list(next(iter(table.values())).keys())
    out["check2_class_table"] = {"rows": len(table), "columns": cols}

    # 3・4. 学習期の件数 (DB は mode=ro、結果の列は読まない)
    conn = sqlite3.connect(f"file:{Path(a.db).as_posix()}?mode=ro", uri=True)
    races = conn.execute(
        """SELECT race_year||race_month_day, track_code, kaiji, nichiji, race_num, track_type_code FROM races
            WHERE race_year BETWEEN '2021' AND '2024' AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10 AND data_div = '7'""").fetchall()
    runs = conn.execute(
        """SELECT h.race_year||h.race_month_day, h.track_code, h.kaiji, h.nichiji, h.race_num, h.blood_register_num, h.abnormal_code
             FROM horse_races h JOIN races r ON r.race_year = h.race_year AND r.race_month_day = h.race_month_day
              AND r.track_code = h.track_code AND r.kaiji = h.kaiji AND r.nichiji = h.nichiji AND r.race_num = h.race_num
            WHERE h.race_year BETWEEN '2021' AND '2024' AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
              AND r.data_div = '7' AND h.horse_num NOT IN ('', '00')""").fetchall()
    conn.close()
    race_info = {}
    for ymd, tc, ka, ni, rn, tt in races:
        s = surface(tt)
        if s is None:
            continue
        rid = f"{ymd}_{tc}_{ka}_{ni}_{rn}"
        row = table.get(rid)
        race_info[rid] = {"ord": ordinal(ymd), "year": int(ymd[:4]), "surface": s,
                          "cls": row["canonical_class"] if row else None}
    missing_class = sum(1 for v in race_info.values() if v["cls"] is None)
    by_key = defaultdict(list)
    for v in race_info.values():
        if v["cls"]:
            by_key[(v["cls"], v["surface"])].append(v["ord"])
    for k in by_key:
        by_key[k].sort()
    counts = defaultdict(list)
    for rid, v in race_info.items():
        if v["year"] not in YEARS or not v["cls"]:
            continue
        days = by_key[(v["cls"], v["surface"])]
        n = bisect_left(days, v["ord"]) - bisect_left(days, v["ord"] - 365)        # [T−365, T−1]、同じ日は含めない
        counts[f"{v['cls']}|{v['surface']}"].append(n)
    out["check3_requirement_sample_sizes_train"] = {
        k: {"target_races": len(x), "min": int(min(x)), "p5": float(np.percentile(x, 5)), "median": float(np.median(x))}
        for k, x in sorted(counts.items())}
    out["check3_races_without_class"] = missing_class
    # 4. 365 日以内の過去走の有無
    hist = defaultdict(list)
    for ymd, tc, ka, ni, rn, bn, abn in runs:
        rid = f"{ymd}_{tc}_{ka}_{ni}_{rn}"
        if rid in race_info and bn and str(abn or "").strip() not in ("1", "2", "3"):
            hist[bn].append(race_info[rid]["ord"])
    for v in hist.values():
        v.sort()
    has, total = Counter(), Counter()
    for ymd, tc, ka, ni, rn, bn, abn in runs:
        rid = f"{ymd}_{tc}_{ka}_{ni}_{rn}"
        info = race_info.get(rid)
        if not info or info["year"] not in YEARS or str(abn or "").strip() in ("1", "2", "3"):
            continue
        total[info["year"]] += 1
        d = hist.get(bn, [])
        if bisect_left(d, info["ord"]) - bisect_left(d, info["ord"] - 365) > 0:
            has[info["year"]] += 1
    out["check4_share_with_past_run_365"] = {str(y): has[y] / total[y] for y in sorted(total)}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
