"""経路2: クロスプール相対価値の歴史検証 (改革案 rev 1.1 §8)。

単勝プール (最効率・控除率 20%) を確率のオラクルとして使い、馬連 (quinella) /
3連複 (trio) の確定オッズを Harville 含意確率と突き合わせる。
「単勝含意 EV = Harville確率 × プールオッズ」の帯別に実回収率を測り、
**他の投票者の組合せ価格の誤り**が搾取可能な大きさで存在するかを判定する。

設計の事前宣言 (sweep 的な後出し探索を防ぐ):
- EV 帯は PRE_DECLARED_BANDS で固定。結果を見て帯を切り直さない。
- 判定基準: EV>=1.0 帯の実回収率が bootstrap CI 下限で 100% を超える帯が
  存在すれば「live 化検討 (PIT 収集拡張)」、全帯 <100% なら経路2 棄却。
- オラクル確率は「確定単勝オッズの正規化」のみ (FLB 補正なし)。補正入りの
  改善版は素朴版が有望だった場合にのみ検討する (多重比較を増やさない)。

誠実な注記:
- 確定オッズ同士の突き合わせ = 発走時点の情報。live では T−10 オッズとの差で
  数 pt 劣化する。ここで出る回収率は上限値として読む。
- Harville は 2-3 着の確率を過大評価する既知バイアスがある (Stern 補正等は
  改善版の課題)。calibration 出力でバイアスの実測を添える。

usage:
    python -m scripts.analyze_cross_pool --from 20240101 --to 20260816 --save
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import DB_PATH, SQL_VALID_HORSE_NUM  # noqa: E402
from predictor.stats import bootstrap_return_rate, wilson_ci  # noqa: E402


def _repro_meta(db_path: str | None) -> dict:
    """再現性メタ (git_sha / dirty / db path / 帯定義)。

    2026-08-22 検証監査指摘: 分析 artifact に git_sha が無いと JSON 単体で
    再現できない (共通停止条件)。backtest の meta と同じ規約に揃える。
    """
    import subprocess
    meta: dict = {"db_path": str(db_path or DB_PATH),
                  "pre_declared_bands": [b if b != float("inf") else "inf"
                                         for b in PRE_DECLARED_BANDS]}
    try:
        meta["git_sha"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=ROOT, check=True).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--short"], capture_output=True, text=True,
            cwd=ROOT, check=True).stdout
        meta["git_dirty"] = bool(status.strip())
    except Exception:
        meta["git_sha"] = None
        meta["git_dirty"] = None
    return meta

ROOT = Path(__file__).resolve().parent.parent

# EV 帯 (事前宣言・固定)。境界を後から動かさないこと。
PRE_DECLARED_BANDS = [0.0, 0.5, 0.7, 0.85, 1.0, 1.15, 1.4, 2.0, float("inf")]

POOLS = {
    # bet_type: (payouts の列 prefix, combo の頭数)
    "quinella": ("umaren", 2),
    "trio": ("sanrenpuku", 3),
}


def harville_top2_prob(p: dict[str, float], i: str, j: str) -> float:
    """i,j が着順不問で 1-2 着に入る確率 (Harville)。"""
    pi, pj = p[i], p[j]
    out = 0.0
    if pi < 1.0:
        out += pi * pj / (1.0 - pi)
    if pj < 1.0:
        out += pj * pi / (1.0 - pj)
    return out


def harville_top3_prob(p: dict[str, float], tri: tuple[str, str, str]) -> float:
    """集合 {a,b,c} が着順不問で 1-3 着を占める確率 (Harville、6 順列の総和)。"""
    a, b, c = tri
    out = 0.0
    for x, y, z in ((a, b, c), (a, c, b), (b, a, c), (b, c, a), (c, a, b), (c, b, a)):
        px, py, pz = p[x], p[y], p[z]
        d1 = 1.0 - px
        d2 = d1 - py
        if d1 <= 0 or d2 <= 0:
            continue
        out += px * (py / d1) * (pz / d2)
    return out


def band_index(ev: float) -> int:
    for k in range(len(PRE_DECLARED_BANDS) - 1):
        if PRE_DECLARED_BANDS[k] <= ev < PRE_DECLARED_BANDS[k + 1]:
            return k
    return len(PRE_DECLARED_BANDS) - 2


def band_label(k: int) -> str:
    lo, hi = PRE_DECLARED_BANDS[k], PRE_DECLARED_BANDS[k + 1]
    hi_s = "inf" if hi == float("inf") else f"{hi:g}"
    return f"[{lo:g},{hi_s})"


def run(from_date: str, to_date: str, db_path: str | None = None) -> dict:
    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    races = conn.execute(
        """
        SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num
        FROM races
        WHERE race_year || race_month_day BETWEEN ? AND ?
          AND track_code BETWEEN '01' AND '10'
        ORDER BY race_year, race_month_day, track_code, race_num
        """,
        (from_date, to_date),
    ).fetchall()

    # by_race: race_key -> [pay_sum, stake_sum]。bootstrap はレース単位で
    # 再サンプルする (同一レース内の組合せは強く相関するため、combo 単位の
    # 再サンプルは CI を過小にする。2026-08-22 検証監査指摘)。
    agg = {
        pool: [
            {"n": 0, "hits": 0, "ret": 0, "by_race": {}}
            for _ in range(len(PRE_DECLARED_BANDS) - 1)
        ]
        for pool in POOLS
    }
    calib = {pool: [[0, 0.0, 0] for _ in range(10)] for pool in POOLS}
    n_races_used = {pool: 0 for pool in POOLS}
    n_races_total = 0
    skipped = {"no_confirmed": 0, "few_runners": 0, "no_payout_row": 0}

    for r in races:
        keys = (
            r["race_year"], r["race_month_day"], r["track_code"],
            r["kaiji"], r["nichiji"], r["race_num"],
        )
        horses = conn.execute(
            f"""
            SELECT horse_num, win_odds, CAST(confirmed_order AS INTEGER) AS fin
            FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=? AND {SQL_VALID_HORSE_NUM}
            """,
            keys,
        ).fetchall()
        runners = [h for h in horses if (h["win_odds"] or 0) > 0]
        if not any((h["fin"] or 0) == 1 for h in horses):
            skipped["no_confirmed"] += 1
            continue
        if len(runners) < 6:
            skipped["few_runners"] += 1
            continue
        n_races_total += 1

        inv = {h["horse_num"]: 1.0 / (h["win_odds"] / 10.0) for h in runners}
        total_inv = sum(inv.values())
        p = {num: v / total_inv for num, v in inv.items()}

        payout_row = conn.execute(
            """SELECT * FROM payouts WHERE race_year=? AND race_month_day=?
               AND track_code=? AND kaiji=? AND nichiji=? AND race_num=?""",
            keys,
        ).fetchone()
        if payout_row is None:
            skipped["no_payout_row"] += 1
            continue

        for pool, (prefix, k_size) in POOLS.items():
            odds_rows = conn.execute(
                """SELECT combo, odds_low FROM exotic_odds
                   WHERE race_year=? AND race_month_day=? AND track_code=?
                     AND kaiji=? AND nichiji=? AND race_num=?
                     AND bet_type=? AND data_div='5' AND odds_low>0""",
                (*keys, pool),
            ).fetchall()
            if not odds_rows:
                continue
            odds_by_combo = {row["combo"]: row["odds_low"] / 10.0 for row in odds_rows}

            # 的中 combo (同着で最大 3 口)
            winners: dict[str, int] = {}
            for i in (1, 2, 3):
                combo = str(payout_row[f"{prefix}_combo{i}"] or "").strip()
                pay = payout_row[f"{prefix}_payout{i}"] or 0
                if combo and pay > 0:
                    winners[combo] = pay
            if not winners:
                continue
            n_races_used[pool] += 1

            nums = sorted(p.keys())
            combos = combinations(nums, k_size)
            for tup in combos:
                combo_key = "".join(tup)
                odds = odds_by_combo.get(combo_key)
                if odds is None:
                    continue
                prob = (
                    harville_top2_prob(p, tup[0], tup[1]) if k_size == 2
                    else harville_top3_prob(p, tup)
                )
                ev = prob * odds
                b = band_index(ev)
                cell = agg[pool][b]
                cell["n"] += 1
                pay = winners.get(combo_key, 0)
                if pay:
                    cell["hits"] += 1
                    cell["ret"] += pay
                rc = cell["by_race"].setdefault(keys, [0, 0])
                rc[0] += pay
                rc[1] += 100
                # calibration: 確率スケールが小さいので粗い等幅ビン
                d = min(int(prob * 10), 9) if k_size == 2 else min(int(prob * 30), 9)
                calib[pool][d][0] += 1
                calib[pool][d][1] += prob
                calib[pool][d][2] += 1 if pay else 0

    result: dict = {
        "meta": _repro_meta(db_path),
        "from_date": from_date,
        "to_date": to_date,
        "races_scanned": len(races),
        "races_evaluated": n_races_total,
        "races_used": n_races_used,
        "skipped": skipped,
        "bands": [band_label(k) for k in range(len(PRE_DECLARED_BANDS) - 1)],
        "pools": {},
    }
    for pool in POOLS:
        rows = []
        for k, cell in enumerate(agg[pool]):
            n = cell["n"]
            row = {
                "band": band_label(k),
                "bets": n,
                "hits": cell["hits"],
                "hit_rate": round(cell["hits"] / n, 6) if n else None,
                "return_rate": round(cell["ret"] / (n * 100), 4) if n else None,
            }
            if n and PRE_DECLARED_BANDS[k] >= 1.0:
                lo, hi = wilson_ci(cell["hits"], n)
                row["hit_rate_ci95"] = [round(lo, 6), round(hi, 6)]
                race_pays = [v[0] for v in cell["by_race"].values()]
                race_stakes = [v[1] for v in cell["by_race"].values()]
                _, rlo, rhi = bootstrap_return_rate(
                    race_pays, race_stakes, n_resample=1000
                )
                row["return_rate_ci95"] = [round(rlo, 4), round(rhi, 4)]
                row["races_in_band"] = len(race_pays)
            rows.append(row)
        cal_rows = []
        for d, (n, psum, hits) in enumerate(calib[pool]):
            if n:
                cal_rows.append({
                    "decile": d,
                    "n": n,
                    "mean_predicted": round(psum / n, 6),
                    "realized": round(hits / n, 6),
                })
        result["pools"][pool] = {"ev_bands": rows, "harville_calibration": cal_rows}
    conn.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    started = datetime.now()
    result = run(args.from_date, args.to_date, db_path=args.db)
    result["elapsed_sec"] = round((datetime.now() - started).total_seconds(), 1)

    for pool, data in result["pools"].items():
        print(f"\n=== {pool} (races={result['races_used'][pool]}) ===")
        print("EV band      | bets      | hit%    | 回収%  | 回収CI95")
        for row in data["ev_bands"]:
            if not row["bets"]:
                continue
            ci = row.get("return_rate_ci95")
            ci_s = f"[{ci[0]*100:.1f},{ci[1]*100:.1f}]" if ci else ""
            print(f"{row['band']:<12} | {row['bets']:>9,} | {row['hit_rate']*100:6.3f}% "
                  f"| {row['return_rate']*100:6.1f}% {ci_s}")
        print("Harville calibration (predicted vs realized):")
        for c in data["harville_calibration"]:
            print(f"  bin{c['decile']}: n={c['n']:>9,} pred={c['mean_predicted']*100:7.3f}% "
                  f"real={c['realized']*100:7.3f}%")

    if args.save:
        out_dir = ROOT / "data" / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = out_dir / f"{ts}_cross_pool_value_{args.from_date}_{args.to_date}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nsaved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
