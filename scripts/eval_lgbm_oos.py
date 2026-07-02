"""OOS dataset キャッシュ上で複数 LGBM モデルの walk-forward 品質を比較する。

方針D Step3 (2026-07-02): 訓練窓 2021-2023 のモデルを OOS 窓 (2024-2025) で評価。
モデル間の「馬の順位付け能力」を分離して測る診断であり、production の
ベッティングスタック (calibrator/filter/Kelly) を通した backtest ではない。

評価対象:
- production-v5: predictor/_v5_backup/ (leg_code 込み 98 特徴)。**live 条件シミュレート**
  のため leg_code は常に unknown コード固定 (本番推論では未走馬の leg_code が空。
  歴史 DB の leg_code は post-race 値なので、素朴に評価するとリークの利益を与えて
  しまい不公正)。
- v5-clean-tuned: data/lgbm_cache/v5_clean_tuned_model.txt (97 特徴, optuna 済)
- v6-clean-tuned: predictor/lgbm_model.txt (112 特徴 F1/F2 入り, optuna 済)

指標: per-race 正規化確率での Brier / LogLoss / top1 的中率 / pooled AUC /
top-pick 単勝フラット ROI (payouts.tan_payout1 と結合)。

使い方:
  python -m scripts.eval_lgbm_oos --cache data/lgbm_cache/w2024_2025_v6feat.npz \
      --from 20240101 --to 20251231
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from scripts.train_lgbm import CATEGORICAL_MAPS, load_dataset_cache

PROJECT = Path(__file__).resolve().parent.parent


def _model_vectors(X: np.ndarray, cache_feats: list[str], model_feats: list[str]) -> np.ndarray:
    """キャッシュ列からモデルの特徴順で行列を組む。

    キャッシュに無い特徴 (leg_code) は categorical unknown コード
    (len(mapping) = 未知値と同じ) の定数列にする = live 配信条件のシミュレート。
    """
    cols = []
    n = X.shape[0]
    for f in model_feats:
        if f in cache_feats:
            cols.append(X[:, cache_feats.index(f)])
        elif f in CATEGORICAL_MAPS or f == "leg_code":
            # v5 の leg_code map は {"1","2","3","4","0"} の 5 値 → unknown = 5
            mapping = CATEGORICAL_MAPS.get(f) or {"1": 0, "2": 1, "3": 2, "4": 3, "0": 4}
            cols.append(np.full(n, float(len(mapping)), dtype=np.float32))
            print(f"  note: '{f}' はキャッシュに無いため unknown 定数 (live 条件)", file=sys.stderr)
        else:
            cols.append(np.full(n, np.nan, dtype=np.float32))
            print(f"  WARN: numeric '{f}' がキャッシュに無い → NaN 列", file=sys.stderr)
    return np.column_stack(cols)


def _per_race_normalize(raw: np.ndarray, groups: list[int]) -> np.ndarray:
    out = np.empty_like(raw)
    pos = 0
    for g in groups:
        seg = np.clip(raw[pos : pos + g], 1e-9, 1.0)
        s = seg.sum()
        out[pos : pos + g] = seg / s if s > 0 else seg
        pos += g
    return out


def _pooled_auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p)
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def evaluate(model_path: Path, model_feats: list[str], X, y, groups, cache_feats,
             payouts: list[int | None]) -> dict:
    import lightgbm as lgb
    booster = lgb.Booster(model_file=str(model_path))
    Xm = _model_vectors(X, cache_feats, model_feats)
    raw = booster.predict(Xm)
    p = _per_race_normalize(np.asarray(raw, dtype=np.float64), groups)

    brier = float(np.mean((p - y) ** 2))
    eps = 1e-15
    logloss = float(-np.mean(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1))))
    auc = _pooled_auc(y, p)

    hits = 0; bets = 0; returned = 0
    pos = 0
    for gi, g in enumerate(groups):
        seg = slice(pos, pos + g)
        top = pos + int(np.argmax(p[seg]))
        if payouts[gi] is not None:
            bets += 1
            if y[top] == 1:
                hits += 1
                returned += payouts[gi]  # 100 円あたり払戻
        pos += g
    return {
        "brier": brier, "logloss": logloss, "auc": auc,
        "top1_hit": hits / bets if bets else float("nan"),
        "flat_roi": returned / (bets * 100) if bets else float("nan"),
        "bets": bets,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", required=True)
    args = ap.parse_args()

    X, y, groups, cache_feats = load_dataset_cache(Path(args.cache), args.from_date, args.to_date)
    z = np.load(args.cache, allow_pickle=False)
    race_keys = [str(k) for k in z["race_keys"]]
    print(f"OOS: X={X.shape}, races={len(groups)}", file=sys.stderr)

    # 単勝払戻 (payouts.tan_payout1, 100 円あたり) を race_keys で引く
    payouts: list[int | None] = []
    with open_db() as conn:
        for k in race_keys:
            date_part, tc, kaiji, nichiji, rn = k.split("_")
            row = conn.execute(
                "SELECT tan_payout1 FROM payouts WHERE race_year=? AND race_month_day=? "
                "AND track_code=? AND kaiji=? AND nichiji=? AND race_num=?",
                (date_part[:4], date_part[4:], tc, kaiji, nichiji, rn),
            ).fetchone()
            payouts.append(row[0] if row and row[0] else None)
    print(f"payout ありレース: {sum(1 for x in payouts if x is not None)}/{len(payouts)}", file=sys.stderr)

    models = []
    v5b = PROJECT / "predictor" / "_v5_backup"
    if v5b.exists():
        feats = json.loads((v5b / "lgbm_features.json").read_text(encoding="utf-8"))["all_features"]
        models.append(("production-v5 (leg_code=unknown固定)", v5b / "lgbm_model.txt", feats))
    v5c = PROJECT / "data" / "lgbm_cache"
    if (v5c / "v5_clean_tuned_model.txt").exists():
        feats = json.loads((v5c / "v5_clean_tuned_meta.json").read_text(encoding="utf-8"))["features"]
        models.append(("v5-clean-tuned", v5c / "v5_clean_tuned_model.txt", feats))
    cur_meta = json.loads((PROJECT / "predictor" / "lgbm_meta.json").read_text(encoding="utf-8"))
    cur_feats = json.loads((PROJECT / "predictor" / "lgbm_features.json").read_text(encoding="utf-8"))["all_features"]
    models.append((f"current ({cur_meta['rule_version']})", PROJECT / "predictor" / "lgbm_model.txt", cur_feats))

    print(f"\n{'model':44} {'brier':>8} {'logloss':>8} {'auc':>7} {'top1':>7} {'flatROI':>8} {'bets':>6}")
    for name, path, feats in models:
        m = evaluate(path, feats, X, y, groups, cache_feats, payouts)
        print(f"{name:44} {m['brier']:8.5f} {m['logloss']:8.5f} {m['auc']:7.4f} "
              f"{m['top1_hit']:7.4f} {m['flat_roi']:8.4f} {m['bets']:6d}")
    return 0


if __name__ == "__main__":
    main()
