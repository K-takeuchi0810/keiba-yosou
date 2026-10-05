"""本番の backfill の後の ai-builder 読み取り側の互換確認 (2026-10-05、手順書の 11)。

ai-builder のコード・タスク・サービスには触れない。ai-builder が import する keiba-yosou の関数
(docs/EXTERNAL_DEPENDENTS.md の表 2) を、固定した worktree のコードで動かし、本番 DB を読み取り専用で開いて確かめる:
  1. import がすべて通る
  2. backfill した期間 (2025) と直近 (2026-10-04) のレースで、compute_features が recent_4corner_* を出し、
     値が範囲内 (平均 0〜18、標本数 1 以上)
  3. predict_race の予想 (馬番・score・印) が、フラグの True / False で同一 (通過順位は scoring に未配線なので、
     corner の値が入っても予想は変わらない)

usage (固定した worktree の根で):
    <main>/.venv64/Scripts/python.exe <main>/data/backtest/corner_scratch_20261004/ai_builder_compat_postbackfill.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WT = Path(os.getcwd()).resolve()
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
DAYS = ("20250928", "20261004")


def main() -> int:
    print(f"1. import OK (code = {WT.name}, config = {config.PROJECT_ROOT}); CORNER_BYTES_VERIFIED = {config.CORNER_BYTES_VERIFIED}")
    ok = True
    with open_db_readonly(PROD_DB) as conn:
        for day in DAYS:
            races = list_races(conn, day, day)[:2]
            if not races:
                print(f"2. {day}: レースなし")
                ok = False
                continue
            for race in races:
                hs = [dict(h) for h in horses_for_race(conn, race)]
                feats = [compute_features(conn, h, dict(race), cache={}) for h in hs]
                with_c = [f for f in feats if f.get("recent_4corner_samples")]
                bad = [f for f in with_c if not (0 <= float(f["recent_4corner_avg_position"]) <= 18)]
                ok &= bool(with_c) and not bad
                print(f"2. {day} track {race['track_code']} R{race['race_num']}: {len(feats)} 頭中 {len(with_c)} 頭で "
                      f"recent_4corner_* あり、範囲外 {len(bad)} (例 avg={with_c[0]['recent_4corner_avg_position'] if with_c else None} "
                      f"n={with_c[0]['recent_4corner_samples'] if with_c else None})")
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
            ok &= key == key_off and len(on) > 0
            print(f"3. {day} predict_race: True {len(on)} 頭 / False {len(off)} 頭、予想 (馬番・score・印) が同一: {key == key_off}")
    print("ALL_OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
