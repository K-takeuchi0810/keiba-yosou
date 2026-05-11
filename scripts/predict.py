"""Output race predictions from the local SQLite database.

Examples:
    python -m scripts.predict
    python -m scripts.predict --date 20260503 --only-bets
    python -m scripts.predict --from 20260501 --to 20260503 --format csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.rules import is_tentative, predict_race
from scripts.backtest import horses_for_race, list_races
from web.codes import track_name

DEFAULT_MIN_ODDS = 10.0
DEFAULT_MAX_ODDS = 20.0
DEFAULT_MIN_VALUE = 0.0


def latest_race_date(conn) -> str | None:
    row = conn.execute("SELECT MAX(race_year || race_month_day) FROM races").fetchone()
    return row[0] if row and row[0] else None


def pick_dates(conn, args) -> tuple[str, str]:
    if args.date:
        return args.date, args.date
    if args.from_date or args.to_date:
        if not (args.from_date and args.to_date):
            raise SystemExit("--from and --to must be used together")
        return args.from_date, args.to_date
    latest = latest_race_date(conn)
    if not latest:
        raise SystemExit("no races found in DB")
    return latest, latest


def _race_label(race: dict) -> str:
    return (
        f"{race['race_year']}{race['race_month_day']} "
        f"{track_name(race['track_code'])} {int(race['race_num'])}R"
    )


def collect_predictions(args) -> list[dict]:
    db_path = args.db
    rows: list[dict] = []
    with open_db(db_path) if db_path else open_db() as conn:
        from_date, to_date = pick_dates(conn, args)
        races = list_races(conn, from_date, to_date, jra_only=not args.all_tracks)
        feature_cache: dict = {}
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            tentative = is_tentative(preds)
            horse_by_num = {h["horse_num"]: h for h in horses}
            for pred in preds[: args.top]:
                horse = horse_by_num.get(pred.horse_num, {})
                odds = (horse.get("win_odds") or 0) / 10.0
                popularity = horse.get("win_popularity") or 0
                min_odds = args.min_odds
                max_odds = args.max_odds
                is_bet = (
                    pred.rank == 1
                    and pred.mark
                    and not tentative
                    and min_odds <= odds <= max_odds
                    and pred.value_score >= args.min_value
                    and pred.expected_value >= args.min_ev
                    and pred.kelly_fraction > 0
                    and pred.confidence not in ("暫定", "混戦", "接戦")
                )
                if args.only_bets and not is_bet:
                    continue
                rows.append(
                    {
                        "date": race["race_year"] + race["race_month_day"],
                        "track_code": race["track_code"],
                        "track": track_name(race["track_code"]),
                        "race_num": int(race["race_num"]),
                        "race_name": race.get("race_name") or race.get("race_short10") or "",
                        "start_time": race.get("start_time") or "",
                        "rank": pred.rank,
                        "mark": pred.mark,
                        "horse_num": int(pred.horse_num or 0),
                        "horse_name": horse.get("horse_name") or "",
                        "jockey": horse.get("jockey_short_name") or "",
                        "odds": odds,
                        "popularity": popularity,
                        "score": round(pred.score, 1),
                        "confidence": pred.confidence,
                        "confidence_gap": round(pred.confidence_gap, 1),
                        "value_score": pred.value_score,
                        "win_probability": round(pred.win_probability * 100, 1),
                        "fair_odds": pred.fair_odds,
                        "expected_value": pred.expected_value,
                        "kelly_fraction": round(pred.kelly_fraction * 100, 2),
                        "bet_candidate": is_bet,
                        "tentative": tentative,
                        "reason": pred.rationale,
                    }
                )
    return rows


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("予想対象がありません")
        return
    current = None
    for r in rows:
        key = (r["date"], r["track_code"], r["race_num"])
        if key != current:
            current = key
            flag = " [暫定]" if r["tentative"] else ""
            print()
            print(f"{r['date']} {r['track']} {r['race_num']}R {r['race_name']}{flag}")
        bet = "買い" if r["bet_candidate"] else ""
        print(
            f"  {r['mark'] or '-':2} {r['rank']:>2}位 "
            f"{r['horse_num']:>2} {r['horse_name']:<18} "
            f"{r['odds']:>5.1f}倍 人気{r['popularity']:>2} "
            f"score={r['score']:>5.1f} 信頼={r['confidence']} "
            f"勝率={r['win_probability']:>4.1f}% EV={r['expected_value']:>4.2f} "
            f"K={r['kelly_fraction']:>4.2f}% value={r['value_score']:>5.1f} {bet}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD. Default: latest race date in DB")
    ap.add_argument("--from", dest="from_date", help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", help="YYYYMMDD")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--only-bets", action="store_true", help="show only top picks matching the odds filter")
    ap.add_argument("--min-odds", type=float, default=DEFAULT_MIN_ODDS)
    ap.add_argument("--max-odds", type=float, default=DEFAULT_MAX_ODDS)
    ap.add_argument("--min-value", type=float, default=DEFAULT_MIN_VALUE)
    ap.add_argument("--min-ev", type=float, default=1.05)
    ap.add_argument("--all-tracks", action="store_true")
    ap.add_argument("--db", default=None, help="SQLite DB path")
    ap.add_argument("--format", choices=["table", "csv", "json"], default="table")
    args = ap.parse_args()

    rows = collect_predictions(args)
    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.format == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()) if rows else ["date"])
        writer.writeheader()
        writer.writerows(rows)
    else:
        print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
