"""特徴が学習域を出ていないかを測る (憲法 Phase 0.5-4B 基盤修復)。

## なぜ要るか

0.5-4A のレビューで、`t_runs` / `j_rides` が学習域の最大値を超える行が
2026 窓で 19.7% / 41.0% あると指摘された。**木モデルは学習域の外を定数で
外挿する**ので、そういう行の出力は「学習して検証した関数」の値ではない。

原因は累積生涯カウントの設計そのもの。カウンタは信頼下限 (2021) から
数え始めるので、**時間が経つほど大きくなる**。学習は 2022-2024、評価は
2026 なので、評価行は学習で一度も見ていない領域に入る。

単純な clip で隠すのは避ける。clip は「1,000 と 2,000 の違いが分からない」
状態をそのままにして、値だけ境界に寄せる。**数えている対象を問い直して
ローリング窓・率に置き換える**のが正しい。

usage:
    .venv64/Scripts/python.exe -m scripts.feature_domain_audit [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402

QUANTILES = (0, 1, 25, 50, 75, 99, 100)


def summarise(values: np.ndarray) -> dict:
    ok = values[np.isfinite(values)]
    if ok.size == 0:
        return {"n": int(values.size), "n_finite": 0}
    return {"n": int(values.size), "n_finite": int(ok.size),
            "nan_rate": float(1 - ok.size / values.size),
            **{f"p{q}": float(np.percentile(ok, q)) for q in QUANTILES}}


def out_of_range(values: np.ndarray, lo: float, hi: float) -> float:
    """学習域 [lo, hi] の外に出ている割合 (NaN は分母から外す)。"""
    ok = values[np.isfinite(values)]
    if ok.size == 0:
        return float("nan")
    return float(((ok < lo) | (ok > hi)).mean())


def run(features: list[str], splits: dict[str, list[dict]]) -> dict:
    """`splits` は {窓名: 行} 。最初の窓を学習域の基準とする。"""
    names = list(splits)
    base = names[0]
    arrays = {k: {f: np.array([r[f] for r in rows], dtype=float)
                  for f in features} for k, rows in splits.items()}

    rows_out: list[dict] = []
    for f in features:
        b = arrays[base][f]
        bf = b[np.isfinite(b)]
        lo, hi = (float(bf.min()), float(bf.max())) if bf.size else (np.nan, np.nan)
        rec = {"feature": f, "train_min": lo, "train_max": hi,
               "stats": {k: summarise(arrays[k][f]) for k in names},
               "out_of_train_range": {
                   k: out_of_range(arrays[k][f], lo, hi) for k in names}}
        rows_out.append(rec)
    import sqlite3

    from db import DB_PATH
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    meta = snapshot(conn)
    conn.close()
    return {"meta": {**meta, "base_split": base, "splits": names,
                     "n_rows": {k: len(v) for k, v in splits.items()}},
            "features": rows_out}


def print_report(out: dict, threshold: float = 0.01) -> None:
    names = out["meta"]["splits"]
    print(f"\n=== 学習域 ({out['meta']['base_split']}) の外に出ている割合 ===")
    for k, n in out["meta"]["n_rows"].items():
        print(f"  {k}: {n:,} 行")
    hdr = f"{'特徴':>26} {'学習 min':>10} {'学習 max':>10} " + " ".join(
        f"{k:>14}" for k in names)
    print()
    print(hdr)
    print("-" * len(hdr))
    worst = []
    for rec in out["features"]:
        rates = [rec["out_of_train_range"][k] for k in names]
        finite = [r for r in rates if r == r]      # 全 NaN なら空になる
        if finite and max(finite) > threshold:
            worst.append(rec)
        print(f"{rec['feature']:>26} {rec['train_min']:10.4g} "
              f"{rec['train_max']:10.4g} " + " ".join(
                  f"{r * 100:13.2f}%" for r in rates))
    print(f"\n域外率が {threshold * 100:.0f}% を超える特徴: "
          f"{len(worst)} 件: {[r['feature'] for r in worst] or 'なし'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None)
    ap.add_argument("--threshold", type=float, default=0.01)
    args = ap.parse_args()

    from scripts.fundamental_model import FEATURES, build_dataset

    splits = {}
    for name in ("train", "validation", "strategy_dev"):
        w = DATA_SPLIT[name]
        print(f"{name} ({w['from']}〜{w['to']}) を構築中 ...", flush=True)
        splits[name] = build_dataset(w["from"], w["to"])[0]

    out = run(list(FEATURES), splits)
    print_report(out, args.threshold)

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
