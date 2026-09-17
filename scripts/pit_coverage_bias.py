"""T−10 取得できたレースに選択バイアスが無いかを見る (憲法 Phase 0.5-2 前提)。

## なぜ要るか

strategy_dev 窓 1,176 レース中 **239 レース (20.3%) が T−10 オッズなし**。
937 レースだけで市場を評価すること自体は正しいが、**239 がランダムに欠けて
いるとは限らない**。開催初期だけ・特定競馬場だけ・午前のレースだけ、といった
偏りがあると、937 は JRA 全体を代表した母集団ではなくなる。

ここでは精緻な検定はしない。目的は
「937 レースに選択バイアスが発生していないか」を確認すること。
偏りがあれば隠さず、今後の評価範囲として明記する。

usage:
    .venv64/Scripts/python.exe -m scripts.pit_coverage_bias [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.pit_t10 import t10_market  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402

TRACK_NAMES = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
               "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
SURFACE = {"1": "芝", "2": "ダート", "3": "障害"}


def _surface(race: dict) -> str:
    code = str(race.get("track_type_code") or "").strip()
    if not code:
        return "不明"
    head = code[0]
    if code[:2] in ("51", "52", "53", "54", "55", "56", "57", "58", "59"):
        return "障害"
    return SURFACE.get(head, f"その他({code})")


def _grade(race: dict) -> str:
    g = str(race.get("grade_code") or "").strip()
    return {"A": "G1", "B": "G2", "C": "G3"}.get(g, "重賞以外")


def _race_num_band(race: dict) -> str:
    try:
        n = int(str(race.get("race_num") or "0"))
    except ValueError:
        return "不明"
    if n <= 3:
        return "1-3R"
    if n <= 6:
        return "4-6R"
    if n <= 9:
        return "7-9R"
    return "10-12R"


def _field_band(n: int) -> str:
    if n <= 8:
        return "8頭以下"
    if n <= 12:
        return "9-12頭"
    if n <= 15:
        return "13-15頭"
    return "16頭以上"


def collect(from_date: str, to_date: str, db_path: str | None = None) -> dict:
    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = conn.execute(
        """SELECT * FROM races
            WHERE (race_year || race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""",
        (from_date, to_date)).fetchall()

    dims: dict[str, dict[str, Counter]] = defaultdict(
        lambda: {"取得": Counter(), "欠損": Counter()})
    n_got = n_missing = 0
    for r in races:
        race = dict(r)
        starters = conn.execute(
            """SELECT COUNT(*) FROM horse_races
                WHERE race_year=? AND race_month_day=? AND track_code=?
                  AND kaiji=? AND nichiji=? AND race_num=?
                  AND horse_num NOT IN ('', '00')""",
            (race["race_year"], race["race_month_day"], race["track_code"],
             race["kaiji"], race["nichiji"], race["race_num"])).fetchone()[0]

        got = t10_market(conn, race) is not None
        bucket = "取得" if got else "欠損"
        if got:
            n_got += 1
        else:
            n_missing += 1

        dims["競馬場"][bucket][TRACK_NAMES.get(race["track_code"], race["track_code"])] += 1
        dims["月"][bucket][race["race_year"] + race["race_month_day"][:2]] += 1
        dims["レース番号"][bucket][_race_num_band(race)] += 1
        dims["芝ダ障"][bucket][_surface(race)] += 1
        dims["頭数"][bucket][_field_band(starters)] += 1
        dims["クラス"][bucket][_grade(race)] += 1
    conn.close()

    out: dict = {"meta": {**snapshot(), "from_date": from_date, "to_date": to_date},
                 "n_got": n_got, "n_missing": n_missing,
                 "overall_rate": round(n_got / (n_got + n_missing), 4)
                 if (n_got + n_missing) else None,
                 "dimensions": {}}
    for dim, counts in dims.items():
        rows = []
        for key in sorted(set(counts["取得"]) | set(counts["欠損"])):
            g, m = counts["取得"][key], counts["欠損"][key]
            total = g + m
            rows.append({"key": key, "got": g, "missing": m, "total": total,
                         "rate": round(g / total, 4) if total else None})
        out["dimensions"][dim] = rows
    return out


def main() -> int:
    dev = DATA_SPLIT["strategy_dev"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=dev["from"])
    ap.add_argument("--to", dest="to_date", default=dev["to"])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    out = collect(args.from_date, args.to_date)
    base = out["overall_rate"] or 0
    print(f"=== T−10 取得率の偏り {args.from_date}〜{args.to_date} ===")
    print(f"全体: 取得 {out['n_got']:,} / 欠損 {out['n_missing']:,} "
          f"= {base * 100:.1f}%")
    for dim, rows in out["dimensions"].items():
        print(f"\n--- {dim} ---")
        print(f"{'':>10} {'取得':>6} {'欠損':>6} {'取得率':>8}  全体比")
        for r in rows:
            if r["total"] < 10:
                continue
            gap = (r["rate"] - base) * 100
            flag = "  ←偏り" if abs(gap) >= 15 else ""
            print(f"{str(r['key']):>10} {r['got']:6,d} {r['missing']:6,d} "
                  f"{r['rate'] * 100:7.1f}% {gap:+7.1f}pt{flag}")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
