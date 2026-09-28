"""9/27 の ai-builder の取得停止が、T−10 の市場の入力をどれだけ悪くしたか (読み取りのみ)。

モデルの成績や ROI は見ない。見るのはデータの取得の可用性だけ。

- レースごとに、本番と同じ規則 (`predictor.pit_t10.t10_market`、決定時刻 = 既知の発走時刻 − 10 分、
  それ以前に受信した最新の 1 枚) で T−10 の市場を選び、選ばれた枚の取得元と古さ (決定時刻 − 受信時刻) を出す
- 馬ごとの選択 (`predictor.pit_market.latest_pit_odds`、予想の生成が使う) の取得元も数える
- 停止の区間: その日の raw 0B30 の取得の間隔が 15 分以上あいた区間 (ai-builder の取得が止まっていた区間)。
  決定時刻がその中に入るレースを「停止中」とする
- 比べる日: 停止が起きる前の開催日 (9/13・9/14) と、停止が多かった 9/26・9/27
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\kizun\dev\keiba-yosou")
sys.path.insert(0, str(ROOT))
from predictor.pit_t10 import RACE_KEYS, decision_time, t10_market  # noqa: E402
from predictor.pit_market import latest_pit_odds  # noqa: E402

DB = f"file:{(ROOT / 'data' / 'keiba.db').as_posix()}?mode=ro"
DAYS = sys.argv[1:] or ["20260913", "20260914", "20260926", "20260927"]
GAP_MIN = 15
FRESH_MIN = 30


def raw_gaps(day: str):
    """その日の raw 0B30 の受信時刻 (ファイル名の epoch) の間隔が GAP_MIN 分以上の区間。"""
    ts = sorted(datetime.fromtimestamp(int(m.group(1)))
                for f in (ROOT / "data" / "raw" / "0B30").iterdir()
                if (m := re.match(rf"0B30_{day}\d{{8}}_(\d+)\.jvd$", f.name)))
    gaps = [(a, b) for a, b in zip(ts, ts[1:]) if (b - a) >= timedelta(minutes=GAP_MIN)]
    return ts, gaps


def q(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))], 1) if xs else None


def main():
    conn = sqlite3.connect(DB, uri=True)
    conn.row_factory = sqlite3.Row
    report = {"observed_at": datetime.now().isoformat(timespec="seconds"), "gap_min": GAP_MIN,
              "fresh_min": FRESH_MIN, "days": {}}
    for day in DAYS:
        ts, gaps = raw_gaps(day)
        races = [dict(r) for r in conn.execute(
            "SELECT * FROM races WHERE race_year=? AND race_month_day=? "
            "AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10 AND COALESCE(data_div,'') <> '9' "
            "ORDER BY start_time", (day[:4], day[4:]))]
        rows = []
        horse_src = Counter()
        for race in races:
            target, start = decision_time(conn, race)
            m = t10_market(conn, race)
            in_outage = bool(target and any(a < target < b for a, b in gaps))
            row = {"race": "-".join(str(race[k]) for k in RACE_KEYS), "decision": target.isoformat() if target else None,
                   "in_outage": in_outage}
            if m is None or not m.ok:
                row.update(status="missing" if m is None else "violation", source=None, age_min=None)
            else:
                src = sorted({r[0] for r in conn.execute(
                    "SELECT source FROM odds_snapshots WHERE race_year=? AND race_month_day=? AND track_code=? "
                    "AND kaiji=? AND nichiji=? AND race_num=? AND fetched_at=?",
                    (*[race[k] for k in RACE_KEYS], m.odds_received_at))})
                age = (target - datetime.fromisoformat(m.odds_received_at)).total_seconds() / 60
                row.update(status="fresh" if age <= FRESH_MIN else "stale", source="+".join(src), age_min=round(age, 2))
            rows.append(row)
            for s in latest_pit_odds(conn, race).values():
                horse_src[s["source"]] += 1

        def summ(sub):
            ages = [r["age_min"] for r in sub if r["age_min"] is not None]
            return {"races": len(sub), "status": dict(Counter(r["status"] for r in sub)),
                    "source": dict(Counter(r["source"] for r in sub if r["source"])),
                    "age_min_p50": q(ages, 0.5), "age_min_p90": q(ages, 0.9), "age_min_max": max(ages) if ages else None,
                    "age_over_5min": sum(a > 5 for a in ages), "age_over_10min": sum(a > 10 for a in ages)}
        out_rows = [r for r in rows if r["in_outage"]]
        norm_rows = [r for r in rows if not r["in_outage"]]
        report["days"][day] = {
            "raw_0B30_files": len(ts), "raw_0B30_span": [ts[0].strftime("%H:%M"), ts[-1].strftime("%H:%M")] if ts else None,
            "outage_windows": [[a.strftime("%H:%M:%S"), b.strftime("%H:%M:%S"), round((b - a).total_seconds() / 60, 1)] for a, b in gaps],
            "outage_minutes_total": round(sum((b - a).total_seconds() for a, b in gaps) / 60, 1),
            "all": summ(rows), "in_outage": summ(out_rows), "not_in_outage": summ(norm_rows),
            "rescued_by_0B31_in_outage": sum(1 for r in out_rows if r["status"] == "fresh" and r["source"] and "0B31" in r["source"] and "0B30" not in r["source"]),
            "stale_or_missing_in_outage": sum(1 for r in out_rows if r["status"] != "fresh"),
            "horse_level_source_latest_pit_odds": dict(horse_src),
            "races": rows,
        }
        d = report["days"][day]
        print(day, "0B30 files", d["raw_0B30_files"], "outage", len(gaps), d["outage_minutes_total"], "min |",
              "all", d["all"]["status"], d["all"]["source"], "p50/p90/max", d["all"]["age_min_p50"], d["all"]["age_min_p90"], d["all"]["age_min_max"], "|",
              "outage", d["in_outage"]["races"], d["in_outage"]["status"], d["in_outage"]["source"], d["in_outage"]["age_min_p50"], d["in_outage"]["age_min_p90"], "|",
              "normal", d["not_in_outage"]["races"], d["not_in_outage"]["age_min_p50"], d["not_in_outage"]["age_min_p90"], "| rescued", d["rescued_by_0B31_in_outage"], flush=True)
    (Path(__file__).resolve().parent / "t10_outage_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
