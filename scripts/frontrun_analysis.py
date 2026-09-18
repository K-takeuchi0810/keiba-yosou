"""ΔAI が終盤市場と実結果を先読みしているかを **価格帯を揃えて** 見る。

## なぜ層別が要るか

素の 5 分位表では第 1 分位 (AI が市場より低く見た馬) の ΔMarket も
第 5 分位も正で、U 字になる。理由は交絡:

  Fundamental は人気馬を薄く見るので、ΔAI が大きく負 = ほぼ人気馬。
  人気馬は最後の 10 分に買われやすい (Phase 0.5-2 で実測)。

つまり素の分位表は「AI の意見」ではなく **「その馬が人気かどうか」** を
見ているだけになりうる。価格帯を揃えて初めて AI 固有の情報を見られる。

> 特徴量一つだけで結果を見るのではなく、特定の条件ではこの組み合わせが
> 効いてくるなど、様々なパターンで検証しないと意味がありません (ユーザ)

usage:
    .venv64/Scripts/python.exe -m scripts.frontrun_analysis
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from predictor.provenance import snapshot  # noqa: E402

# T−10 市場の含意確率で層を切る。層の中では「市場から見た強さ」がほぼ同じ。
PRICE_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.000, 0.020, "T-10 0-2%"),
    (0.020, 0.050, "T-10 2-5%"),
    (0.050, 0.100, "T-10 5-10%"),
    (0.100, 0.200, "T-10 10-20%"),
    (0.200, 1.001, "T-10 20%+"),
)
N_BOOT = 2000
SEED = 20260918


def load(path: Path, max_lead: float, confirmed_only: bool) -> list[dict]:
    """標本を読み、**信用できる行だけ**に絞る。

    - `lead_min` が大きい行は T−10 のオッズではない (朝〜前夜のスナップ)。
    - `final_odds_confirmed=0` の行は `horse_races.win_odds` が確定払戻と
      一致しておらず、ΔMarket が本物の値動きを表していない。

    どちらも 2026-09-18 の専門家レビューで発覚した。絞らずに出した
    「価格を落とした相関 +0.180」は、この 2 つの汚染を含んだ値だった。
    """
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("won", "p_t10", "p_fund", "p_final", "delta_ai",
                  "delta_market", "odds_t10", "odds_final", "lead_min"):
            r[k] = float(r[k])
        r["final_odds_confirmed"] = int(r["final_odds_confirmed"])
    kept = [r for r in rows if r["lead_min"] <= max_lead]
    if confirmed_only:
        kept = [r for r in kept if r["final_odds_confirmed"]]
    return kept


def _block_boot(rows: list[dict], stat, n_boot: int = N_BOOT,
                seed: int = SEED) -> tuple[float, float]:
    """レースを塊として再抽出した 95% 区間。

    同一レースの馬は「1 頭しか勝たない」ので独立ではない。馬単位で再抽出すると
    区間が狭く出て、無い差を有ると言ってしまう。
    """
    blocks: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        blocks[r["race_id"]].append(r)
    bl = list(blocks.values())
    rng = random.Random(seed)
    vals: list[float] = []
    for _ in range(n_boot):
        sample: list[dict] = []
        for _ in range(len(bl)):
            sample.extend(bl[rng.randrange(len(bl))])
        v = stat(sample)
        if v is not None and not np.isnan(v):
            vals.append(v)
    if len(vals) < n_boot // 2:
        return float("nan"), float("nan")
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


def _terciles(rows: list[dict]) -> list[list[dict]]:
    o = sorted(rows, key=lambda r: r["delta_ai"])
    n = len(o) // 3
    return [o[:n], o[n:2 * n], o[2 * n:]] if n else []


def _band_stat(lo: float, hi: float, kind: str):
    """再抽出標本に対して「上位三分位 − 下位三分位」を計算する関数を作る。

    層の切り方も三分位の境界も **再抽出のたびに引き直す**。固定した境界を
    使い回すと、境界自体の不確実性が区間に入らず狭く出る。
    """
    def stat(sample: list[dict]) -> float | None:
        band = [r for r in sample if lo <= r["p_t10"] < hi]
        t = _terciles(band)
        if not t or not t[0] or not t[2]:
            return None
        if kind == "market":
            return (sum(r["delta_market"] for r in t[2]) / len(t[2])
                    - sum(r["delta_market"] for r in t[0]) / len(t[0]))
        ref = "p_t10" if kind == "win" else "p_final"
        top = (sum(r["won"] for r in t[2]) / len(t[2])
               - sum(r[ref] for r in t[2]) / len(t[2]))
        bot = (sum(r["won"] for r in t[0]) / len(t[0])
               - sum(r[ref] for r in t[0]) / len(t[0]))
        return top - bot
    return stat


def stratified(rows: list[dict]) -> list[dict]:
    """価格帯 × ΔAI 三分位。上位三分位 − 下位三分位の差に区間を付ける。"""
    out: list[dict] = []
    for lo, hi, label in PRICE_BANDS:
        band = [r for r in rows if lo <= r["p_t10"] < hi]
        if len(band) < 200:
            continue
        cells = _terciles(band)
        if not cells:
            continue
        rec: dict = {"band": label, "n": len(band), "cells": []}
        for i, cell in enumerate(cells):
            rec["cells"].append({
                "tercile": i + 1, "n": len(cell),
                "delta_ai_mean": sum(r["delta_ai"] for r in cell) / len(cell),
                "delta_market_mean": sum(r["delta_market"] for r in cell) / len(cell),
                "p_t10_mean": sum(r["p_t10"] for r in cell) / len(cell),
                "p_final_mean": sum(r["p_final"] for r in cell) / len(cell),
                "actual_win_rate": sum(r["won"] for r in cell) / len(cell),
            })
        rec["market_gap_hi_minus_lo"] = (rec["cells"][2]["delta_market_mean"]
                                         - rec["cells"][0]["delta_market_mean"])
        rec["market_gap_ci95"] = list(
            _block_boot(rows, _band_stat(lo, hi, "market")))
        rec["win_edge_gap_hi_minus_lo"] = (
            (rec["cells"][2]["actual_win_rate"] - rec["cells"][2]["p_t10_mean"])
            - (rec["cells"][0]["actual_win_rate"] - rec["cells"][0]["p_t10_mean"]))
        rec["win_edge_gap_ci95"] = list(
            _block_boot(rows, _band_stat(lo, hi, "win")))
        # **払戻は最終オッズで決まる**。金になるかを問うならこちらが本命。
        # T−10 に勝っても最終市場に勝てなければ、パリミュチュエルでは
        # 利益にならない (T−10 のオッズで買えるわけではないため)。
        rec["final_edge_gap_hi_minus_lo"] = (
            (rec["cells"][2]["actual_win_rate"] - rec["cells"][2]["p_final_mean"])
            - (rec["cells"][0]["actual_win_rate"] - rec["cells"][0]["p_final_mean"]))
        rec["final_edge_gap_ci95"] = list(
            _block_boot(rows, _band_stat(lo, hi, "final")))
        out.append(rec)
    return out


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _residualise(rows: list[dict], key: str) -> np.ndarray:
    z = _logit(np.array([r["p_t10"] for r in rows]))
    X = np.vstack([np.ones_like(z), z, z ** 2, z ** 3]).T
    v = np.array([r[key] for r in rows])
    return v - X @ np.linalg.lstsq(X, v, rcond=None)[0]


def partial_correlation(rows: list[dict]) -> dict:
    """ΔMarket と ΔAI の関係から **価格水準の効果を落とした** もの。

    どちらも logit(p_t10) の 3 次式で回帰し、その残差どうしの相関を取る。
    素の相関と大きく違えば、素の相関は価格水準を見ていたということ。
    """
    da = np.array([r["delta_ai"] for r in rows])
    dm = np.array([r["delta_market"] for r in rows])
    ra, rm = _residualise(rows, "delta_ai"), _residualise(rows, "delta_market")

    def stat(sample: list[dict]) -> float | None:
        aa, mm = _residualise(sample, "delta_ai"), _residualise(sample, "delta_market")
        if aa.std() == 0 or mm.std() == 0:
            return None
        return float(np.corrcoef(aa, mm)[0, 1])

    lo, hi = _block_boot(rows, stat, n_boot=500)
    return {"raw": float(np.corrcoef(da, dm)[0, 1]),
            "partial_given_price": float(np.corrcoef(ra, rm)[0, 1]),
            "partial_ci95": [lo, hi]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="?",
                    default="data/backtest/20260918_phase05_3_fundamental_samples.csv")
    ap.add_argument("--json", default=None)
    ap.add_argument("--max-lead", type=float, default=30.0,
                    help="T−10 スナップの発走までの残り分数の上限")
    ap.add_argument("--all-final", action="store_true",
                    help="最終オッズが確定払戻と一致しない行も含める (参考用)")
    args = ap.parse_args()

    rows = load(Path(args.csv), args.max_lead, not args.all_final)
    if not rows:
        print("条件を満たす行が無い", file=sys.stderr)
        return 1
    n_races = len({r["race_id"] for r in rows})
    print(f"=== 価格帯を揃えた ΔAI の検定 ({n_races:,} レース / {len(rows):,} 頭) ===")
    print(f"絞り込み: T−10 の鮮度 {args.max_lead:.0f} 分以内"
          + ("" if args.all_final else " / 最終オッズが確定払戻と一致"))
    print("ΔMarket = P_final − P_T10 (市場がその後どう動いたか)")
    print("実−T10 = その群で市場が外していた量\n")

    strat = stratified(rows)
    for rec in strat:
        print(f"[{rec['band']}]  n={rec['n']:,}")
        print(f"{'ΔAI 三分位':>12} {'頭数':>6} {'ΔAI 平均':>10} "
              f"{'ΔMarket 平均':>13} {'実勝率':>8} {'T-10':>8} {'実−T10':>9} "
              f"{'最終':>8} {'実−最終':>9}")
        for c in rec["cells"]:
            print(f"{c['tercile']:>12} {c['n']:6,d} {c['delta_ai_mean']:+10.4f} "
                  f"{c['delta_market_mean']:+13.5f} "
                  f"{c['actual_win_rate'] * 100:7.2f}% {c['p_t10_mean'] * 100:7.2f}% "
                  f"{(c['actual_win_rate'] - c['p_t10_mean']) * 100:+8.2f}pt "
                  f"{c['p_final_mean'] * 100:7.2f}% "
                  f"{(c['actual_win_rate'] - c['p_final_mean']) * 100:+8.2f}pt")
        lo, hi = rec["market_gap_ci95"]
        print(f"    上位−下位 ΔMarket = {rec['market_gap_hi_minus_lo'] * 100:+.3f}pt "
              f"95% 区間 [{lo * 100:+.3f}, {hi * 100:+.3f}]pt")
        lo, hi = rec["win_edge_gap_ci95"]
        print(f"    上位−下位 (実勝率−T-10)  = "
              f"{rec['win_edge_gap_hi_minus_lo'] * 100:+.3f}pt "
              f"95% 区間 [{lo * 100:+.3f}, {hi * 100:+.3f}]pt")
        lo, hi = rec["final_edge_gap_ci95"]
        print(f"    上位−下位 (実勝率−最終) = "
              f"{rec['final_edge_gap_hi_minus_lo'] * 100:+.3f}pt "
              f"95% 区間 [{lo * 100:+.3f}, {hi * 100:+.3f}]pt  ← 払戻はこちら\n")

    pc = partial_correlation(rows)
    print("=== 価格水準の効果を落とした相関 ===")
    print(f"  素の相関           {pc['raw']:+.4f}")
    print(f"  価格を落とした相関 {pc['partial_given_price']:+.4f} "
          f"95% 区間 [{pc['partial_ci95'][0]:+.4f}, {pc['partial_ci95'][1]:+.4f}]")

    out = {"meta": {**snapshot(), "source_csv": args.csv, "n_races": n_races,
                    "n_horses": len(rows), "n_bootstrap": N_BOOT,
                    "n_hypotheses": len(strat) * 3 + 1},
           "stratified": strat, "correlation": pc,
           "filters": {"max_lead_minutes": args.max_lead,
                       "confirmed_final_only": not args.all_final}}
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
