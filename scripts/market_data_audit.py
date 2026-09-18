"""「市場」として使っていた 2 つの列が本当に市場なのかを検査する。

## なぜ要るか

Phase 0.5-2 / 0.5-3 は 2 つの価格を「市場」として扱った。専門家レビューで
どちらも額面どおりではないと指摘され、実測で裏が取れた。

**欠陥 A: `horse_races.win_odds` は確定オッズではない。**
確定単勝払戻 (`payouts`, data_div=2) と突き合わせると、勝ち馬 932 頭のうち
552 頭で一致しない。月別の不一致率は 5 月 95.0% / 6 月 93.1% / 7 月 0.0% /
8 月 40.0%。ずれは丸めの範囲を超える (比の最小 0.303、最大 4.149)。

**欠陥 B: 「T−10 のオッズ」の 3 割は T−10 のものではない。**
採用したスナップの発走までの残り時間は中央値 19.9 分だが、**32.8% が 30 分超**、
最大 964 分 (前夜)。Phase 0.5-1 は「決定時刻までの余裕の中央値と最小値」を
報告したので、この裾が見えていなかった。規則 (決定時刻以前で最新) は守られて
いる。問題は **その時刻に我々が持っていた最新値が古かった** こと。
「市場は T−10 でこの程度」と読むと、市場を不当に低く見積もる。

## この検査が出すもの

1. 確定払戻と `horse_races.win_odds` の一致率 (月別・全体)
2. T−10 スナップの鮮度分布と、鮮度で絞った場合のレース数
3. **鮮度で絞った T−10 市場ベースライン** (0.5-4 が越えるべき線)

usage:
    .venv64/Scripts/python.exe -m scripts.market_data_audit [--max-lead 30] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, guard_analysis_window  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.evaluation import brier, expected_calibration_error, log_loss  # noqa: E402
from predictor.pit_t10 import RACE_KEYS, decision_time, t10_market  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402

# 確定単勝払戻。JRA の払戻は 10 円単位なので、オッズに直すと 0.1 刻み。
PAYOUT_COLS = (("tan_horse_num1", "tan_payout1"), ("tan_horse_num2", "tan_payout2"),
               ("tan_horse_num3", "tan_payout3"))
CONFIRMED_DATA_DIV = "2"


def confirmed_win_payouts(conn: sqlite3.Connection, race: dict) -> dict[str, float]:
    """確定した単勝払戻 (100 円あたり) を 馬番 → オッズ倍率 で返す。

    **これが唯一の「本当に払い戻された価格」**。ただし単勝は 1〜3 着同着ぶんしか
    無いので、勝ち馬ぶんしか取れない。全頭の最終確率ベクトルは作れない。
    """
    row = conn.execute(
        """SELECT * FROM payouts
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=? AND data_div=?""",
        (*[race.get(k) for k in RACE_KEYS], CONFIRMED_DATA_DIV)).fetchone()
    if row is None:
        return {}
    out: dict[str, float] = {}
    for hcol, pcol in PAYOUT_COLS:
        h, p = row[hcol], row[pcol]
        if h is None or p in (None, "", 0):
            continue
        h = str(h).strip().zfill(2)
        if h in ("", "00"):
            continue
        out[h] = float(p) / 100.0
    return out


def run(from_date: str, to_date: str, max_lead: int) -> dict:
    from_date, to_date, _ = guard_analysis_window(
        from_date, to_date, context="market_data_audit")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = [dict(r) for r in conn.execute(
        """SELECT * FROM races
            WHERE (race_year||race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""",
        (from_date, to_date))]

    month_total, month_mismatch = Counter(), Counter()
    leads: list[tuple[float, str]] = []
    samples: list[dict] = []

    for race in races:
        month = str(race["race_month_day"])[:2]
        pay = confirmed_win_payouts(conn, race)
        winners = conn.execute(
            """SELECT horse_num, win_odds FROM horse_races
                WHERE race_year=? AND race_month_day=? AND track_code=?
                  AND kaiji=? AND nichiji=? AND race_num=? AND confirmed_order=1""",
            tuple(race.get(k) for k in RACE_KEYS)).fetchall()
        for w in winners:
            h = str(w["horse_num"]).strip().zfill(2)
            if h not in pay:
                continue
            month_total[month] += 1
            if abs(pay[h] - w["win_odds"] / 10.0) > 1e-6:
                month_mismatch[month] += 1

        m10 = t10_market(conn, race)
        target, start = decision_time(conn, race)
        if m10 is None or not m10.ok or start is None:
            continue
        lead = (start - datetime.fromisoformat(m10.odds_received_at)).total_seconds() / 60.0
        rid = "-".join(str(race.get(k)) for k in RACE_KEYS)
        leads.append((lead, rid))

        runners = conn.execute(
            """SELECT horse_num, confirmed_order FROM horse_races
                WHERE race_year=? AND race_month_day=? AND track_code=?
                  AND kaiji=? AND nichiji=? AND race_num=?
                  AND horse_num NOT IN ('', '00')""",
            tuple(race.get(k) for k in RACE_KEYS)).fetchall()
        won = {str(r["horse_num"]).strip(): (1 if r["confirmed_order"] == 1 else 0)
               for r in runners}
        if set(won) != set(m10.implied):
            continue
        for h, p in m10.implied.items():
            samples.append({"race_id": rid, "lead_min": lead, "won": won[h],
                            "p_t10": p, "payout": pay.get(h.zfill(2))})
    conn.close()

    leads.sort()
    vals = [x for x, _ in leads]

    def pct(q):
        return vals[min(int(q * len(vals)), len(vals) - 1)] if vals else float("nan")

    def baseline(rows):
        y = [r["won"] for r in rows]
        p = [r["p_t10"] for r in rows]
        return {"n_races": len({r["race_id"] for r in rows}), "n_horses": len(rows),
                "log_loss": log_loss(y, p), "brier": brier(y, p),
                "calibration_error": expected_calibration_error(y, p)}

    fresh = [r for r in samples if r["lead_min"] <= max_lead]
    return {
        "meta": {**snapshot(conn=None), "from_date": from_date, "to_date": to_date,
                 "max_lead_minutes": max_lead},
        "defect_a_final_odds": {
            "total_winners_checked": sum(month_total.values()),
            "mismatch": sum(month_mismatch.values()),
            "by_month": {m: {"n": month_total[m], "mismatch": month_mismatch[m],
                             "rate": month_mismatch[m] / month_total[m]}
                         for m in sorted(month_total)},
        },
        "defect_b_t10_staleness": {
            "n_races": len(vals),
            "lead_min": {"min": vals[0] if vals else None, "p25": pct(.25),
                         "median": pct(.5), "p75": pct(.75), "p90": pct(.9),
                         "max": vals[-1] if vals else None},
            "over_minutes": {str(t): sum(1 for v in vals if v > t)
                             for t in (15, 20, 30, 60, 120)},
        },
        "baseline_all": baseline(samples),
        "baseline_fresh_only": baseline(fresh),
    }


def main() -> int:
    dev = DATA_SPLIT["strategy_dev"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=dev["from"])
    ap.add_argument("--to", dest="to_date", default=dev["to"])
    ap.add_argument("--max-lead", type=int, default=30,
                    help="T−10 スナップの発走までの残り分数の上限")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    out = run(args.from_date, args.to_date, args.max_lead)

    a = out["defect_a_final_odds"]
    print("=== 欠陥 A: horse_races.win_odds は確定オッズか ===")
    print(f"  勝ち馬 {a['total_winners_checked']:,} 頭のうち "
          f"確定払戻と不一致 {a['mismatch']:,} 頭 "
          f"({a['mismatch'] / max(a['total_winners_checked'], 1) * 100:.1f}%)")
    for m, v in a["by_month"].items():
        print(f"    {m} 月 {v['mismatch']:4d}/{v['n']:4d} = {v['rate'] * 100:5.1f}%")

    b = out["defect_b_t10_staleness"]
    lm = b["lead_min"]
    print("\n=== 欠陥 B: 採用した T−10 スナップの発走までの残り分数 ===")
    print(f"  n={b['n_races']:,}  min {lm['min']:.1f} / p25 {lm['p25']:.1f} / "
          f"中央値 {lm['median']:.1f} / p75 {lm['p75']:.1f} / p90 {lm['p90']:.1f} / "
          f"max {lm['max']:.1f}")
    for t, n in b["over_minutes"].items():
        print(f"    {t:>3} 分より古い: {n:4d} レース "
              f"({n / max(b['n_races'], 1) * 100:.1f}%)")

    print("\n=== T−10 市場ベースライン ===")
    hdr = f"{'集合':>26} {'レース':>7} {'頭数':>8} {'LogLoss':>10} {'Brier':>9} {'較正誤差':>10}"
    print(hdr); print("-" * len(hdr))
    for label, key in (("全部 (鮮度を問わない)", "baseline_all"),
                       (f"鮮度 {out['meta']['max_lead_minutes']} 分以内のみ",
                        "baseline_fresh_only")):
        r = out[key]
        print(f"{label:>26} {r['n_races']:7,d} {r['n_horses']:8,d} "
              f"{r['log_loss']:10.5f} {r['brier']:9.5f} {r['calibration_error']:10.5f}")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
