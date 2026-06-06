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

two-proportion z-test: default は pooled SE under H0。
Gate-2 (c) 判定は Bonferroni / BH-FDR 補正後 survivor 数を採用。

実行: python -m scripts.q1_root_cause
出力: data/h3_3_q1_root_cause.log
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from scripts._stats_helper import (
    bonferroni_alpha,
    bonferroni_z_threshold,
    multiple_comparison_results,
    two_proportion_z_test,
)


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
        test = two_proportion_z_test(
            s25["hits"],
            s25["n"],
            s26["hits"],
            s26["n"],
            method=compute_delta_sigma.z_method,
        )
        rows.append({
            "bucket": b,
            "n_25": s25["n"], "hit_25": s25["hits"], "hr_25": test["p_a"],
            "n_26": s26["n"], "hit_26": s26["hits"], "hr_26": test["p_b"],
            "delta": test["delta"], "se": test["se"], "z": test["z"],
            "p_two_sided": test["p_two_sided"],
        })
    # buckets only in one year
    only_25 = stats_25.keys() - stats_26.keys()
    only_26 = stats_26.keys() - stats_25.keys()
    return {"common": sorted(rows, key=lambda x: x["z"]),
            "only_25": sorted(only_25), "only_26": sorted(only_26)}


compute_delta_sigma.z_method = "pooled"


def fmt_row(r: dict, axis_name: str) -> str:
    flag = ""
    if r.get("bonferroni_p", 1.0) <= fmt_row.alpha:
        flag = "  *** Bonferroni ***"
    elif r.get("bh_q", 1.0) <= fmt_row.alpha:
        flag = "  ** BH-FDR **"
    elif abs(r["z"]) >= 2.0:
        flag = "  ** naive >=2σ **"
    return (
        f"  {axis_name:>30}  | {r['bucket']:<30}  "
        f"| 25: {r['hit_25']:>3}/{r['n_25']:>3} ({r['hr_25']:6.3%})  "
        f"| 26: {r['hit_26']:>3}/{r['n_26']:>3} ({r['hr_26']:6.3%})  "
        f"| δ={r['delta']:+7.4f}  z={r['z']:+5.2f}  "
        f"p={r['p_two_sided']:.4f}  "
        f"p_bonf={r.get('bonferroni_p', 1.0):.4f}  "
        f"q={r.get('bh_q', 1.0):.4f}{flag}"
    )


fmt_row.alpha = 0.05


def feature_hint(axis_name: str, bucket: str) -> list[str]:
    """Return compact Tier 2/3 hints for exploratory rows."""
    if axis_name == "track_code":
        return [
            "T2.3 track_recent_top3_rate_30d (track drift / recent form)",
            "T2.2 track_surface_distance_top3_rate (track x surface x distance)",
            "T3.2 track_bias_inside_outside (track bias)",
        ]
    if axis_name == "starter_count" and bucket == "<=8 small":
        return [
            "T2.1b expected_pace_index (small-race pace dynamics)",
            "T2.1a pace_runners_count_pct (small-race pace composition)",
        ]
    if axis_name == "grade_code" and bucket == "0":
        return [
            "Tier 1 grade_code existing signal",
            "T2.2 track_grade interactional feature candidate",
        ]
    if axis_name.startswith("dm_rank") or axis_name.startswith("tm_rank"):
        return [
            "MING dynamics monitor (H4 raw DM/TM yearly distribution split)",
        ]
    if axis_name == "distance bucket":
        return [
            "data-quality audit for distance missing/invalid",
            "T2.2 distance interaction features if replicated",
        ]
    return ["monitor only; no direct B1-S1 feature gate"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/dump_picks_h2.csv")
    parser.add_argument("--db", default="data/keiba.db")
    parser.add_argument("--out", default="data/h3_3_q1_root_cause.log")
    parser.add_argument("--min-n", type=int, default=30,
                        help="Minimum picks per bucket to include (default: 30)")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument(
        "--z-method",
        choices=("pooled", "unpooled"),
        default="pooled",
        help="Two-proportion z-test SE definition (default: pooled under H0)",
    )
    args = parser.parse_args()
    compute_delta_sigma.z_method = args.z_method
    fmt_row.alpha = args.alpha

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
    overall_test = two_proportion_z_test(hit25, n25, hit26, n26, method=args.z_method)
    overall_delta = overall_test["delta"]
    overall_z = overall_test["z"]
    out_lines.append(
        f"Overall delta:     {overall_delta:+.4f} "
        f"(z={overall_z:+.2f}, p={overall_test['p_two_sided']:.4f}, method={args.z_method})"
    )
    out_lines.append("")

    # Attach race meta (distance + starter_count)
    matched = attach_race_meta(picks, Path(args.db))
    out_lines.append(f"Joined with races table for distance/starter_count: matched={matched}/{len(picks)}")
    out_lines.append("")
    out_lines.append(f"min_n per bucket (filter): {args.min_n}")
    out_lines.append(f"z-test method: {args.z_method}")
    out_lines.append(f"alpha: {args.alpha:.4f}")
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

    axis_results = []
    all_rows: list[dict] = []

    for axis_name, field, bucket_fn in axes:
        stats_25 = aggregate_by_axis(picks, "2025", bucket_fn, field, args.min_n)
        stats_26 = aggregate_by_axis(picks, "2026", bucket_fn, field, args.min_n)
        cmp = compute_delta_sigma(stats_25, stats_26)
        for r in cmp["common"]:
            r["axis"] = axis_name
            all_rows.append(r)
        axis_results.append((axis_name, cmp))

    corrections = multiple_comparison_results([r["p_two_sided"] for r in all_rows])
    for r, correction in zip(all_rows, corrections):
        r["bonferroni_p"] = correction.bonferroni_p
        r["bh_q"] = correction.bh_q

    family_size = len(all_rows)
    bonf_alpha = bonferroni_alpha(args.alpha, family_size)
    bonf_z_two_sided = bonferroni_z_threshold(args.alpha, family_size, two_sided=True)
    bonf_z_one_sided = bonferroni_z_threshold(args.alpha, family_size, two_sided=False)

    out_lines.append("=" * 100)
    out_lines.append("Multiple-comparison family definition")
    out_lines.append("=" * 100)
    out_lines.append("")
    out_lines.append(
        "family = all displayed H3-3 buckets with min_n >= threshold and both 2025Q1/2026Q1 present"
    )
    out_lines.append(f"family size N = {family_size}")
    out_lines.append(f"Bonferroni alpha/N = {bonf_alpha:.9f}")
    out_lines.append(f"Bonferroni two-sided |z| threshold = {bonf_z_two_sided:.3f}")
    out_lines.append(f"Bonferroni one-sided |z| threshold = {bonf_z_one_sided:.3f}")
    out_lines.append("BH-FDR threshold = q <= alpha")
    out_lines.append("")

    for axis_name, cmp in axis_results:
        out_lines.append("-" * 100)
        out_lines.append(f"Axis: {axis_name}")
        out_lines.append("-" * 100)
        if cmp["common"]:
            for r in cmp["common"]:
                out_lines.append(fmt_row(r, axis_name))
        else:
            out_lines.append("  (no common buckets with min_n)")
        if cmp["only_25"]:
            out_lines.append(f"  (buckets only in 2025Q1 with min_n: {cmp['only_25']})")
        if cmp["only_26"]:
            out_lines.append(f"  (buckets only in 2026Q1 with min_n: {cmp['only_26']})")
        out_lines.append("")

    naive_candidates = [r for r in all_rows if abs(r["z"]) >= 2.0]
    bonferroni_survivors = [r for r in all_rows if r["bonferroni_p"] <= args.alpha]
    bh_survivors = [r for r in all_rows if r["bh_q"] <= args.alpha]
    exploratory_rows = sorted(
        [r for r in all_rows if abs(r["z"]) >= 1.7],
        key=lambda r: abs(r["z"]),
        reverse=True,
    )

    # Summary
    out_lines.append("=" * 100)
    out_lines.append("Corrected causal candidate summary")
    out_lines.append("=" * 100)
    out_lines.append("")
    out_lines.append(f"  naive |z| >= 2.0 rows: {len(naive_candidates)}")
    out_lines.append(f"  Bonferroni survivors: {len(bonferroni_survivors)}")
    out_lines.append(f"  BH-FDR survivors: {len(bh_survivors)}")
    out_lines.append("")
    if not bonferroni_survivors and not bh_survivors:
        out_lines.append("  No corrected causal candidates found.")
        out_lines.append("  Gate-2 (c) corrected verdict: FAIL (corrected survivor 不在)")
    else:
        out_lines.append("  Corrected candidates:")
        out_lines.append("")
        for r in sorted(bonferroni_survivors or bh_survivors, key=lambda row: abs(row["z"]), reverse=True):
            sign = "MORE-MISS in 2026" if r["delta"] < 0 else "MORE-HIT in 2026"
            out_lines.append(
                f"  - axis={r['axis']:>25} | bucket={r['bucket']:<25} | "
                f"δ={r['delta']:+.4f} | z={r['z']:+.2f} | "
                f"p_bonf={r['bonferroni_p']:.4f} | q={r['bh_q']:.4f} | {sign}"
            )
        out_lines.append("")
        out_lines.append("  Gate-2 (c) corrected verdict: PASS")

    out_lines.append("")
    out_lines.append("=" * 100)
    out_lines.append("Exploratory signal summary (= Gate PASS ではなく優先順位の参考値)")
    out_lines.append("=" * 100)
    out_lines.append("")
    if not exploratory_rows:
        out_lines.append("  No exploratory rows at |z| >= 1.7.")
    else:
        for r in exploratory_rows:
            sign = "MORE-MISS in 2026" if r["delta"] < 0 else "MORE-HIT in 2026"
            out_lines.append(
                f"  - axis={r['axis']:>25} | bucket={r['bucket']:<25} | "
                f"δ={r['delta']:+.4f} | z={r['z']:+.2f} | "
                f"p={r['p_two_sided']:.4f} | p_bonf={r['bonferroni_p']:.4f} | "
                f"q={r['bh_q']:.4f} | {sign}"
            )
            for hint in feature_hint(r["axis"], r["bucket"]):
                out_lines.append(f"      * {hint}")
    out_lines.append("")
    out_lines.append("Invariant 2 handling: exploratory rows may guide diagnostic priorities,")
    out_lines.append("but Gate / 採否判定 uses corrected survivor count only.")

    out_lines.append("")
    out_lines.append("=" * 100)
    out_lines.append("Raw correction summary (JSON)")
    out_lines.append("=" * 100)
    out_lines.append("")
    out_lines.append(json.dumps({
        "family_size": family_size,
        "alpha": args.alpha,
        "z_method": args.z_method,
        "bonferroni_alpha": bonf_alpha,
        "bonferroni_z_two_sided": bonf_z_two_sided,
        "bonferroni_z_one_sided": bonf_z_one_sided,
        "naive_abs_z_ge_2": len(naive_candidates),
        "bonferroni_survivors": len(bonferroni_survivors),
        "bh_fdr_survivors": len(bh_survivors),
        "top_rows": [
            {
                "axis": r["axis"],
                "bucket": r["bucket"],
                "z": r["z"],
                "p_two_sided": r["p_two_sided"],
                "bonferroni_p": r["bonferroni_p"],
                "bh_q": r["bh_q"],
            }
            for r in sorted(all_rows, key=lambda row: abs(row["z"]), reverse=True)[:12]
        ],
    }, ensure_ascii=False, indent=2))

    out_text = "\n".join(out_lines) + "\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(out_text, encoding="utf-8")

    # stdout 短縮版
    print(f"Wrote {args.out}")
    print(f"Family size: {family_size}")
    print(f"Naive candidates: {len(naive_candidates)} (|z| >= 2.0)")
    print(f"Bonferroni survivors: {len(bonferroni_survivors)}")
    print(f"BH-FDR survivors: {len(bh_survivors)}")
    print(f"Overall 2026Q1 delta: {overall_delta:+.4f} (z={overall_z:+.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
