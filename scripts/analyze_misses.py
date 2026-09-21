"""敗因法解剖データセット: 「◎ が負けたレースで何が起きたか」をレース単位で並べる。

既存の診断 (diag_pred_accuracy / analyze_predictions) はスライス別の集計止まりで、
**レース単位の因果**—◎ はどこで負けたのか、勝った馬は何を持っていたのか—を
見る artifact が存在しなかった。本スクリプトはそれを作る。

入力 (再計算不要。既存の答え合わせ証跡を使う):
  - data/results/<date>/evaluation_summary.csv (◎ 印・朝オッズ・確定オッズ・着順・払戻)
  - data/results/<date>/predictions.csv (rationale = 実際に発火したシグナル文)
  - data/keiba.db (コーナー通過順・ラップ・馬体重・騎手・脚質・上がり3F 等の文脈)

出力: data/diag/miss_forensics_<ts>.csv (1 行 = 1 レース) + _summary.json

1 レース 1 行に「◎ 側」と「勝ち馬側」を横並びで置き、両者の差分を列にする。
これにより「◎ が 4角で何番手だったか」「勝ち馬は ◎ より人気だったか」等を
仮説ごとに集計できる。

usage:
    python -m scripts.analyze_misses --save
    python -m scripts.analyze_misses --era v6 --save
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import DB_PATH, PROJECT_ROOT  # noqa: E402

RESULTS_DIR = PROJECT_ROOT / "data" / "results"
OUT_DIR = PROJECT_ROOT / "data" / "diag"

# HTML に刻まれた lgbm rule_version から世代を判定する (混在期があるため)
ERA_PATTERNS = {"v6": "lgbm-v6", "v5": "lgbm-v5"}


def detect_era(date_dir: Path) -> str | None:
    """その開催日の予想 HTML がどのモデル世代で生成されたか。"""
    for pattern in ("predictions_source_*.html", "archive/*.html"):
        for html in sorted(date_dir.glob(pattern)):
            try:
                head = html.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for era, needle in ERA_PATTERNS.items():
                if needle in head:
                    return era
    return None


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def load_rationales(date_dir: Path) -> dict[tuple[str, str], str]:
    """(race_id, horse_num) -> rationale 文 (実際に発火したシグナル)。"""
    path = date_dir / "predictions.csv"
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[(row["race_id"], row["horse_num"])] = row.get("rationale") or ""
    return out


def horse_context(conn: sqlite3.Connection, date: str, track: str,
                  race_num: str, horse_num: str) -> dict:
    """DB から当該馬の当日文脈 (コーナー通過順・脚質・馬体重・騎手・上がり)。"""
    row = conn.execute(
        """
        SELECT h.corner_order_1 c1, h.corner_order_2 c2, h.corner_order_3 c3,
               h.corner_order_4 c4, h.leg_quality_code leg, h.final_3f,
               h.horse_weight, h.weight_change_sign ws,
               CAST(h.weight_change_diff AS INTEGER) wd,
               h.jockey_short_name jockey, h.trainer_short_name trainer,
               CAST(h.burden_weight AS INTEGER) burden, h.age, h.sex_code,
               h.mining_predicted_order ming, h.waku_num,
               CAST(h.confirmed_order AS INTEGER) fin, h.finish_time,
               h.abnormal_code
          FROM horse_races h
         WHERE h.race_year=? AND h.race_month_day=? AND h.track_code=?
           AND CAST(h.race_num AS INTEGER)=? AND CAST(h.horse_num AS INTEGER)=?
        """,
        (date[:4], date[4:], track, int(race_num), int(horse_num)),
    ).fetchone()
    return dict(row) if row else {}


def race_context(conn: sqlite3.Connection, date: str, track: str,
                 race_num: str) -> dict:
    row = conn.execute(
        """
        SELECT race_name, grade_code, distance, track_type_code, course_div,
               CAST(starter_count AS INTEGER) starter_count, weather_code,
               turf_condition, dirt_condition, front3f_time, last3f_time,
               lap_times, start_time
          FROM races
         WHERE race_year=? AND race_month_day=? AND track_code=?
           AND CAST(race_num AS INTEGER)=?
        """,
        (date[:4], date[4:], track, int(race_num)),
    ).fetchone()
    return dict(row) if row else {}


RATIONALE_TOKEN = re.compile(r"[0-9０-９.]+")


def normalize_tokens(rationale: str) -> list[str]:
    """rationale を「N」正規化したトークン列に (集計用)。"""
    return [RATIONALE_TOKEN.sub("N", t.strip())
            for t in (rationale or "").split(";") if t.strip()]


def build(era_filter: str | None = None, db_path: str | None = None) -> tuple[list[dict], dict]:
    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows: list[dict] = []
    # 理由ごとに数える。`excluded_cancelled` (永久) と
    # `excluded_result_not_yet_available` (一時) を分けて見えるようにする。
    from collections import defaultdict
    skipped = defaultdict(int, {"no_summary": 0, "no_mark": 0,
                                "no_result": 0, "era_filtered": 0})

    for date_dir in sorted(RESULTS_DIR.iterdir()):
        if not date_dir.is_dir():
            continue
        summary = date_dir / "evaluation_summary.csv"
        if not summary.exists():
            skipped["no_summary"] += 1
            continue
        era = detect_era(date_dir)
        if era_filter and era != era_filter:
            skipped["era_filtered"] += 1
            continue
        date = date_dir.name.replace("-", "")
        rationales = load_rationales(date_dir)

        # レース単位に束ねる
        by_race: dict[str, list[dict]] = {}
        with summary.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if not r["race_id"].startswith(date):
                    continue  # HTML に混在する翌日分を除外
                by_race.setdefault(r["race_id"], []).append(r)

        for race_id, horses in by_race.items():
            pick = next((h for h in horses if h["mark"] == "◎"), None)
            if pick is None:
                skipped["no_mark"] += 1
                continue
            # 評価対象外のレースは分析にも入れない。主要集計だけで除外しても、
            # ここが素通りだと分析系で中止レースが復活する。
            # **理由ごとに数える**: cancelled は永久除外、
            # result_not_yet_available は結果が来れば評価可へ戻る一時状態なので、
            # 同じ「除外」で潰すと前者と後者の区別が付かなくなる。
            reason = (pick.get("evaluation_exclusion_reason") or "").strip()
            if reason:
                skipped[f"excluded_{reason}"] += 1
                continue
            if str(pick.get("evaluable", "")).strip().lower() in ("false", "0"):
                skipped["excluded_not_evaluable"] += 1
                continue
            winner = next((h for h in horses if _i(h["confirmed_order"]) == 1), None)
            if winner is None:
                skipped["no_result"] += 1
                continue

            track = pick["track_code"]
            race_num = pick["race_num"]
            rc = race_context(conn, date, track, race_num)
            pc = horse_context(conn, date, track, race_num, pick["horse_num"])
            wc = horse_context(conn, date, track, race_num, winner["horse_num"])
            hit = pick["horse_num"] == winner["horse_num"]

            # 勝ち馬に我々が付けた印 (無印 = モデル 6 位以下)
            winner_mark = winner["mark"] or ""
            winner_model_rank = _i(winner["model_rank_by_mark"])

            rows.append({
                "race_id": race_id,
                "date": date,
                "era": era,
                "track_code": track,
                "race_num": race_num,
                "race_name": rc.get("race_name"),
                "grade_code": (rc.get("grade_code") or "").strip(),
                "distance": rc.get("distance"),
                "track_type_code": rc.get("track_type_code"),
                "starter_count": rc.get("starter_count"),
                "weather_code": rc.get("weather_code"),
                "turf_condition": rc.get("turf_condition"),
                "dirt_condition": rc.get("dirt_condition"),
                "front3f_time": rc.get("front3f_time"),
                "last3f_time": rc.get("last3f_time"),
                "hit": int(hit),
                # ---- ◎ 側 ----
                "pick_num": pick["horse_num"],
                "pick_name": pick["horse_name"],
                "pick_finish": _i(pick["confirmed_order"]),
                "pick_morning_odds": _f(pick["morning_odds"]),
                "pick_morning_pop": _i(pick["morning_popularity"]),
                "pick_final_odds": _f(pick["final_odds"]),
                "pick_final_pop": _i(pick["final_popularity"]),
                "pick_win_prob": _f(pick["win_probability"]),
                "pick_ev": _f(pick["expected_value_morning"]),
                "pick_confidence": pick.get("confidence"),
                "pick_c1": pc.get("c1"), "pick_c2": pc.get("c2"),
                "pick_c3": pc.get("c3"), "pick_c4": pc.get("c4"),
                "pick_leg": pc.get("leg"), "pick_final3f": pc.get("final_3f"),
                "pick_weight": pc.get("horse_weight"),
                "pick_weight_sign": pc.get("ws"), "pick_weight_diff": pc.get("wd"),
                "pick_jockey": pc.get("jockey"), "pick_trainer": pc.get("trainer"),
                "pick_burden": pc.get("burden"), "pick_age": pc.get("age"),
                "pick_waku": pc.get("waku_num"), "pick_ming": pc.get("ming"),
                "pick_abnormal": pc.get("abnormal_code"),
                "pick_rationale": rationales.get((race_id, pick["horse_num"]), ""),
                # ---- 勝ち馬側 ----
                "win_num": winner["horse_num"],
                "win_name": winner["horse_name"],
                "win_mark": winner_mark,
                "win_model_rank": winner_model_rank,
                "win_morning_odds": _f(winner["morning_odds"]),
                "win_morning_pop": _i(winner["morning_popularity"]),
                "win_final_odds": _f(winner["final_odds"]),
                "win_final_pop": _i(winner["final_popularity"]),
                "win_c1": wc.get("c1"), "win_c2": wc.get("c2"),
                "win_c3": wc.get("c3"), "win_c4": wc.get("c4"),
                "win_leg": wc.get("leg"), "win_final3f": wc.get("final_3f"),
                "win_weight": wc.get("horse_weight"),
                "win_weight_sign": wc.get("ws"), "win_weight_diff": wc.get("wd"),
                "win_jockey": wc.get("jockey"), "win_trainer": wc.get("trainer"),
                "win_burden": wc.get("burden"), "win_age": wc.get("age"),
                "win_waku": wc.get("waku_num"), "win_ming": wc.get("ming"),
                "win_rationale": rationales.get((race_id, winner["horse_num"]), ""),
                # ---- 差分 (仮説検証の軸) ----
                "pop_gap": (_i(winner["final_popularity"]) or 0) - (_i(pick["final_popularity"]) or 0),
                "odds_ratio": (
                    round(_f(winner["final_odds"]) / _f(pick["final_odds"]), 3)
                    if _f(winner["final_odds"]) and _f(pick["final_odds"]) else None
                ),
                "win_was_unmarked": int(not winner_mark),
                "pick_payout": _i(pick["win_payout"]),
            })
    conn.close()

    # サマリ
    n = len(rows)
    hits = sum(r["hit"] for r in rows)
    misses = [r for r in rows if not r["hit"]]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "races": n,
        "hits": hits,
        "hit_rate": round(hits / n, 4) if n else None,
        "skipped": skipped,
        "era_breakdown": {},
        "miss_winner_mark_dist": {},
        "miss_pick_finish_dist": {},
    }
    from collections import Counter
    summary["era_breakdown"] = dict(Counter(r["era"] for r in rows))
    summary["miss_winner_mark_dist"] = dict(
        Counter(r["win_mark"] or "無印" for r in misses))
    summary["miss_pick_finish_dist"] = dict(
        Counter(str(r["pick_finish"]) for r in misses))
    try:
        summary["git_sha"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=PROJECT_ROOT, check=True).stdout.strip()
    except Exception:
        summary["git_sha"] = None
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--era", default=None, choices=["v5", "v6"],
                    help="モデル世代で絞る (既定: 全世代)")
    ap.add_argument("--db", default=None)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    rows, summary = build(era_filter=args.era, db_path=args.db)
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    if args.save and rows:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{args.era}" if args.era else ""
        out = OUT_DIR / f"miss_forensics_{ts}{suffix}.csv"
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        (OUT_DIR / f"miss_forensics_{ts}{suffix}_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
