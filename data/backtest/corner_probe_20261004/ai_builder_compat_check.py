"""ai-builder の読み取り側の互換確認 (2026-10-04、CORNER_BYTES_VERIFIED を True にしたコミットについて)。

ai-builder のコード・タスクには触れない。docs/EXTERNAL_DEPENDENTS.md の表 2 (読み取り側) の import を、この worktree の
コードで動かし、本番 DB を読み取り専用で開いて確かめる:
  1. import がすべて通る
  2. compute_features が、通過順位のある期間 (2026-07 以降) のレースで recent_4corner_* を出す
  3. predict_race の予想 (馬番・score・印) が、フラグの True / False で同一 (通過順位は scoring に未配線)

usage (worktree の根で):
    .venv64/Scripts/python.exe data/backtest/corner_probe_20261004/ai_builder_compat_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WT))

import config  # noqa: E402
from db import open_db_readonly  # noqa: E402
from predictor import sire_lines  # noqa: E402,F401
from predictor.features import compute_features, horse_past_runs  # noqa: E402,F401
from predictor.rules import is_tentative, predict_race  # noqa: E402,F401
from scripts.backtest import (  # noqa: E402,F401
    get_payout_row, horses_for_race, list_races, payout_from_row, popularity_config, race_odds_untrusted)
from web.codes import track_name, track_type  # noqa: E402,F401

PROD_DB = r"C:\Users\kizun\dev\keiba-yosou\data\keiba.db"
DAY = "20260920"


def main() -> int:
    print(f"1. import OK (code = {WT.name}); CORNER_BYTES_VERIFIED = {config.CORNER_BYTES_VERIFIED}")
    with open_db_readonly(PROD_DB) as conn:
        races = list_races(conn, DAY, DAY)[:2]
        for race in races:
            hs = [dict(h) for h in horses_for_race(conn, race)]
            feats = [compute_features(conn, h, dict(race), cache={}) for h in hs]
            with_c = [f for f in feats if f.get("recent_4corner_samples")]
            print(f"2. {race['race_year']}{race['race_month_day']} track {race['track_code']} R{race['race_num']}: "
                  f"{len(feats)} 頭中 {len(with_c)} 頭で recent_4corner_* あり "
                  f"(例 avg={with_c[0]['recent_4corner_avg_position']} n={with_c[0]['recent_4corner_samples']})")
        race = races[0]
        hs = [dict(h) for h in horses_for_race(conn, race)]
        on = predict_race(hs, conn, dict(race), cache={})
        config.CORNER_BYTES_VERIFIED = False
        try:
            off = predict_race(hs, conn, dict(race), cache={})
        finally:
            config.CORNER_BYTES_VERIFIED = True
        key = [(p.horse_num, round(p.score, 9), getattr(p, "mark", None)) for p in on]
        key_off = [(p.horse_num, round(p.score, 9), getattr(p, "mark", None)) for p in off]
        print(f"3. predict_race: True {len(on)} 頭 / False {len(off)} 頭、予想 (馬番・score・印) が同一: {key == key_off}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
