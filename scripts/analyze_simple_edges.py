"""経路1 (FLB セグメント) / 経路3 (WIN5 キャリーオーバー) の棄却証跡スクリプト。

改革案 rev 1.2 (docs/REFORM_2026H2_MARKET_RESIDUAL.md §9) の経路1・経路3 は
当初 ad-hoc クエリで測定され、スクリプト・artifact が保存されていなかった
(2026-08-22 検証監査指摘: 再導出で母数が一致しない = 除外規約が文書化されて
いない)。本スクリプトは同じ測定を再実行可能な形で固定し、JSON に保存する。

母数の定義 (経路1):
- JRA 中央 (track_code 01-10)、指定期間、confirmed_order 非 NULL
- **確定オッズのみ** (odds_fetched_at IS NULL)。repair_odds_stamps --apply の
  前後で「発走前 snapshot が復元された行」は確定オッズでなくなるため、
  この母数は repair 適用状態に依存する。meta.git_sha と db の状態で固定する。
- 超本命帯 = win_odds 10..15 (1.0〜1.5 倍、境界含む)

判別子 (経路1、4 つで固定 — 追加・変更は多重比較を増やすので禁止):
  (a) mining_predicted_order == 1 / > 1 / NULL
  (b) 馬体重 10kg 以上減 (weight_change_sign='-' AND diff>=10)
  (c) 少頭数 starter_count <= 10
  (d) 終盤レース race_num >= 11

経路3 (WIN5): 全開催回について 市場平均EV = 0.7 + carryover_initial/売上金額。
data_div='9' 等の中止・不成立回は「機会」に数えない。

usage:
    python -m scripts.analyze_simple_edges --from 20210101 --to 20260816 --save
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import DB_PATH  # noqa: E402
from predictor.stats import bootstrap_return_rate, wilson_ci  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

ULTRA_FAVORITE_ODDS = (10, 15)  # 0.1 倍単位、両端含む


def _repro_meta(db_path: str | None) -> dict:
    meta: dict = {"db_path": str(db_path or DB_PATH)}
    try:
        meta["git_sha"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=ROOT, check=True).stdout.strip()
        meta["git_dirty"] = bool(subprocess.run(
            ["git", "status", "--short"], capture_output=True, text=True,
            cwd=ROOT, check=True).stdout.strip())
    except Exception:
        meta["git_sha"] = None
        meta["git_dirty"] = None
    return meta


def _summarize(rows: list) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    wins = sum(1 for r in rows if r["fin"] == 1)
    pays = [r["win_odds"] * 10 if r["fin"] == 1 else 0 for r in rows]
    stakes = [100] * n
    hlo, hhi = wilson_ci(wins, n)
    _, rlo, rhi = bootstrap_return_rate(pays, stakes, n_resample=1000)
    return {
        "n": n,
        "wins": wins,
        "hit_rate": round(wins / n, 4),
        "hit_rate_ci95": [round(hlo, 4), round(hhi, 4)],
        "return_rate": round(sum(pays) / (n * 100), 4),
        "return_rate_ci95": [round(rlo, 4), round(rhi, 4)],
    }


def run_route1(conn: sqlite3.Connection, from_date: str, to_date: str) -> dict:
    rows = conn.execute(
        """
        SELECT h.win_odds, CAST(h.confirmed_order AS INTEGER) fin,
               h.mining_predicted_order mp, h.weight_change_sign ws,
               CAST(h.weight_change_diff AS INTEGER) wd,
               CAST(r.starter_count AS INTEGER) sc,
               CAST(h.race_num AS INTEGER) rn
        FROM horse_races h
        JOIN races r USING (race_year, race_month_day, track_code,
                            kaiji, nichiji, race_num)
        WHERE h.race_year || h.race_month_day BETWEEN ? AND ?
          AND h.track_code BETWEEN '01' AND '10'
          AND h.confirmed_order IS NOT NULL
          AND h.odds_fetched_at IS NULL
          AND h.win_odds BETWEEN ? AND ?
        """,
        (from_date, to_date, *ULTRA_FAVORITE_ODDS),
    ).fetchall()
    out = {"universe_def": "JRA 01-10 / confirmed / odds_fetched_at IS NULL / "
                           f"win_odds in [{ULTRA_FAVORITE_ODDS[0]},{ULTRA_FAVORITE_ODDS[1]}]",
           "overall": _summarize(rows)}
    out["splits"] = {
        "mining_rank1": _summarize([r for r in rows if r["mp"] == 1]),
        "mining_rank_gt1": _summarize([r for r in rows if r["mp"] and r["mp"] > 1]),
        "mining_missing": _summarize([r for r in rows if not r["mp"]]),
        "weight_drop_ge10": _summarize(
            [r for r in rows if r["ws"] == "-" and (r["wd"] or 0) >= 10]),
        "small_field_le10": _summarize([r for r in rows if (r["sc"] or 0) <= 10]),
        "large_field_gt10": _summarize([r for r in rows if (r["sc"] or 0) > 10]),
        "race_11_12": _summarize([r for r in rows if (r["rn"] or 0) >= 11]),
        "race_1_10": _summarize([r for r in rows if 0 < (r["rn"] or 0) < 11]),
    }
    return out


def run_route3(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT w.race_year, w.race_month_day, w.sale_votes,
               w.carryover_initial, w.data_div,
               p.payout, p.hit_votes
        FROM win5 w
        LEFT JOIN win5_payouts p USING (race_year, race_month_day)
        WHERE w.sale_votes > 0
        """
    ).fetchall()
    events = []
    ev_positive = []
    for r in rows:
        sales_yen = r["sale_votes"] * 100
        ev = 0.7 + (r["carryover_initial"] or 0) / sales_yen
        rec = {
            "date": f"{r['race_year']}-{r['race_month_day']}",
            "ev": round(ev, 4),
            "carryover_yen": r["carryover_initial"] or 0,
            "sales_yen": sales_yen,
            "data_div": r["data_div"],
            "has_payout_row": r["payout"] is not None,
        }
        events.append(rec)
        # data_div '9' 等 (中止・不成立) は機会に数えない
        if ev > 1.0 and r["data_div"] not in ("9", "0") and r["payout"] is not None:
            ev_positive.append(rec)
    events.sort(key=lambda x: -x["ev"])
    return {
        "n_events": len(events),
        "ev_formula": "0.7 + carryover_initial / (sale_votes*100)",
        "real_ev_positive_opportunities": len(ev_positive),
        "ev_positive_detail": ev_positive,
        "top10_by_ev": events[:10],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default="20210101")
    ap.add_argument("--to", dest="to_date", default="20260816")
    ap.add_argument("--db", default=None)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    result = {
        "meta": _repro_meta(args.db),
        "from_date": args.from_date,
        "to_date": args.to_date,
        "route1_ultra_favorite": run_route1(conn, args.from_date, args.to_date),
        "route3_win5": run_route3(conn),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.close()

    r1 = result["route1_ultra_favorite"]
    print(f"=== 経路1 超本命帯 ({args.from_date}-{args.to_date}) ===")
    o = r1["overall"]
    print(f"  全体: n={o['n']} 勝率{o['hit_rate']*100:.1f}% 回収{o['return_rate']*100:.1f}% "
          f"CI[{o['return_rate_ci95'][0]*100:.1f},{o['return_rate_ci95'][1]*100:.1f}]")
    for k, v in r1["splits"].items():
        if v.get("n"):
            print(f"  {k:<18} n={v['n']:>5} 回収{v['return_rate']*100:6.1f}% "
                  f"CI[{v['return_rate_ci95'][0]*100:.1f},{v['return_rate_ci95'][1]*100:.1f}]")
    r3 = result["route3_win5"]
    print(f"=== 経路3 WIN5 ===")
    print(f"  開催 {r3['n_events']} 回 / 実質 EV>1 機会 {r3['real_ev_positive_opportunities']} 回")

    if args.save:
        out_dir = ROOT / "data" / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = out_dir / f"{ts}_simple_edges_{args.from_date}_{args.to_date}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
