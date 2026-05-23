"""Phase H2 N1+N8+N2 共有 dump: predict_race を 2025-01〜2026-05 全 JRA 中央
race に走らせ、per-pick (= top-1 + mark, non-tentative) と per-race (= top-1
regardless of mark, for Brier including non-bet races) の 2 CSV を出力する。

このスクリプトが時間を食う唯一の場所 (~90-140 min)。これ 1 回で N1 (月次
Brier)、N8 (fold 分割 sensitivity)、N2 (同オッズ帯 LGBM vs MING) すべての
analyze スクリプトに供給できる。

usage:
    python -m scripts.dump_predictions \
        --from 20250101 --to 20260517 \
        --out-picks data/dump_picks.csv \
        --out-races data/dump_races.csv \
        --db /c/Users/kizun/dev/keiba-yosou/data/keiba.db
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.rules import is_tentative, predict_race
from scripts.backtest import get_payout, horses_for_race, list_races


PICK_FIELDS = [
    "date",            # yyyymmdd
    "track_code",
    "race_num",
    "grade_code",
    "top_horse_num",
    "top_rank",
    "top_mark",
    "p_win",                       # calibrated post-blend (decision-level)
    "p_raw_blended",               # pre-calibrator LGBM blend (race 内 Σ=1)
    "ev",
    "kelly",
    "confidence",
    "odds",                        # 倍率 (1/10 from win_odds)
    "popularity",
    "tm_score",
    "tm_rank",
    "dm_rank",
    "tan_payout",                  # 100 円賭けに対する払戻 (0 = 不的中)
    "fuku_payout",
    "y_win",                       # 1 if tan_payout > 0 else 0
]

RACE_FIELDS = [
    "date",
    "track_code",
    "race_num",
    "grade_code",
    "tentative",                   # 1 if race was tentative (LGBM skipped), else 0
    "top_horse_num",
    "top_rank",
    "top_has_mark",                # 1 if top rank=1 had a mark
    "p_win",                       # top-1 の calibrated probability
    "p_raw_blended",
    "ev",
    "odds",
    "y_top_is_winner",             # 1 if top horse was actual winner
    "tan_payout_if_bet",           # 100-yen bet on top -> payout
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", required=True)
    ap.add_argument("--out-picks", required=True)
    ap.add_argument("--out-races", required=True)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    started = time.time()

    out_picks_path = Path(args.out_picks)
    out_races_path = Path(args.out_races)
    out_picks_path.parent.mkdir(parents=True, exist_ok=True)
    out_races_path.parent.mkdir(parents=True, exist_ok=True)

    n_races = 0
    n_picks = 0
    n_tentative = 0
    n_no_top = 0

    with open_db(args.db) if args.db else open_db() as conn, \
         out_picks_path.open("w", encoding="utf-8", newline="") as pf, \
         out_races_path.open("w", encoding="utf-8", newline="") as rf:
        pw = csv.DictWriter(pf, fieldnames=PICK_FIELDS)
        rw = csv.DictWriter(rf, fieldnames=RACE_FIELDS)
        pw.writeheader()
        rw.writeheader()

        races = list_races(conn, args.from_date, args.to_date, jra_only=True)
        feature_cache: dict = {}
        last_log = time.time()

        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            n_races += 1
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)

            # actual winner: payouts.umaban_1 もしくは tan_payout1 が non-zero な horse
            # 既存 backtest.get_payout(conn, race, horse_num, "tan") が 100-yen 賭けの
            # 払戻 (= 0 if 負け) を返すので、それを使う
            tentative_flag = 1 if is_tentative(preds) else 0
            if tentative_flag:
                n_tentative += 1

            top = next((p for p in preds if p.rank == 1), None)
            if not top:
                n_no_top += 1
                continue

            date_str = f"{race['race_year']}{race['race_month_day']}"
            top_tan = get_payout(conn, race, top.horse_num, "tan")
            top_fuku = get_payout(conn, race, top.horse_num, "fuku")
            horse = next((h for h in horses if h.get("horse_num") == top.horse_num), None)
            top_feat = (horse.get("_features") if horse else None) or {}

            odds_val = (horse.get("win_odds") or 0) / 10.0 if horse else 0
            popularity_val = horse.get("win_popularity") or 0 if horse else 0

            # per-race row (Brier 用、tentative も含む)
            rw.writerow({
                "date": date_str,
                "track_code": race["track_code"],
                "race_num": race["race_num"],
                "grade_code": (race.get("grade_code") or "").strip(),
                "tentative": tentative_flag,
                "top_horse_num": top.horse_num,
                "top_rank": top.rank,
                "top_has_mark": 1 if top.mark else 0,
                "p_win": f"{float(top.win_probability or 0):.6f}",
                "p_raw_blended": f"{float(top.raw_blended_probability or 0):.6f}",
                "ev": f"{float(top.expected_value or 0):.6f}",
                "odds": f"{odds_val:.2f}",
                "y_top_is_winner": 1 if top_tan > 0 else 0,
                "tan_payout_if_bet": top_tan,
            })

            # per-pick row (= filter_sweep 互換、tentative 除外 + mark 必須)
            if tentative_flag or not top.mark:
                continue

            pw.writerow({
                "date": date_str,
                "track_code": race["track_code"],
                "race_num": race["race_num"],
                "grade_code": (race.get("grade_code") or "").strip(),
                "top_horse_num": top.horse_num,
                "top_rank": top.rank,
                "top_mark": top.mark,
                "p_win": f"{float(top.win_probability or 0):.6f}",
                "p_raw_blended": f"{float(top.raw_blended_probability or 0):.6f}",
                "ev": f"{float(top.expected_value or 0):.6f}",
                "kelly": f"{float(top.kelly_fraction or 0):.6f}",
                "confidence": top.confidence,
                "odds": f"{odds_val:.2f}",
                "popularity": popularity_val,
                "tm_score": int(top_feat.get("mining_tm_score") or 0),
                "tm_rank": int(top_feat.get("mining_tm_rank") or 0),
                "dm_rank": int(top_feat.get("mining_dm_rank") or 0),
                "tan_payout": top_tan,
                "fuku_payout": top_fuku,
                "y_win": 1 if top_tan > 0 else 0,
            })
            n_picks += 1

            if time.time() - last_log > 60:
                elapsed = time.time() - started
                print(
                    f"  progress: {n_races} races, {n_picks} picks, "
                    f"{n_tentative} tentative, {elapsed:.0f}s elapsed",
                    file=sys.stderr,
                    flush=True,
                )
                last_log = time.time()

    elapsed = time.time() - started
    print(
        f"done: {n_races} races, {n_picks} picks, {n_tentative} tentative, "
        f"{n_no_top} no_top, {elapsed:.0f}s",
        file=sys.stderr,
    )
    print(f"out_picks={out_picks_path}", file=sys.stderr)
    print(f"out_races={out_races_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
