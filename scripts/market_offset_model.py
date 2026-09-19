"""市場オフセットモデル (憲法 Phase 0.5-4A)。

    logit(P_true) = logit(P_market) + AI 補正

LightGBM の `init_score = logit(P_market)` で学習する。教師は実際の着順のみ。
**最終市場は教師にも特徴にも使わない。**

## 事前登録 (docs/PHASE05_PREREG.md) からの変更は一切しない

特徴 30 / 学習期間 / モデル / ハイパーパラメータ / 主分析条件は
`scripts/fundamental_model.py` と同一。**0.5-3 から 1 つも変えない。**
これは「現在の特徴セットでは市場を超えられない」という仮説を正式に検証する
実験であって、勝たせるための実験ではない。

## 学習時の市場価格について (2026-09-19 に訂正)

`odds_snapshots` は 2026-05 以降しか無い。学習期間 (2021-2025) には T−10 の
市場価格が存在しないので、`horse_races.win_odds` を使う。

**当初この列を「確定オッズではない (47.8% 不一致)」と書いたが、それは誤り。**
47.8% 不一致は **2026 年だけ** の現象で、fresh odds 取得 (0B30/0B31) が
発走前の値を後から書いているために起きる。年別の一致率 (勝ち馬 vs 確定単勝払戻):

    2021 99.5% / 2022 99.8% / 2023 99.8% / 2024 99.7% / 2025 99.7% / 2026 77.4%

しかも 2021-2025 の不一致は **全件が同着** (払戻が半額になる) なので、
実質 **一致率 100%**。つまり学習の init_score は **確定した最終オッズそのもの**。

これは skew の向きを逆にする。同一 626 レースで測ると:

    win_odds implied の LogLoss 0.21110  <  T-10 implied 0.21351
    差 -0.00241、95% 区間 [-0.00405, -0.00097] (0 を含まない)

**学習の基準市場は運用の基準市場より強い。** モデルが学ぶ残差
`logit(P_true) - logit(P_final)` には T-10 から最終までの遅い資金の情報が
含まれない。したがって:

- **金額 (回収率) については負の結果をそのまま読める。** 払戻は確定オッズで
  決まるので、確定市場に足せない特徴は原理的に回収率エッジを作れない
- **「T-10 市場に足せるか」は、この設計では検定していない。** T-10 固有の
  非効率 (0.5-3 の先読み +0.169 に対応する成分) は原理的に学べない

usage:
    .venv64/Scripts/python.exe -m scripts.market_offset_model --fit
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT, guard_analysis_window  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.feature_manifest import assert_no_market_features  # noqa: E402
from predictor.provenance import snapshot  # noqa: E402
from scripts.fundamental_model import (  # noqa: E402
    FEATURES,
    TRUST_FLOOR_YEAR,
    build_dataset,
)

MODEL_PATH = (Path(__file__).resolve().parent.parent / "predictor"
              / "market_offset_model.txt")
META_PATH = MODEL_PATH.with_suffix(".meta.json")

# 0.5-3 と同一。事前登録で「変更禁止」と宣言した項目。
PARAMS = {
    "objective": "binary", "learning_rate": 0.03, "num_leaves": 63,
    "min_child_samples": 100, "bagging_fraction": 0.8, "bagging_freq": 1,
    "feature_fraction": 0.8, "seed": 20260918, "verbose": -1,
}
NUM_BOOST_ROUND = 2000
EARLY_STOPPING = 100


def logit(p) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def training_market(conn: sqlite3.Connection, from_year: str,
                    to_date: str) -> dict[tuple[str, str], float]:
    """学習用の市場確率。`(race_id, 馬番) → レース内で正規化した確率`。

    **これは確定オッズではない** (docstring 冒頭の注意を参照)。
    """
    rows = conn.execute(
        """SELECT (race_year||'-'||race_month_day||'-'||track_code||'-'||kaiji
                   ||'-'||nichiji||'-'||race_num) rid, horse_num, win_odds
             FROM horse_races
            WHERE race_year >= ? AND (race_year||race_month_day) <= ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
              AND horse_num NOT IN ('', '00') AND win_odds > 0""",
        (from_year, to_date)).fetchall()
    by_race: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for rid, hn, odds in rows:
        by_race[rid].append((str(hn).strip(), 10.0 / odds))
    out: dict[tuple[str, str], float] = {}
    for rid, items in by_race.items():
        tot = sum(v for _, v in items)
        if tot <= 0:
            continue
        for hn, v in items:
            out[(rid, hn)] = v / tot
    return out


def payout_agreement(conn: sqlite3.Connection, from_year: str,
                     to_date: str, sample: int = 4000) -> float:
    """勝ち馬の `win_odds` が確定単勝払戻と一致する割合。

    **この列の意味が期間によって変わる**ので、学習前に必ず測る。2026 年は
    fresh odds 取得が発走前の値を後から書くため一致率が 77% まで落ちる。
    同じ列を確定オッズのつもりで学習に使うと、気づかないまま意味が変わる。
    同着は払戻が半額になるので一致しない。除外せず分母に入れる (保守的)。
    """
    rows = conn.execute(
        """SELECT h.horse_num hn, h.win_odds o,
                  p.tan_horse_num1 h1, p.tan_payout1 p1,
                  p.tan_horse_num2 h2, p.tan_payout2 p2
             FROM horse_races h
             JOIN payouts p ON p.race_year=h.race_year
              AND p.race_month_day=h.race_month_day AND p.track_code=h.track_code
              AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji AND p.race_num=h.race_num
              AND p.data_div='2'
            WHERE h.confirmed_order=1 AND h.race_year >= ?
              AND (h.race_year||h.race_month_day) <= ?
              AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
            LIMIT ?""", (from_year, to_date, sample)).fetchall()
    ok = tot = 0
    for r in rows:
        pay = None
        for hc, pc in (("h1", "p1"), ("h2", "p2")):
            if (str(r[hc]).strip().zfill(2) == str(r["hn"]).strip().zfill(2)
                    and r[pc]):
                pay = r[pc]
        if not pay:
            continue
        tot += 1
        if abs(pay / 100.0 - r["o"] / 10.0) < 1e-6:
            ok += 1
    return ok / tot if tot else 0.0


def attach_market(data: list[dict], market: dict[tuple[str, str], float],
                  stats: Counter) -> list[dict]:
    """市場価格が取れた行だけ残す。

    取れない行 (2021-2025 の競走除外馬など、`win_odds=0`) は
    `init_score` が定義できないので学習に使えない。**黙って落とさず数える。**
    """
    kept = []
    for d in data:
        p = market.get((d["race_id"], d["horse_num"]))
        if p is None:
            stats["skip_no_market_price"] += 1
            continue
        d["p_market"] = p
        kept.append(d)
    return kept


def _matrix(data: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X = np.array([[d[c] for c in FEATURES] for d in data], dtype=float)
    y = np.array([d["won"] for d in data])
    init = logit([d["p_market"] for d in data])
    return X, y, init


def fit() -> dict:
    """2021-2023 で学習し、2024-2025 で早期停止する。2026 は一切見ない。"""
    import lightgbm as lgb

    assert_no_market_features(
        FEATURES, source_module=Path(__file__).parent / "fundamental_model.py")
    tr_from, tr_to = DATA_SPLIT["train"]["from"], DATA_SPLIT["train"]["to"]
    va_from, va_to = DATA_SPLIT["validation"]["from"], DATA_SPLIT["validation"]["to"]
    # 市場価格と一致率の検査は着順を読むので、ここでも封印の門を通す。
    # 学習窓は封印窓より前なので現状は素通りだが、窓を延ばしたときに抜けない
    # ようにする (呼び出し側の作法に任せると必ず抜ける)。
    tr_from, tr_to, _ = guard_analysis_window(
        tr_from, tr_to, context="market_offset_model.fit/train")
    va_from, va_to, _ = guard_analysis_window(
        va_from, va_to, context="market_offset_model.fit/validation")

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    market = training_market(conn, TRUST_FLOOR_YEAR, va_to)
    agreement = payout_agreement(conn, TRUST_FLOOR_YEAR, va_to)
    print(f"学習用の市場価格 {len(market):,} 頭ぶん "
          f"(確定払戻との一致率 {agreement:.4f})", flush=True)
    if agreement < 0.99:
        conn.close()
        raise ValueError(
            f"学習用の市場価格が確定払戻と {agreement:.1%} しか一致しない。"
            "この列の意味が変わっている (2026 のように発走前の値が"
            "書かれている可能性)。意味を確かめてから学習すること。")

    stats: Counter = Counter()
    print(f"学習データ構築 {tr_from}〜{tr_to} ...", flush=True)
    train = attach_market(build_dataset(tr_from, tr_to)[0], market, stats)
    print(f"  {len(train):,} 頭", flush=True)
    print(f"検証データ構築 {va_from}〜{va_to} ...", flush=True)
    valid = attach_market(build_dataset(va_from, va_to)[0], market, stats)
    print(f"  {len(valid):,} 頭 (市場価格が無く除外 {stats['skip_no_market_price']:,})",
          flush=True)

    Xtr, ytr, itr = _matrix(train)
    Xva, yva, iva = _matrix(valid)
    dtrain = lgb.Dataset(Xtr, label=ytr, init_score=itr,
                         feature_name=list(FEATURES))
    dvalid = lgb.Dataset(Xva, label=yva, init_score=iva, reference=dtrain,
                         feature_name=list(FEATURES))
    booster = lgb.train(
        PARAMS, dtrain, num_boost_round=NUM_BOOST_ROUND,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)])
    booster.save_model(str(MODEL_PATH), num_iteration=booster.best_iteration)

    # 検証での確認 (合否には使わない。早期停止が効いているかの目視用)
    margin = booster.predict(Xva, num_iteration=booster.best_iteration,
                             raw_score=True)
    conn.close()
    from predictor.evaluation import log_loss
    p_off = 1.0 / (1.0 + np.exp(-(iva + margin)))
    meta = {**snapshot(conn), "features": FEATURES, "params": PARAMS,
            "training_market_payout_agreement": agreement,
            "train": [tr_from, tr_to], "validation": [va_from, va_to],
            "n_train": len(train), "n_valid": len(valid),
            "excluded": dict(stats),
            "best_iteration": int(booster.best_iteration),
            "validation_log_loss_market_only": log_loss(list(yva),
                                                        list(1 / (1 + np.exp(-iva)))),
            "validation_log_loss_offset": log_loss(list(yva), list(p_off)),
            "training_market_source":
                "horse_races.win_odds (2021-2025 では確定オッズ。同着を除き一致率 100%)",
            "market_features": 0}
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    print(f"\n保存: {MODEL_PATH.name} (best_iteration={meta['best_iteration']})")
    print(f"  検証 LogLoss 市場のみ {meta['validation_log_loss_market_only']:.5f}"
          f" → オフセット後 {meta['validation_log_loss_offset']:.5f}")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fit", action="store_true")
    args = ap.parse_args()
    if args.fit:
        fit()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
