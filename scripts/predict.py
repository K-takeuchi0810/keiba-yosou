"""Output race predictions from the local SQLite database.

Examples:
    python -m scripts.predict
    python -m scripts.predict --date 20260503 --only-bets
    python -m scripts.predict --from 20260501 --to 20260503 --format csv
    python -m scripts.predict --only-bets --bet-size-mode third
    python -m scripts.predict --only-bets --bet-size-mode kelly_quarter --bet-unit 1000

Bet sizing (2026-05-16 added):
- `flat`: bet_unit per pick (default 100 円)
- `third`: bet_unit / 3 (= 小口モード、P14 採用後の安全運用用)
- `half`: bet_unit / 2
- `kelly_quarter`: bet_unit × (kelly_fraction / 4)、capped at bet_unit

買い目フィルタは `config.BUY_FILTER_DEFAULT` を参照 (UI / GUI / backtest と統一)。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BUY_FILTER_DEFAULT, is_whitelisted_race
from db import open_db
from predictor.rules import is_tentative, predict_race
from scripts.backtest import horses_for_race, list_races
from web.codes import track_name


def compute_bet_size(
    pred,
    mode: str,
    bet_unit: int,
) -> int:
    """賭金サイズを mode に応じて算出。

    `pred` は predictor.rules.Prediction (kelly_fraction フィールドを持つ)。
    `bet_unit` は基準単位 (100 / 1000 / 10000 円等)。
    戻り: 円単位の整数 (10 円単位に丸める)。
    """
    if mode == "flat":
        size = bet_unit
    elif mode == "third":
        size = bet_unit / 3
    elif mode == "half":
        size = bet_unit / 2
    elif mode == "kelly_quarter":
        # 1/4 Kelly: f* / 4 を bet_unit に掛ける。f* > 1 はあり得ないので cap。
        kelly = max(0.0, min(1.0, float(pred.kelly_fraction or 0)))
        size = bet_unit * kelly * 0.25
        size = min(size, bet_unit)  # 念のため bet_unit 上限
    else:
        raise ValueError(f"unknown bet-size-mode: {mode!r}")
    # 10 円単位丸め (最低 10 円)
    rounded = max(10, int(round(size / 10)) * 10)
    return rounded


def _is_bet_candidate(pred, horse: dict, tentative: bool, race: dict) -> bool:
    """買い候補判定。S7-α-2 (2026-05-18) で `predictor.filter.is_buy_candidate` に集約。

    本関数は後方互換のためのラッパー (scripts/predict.py 外から `_is_bet_candidate` で
    参照されていたかもしれないため残す)。新規コードは `is_buy_candidate` を直接呼ぶ。
    """
    from datetime import datetime

    from predictor.filter import is_buy_candidate
    # CLI 予想はライブ運用なので now を渡してオッズ鮮度も評価する (2026-06-13)
    return is_buy_candidate(pred, horse, tentative, race=race, now=datetime.now())


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
                # config.BUY_FILTER_DEFAULT を参照 (UI / GUI / backtest と統一)
                is_bet = _is_bet_candidate(pred, horse, tentative, race)
                bet_size = compute_bet_size(pred, args.bet_size_mode, args.bet_unit) if is_bet else 0
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
                        "bet_size_yen": bet_size,
                        "bet_size_mode": args.bet_size_mode if is_bet else "",
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
    total_bet = 0
    for r in rows:
        key = (r["date"], r["track_code"], r["race_num"])
        if key != current:
            current = key
            flag = " [暫定]" if r["tentative"] else ""
            print()
            print(f"{r['date']} {r['track']} {r['race_num']}R {r['race_name']}{flag}")
        bet_part = (
            f"買い {r['bet_size_yen']:>4}円 ({r['bet_size_mode']})"
            if r["bet_candidate"] else ""
        )
        if r["bet_candidate"]:
            total_bet += r["bet_size_yen"]
        print(
            f"  {r['mark'] or '-':2} {r['rank']:>2}位 "
            f"{r['horse_num']:>2} {r['horse_name']:<18} "
            f"{r['odds']:>5.1f}倍 人気{r['popularity']:>2} "
            f"score={r['score']:>5.1f} 信頼={r['confidence']} "
            f"勝率={r['win_probability']:>4.1f}% EV={r['expected_value']:>4.2f} "
            f"K={r['kelly_fraction']:>4.2f}% value={r['value_score']:>5.1f} {bet_part}"
        )
    bet_rows = [r for r in rows if r["bet_candidate"]]
    if bet_rows:
        print()
        print(f"=== 投資合計: {total_bet:,} 円 ({len(bet_rows)} 点) ===")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD. Default: latest race date in DB")
    ap.add_argument("--from", dest="from_date", help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", help="YYYYMMDD")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument(
        "--only-bets", action="store_true",
        help="show only buy_only picks (= matching config.BUY_FILTER_DEFAULT)",
    )
    ap.add_argument(
        "--bet-size-mode",
        choices=["flat", "third", "half", "kelly_quarter"],
        default="third",
        help="P14 後の安全運用は 'third' (1/3 size) を推奨。Kelly fraction 本実装後は "
             "'kelly_quarter' (= 1/4 Kelly) を default に。",
    )
    ap.add_argument(
        "--bet-unit", type=int, default=100,
        help="基準賭金単位 (default 100 円、flat なら 1 件 100 円、third なら 33 円)。"
             "kelly_quarter モード使用時は bet_unit >= 10000 円を強く推奨。"
             "P16 A1 後の Kelly uncap で kelly_fraction は連続値 (0-1) となるが、"
             "現状の calibrator 状態では Kelly は 0.05〜0.15 帯に集中するので、"
             "bet_unit=100 / 1000 では 10 円単位丸めで縮退する (bet_unit=1000 でも "
             "Kelly 0.05〜0.10 が全員 20 円固定)。bet_unit=10000 で Kelly 0.05 → 130 円、"
             "Kelly 0.10 → 250 円、Kelly 0.20 → 500 円の解像度。",
    )
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
