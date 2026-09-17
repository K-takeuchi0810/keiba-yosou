"""T−10 市場と最終市場を同一レース集合で比較する (憲法 Phase 0.5-2)。

## 何を測るか

**AI を一切混ぜず**、市場だけで
「締切までの 10 分で、市場は結果をどれだけよりよく説明するようになったか」
を測る。

    ΔLogLoss = LogLoss(T−10) − LogLoss(Final)

正なら最終市場のほうが情報が多い。点推定だけで結論せず、
**レース単位ブートストラップの 95% 区間**を必ず付ける。

## 馬集合の一致

T−10 の後に取消・除外が起きると、T−10 時点と最終で馬集合が変わる。
黙って比較してはいけないので分類して数え、**主分析は集合が完全一致する
レースだけ**で行う。

## Final Market の扱い

最終オッズは **ベンチマーク・分析対象・精算** にのみ使う。
モデルの特徴量にしてはいけない (憲法 Phase 0.5-6)。

usage:
    .venv64/Scripts/python.exe -m scripts.market_baseline [--json out.json] [--movements out.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, guard_analysis_window, sealed_notice  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.evaluation import brier, expected_calibration_error, log_loss  # noqa: E402
from predictor.pit_t10 import RACE_KEYS, t10_market  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402


def _final_market(conn: sqlite3.Connection, race: dict) -> dict[str, float]:
    """最終オッズ (確定) から馬番→倍率。出走取消馬は win_odds=0 で自然に落ちる。"""
    rows = conn.execute(
        """SELECT horse_num, win_odds FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND horse_num NOT IN ('', '00') AND win_odds > 0""",
        tuple(race.get(k) for k in RACE_KEYS)).fetchall()
    return {str(r[0]).strip(): r[1] / 10.0 for r in rows}


def _winner(conn: sqlite3.Connection, race: dict) -> str | None:
    row = conn.execute(
        """SELECT tan_horse_num1 FROM payouts
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=? AND tan_payout1 > 0""",
        tuple(race.get(k) for k in RACE_KEYS)).fetchone()
    return str(row[0]).strip().lstrip("0") if row else None


def _implied(odds: dict[str, float]) -> tuple[dict[str, float], float]:
    raw = {h: 1.0 / o for h, o in odds.items() if o > 0}
    mass = sum(raw.values())
    if mass <= 0:
        return ({}, 0.0)
    return ({h: v / mass for h, v in raw.items()}, mass)


def collect(from_date: str, to_date: str, db_path: str | None = None) -> dict:
    # 結果 (払戻) を読むので封印の門を通す。Lockbox を開けていない現在は
    # 素通りするが、開始後に無自覚で封印窓を集計しないための門。
    from_date, to_date, sealed_info = guard_analysis_window(
        from_date, to_date, context="market_baseline")
    notice = sealed_notice(sealed_info)
    if notice:
        print(notice, file=sys.stderr)
    if sealed_info.get("fully_sealed"):
        return {"meta": {"sealed": sealed_info}, "counts": {},
                "n_races_analysed": 0, "n_horses_analysed": 0,
                "_movements": []}

    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = conn.execute(
        """SELECT * FROM races
            WHERE (race_year || race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
            ORDER BY race_year, race_month_day, track_code, race_num""",
        (from_date, to_date)).fetchall()

    c = Counter()
    # 主分析用 (馬集合が完全一致するレースのみ)
    samples: list[dict] = []
    movements: list[dict] = []

    for r in races:
        race = dict(r)
        c["races_total"] += 1
        m10 = t10_market(conn, race)
        if m10 is None:
            c["no_t10"] += 1
            continue
        c["t10_available"] += 1
        if not m10.ok:
            c["pit_violation"] += 1
            continue

        final_odds = _final_market(conn, race)
        if not final_odds:
            c["no_final"] += 1
            continue
        win = _winner(conn, race)
        if win is None:
            c["no_payout"] += 1
            continue

        set10, setf = set(m10.odds), set(final_odds)
        if set10 == setf:
            c["runner_set_same"] += 1
            category = "same"
        elif set10 > setf:
            c["runner_set_t10_only"] += 1     # T−10 後に取消・除外
            category = "scratched_after_t10"
        else:
            c["runner_set_other"] += 1
            category = "other_mismatch"

        p_final, mass_final = _implied(final_odds)
        # 価格変化のデータセットは全レースぶん残す (集合不一致も category で区別)
        rank_f = {h: i + 1 for i, h in enumerate(
            sorted(final_odds, key=lambda x: final_odds[x]))}
        for h in sorted(set10 & setf):
            movements.append({
                "race_id": m10.race_id, "horse_num": h, "category": category,
                "odds_t10": round(m10.odds[h], 1),
                "odds_final": round(final_odds[h], 1),
                "odds_ratio": round(final_odds[h] / m10.odds[h], 4),
                "p_t10": round(m10.implied[h], 6),
                "p_final": round(p_final.get(h, 0.0), 6),
                "p_diff": round(p_final.get(h, 0.0) - m10.implied[h], 6),
                "p_ratio": round(p_final.get(h, 0.0) / m10.implied[h], 4)
                if m10.implied[h] > 0 else None,
                "rank_t10": m10.market_rank[h], "rank_final": rank_f.get(h),
                "won": 1 if h.lstrip("0") == win else 0,
            })

        if category != "same":
            continue
        for h in sorted(set10):
            samples.append({
                "race_id": m10.race_id, "horse_num": h,
                "p_t10": m10.implied[h], "p_final": p_final.get(h, 0.0),
                "won": 1 if h.lstrip("0") == win else 0,
                "date": race["race_year"] + race["race_month_day"],
            })
    conn.close()

    y = [s["won"] for s in samples]
    p10 = [s["p_t10"] for s in samples]
    pf = [s["p_final"] for s in samples]
    race_ids = [s["race_id"] for s in samples]

    def metrics(p: list[float]) -> dict:
        winners = [pi for pi, yi in zip(p, y) if yi]
        return {
            "log_loss": log_loss(y, p), "brier": brier(y, p),
            "calibration_error": expected_calibration_error(y, p),
            "winner_mean_probability": (sum(winners) / len(winners)
                                        if winners else float("nan")),
        }

    m_t10, m_fin = metrics(p10), metrics(pf)
    delta_ll = m_t10["log_loss"] - m_fin["log_loss"]

    # レース単位ブートストラップで ΔLogLoss の区間を出す
    by_race: dict[str, list[int]] = {}
    for i, rid in enumerate(race_ids):
        by_race.setdefault(rid, []).append(i)
    blocks = list(by_race.values())
    rng = random.Random(20260918)
    boot: list[float] = []
    for _ in range(2000):
        idx: list[int] = []
        for _ in range(len(blocks)):
            idx.extend(blocks[rng.randrange(len(blocks))])
        yy = [y[i] for i in idx]
        boot.append(log_loss(yy, [p10[i] for i in idx])
                    - log_loss(yy, [pf[i] for i in idx]))
    boot.sort()

    return {
        "meta": {**snapshot(), "from_date": from_date, "to_date": to_date,
                 "odds_source_t10": "T-10", "odds_source_final": "final",
                 "sealed": sealed_info},
        "counts": dict(c),
        "n_races_analysed": len(by_race), "n_horses_analysed": len(samples),
        "t10_market": m_t10, "final_market": m_fin,
        "delta_log_loss": delta_ll,
        "delta_log_loss_ci95": [boot[50], boot[1949]],
        "movements_rows": len(movements),
        "_movements": movements,
    }


def main() -> int:
    dev = DATA_SPLIT["strategy_dev"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=dev["from"])
    ap.add_argument("--to", dest="to_date", default=dev["to"])
    ap.add_argument("--json", default=None)
    ap.add_argument("--movements", default=None, help="価格変化を CSV で保存")
    args = ap.parse_args()

    out = collect(args.from_date, args.to_date)
    c = out["counts"]
    print(f"=== 市場ベースライン {args.from_date}〜{args.to_date} ===")
    print(f"  レース総数                {c.get('races_total', 0):6,d}")
    print(f"  T−10 取得できず           {c.get('no_t10', 0):6,d}")
    print(f"  T−10 取得できた           {c.get('t10_available', 0):6,d}")
    print(f"    PIT 違反で除外          {c.get('pit_violation', 0):6,d}")
    print(f"    最終オッズなし          {c.get('no_final', 0):6,d}")
    print(f"    払戻なし                {c.get('no_payout', 0):6,d}")
    print(f"  馬集合が完全一致          {c.get('runner_set_same', 0):6,d}  ← 主分析")
    print(f"    T−10 後に取消・除外      {c.get('runner_set_t10_only', 0):6,d}")
    print(f"    その他の不一致          {c.get('runner_set_other', 0):6,d}")
    print()
    print(f"主分析: {out['n_races_analysed']:,} レース / {out['n_horses_analysed']:,} 頭")
    print()
    hdr = f"{'指標':>22} {'T−10 市場':>12} {'最終市場':>12} {'差':>10}"
    print(hdr); print("-" * len(hdr))
    for key, name in (("log_loss", "LogLoss"), ("brier", "Brier Score"),
                      ("calibration_error", "Calibration Error"),
                      ("winner_mean_probability", "勝ち馬の平均確率")):
        a, b = out["t10_market"][key], out["final_market"][key]
        print(f"{name:>22} {a:12.5f} {b:12.5f} {a - b:+10.5f}")
    lo, hi = out["delta_log_loss_ci95"]
    print()
    print(f"ΔLogLoss = LogLoss(T−10) − LogLoss(最終) = {out['delta_log_loss']:+.5f}")
    print(f"  レース単位ブートストラップ 95% 区間 [{lo:+.5f}, {hi:+.5f}]")
    print(f"  → {'最終市場のほうが情報が多い' if lo > 0 else '区間が 0 をまたぐ (差を断定できない)'}")

    movements = out.pop("_movements")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"saved: {args.json}")
    if args.movements:
        Path(args.movements).parent.mkdir(parents=True, exist_ok=True)
        with open(args.movements, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(movements[0]))
            w.writeheader()
            w.writerows(movements)
        print(f"saved: {args.movements} ({len(movements):,} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
