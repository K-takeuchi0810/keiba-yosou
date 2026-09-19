"""Phase 0.5-4A: 市場オフセットモデルを事前登録どおりに 1 回だけ検証する。

事前登録は `docs/PHASE05_PREREG.md`。**このスクリプトは登録内容を実装するだけで、
閾値も集合も後から動かさない。**

## 合格条件 (事前登録 4)

- **主要**: 条件付きロジット `won ~ β₁·logit(P_T10) + β₂·AI補正` で
  β₂ > 0 かつレース単位ブートストラップ 95% 区間の下限 > 0
- 補助: LogLoss < 0.21351 / 帯別較正が市場より悪くない (Bonferroni 0.05/6)
- **金額**: 100 円均等・確定払戻で回収率 95% 区間の下限 > 100%

## 棄却条件 (事前登録 4-3)

1. 補正が市場価格の単調変換にすぎない
   → `logit(P_T10)` の 3 次式を同時に入れても β₂ が生き残るかで判定
2. 鮮度 30 分以内で負けているのに全体では勝っている (古いオッズに勝っただけ)
3. 特徴に市場由来が混入 (`assert_no_market_features` が例外)

## 事前登録の不備 (正直に記録する)

4-2 に **購入条件を書いていなかった**。結果を見てから決めると事前登録の意味が
無くなるので、0.5-3 で既に公表している 2 つ (全頭 / AI が市場より 5pt 以上高い馬)
をそのまま使う。閾値の探索はしない。

usage:
    .venv64/Scripts/python.exe -m scripts.market_offset_eval --json out.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, guard_analysis_window  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.feature_manifest import assert_no_market_features  # noqa: E402
from predictor.pit_t10 import RACE_KEYS, decision_time, t10_market  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402
from scripts.fundamental_eval import (  # noqa: E402
    DEFAULT_MAX_LEAD_MINUTES,
    _block_boot,
    _final_market_odds,
    _logit,
    _normalise,
    band_calibration,
    conditional_logit,
    flat_bet_roi,
    metrics,
)
from scripts.fundamental_model import FEATURES, build_dataset  # noqa: E402
from scripts.market_data_audit import confirmed_win_payouts  # noqa: E402
from scripts.market_offset_model import MODEL_PATH  # noqa: E402

# 事前登録で固定した基準線 (鮮度 30 分以内・626 レースの T−10 市場)。
BASELINE_LOG_LOSS = 0.21351
# 補助仮説 6 個の Bonferroni。0.05/6 の両側 z。
BONFERRONI_Z = 2.638
# 0.5-3 で既に公表している購入条件。結果を見てから決めない。
BUY_EDGE_PT = 0.05


def collect(from_date: str, to_date: str) -> tuple[list[dict], Counter]:
    """T−10 市場を init_score にして補正を当て、確定払戻と突き合わせる。"""
    import lightgbm as lgb

    assert_no_market_features(
        FEATURES, source_module=Path(__file__).parent / "fundamental_model.py")
    print("評価期間の特徴を構築中 ...", flush=True)
    data, _ = build_dataset(from_date, to_date)
    booster = lgb.Booster(model_file=str(MODEL_PATH))
    X = np.array([[d[c] for c in FEATURES] for d in data], dtype=float)
    for d, m in zip(data, booster.predict(X, raw_score=True), strict=True):
        d["margin"] = float(m)

    by_race: dict[str, list[dict]] = defaultdict(list)
    for d in data:
        by_race[d["race_id"]].append(d)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = {r["race_id"]: dict(r) for r in conn.execute(
        """SELECT *, (race_year||'-'||race_month_day||'-'||track_code||'-'||kaiji
                      ||'-'||nichiji||'-'||race_num) AS race_id
             FROM races
            WHERE (race_year||race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""",
        (from_date, to_date))}

    c: Counter = Counter()
    samples: list[dict] = []
    for rid, rows in by_race.items():
        race = races.get(rid)
        if race is None:
            c["no_race"] += 1
            continue
        m10 = t10_market(conn, race)
        _, start = decision_time(conn, race)
        if m10 is None or not m10.ok or start is None:
            c["no_t10"] += 1
            continue
        final_odds = _final_market_odds(conn, race)
        payouts = confirmed_win_payouts(conn, race)
        if not final_odds:
            c["no_final"] += 1
            continue
        if (set(m10.odds) != set(final_odds)
                or set(m10.odds) != {r["horse_num"] for r in rows}):
            c["runner_set_mismatch"] += 1
            continue
        c["analysed"] += 1

        lead = ((start - datetime.fromisoformat(m10.odds_received_at))
                .total_seconds() / 60.0)
        # logit(P_true) = logit(P_market_T10) + 補正
        raw = {r["horse_num"]: float(
            1.0 / (1.0 + np.exp(-(_logit(m10.implied[r["horse_num"]])
                                  + r["margin"])))) for r in rows}
        p_off = _normalise(raw)
        winners = [r["horse_num"] for r in rows if r["won"] == 1]
        confirmed = bool(winners) and all(
            h.zfill(2) in payouts
            and abs(payouts[h.zfill(2)] - final_odds[h]) < 1e-6 for h in winners)
        if lead <= DEFAULT_MAX_LEAD_MINUTES:
            c["t10_fresh"] += 1

        for r in rows:
            h = r["horse_num"]
            samples.append({
                "race_id": rid, "horse_num": h, "date": r["date"],
                "won": r["won"], "lead_min": round(lead, 2),
                "final_odds_confirmed": int(confirmed),
                "p_t10": m10.implied[h], "p_offset": p_off[h],
                "margin": r["margin"],
                "z_t10": float(_logit(m10.implied[h])),
                "edge": p_off[h] - m10.implied[h],
                "odds_t10": m10.odds[h],
                "payout_odds": payouts.get(h.zfill(2), 0.0),
            })
    conn.close()
    return samples, c


def _add_price_polynomial(rows: list[dict]) -> None:
    """棄却条件 1 の検査用。`logit(P_T10)` の 2 次・3 次項を足す。"""
    for r in rows:
        z = r["z_t10"]
        r["z2"] = z * z
        r["z3"] = z * z * z


def run(from_date: str, to_date: str) -> dict:
    from_date, to_date, _ = guard_analysis_window(
        from_date, to_date, context="market_offset_eval")
    samples, counts = collect(from_date, to_date)
    fresh = [s for s in samples if s["lead_min"] <= DEFAULT_MAX_LEAD_MINUTES]
    _add_price_polynomial(fresh)
    _add_price_polynomial(samples)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    meta_snapshot = snapshot(conn)
    conn.close()

    out: dict = {
        "meta": {**meta_snapshot, "from_date": from_date, "to_date": to_date,
                 "prereg": "docs/PHASE05_PREREG.md", "run_index": 1,
                 "baseline_log_loss": BASELINE_LOG_LOSS,
                 "max_lead_minutes": DEFAULT_MAX_LEAD_MINUTES,
                 "buy_edge_pt": BUY_EDGE_PT, "market_features": 0},
        "counts": dict(counts),
        "sets": {"all": {"n_races": len({s["race_id"] for s in samples}),
                         "n_horses": len(samples)},
                 "fresh_t10": {"n_races": len({s["race_id"] for s in fresh}),
                               "n_horses": len(fresh)}},
    }

    # --- 主要仮説: 市場を与えた上での補正の係数 ---
    beta = conditional_logit(fresh, ["z_t10", "margin"])
    lo, hi = _block_boot(
        fresh, lambda d: conditional_logit(d, ["z_t10", "margin"])[1], n_boot=300)
    out["primary_conditional_logit"] = {
        "coef_market": beta[0], "coef_correction": beta[1],
        "coef_correction_ci95": [lo, hi],
        "pass": bool(beta[1] > 0 and lo > 0)}

    # --- 棄却条件 1: 価格の単調変換にすぎないか ---
    beta_p = conditional_logit(fresh, ["z_t10", "z2", "z3", "margin"])
    lo_p, hi_p = _block_boot(
        fresh, lambda d: conditional_logit(d, ["z_t10", "z2", "z3", "margin"])[3],
        n_boot=300)
    out["rejection_1_price_polynomial"] = {
        "coef_correction": beta_p[3], "coef_correction_ci95": [lo_p, hi_p],
        "survives": bool(beta_p[3] > 0 and lo_p > 0)}

    # --- 補助: LogLoss と帯別較正 ---
    for label, rows in (("fresh_t10", fresh), ("all", samples)):
        out[f"t10_market_{label}"] = metrics(rows, "p_t10")
        out[f"offset_{label}"] = metrics(rows, "p_offset")
    out["hypothesis_2_log_loss"] = {
        "offset": out["offset_fresh_t10"]["log_loss"],
        "baseline": BASELINE_LOG_LOSS,
        "pass": bool(out["offset_fresh_t10"]["log_loss"] < BASELINE_LOG_LOSS)}

    out["band_calibration_offset"] = band_calibration(fresh, "p_offset")
    out["band_calibration_t10"] = band_calibration(fresh, "p_t10")

    # --- 棄却条件 2: 鮮度内で負けて全体で勝っていないか ---
    d_fresh = (out["offset_fresh_t10"]["log_loss"]
               - out["t10_market_fresh_t10"]["log_loss"])
    d_all = out["offset_all"]["log_loss"] - out["t10_market_all"]["log_loss"]
    out["rejection_2_stale_only_win"] = {
        "delta_fresh": d_fresh, "delta_all": d_all,
        "triggered": bool(d_fresh > 0 and d_all < 0)}

    # --- 金額 ---
    buys = [s for s in fresh if s["edge"] > BUY_EDGE_PT]
    out["flat_bet_all"] = flat_bet_roi(fresh)
    out["flat_bet_edge"] = flat_bet_roi(buys) if buys else None
    money = out["flat_bet_edge"] or out["flat_bet_all"]
    out["money_pass"] = bool(money and money["roi_ci95"][0] > 1.0)

    out["verdict"] = {
        "primary": out["primary_conditional_logit"]["pass"],
        "money": out["money_pass"],
        "rejected_by": [k for k, v in (
            ("補正が価格の単調変換にすぎない",
             not out["rejection_1_price_polynomial"]["survives"]
             and out["primary_conditional_logit"]["pass"]),
            ("古いオッズにだけ勝っている",
             out["rejection_2_stale_only_win"]["triggered"]),
        ) if v],
    }
    out["verdict"]["overall_pass"] = bool(
        out["verdict"]["primary"] and out["verdict"]["money"]
        and not out["verdict"]["rejected_by"])
    out["_samples"] = samples
    return out


def main() -> int:
    dev = DATA_SPLIT["strategy_dev"]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=dev["from"])
    ap.add_argument("--to", dest="to_date", default=dev["to"])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    out = run(args.from_date, args.to_date)
    s = out["sets"]
    print(f"\n=== Phase 0.5-4A ({out['meta']['prereg']} どおり 1 回のみ) ===")
    print(f"  主分析 (鮮度 {out['meta']['max_lead_minutes']} 分以内) "
          f"{s['fresh_t10']['n_races']:,} レース / {s['fresh_t10']['n_horses']:,} 頭")
    print(f"  参考 (全体) {s['all']['n_races']:,} レース / "
          f"{s['all']['n_horses']:,} 頭")

    p = out["primary_conditional_logit"]
    lo, hi = p["coef_correction_ci95"]
    print("\n=== 主要仮説: 市場を与えた上で AI 補正に価値はあるか ===")
    print(f"  市場の係数   {p['coef_market']:+.4f}")
    print(f"  補正の係数   {p['coef_correction']:+.4f} 95% 区間 [{lo:+.4f}, {hi:+.4f}]")
    print(f"  → {'合格' if p['pass'] else '不合格 (区間が 0 を含む)'}")

    r1 = out["rejection_1_price_polynomial"]
    lo1, hi1 = r1["coef_correction_ci95"]
    print("\n=== 棄却条件 1: 補正は価格の単調変換にすぎないか ===")
    print(f"  logit(P_T10) の 3 次式を同時に入れた場合の補正の係数 "
          f"{r1['coef_correction']:+.4f} [{lo1:+.4f}, {hi1:+.4f}]")
    print(f"  → {'生き残る' if r1['survives'] else '生き残らない'}")

    print("\n=== 補助 1: LogLoss ===")
    hdr = f"{'集合':>14} {'T−10 市場':>12} {'オフセット後':>14} {'差':>10}"
    print(hdr); print("-" * len(hdr))
    for label, title in (("fresh_t10", "鮮度内 (主)"), ("all", "全体 (参考)")):
        a = out[f"t10_market_{label}"]["log_loss"]
        b = out[f"offset_{label}"]["log_loss"]
        print(f"{title:>14} {a:12.5f} {b:14.5f} {b - a:+10.5f}")
    h2 = out["hypothesis_2_log_loss"]
    print(f"  事前登録の基準線 {h2['baseline']:.5f} に対し "
          f"{'下回った' if h2['pass'] else '下回らなかった'}")

    print("\n=== 補助 2-6: 確率帯ごとの較正 (Bonferroni z≥2.64) ===")
    mkt = {r["band"]: r for r in out["band_calibration_t10"]}
    print(f"{'帯':>8} {'頭数':>7} {'予測':>7} {'実際':>7} {'ずれ':>8} "
          f"{'95% 区間':>22} | {'市場のずれ':>10}")
    for r in out["band_calibration_offset"]:
        m = mkt.get(r["band"])
        lo_b, hi_b = r["gap_ci95"]
        mg = f"{(m['gap']) * 100:+9.2f}pt" if m else ""
        print(f"{r['band']:>8} {r['n']:7,d} {r['predicted'] * 100:6.2f}% "
              f"{r['actual'] * 100:6.2f}% {r['gap'] * 100:+7.2f}pt "
              f"[{lo_b * 100:+6.2f}, {hi_b * 100:+6.2f}]pt | {mg}")

    print("\n=== 金額 (100 円均等 / 払戻は確定値) ===")
    for key, title in (("flat_bet_all", "鮮度内の全頭"),
                       ("flat_bet_edge",
                        f"補正後が市場より {BUY_EDGE_PT * 100:.0f}pt 以上高い馬")):
        r = out.get(key)
        if not r:
            continue
        lo_r, hi_r = r["roi_ci95"]
        print(f"  {title:>32} {r['n_bets']:6,d} 点 {r['roi'] * 100:6.1f}% "
              f"95% 区間 [{lo_r * 100:.1f}, {hi_r * 100:.1f}]%")

    v = out["verdict"]
    print("\n=== 事前登録に照らした判定 ===")
    print(f"  主要仮説 (β₂ の区間下限 > 0)     {'合格' if v['primary'] else '不合格'}")
    print(f"  金額 (回収率の区間下限 > 100%)   {'合格' if v['money'] else '不合格'}")
    print(f"  棄却条件                         "
          f"{'該当なし' if not v['rejected_by'] else ' / '.join(v['rejected_by'])}")
    print(f"  **総合: {'合格' if v['overall_pass'] else '不合格'}**")

    out.pop("_samples")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
