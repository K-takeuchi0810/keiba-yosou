"""H3-3: 2026Q1 LGBM 崩壊の root cause 探索 (5 軸分解).

P19 B1-S0 Step 3: dump_picks_h2.csv の per-pick データを 2025Q1 (baseline) と
2026Q1 (= LGBM 崩壊 cohort) で 5 軸分解し、hit_rate delta が >= 2σ の軸 =
causal candidate として特定する。

軸:
  1. grade_code (race grade)
  2. popularity (人気)
  3. track_code (競馬場)
  4. odds bucket (オッズ帯)
  5. distance bucket (距離帯、races join)
  (bonus) dm_rank / tm_rank の MING rank 帯

2σ test: pooled SE of delta = sqrt(p25(1-p25)/n25 + p26(1-p26)/n26)
         delta / SE >= 2.0 で causal candidate

実行: python -m scripts.q1_root_cause
出力: data/h3_3_q1_root_cause.log
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from math import sqrt
from pathlib import Path
from typing import Iterable


def load_picks(csv_path: Path) -> list[dict]:
    picks = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row["date"]
            if not (date.startswith("2025") or date.startswith("2026")):
                continue
            mm = int(date[4:6])
            if mm < 1 or mm > 3:
                continue
            picks.append({
                "year": date[:4],
                "month": mm,
                "date": date,
                "track_code": row["track_code"],
                "race_num": row["race_num"],
                "grade_code": row["grade_code"],
                "p_win": float(row["p_win"]),
                "odds": float(row["odds"]),
                "popularity": int(row["popularity"]) if row["popularity"] else 0,
                "tm_score": int(row["tm_score"]) if row["tm_score"] else 0,
                "tm_rank": int(row["tm_rank"]) if row["tm_rank"] else 0,
                "dm_rank": int(row["dm_rank"]) if row["dm_rank"] else 0,
                "y_win": int(row["y_win"]),
            })
    return picks


def attach_race_meta(picks: list[dict], db_path: Path) -> int:
    """Join with races table for distance + starter_count. Return # picks attached."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    matched = 0
    for p in picks:
        race_year = p["year"]
        race_month_day = p["date"][4:8]
        row = cur.execute(
            "SELECT distance, starter_count FROM races "
            "WHERE race_year=? AND race_month_day=? AND track_code=? AND race_num=?",
            (race_year, race_month_day, p["track_code"], p["race_num"]),
        ).fetchone()
        if row:
            p["distance"] = row[0]
            p["starter_count"] = row[1]
            matched += 1
        else:
            p["distance"] = None
            p["starter_count"] = None
    conn.close()
    return matched


def bucket_odds(odds: float) -> str:
    if odds <= 0:
        return "missing"
    if odds < 3:
        return "<3 (heavy-favorite)"
    if odds < 7:
        return "3-7 (favorite)"
    if odds < 20:
        return "7-20 (mid)"
    if odds < 50:
        return "20-50 (long-shot)"
    return ">=50 (deep)"


def bucket_distance(dist) -> str:
    if dist is None or dist <= 0:
        return "missing/invalid"
    if dist < 1400:
        return "sprint (<1400m)"
    if dist < 1800:
        return "mile (1400-1799m)"
    if dist < 2200:
        return "middle (1800-2199m)"
    if dist < 2600:
        return "long (2200-2599m)"
    return "marathon (>=2600m)"


def bucket_popularity(p: int) -> str:
    if p == 1:
        return "1 (top-favorite)"
    if p <= 3:
        return "2-3"
    if p <= 6:
        return "4-6"
    return "7+"


def bucket_dm_rank(r: int) -> str:
    if r == 0:
        return "0/missing"
    if r == 1:
        return "1 (top-MING)"
    if r <= 3:
        return "2-3"
    if r <= 9:
        return "4-9"
    return ">=10"


def bucket_grade_code(g: str) -> str:
    if not g:
        return "(blank, regular)"
    # Filter out clear garbage characters (control codes or non-ASCII)
    if not g.isprintable() or len(g) > 3:
        return f"garbage:{ord(g[0])}"
    return g


def bucket_starter_count(n) -> str:
    if n is None or n <= 0:
        return "missing/invalid"
    if n <= 8:
        return "<=8 small"
    if n <= 12:
        return "9-12"
    if n <= 15:
        return "13-15"
    if n <= 18:
        return "16-18"
    return ">=19 (likely-garbage)"


def aggregate_by_axis(
    picks: list[dict],
    year: str,
    bucket_fn,
    field: str,
    min_n: int = 30,
) -> dict:
    """Return {bucket: (n, hits, hit_rate)} for given year."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for p in picks:
        if p["year"] != year:
            continue
        b = bucket_fn(p[field])
        buckets[b].append(p["y_win"])
    result = {}
    for b, ys in buckets.items():
        if len(ys) < min_n:
            continue
        result[b] = {"n": len(ys), "hits": sum(ys), "hit_rate": sum(ys) / len(ys)}
    return result


def compute_delta_sigma(stats_25: dict, stats_26: dict) -> dict:
    """For each bucket present in BOTH years, compute delta and sigma (in SE units)."""
    common_buckets = set(stats_25.keys()) & set(stats_26.keys())
    rows = []
    for b in common_buckets:
        s25 = stats_25[b]
        s26 = stats_26[b]
        p25, n25 = s25["hit_rate"], s25["n"]
        p26, n26 = s26["hit_rate"], s26["n"]
        # SE of (p26 - p25) under H0: p_pooled
        se = sqrt(p25 * (1 - p25) / n25 + p26 * (1 - p26) / n26)
        delta = p26 - p25
        z = delta / se if se > 0 else 0
        rows.append({
            "bucket": b,
            "n_25": n25, "hit_25": s25["hits"], "hr_25": p25,
            "n_26": n26, "hit_26": s26["hits"], "hr_26": p26,
            "delta": delta, "se": se, "z": z,
        })
    # buckets only in one year
    only_25 = stats_25.keys() - stats_26.keys()
    only_26 = stats_26.keys() - stats_25.keys()
    return {"common": sorted(rows, key=lambda x: x["z"]),
            "only_25": sorted(only_25), "only_26": sorted(only_26)}


def fmt_row(r: dict, axis_name: str) -> str:
    flag = ""
    if abs(r["z"]) >= 2.0:
        flag = "  ** >=2σ **"
    if abs(r["z"]) >= 3.0:
        flag = "  *** >=3σ ***"
    return (
        f"  {axis_name:>30}  | {r['bucket']:<30}  "
        f"| 25: {r['hit_25']:>3}/{r['n_25']:>3} ({r['hr_25']:6.3%})  "
        f"| 26: {r['hit_26']:>3}/{r['n_26']:>3} ({r['hr_26']:6.3%})  "
        f"| δ={r['delta']:+7.4f}  z={r['z']:+5.2f}{flag}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/dump_picks_h2.csv")
    parser.add_argument("--db", default="data/keiba.db")
    parser.add_argument("--out", default="data/h3_3_q1_root_cause.log")
    parser.add_argument("--min-n", type=int, default=30,
                        help="Minimum picks per bucket to include (default: 30)")
    args = parser.parse_args()

    out_lines = []
    out_lines.append("H3-3: 2026Q1 LGBM 崩壊 root cause 探索 (5+ 軸分解)")
    out_lines.append("=" * 100)
    out_lines.append("")

    csv_path = Path(args.csv)
    picks = load_picks(csv_path)
    n25 = sum(1 for p in picks if p["year"] == "2025")
    n26 = sum(1 for p in picks if p["year"] == "2026")
    hit25 = sum(p["y_win"] for p in picks if p["year"] == "2025")
    hit26 = sum(p["y_win"] for p in picks if p["year"] == "2026")
    out_lines.append(f"Loaded picks (Jan-Mar): 2025={n25}, 2026={n26}")
    out_lines.append(f"Baseline hit_rate: 2025Q1={hit25/n25:.4f} ({hit25}/{n25})")
    out_lines.append(f"Cohort hit_rate:   2026Q1={hit26/n26:.4f} ({hit26}/{n26})")
    overall_delta = hit26 / n26 - hit25 / n25
    overall_se = sqrt(
        (hit25 / n25) * (1 - hit25 / n25) / n25
        + (hit26 / n26) * (1 - hit26 / n26) / n26
    )
    overall_z = overall_delta / overall_se
    out_lines.append(f"Overall delta:     {overall_delta:+.4f} (z={overall_z:+.2f})")
    out_lines.append("")

    # Attach race meta (distance + starter_count)
    matched = attach_race_meta(picks, Path(args.db))
    out_lines.append(f"Joined with races table for distance/starter_count: matched={matched}/{len(picks)}")
    out_lines.append("")
    out_lines.append(f"min_n per bucket (filter): {args.min_n}")
    out_lines.append("")

    # 5 軸 + bonus
    axes = [
        ("grade_code", "grade_code", bucket_grade_code),
        ("popularity", "popularity", bucket_popularity),
        ("track_code", "track_code", lambda x: f"track_{x}" if x else "missing"),
        ("odds bucket", "odds", bucket_odds),
        ("distance bucket", "distance", bucket_distance),
        ("starter_count", "starter_count", bucket_starter_count),
        ("dm_rank (MING DM)", "dm_rank", bucket_dm_rank),
        ("tm_rank (MING TM)", "tm_rank", bucket_dm_rank),  # 同じ bucket_fn 流用
    ]

    causal_candidates: list[tuple[str, dict]] = []

    for axis_name, field, bucket_fn in axes:
        stats_25 = aggregate_by_axis(picks, "2025", bucket_fn, field, args.min_n)
        stats_26 = aggregate_by_axis(picks, "2026", bucket_fn, field, args.min_n)
        cmp = compute_delta_sigma(stats_25, stats_26)

        out_lines.append("-" * 100)
        out_lines.append(f"Axis: {axis_name}")
        out_lines.append("-" * 100)
        if cmp["common"]:
            for r in cmp["common"]:
                out_lines.append(fmt_row(r, axis_name))
                if abs(r["z"]) >= 2.0:
                    causal_candidates.append((axis_name, r))
        else:
            out_lines.append("  (no common buckets with min_n)")
        if cmp["only_25"]:
            out_lines.append(f"  (buckets only in 2025Q1 with min_n: {cmp['only_25']})")
        if cmp["only_26"]:
            out_lines.append(f"  (buckets only in 2026Q1 with min_n: {cmp['only_26']})")
        out_lines.append("")

    # Summary
    out_lines.append("=" * 100)
    out_lines.append("Causal candidate summary (= |z| >= 2.0 buckets)")
    out_lines.append("=" * 100)
    out_lines.append("")
    if not causal_candidates:
        out_lines.append("  No causal candidates found at z >= 2.0 threshold.")
        out_lines.append("  Gate-2 (c) 判定: FAIL (>= 1 個 candidate 不在)")
    else:
        out_lines.append(f"  Total: {len(causal_candidates)} candidate(s)")
        out_lines.append("")
        for axis_name, r in causal_candidates:
            sign = "MORE-MISS in 2026" if r["delta"] < 0 else "MORE-HIT in 2026"
            out_lines.append(
                f"  - axis={axis_name:>25} | bucket={r['bucket']:<25} | "
                f"δ={r['delta']:+.4f} | z={r['z']:+.2f} | {sign}"
            )
        out_lines.append("")
        out_lines.append(f"  Gate-2 (c) 判定: PASS (>= 1 個 candidate 特定)")

    out_lines.append("")
    out_lines.append("=" * 100)
    out_lines.append("Tier 2/3 features 対応 check (= 個別 candidate が Tier 2/3 features で説明可能か)")
    out_lines.append("=" * 100)
    out_lines.append("")
    out_lines.append(
        "(本 step 末 に手動で対応表を書く、causal candidate と PHASE6_TIER23_DESIGN.md の"
    )
    out_lines.append(
        " features 候補のクロスチェック)"
    )

    out_text = "\n".join(out_lines) + "\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(out_text, encoding="utf-8")

    # stdout 短縮版
    print(f"Wrote {args.out}")
    print(f"Causal candidates: {len(causal_candidates)} (z >= 2.0)")
    print(f"Overall 2026Q1 delta: {overall_delta:+.4f} (z={overall_z:+.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
