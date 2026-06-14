"""フェーズ4 検証用: top-1 (◎) の確率を構成要素に分解して出力する。

predict_race を 1 回走らせ、その出力 (全馬の raw_blended_probability) から
calibrator 適用後 model 確率 (cal_model) と市場確率 (market) を再構成し、
◎ (rank1, mark, 非tentative) について以下を CSV 出力する:

  raw_blended_top, cal_model_top, market_top, odds, popularity, confidence,
  win_prob_current (= predict_race が返した investment prob、sanity 用),
  tan_payout, fuku_payout, y_win

これにより re-run なしで `_investment_probability` の blend 重み・discount を
CSV 上で自由に sweep でき、市場単独 (w=0) の calibration 上限も測れる。

usage:
    python -m scripts.diag_blend_decompose --from 20250701 --to 20260614 \
        --out data/diag/decompose_2025H2_2026.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.rules import (
    _apply_calibrator,
    is_tentative,
    predict_race,
)
from scripts.backtest import get_payout, horses_for_race, list_races

FIELDS = [
    "date", "track_code", "race_num", "popularity", "odds", "confidence",
    "raw_blended_top", "cal_model_top", "market_top", "win_prob_current",
    "tan_payout", "fuku_payout", "y_win",
]


def market_probs(horses: list[dict]) -> dict[str, float]:
    implied = []
    for h in horses:
        odds = (h.get("win_odds") or 0) / 10.0
        implied.append((h.get("horse_num") or "", 1.0 / odds if odds > 1.0 else 0.0))
    total = sum(p for _, p in implied)
    if total <= 0:
        return {}
    return {num: p / total for num, p in implied}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    n = 0
    last = started

    with open_db(args.db) if args.db else open_db() as conn, \
            out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        races = list_races(conn, args.from_date, args.to_date, jra_only=True)
        cache: dict = {}
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            preds = predict_race(horses, conn=conn, race=race, cache=cache)
            if is_tentative(preds):
                continue
            top = next((p for p in preds if p.rank == 1), None)
            if not top or not top.mark:
                continue
            blended = {p.horse_num: float(p.raw_blended_probability or 0) for p in preds}
            cal = _apply_calibrator(blended)
            mkt = market_probs(horses)
            num = top.horse_num
            horse = next((h for h in horses if h.get("horse_num") == num), None)
            odds = (horse.get("win_odds") or 0) / 10.0 if horse else 0.0
            pop = (horse.get("win_popularity") or 0) if horse else 0
            tan = get_payout(conn, race, num, "tan")
            fuku = get_payout(conn, race, num, "fuku")
            w.writerow({
                "date": f"{race['race_year']}{race['race_month_day']}",
                "track_code": race["track_code"],
                "race_num": race["race_num"],
                "popularity": pop,
                "odds": f"{odds:.2f}",
                "confidence": top.confidence,
                "raw_blended_top": f"{blended.get(num, 0):.6f}",
                "cal_model_top": f"{cal.get(num, 0):.6f}",
                "market_top": f"{mkt.get(num, 0):.6f}",
                "win_prob_current": f"{float(top.win_probability or 0):.6f}",
                "tan_payout": tan,
                "fuku_payout": fuku,
                "y_win": 1 if tan > 0 else 0,
            })
            n += 1
            if time.time() - last > 60:
                print(f"  {n} picks, {time.time()-started:.0f}s", file=sys.stderr, flush=True)
                last = time.time()

    print(f"done: {n} picks, {time.time()-started:.0f}s -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
