"""T−10 予想ランナー (改革 R1-1 柱 1)。

開催日に頻繁に起動し、**発走 T−n 分に達したレースだけ**を、その時点で観測
可能だった市場 (predictor.pit_market) で再計算して記録する。

## なぜ朝の生成と別に要るのか

朝 8-9 時の生成では市場人気加点が 0/367 で不発、オッズ保有も 57.5% しかなく、
EV は壊れた値になる (2026-08-22 実測)。一方 backtest は確定オッズを見るので
市場ブレンドが常に効く。この乖離 (train-serve skew) の解消が改革 R1-1 の
中心で、そのために「購入可能時刻の市場で判断する経路」を作る。

## 実行時刻に依存しない

cutoff は**発走時刻から逆算** (T−n) するので、T−10 に走らせても T−8 に
走らせても、後日 backtest で再計算しても**同じ入力・同じ出力**になる。
スケジューラが遅延しても記録の意味が変わらない。

- 発走前に処理できた → `actionable=True` (実際に買える時点の判断)
- 発走後に処理した (スケジューラ欠損等) → `actionable=False`。入力は同一
  なので記録としては有効だが、「買えたはず」とは主張しない

## 出力

1. `data/runtime/t10/<YYYYMMDD>.json` — レース単位の判断記録 (append、冪等)
2. `prediction_log` テーブル — 発行時点予想の DB 側証跡 (答え合わせ用)

買い候補はサスペンド中 (config.BUY_FILTER_DEFAULT["suspended"]) なので、
本ランナーは**購入推奨を出さない**。観察記録の蓄積が目的。

usage:
    .venv64/Scripts/python.exe -m scripts.predict_t10                # 通常 (今日)
    .venv64/Scripts/python.exe -m scripts.predict_t10 --dry-run
    .venv64/Scripts/python.exe -m scripts.predict_t10 --date 20260816 --all-day
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PIT_GATE_MINUTES, PROJECT_ROOT  # noqa: E402
from db import insert_prediction_log, open_db  # noqa: E402
from predictor.pit_market import apply_pit_odds, summarize_coverage  # noqa: E402
from predictor.rules import RULES_VERSION, is_tentative, predict_race  # noqa: E402
from scripts.backtest import horses_for_race  # noqa: E402

OUT_DIR = PROJECT_ROOT / "data" / "runtime" / "t10"


def _race_start(race: dict) -> datetime | None:
    st = str(race.get("start_time") or "").strip()
    if not st:
        return None
    st = st.zfill(4)
    date = f"{race.get('race_year','')}{race.get('race_month_day','')}"
    if len(date) != 8 or not (date + st[:4]).isdigit():
        return None
    try:
        return datetime.strptime(date + st[:4], "%Y%m%d%H%M")
    except ValueError:
        return None


def _race_key(race: dict) -> str:
    return (f"{race['race_year']}{race['race_month_day']}-{race['track_code']}"
            f"-{race['kaiji']}-{race['nichiji']}-{race['race_num']}")


def load_state(date: str) -> dict:
    """その日の記録を読む (冪等性の出典)。"""
    path = OUT_DIR / f"{date}.json"
    if not path.exists():
        return {"date": date, "gate_minutes": PIT_GATE_MINUTES, "races": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 壊れていても運用は止めない (新規で作り直す)。旧ファイルは .bad に退避。
        try:
            path.rename(path.with_suffix(".json.bad"))
        except OSError:
            pass
        return {"date": date, "gate_minutes": PIT_GATE_MINUTES, "races": {}}


def save_state(date: str, state: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{date}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # 原子的差し替え (途中で落ちても壊れたファイルを残さない)
    return path


def due_races(races: list[dict], now: datetime, gate_minutes: int,
              all_day: bool = False) -> list[tuple[dict, float]]:
    """処理対象 (発走まで gate 分以内、または発走後) を返す。

    all_day=True は時刻を無視して全レースを対象にする (backfill / 検証用)。
    戻り値の float は「発走までの分数」(負なら発走後)。
    """
    out = []
    for race in races:
        start = _race_start(race)
        if start is None:
            continue
        mins = (start - now).total_seconds() / 60.0
        if all_day or mins <= gate_minutes:
            out.append((race, mins))
    return out


def run(date: str, *, now: datetime | None = None, gate_minutes: int | None = None,
        all_day: bool = False, include_late: bool = True,
        dry_run: bool = False) -> dict:
    now = now or datetime.now()
    gate = PIT_GATE_MINUTES if gate_minutes is None else gate_minutes
    state = load_state(date)
    state["gate_minutes"] = gate
    processed, skipped_done, skipped_no_horses, late = 0, 0, 0, 0
    metas: list[dict] = []

    with open_db() as conn:
        races = [dict(r) for r in conn.execute(
            """
            SELECT race_year, race_month_day, track_code, kaiji, nichiji,
                   race_num, start_time, race_name, grade_code, distance,
                   track_type_code, starter_count, weather_code,
                   turf_condition, dirt_condition
            FROM races
            WHERE race_year=? AND race_month_day=? AND track_code BETWEEN '01' AND '10'
            ORDER BY track_code, race_num
            """,
            (date[:4], date[4:]),
        ).fetchall()]

        targets = due_races(races, now, gate, all_day=all_day)
        for race, mins in targets:
            key = _race_key(race)
            if key in state["races"]:
                skipped_done += 1
                continue
            actionable = mins > 0
            if not actionable:
                late += 1
                if not include_late:
                    continue

            horses = horses_for_race(conn, race)
            if not horses:
                skipped_no_horses += 1
                continue

            # ここが改革の核心: 判断入力を T−n 時点の市場に固定する
            pit_horses, pit_meta = apply_pit_odds(conn, race, horses, gate)
            metas.append(pit_meta)
            preds = predict_race(pit_horses, conn=conn, race=race)
            tentative = is_tentative(preds)

            top = next((p for p in preds if p.rank == 1 and p.mark), None)
            horse_by_num = {h.get("horse_num"): h for h in pit_horses}
            generated_at = now.isoformat(timespec="seconds")
            record = {
                "race_key": key,
                "track_code": race["track_code"],
                "race_num": race["race_num"],
                "race_name": race.get("race_name"),
                "start_time": race.get("start_time"),
                "generated_at": generated_at,
                "minutes_to_start": round(mins, 1),
                "actionable": actionable,
                "tentative": tentative,
                "pit": pit_meta,
                "model_version": RULES_VERSION,
                "picks": [
                    {
                        "horse_num": p.horse_num,
                        "mark": p.mark,
                        "rank": p.rank,
                        "win_probability": p.win_probability,
                        "expected_value": p.expected_value,
                        "confidence": p.confidence,
                        "win_odds": (horse_by_num.get(p.horse_num) or {}).get("win_odds"),
                        "win_popularity": (horse_by_num.get(p.horse_num) or {}).get("win_popularity"),
                    }
                    for p in preds if p.mark
                ],
                "top_mark": top.mark if top else None,
                "top_horse_num": top.horse_num if top else None,
            }
            if dry_run:
                print(f"  [dry-run] {key} T{mins:+.0f}min "
                      f"coverage={pit_meta['coverage']:.0%} "
                      f"top={record['top_horse_num']} tentative={tentative}")
                continue

            state["races"][key] = record
            insert_prediction_log(
                conn, race,
                [{
                    "horse_num": p.horse_num, "mark": p.mark, "rank": p.rank,
                    "score": p.score, "win_probability": p.win_probability,
                    "raw_blended_probability": p.raw_blended_probability,
                    "win_odds": (horse_by_num.get(p.horse_num) or {}).get("win_odds"),
                    "win_popularity": (horse_by_num.get(p.horse_num) or {}).get("win_popularity"),
                    "confidence": p.confidence,
                } for p in preds],
                generated_at=generated_at,
                model_version=f"t10:{RULES_VERSION}",
            )
            processed += 1

    summary = {
        "date": date,
        "now": now.isoformat(timespec="seconds"),
        "gate_minutes": gate,
        "races_in_db": len(races),
        "targets": len(targets),
        "processed": processed,
        "already_done": skipped_done,
        "late_after_start": late,
        "no_horses": skipped_no_horses,
        "coverage": summarize_coverage(metas) if metas else None,
        "total_recorded": len(state["races"]),
    }
    if not dry_run and processed:
        state["last_run"] = summary
        path = save_state(date, state)
        summary["state_path"] = str(path)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="YYYYMMDD (既定: 今日)")
    ap.add_argument("--gate-minutes", type=int, default=None,
                    help=f"T−n の n (既定: config.PIT_GATE_MINUTES={PIT_GATE_MINUTES})")
    ap.add_argument("--all-day", action="store_true",
                    help="時刻を無視して全レースを処理 (backfill / 検証用)")
    ap.add_argument("--no-late", action="store_true",
                    help="発走後のレースは記録しない (既定は記録して actionable=False)")
    ap.add_argument("--dry-run", action="store_true", help="書き込まず対象だけ表示")
    args = ap.parse_args()

    date = args.date or datetime.now().strftime("%Y%m%d")
    summary = run(date, gate_minutes=args.gate_minutes, all_day=args.all_day,
                  include_late=not args.no_late, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
