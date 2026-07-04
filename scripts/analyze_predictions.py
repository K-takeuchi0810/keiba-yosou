"""Analyze prediction accuracy against confirmed race results in the local DB."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.rules import predict_race
from scripts.backtest import distance_bucket_label, get_payout, horses_for_race, list_races
from web.codes import track_name


def pct(a: int | float, b: int | float) -> float:
    return round(a / b * 100, 1) if b else 0.0


def surface_name(code: str | None) -> str:
    try:
        n = int((code or "").strip())
    except ValueError:
        return "その他"
    if 10 <= n <= 22:
        return "芝"
    if 23 <= n <= 29:
        return "ダート"
    return "障害/その他"


# 距離バケットは backtest.distance_bucket_label に一元化 (2026-07-04)。
# 境界値 (1400/1800/2200) が本ファイル・backtest・predictor の 3 箇所に平行記述され
# 乖離リスクがあった (code-quality 監査指摘)。ラベルは "<=1400" 等から
# sprint/mile/middle/long に変わる (bias_scan / backtest by_bucket と同一語彙)。
def bucket(distance: int | None) -> str:
    return distance_bucket_label(distance)


def popularity_bucket(popularity: int | None) -> str:
    p = popularity or 0
    if 1 <= p <= 3:
        return "1-3人気"
    if 4 <= p <= 6:
        return "4-6人気"
    if p >= 7:
        return "7人気以下"
    return "人気不明"


def race_group(race: dict) -> str:
    grade = (race.get("grade_code") or "").strip()
    symbol = (race.get("race_symbol_code") or "").strip()
    if grade in ("A", "B", "C", "D", "F", "G", "H", "I", "L") or symbol[:1] in ("N", "M"):
        return "OP/重賞"
    if race.get("race_name"):
        return "特別/条件"
    if symbol in ("000", "002", "003", "004", "020", "023", "024"):
        return "新馬/未勝利寄り"
    return "一般条件"


def ev_bucket(ev: float) -> str:
    if ev >= 1.2:
        return "EV>=1.20"
    if ev >= 1.0:
        return "EV1.00-1.19"
    if ev > 0:
        return "EV<1.00"
    return "EV不明"


def add(stats: dict, key: str, win: bool, top3: bool, ret: int) -> None:
    s = stats[key]
    s["n"] += 1
    s["win"] += int(win)
    s["top3"] += int(top3)
    s["ret"] += ret


def print_stats(title: str, stats: dict) -> None:
    print(title)
    for key, s in sorted(stats.items()):
        print(
            f"  {key}: n={s['n']} win={s['win']}({pct(s['win'], s['n'])}%) "
            f"top3={s['top3']}({pct(s['top3'], s['n'])}%) "
            f"ret={pct(s['ret'], s['n'] * 100)}%"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD")
    ap.add_argument("--from", dest="from_date", help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", help="YYYYMMDD")
    ap.add_argument("--db", default=None)
    ap.add_argument("--misses", type=int, default=10)
    args = ap.parse_args()

    from_date = args.date or args.from_date
    to_date = args.date or args.to_date or from_date
    if not from_date or not to_date:
        raise SystemExit("--date or --from/--to is required")

    rows = []
    by_conf = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "ret": 0})
    by_track = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "ret": 0})
    by_surface = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "ret": 0})
    by_dist = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "ret": 0})
    by_popularity = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "ret": 0})
    by_group = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "ret": 0})
    by_ev = defaultdict(lambda: {"n": 0, "win": 0, "top3": 0, "ret": 0})
    winner_rank = Counter()
    misses = []

    with open_db(args.db) if args.db else open_db() as conn:
        feature_cache: dict = {}
        races = list_races(conn, from_date, to_date, jra_only=True)
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            actual_win = next((h for h in horses if h.get("confirmed_order") == 1), None)
            if not actual_win:
                continue
            actual_top3 = {h["horse_num"] for h in horses if h.get("confirmed_order") in (1, 2, 3)}
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            top = preds[0]
            horse_by_num = {h["horse_num"]: h for h in horses}
            top_horse = horse_by_num[top.horse_num]
            win = top.horse_num == actual_win["horse_num"]
            top3 = top.horse_num in actual_top3
            ret = get_payout(conn, race, top.horse_num, "tan")
            rows.append((win, top3, ret))
            add(by_conf, top.confidence, win, top3, ret)
            add(by_track, track_name(race["track_code"]), win, top3, ret)
            add(by_surface, surface_name(race.get("track_type_code")), win, top3, ret)
            add(by_dist, bucket(race.get("distance")), win, top3, ret)
            add(by_popularity, popularity_bucket(top_horse.get("win_popularity")), win, top3, ret)
            add(by_group, race_group(race), win, top3, ret)
            add(by_ev, ev_bucket(top.expected_value), win, top3, ret)
            wr = next((p.rank for p in preds if p.horse_num == actual_win["horse_num"]), 99)
            winner_rank[wr] += 1
            if not top3 and len(misses) < args.misses:
                misses.append(
                    (
                        race["race_year"] + race["race_month_day"],
                        track_name(race["track_code"]),
                        int(race["race_num"]),
                        top.horse_num,
                        top_horse.get("horse_name"),
                        actual_win["horse_num"],
                        actual_win.get("horse_name"),
                        wr,
                        top.confidence,
                        round(top.score, 1),
                        top.rationale,
                    )
                )

    n = len(rows)
    wins = sum(r[0] for r in rows)
    top3s = sum(r[1] for r in rows)
    ret = sum(r[2] for r in rows)
    print(f"SUMMARY n={n} win={wins}({pct(wins, n)}%) top3={top3s}({pct(top3s, n)}%) ret={pct(ret, n * 100)}%")
    print_stats("CONFIDENCE", by_conf)
    print_stats("TRACK", by_track)
    print_stats("SURFACE", by_surface)
    print_stats("DISTANCE", by_dist)
    print_stats("TOP_POPULARITY", by_popularity)
    print_stats("RACE_GROUP", by_group)
    print_stats("TOP_EV", by_ev)
    print("WINNER_RANK", sorted(winner_rank.items()))
    if misses:
        print("MISSES")
        for m in misses:
            print("  " + " | ".join(map(str, m)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
