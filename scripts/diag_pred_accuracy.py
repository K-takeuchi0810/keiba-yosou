"""フェーズ1 診断: dump_predictions の per-pick / per-race CSV から、
予想◎ (rank1 + mark, non-tentative) の単勝/複勝の的中率・回収率と、
top-1 の win_probability calibration (reliability + Brier) をスライス別に算出する。

学習・採用判断には使わない純粋な「答え合わせ」レポート生成器。

usage:
    python -m scripts.diag_pred_accuracy \
        --picks data/diag/dump_picks_2024_2026.csv \
        --races data/diag/dump_races_2024_2026.csv \
        --db /c/Users/kizun/dev/keiba-yosou/data/keiba.db \
        [--from 20240101 --to 20251231]   # 期間で絞る (TEST 限定など)

stdout に Markdown レポートを出力 (scorecard へリダイレクト想定)。
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.stats import bootstrap_return_rate, wilson_ci


# ---- スライス定義 -------------------------------------------------------

def pop_band(pop: int) -> str:
    if pop <= 0:
        return "unknown"
    if pop <= 3:
        return "1-3"
    if pop <= 6:
        return "4-6"
    if pop <= 9:
        return "7-9"
    return "10+"


POP_ORDER = ["1-3", "4-6", "7-9", "10+", "unknown"]


def surface_name(track_type_code: str | None) -> str:
    try:
        n = int((track_type_code or "").strip())
    except ValueError:
        return "?"
    if 10 <= n <= 22:
        return "芝"
    if 23 <= n <= 29:
        return "ダート"
    return "障害他"


def dist_bucket(d: int | None) -> str:
    d = d or 0
    if d <= 0:
        return "?"
    if d <= 1400:
        return "<=1400"
    if d <= 1800:
        return "1401-1800"
    if d <= 2200:
        return "1801-2200"
    return ">2200"


DIST_ORDER = ["<=1400", "1401-1800", "1801-2200", ">2200", "?"]


def grade_name(code: str | None) -> str:
    c = (code or "").strip()
    return {
        "A": "G1", "B": "G2", "C": "G3", "D": "重賞扱",
        "E": "L/OP特", "F": "重賞(F)",
    }.get(c, "条件/その他" if not c else f"grade={c}")


CONF_ORDER = ["確勝級", "有力", "上位", "押さえ", "混戦", "?"]


# ---- 集計コア -----------------------------------------------------------

class Agg:
    __slots__ = ("n", "tan_hits", "tan_payouts", "fuku_hits", "fuku_payouts")

    def __init__(self) -> None:
        self.n = 0
        self.tan_hits = 0
        self.tan_payouts: list[int] = []
        self.fuku_hits = 0
        self.fuku_payouts: list[int] = []

    def add(self, tan_payout: int, fuku_payout: int) -> None:
        self.n += 1
        self.tan_payouts.append(tan_payout if tan_payout > 0 else 0)
        self.fuku_payouts.append(fuku_payout if fuku_payout > 0 else 0)
        if tan_payout > 0:
            self.tan_hits += 1
        if fuku_payout > 0:
            self.fuku_hits += 1

    def row(self) -> dict:
        n = self.n
        stakes = [100] * n
        if n:
            t_lo, t_hi = wilson_ci(self.tan_hits, n)
            t_ret, t_rlo, t_rhi = bootstrap_return_rate(self.tan_payouts, stakes)
            f_ret, f_rlo, f_rhi = bootstrap_return_rate(self.fuku_payouts, stakes)
        else:
            t_lo = t_hi = t_ret = t_rlo = t_rhi = f_ret = f_rlo = f_rhi = 0.0
        return {
            "n": n,
            "tan_hit": self.tan_hits / n if n else 0.0,
            "tan_hit_ci": (t_lo, t_hi),
            "tan_ret": sum(self.tan_payouts) / (100 * n) if n else 0.0,
            "tan_ret_ci": (t_rlo, t_rhi),
            "fuku_hit": self.fuku_hits / n if n else 0.0,
            "fuku_ret": sum(self.fuku_payouts) / (100 * n) if n else 0.0,
            "fuku_ret_ci": (f_rlo, f_rhi),
        }


def fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def emit_table(title: str, keys: list[str], aggs: dict[str, Agg]) -> None:
    print(f"\n### {title}\n")
    print("| slice | n | 単勝的中 | 単勝的中CI95 | 単勝回収 | 単勝回収CI95 | 複勝的中 | 複勝回収 |")
    print("|---|--:|--:|--:|--:|--:|--:|--:|")
    for k in keys:
        a = aggs.get(k)
        if not a or a.n == 0:
            continue
        r = a.row()
        print(
            f"| {k} | {r['n']} | {fmt_pct(r['tan_hit'])} | "
            f"[{fmt_pct(r['tan_hit_ci'][0])}, {fmt_pct(r['tan_hit_ci'][1])}] | "
            f"{fmt_pct(r['tan_ret'])} | "
            f"[{fmt_pct(r['tan_ret_ci'][0])}, {fmt_pct(r['tan_ret_ci'][1])}] | "
            f"{fmt_pct(r['fuku_hit'])} | {fmt_pct(r['fuku_ret'])} |"
        )


# ---- main ---------------------------------------------------------------

def load_race_meta(db_path: str | None) -> dict:
    """(date, track_code, race_num) -> {distance, track_type_code} を keiba.db から。"""
    meta: dict = {}
    with open_db(db_path) if db_path else open_db() as conn:
        for r in conn.execute(
            "SELECT race_year, race_month_day, track_code, race_num, "
            "distance, track_type_code FROM races "
            "WHERE CAST(track_code AS INTEGER) BETWEEN 1 AND 10"
        ):
            d = dict(r)
            date = f"{d['race_year']}{d['race_month_day']}"
            key = (date, d["track_code"], d["race_num"])
            meta[key] = {
                "distance": d.get("distance"),
                "track_type_code": d.get("track_type_code"),
            }
    return meta


def in_range(date: str, lo: str | None, hi: str | None) -> bool:
    if lo and date < lo:
        return False
    if hi and date > hi:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", required=True)
    ap.add_argument("--races", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--from", dest="from_date", default=None)
    ap.add_argument("--to", dest="to_date", default=None)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    meta = load_race_meta(args.db)

    # ---- per-pick (◎) スライス ----
    overall = Agg()
    by_pop: dict[str, Agg] = defaultdict(Agg)
    by_surface: dict[str, Agg] = defaultdict(Agg)
    by_dist: dict[str, Agg] = defaultdict(Agg)
    by_grade: dict[str, Agg] = defaultdict(Agg)
    by_conf: dict[str, Agg] = defaultdict(Agg)
    by_year: dict[str, Agg] = defaultdict(Agg)
    # 人気帯 × 信頼度の交差 (過剰自信診断)
    by_pop_year: dict[str, Agg] = defaultdict(Agg)

    with open(args.picks, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            date = row["date"]
            if not in_range(date, args.from_date, args.to_date):
                continue
            tan = int(row["tan_payout"] or 0)
            fuku = int(row["fuku_payout"] or 0)
            pop = int(row["popularity"] or 0)
            year = date[:4]
            key = (date, row["track_code"], row["race_num"])
            m = meta.get(key, {})

            overall.add(tan, fuku)
            by_pop[pop_band(pop)].add(tan, fuku)
            by_surface[surface_name(m.get("track_type_code"))].add(tan, fuku)
            by_dist[dist_bucket(m.get("distance"))].add(tan, fuku)
            by_grade[grade_name(row.get("grade_code"))].add(tan, fuku)
            by_conf[(row.get("confidence") or "?").strip() or "?"].add(tan, fuku)
            by_year[year].add(tan, fuku)
            by_pop_year[f"{year}/{pop_band(pop)}"].add(tan, fuku)

    # ---- per-race calibration (top-1 全部、tentative 除外) ----
    # reliability: p_win bin -> (mean_p, actual_win_rate, n)
    bins = [(i / 20, (i + 1) / 20) for i in range(20)]  # 0.05 刻み
    bin_sum_p = [0.0] * 20
    bin_wins = [0] * 20
    bin_n = [0] * 20
    brier_terms: list[float] = []
    # 信頼度ティア別 Brier は per-pick (mark あり) で confidence を持つ → 別途
    n_race_rows = 0

    with open(args.races, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            date = row["date"]
            if not in_range(date, args.from_date, args.to_date):
                continue
            if int(row.get("tentative") or 0):
                continue
            p = float(row["p_win"] or 0)
            y = int(row["y_top_is_winner"] or 0)
            n_race_rows += 1
            brier_terms.append((p - y) ** 2)
            idx = min(int(p * 20), 19)
            bin_sum_p[idx] += p
            bin_wins[idx] += y
            bin_n[idx] += 1

    # ---- 出力 ----
    label = args.label or f"{args.from_date or 'all'}..{args.to_date or 'all'}"
    print(f"# フェーズ1 予想◎ 答え合わせ診断 — {label}\n")
    print(f"- picks CSV: `{args.picks}`")
    print(f"- races CSV: `{args.races}`")
    print(f"- 期間フィルタ: from={args.from_date} to={args.to_date}")
    print(f"- ◎ picks (mark付き非tentative top-1): **{overall.n}**")
    print(f"- calibration 対象 top-1 races (非tentative): **{n_race_rows}**")

    r = overall.row()
    print("\n## ◎ 全体成績\n")
    print(f"- 単勝的中率: **{fmt_pct(r['tan_hit'])}** "
          f"(CI95 [{fmt_pct(r['tan_hit_ci'][0])}, {fmt_pct(r['tan_hit_ci'][1])}])")
    print(f"- 単勝回収率: **{fmt_pct(r['tan_ret'])}** "
          f"(CI95 [{fmt_pct(r['tan_ret_ci'][0])}, {fmt_pct(r['tan_ret_ci'][1])}])")
    print(f"- 複勝的中率: **{fmt_pct(r['fuku_hit'])}**")
    print(f"- 複勝回収率: **{fmt_pct(r['fuku_ret'])}** "
          f"(CI95 [{fmt_pct(r['fuku_ret_ci'][0])}, {fmt_pct(r['fuku_ret_ci'][1])}])")

    emit_table("人気帯別 (★H1/H2 検証)", POP_ORDER, by_pop)
    emit_table("年/期間別 (TEST 2024-25 vs PROD 2026)", sorted(by_year), by_year)
    emit_table("年×人気帯 (レジーム×H1/H2)",
               [f"{y}/{p}" for y in sorted({k.split('/')[0] for k in by_pop_year})
                for p in POP_ORDER if f"{y}/{p}" in by_pop_year], by_pop_year)
    emit_table("芝/ダート別", ["芝", "ダート", "障害他", "?"], by_surface)
    emit_table("距離帯別", DIST_ORDER, by_dist)
    emit_table("グレード別", sorted(by_grade), by_grade)
    emit_table("信頼度ティア別", sorted(by_conf), by_conf)

    # calibration
    brier = sum(brier_terms) / len(brier_terms) if brier_terms else 0.0
    print("\n## キャリブレーション (top-1 win_probability)\n")
    print(f"- 全体 Brier (top-1): **{brier:.4f}** (n={n_race_rows})")
    print("\n### reliability curve (p_win bin → 実勝率)\n")
    print("| p_win bin | n | 平均予測p | 実勝率 | gap(予測-実) |")
    print("|---|--:|--:|--:|--:|")
    for i, (lo, hi) in enumerate(bins):
        if bin_n[i] == 0:
            continue
        mean_p = bin_sum_p[i] / bin_n[i]
        actual = bin_wins[i] / bin_n[i]
        gap = mean_p - actual
        flag = " ⚠過剰自信" if gap > 0.05 and bin_n[i] >= 20 else ""
        print(f"| [{lo:.2f},{hi:.2f}) | {bin_n[i]} | {mean_p:.3f} | "
              f"{actual:.3f} | {gap:+.3f}{flag} |")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
