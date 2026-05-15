"""LGBM モデルの信号弱点を SHAP / partial dependence で分析。

usage:
    .venv64\\Scripts\\python.exe -m scripts.analyze_lgbm --from 20240101 --to 20251231
    .venv64\\Scripts\\python.exe -m scripts.analyze_lgbm --shap-only --sample-size 5000

出力:
- 各 feature の平均 |SHAP| ranking (= 重要度の絶対指標)
- feature_importance vs SHAP の乖離 (= モデルが「使ってる」と「効いてる」のズレ)
- prediction error が大きいサンプルの SHAP 内訳 (信号弱点の同定)

依存: LightGBM 内蔵 SHAP (`pred_contrib=True`) を使うので追加 install 不要。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from db import open_db
from predictor.features import compute_features
from scripts.backtest import horses_for_race, list_races
from scripts.train_lgbm import (
    ALL_FEATURES,
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    _feature_vector,
)


def build_eval_dataset(
    conn,
    from_date: str,
    to_date: str,
    sample_size: int | None = None,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """評価用 (X, y) を抽出。sample_size で乱数 sampling。"""
    rng = np.random.default_rng(seed)
    races = list_races(conn, from_date, to_date, jra_only=True)
    X_rows: list[list[float]] = []
    y_list: list[int] = []
    cache: dict = {}
    for race in races:
        horses = horses_for_race(conn, race)
        if not horses:
            continue
        if not any((h.get("confirmed_order") or 0) == 1 for h in horses):
            continue
        for h in horses:
            try:
                feat = compute_features(conn, h, race, cache=cache)
            except Exception:
                continue
            X_rows.append(_feature_vector(feat))
            y_list.append(1 if (h.get("confirmed_order") or 0) == 1 else 0)
    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_list, dtype=np.int8)
    if sample_size and len(X) > sample_size:
        idx = rng.choice(len(X), sample_size, replace=False)
        X = X[idx]
        y = y[idx]
    return X, y


def compute_shap_values(model, X: np.ndarray) -> np.ndarray:
    """LightGBM 内蔵 SHAP (predict(pred_contrib=True))。

    戻り shape: (n_samples, n_features + 1) where 末尾は bias。
    """
    sv = model.predict(X, pred_contrib=True)
    return np.asarray(sv)


def report_global_importance(
    model,
    shap_values: np.ndarray,
    feature_importance_gain: dict,
) -> list[dict]:
    """SHAP と gain importance を並べて比較し、乖離が大きい feature を強調。"""
    n_features = len(ALL_FEATURES)
    abs_shap = np.abs(shap_values[:, :n_features])
    mean_abs_shap = abs_shap.mean(axis=0)
    median_abs_shap = np.median(abs_shap, axis=0)

    # gain importance を 0-100 に正規化
    total_gain = sum(feature_importance_gain.values()) or 1
    gain_pct = {k: v / total_gain * 100 for k, v in feature_importance_gain.items()}

    # mean_abs_shap も 0-100 に正規化
    total_shap = mean_abs_shap.sum() or 1
    shap_pct = mean_abs_shap / total_shap * 100

    rows: list[dict] = []
    for i, fname in enumerate(ALL_FEATURES):
        rows.append({
            "feature": fname,
            "mean_abs_shap": round(float(mean_abs_shap[i]), 6),
            "median_abs_shap": round(float(median_abs_shap[i]), 6),
            "shap_pct": round(float(shap_pct[i]), 3),
            "gain_pct": round(gain_pct.get(fname, 0), 3),
            "gain_minus_shap": round(gain_pct.get(fname, 0) - float(shap_pct[i]), 3),
        })
    rows.sort(key=lambda r: -r["mean_abs_shap"])
    return rows


def report_weak_signals(rows: list[dict], threshold_pct: float = 0.5) -> list[dict]:
    """SHAP が小さい (= 効いてない) のに gain が大きい feature を弱信号として返す。

    また SHAP が大きいのに gain が小さい feature も「過小評価信号」として返す。
    """
    weak = []
    overhyped = []
    for r in rows:
        gms = r["gain_minus_shap"]
        if gms > threshold_pct:
            overhyped.append({**r, "category": "overhyped (split used but predicts little)"})
        elif gms < -threshold_pct:
            weak.append({**r, "category": "underused (predicts much but few splits)"})
    return weak + overhyped


def partial_dependence(
    model,
    X: np.ndarray,
    feature_idx: int,
    n_points: int = 20,
) -> list[tuple[float, float]]:
    """ある feature の平均予測値を変動範囲で plot 用に算出。

    戻り: [(feature_value, avg_predicted_probability), ...]
    """
    feature_col = X[:, feature_idx]
    valid_col = feature_col[~np.isnan(feature_col)]
    if len(valid_col) == 0:
        return []
    grid = np.linspace(np.quantile(valid_col, 0.05), np.quantile(valid_col, 0.95), n_points)
    results: list[tuple[float, float]] = []
    sample_size = min(2000, len(X))
    idx = np.random.default_rng(42).choice(len(X), sample_size, replace=False)
    sample = X[idx].copy()
    for v in grid:
        sample[:, feature_idx] = v
        pred = model.predict(sample)
        results.append((float(v), float(pred.mean())))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default="20240101")
    ap.add_argument("--to", dest="to_date", default="20251231")
    ap.add_argument(
        "--sample-size", type=int, default=10000,
        help="SHAP 計算サンプル数 (default 10000、メモリ節約)",
    )
    ap.add_argument(
        "--top-pd", type=int, default=5,
        help="partial dependence を計算する top feature 数 (mean |SHAP| 順)",
    )
    ap.add_argument(
        "--out",
        default="data/backtest/lgbm_shap_analysis.json",
        help="JSON 出力ファイル",
    )
    args = ap.parse_args()

    import lightgbm as lgb
    from config import PROJECT_ROOT

    model_path = PROJECT_ROOT / "predictor" / "lgbm_model.txt"
    if not model_path.exists():
        print("ERROR: lgbm_model.txt not found", file=sys.stderr)
        return 1
    model = lgb.Booster(model_file=str(model_path))

    meta_path = PROJECT_ROOT / "predictor" / "lgbm_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    feature_importance = meta.get("feature_importance") or {}

    print(f"=== build eval dataset {args.from_date}-{args.to_date} ===", file=sys.stderr)
    with open_db() as conn:
        X, y = build_eval_dataset(
            conn, args.from_date, args.to_date, sample_size=args.sample_size,
        )
    print(f"  shape: X={X.shape}, y_mean={y.mean():.4f}", file=sys.stderr)

    print("=== computing SHAP values ===", file=sys.stderr)
    sv = compute_shap_values(model, X)
    print(f"  shap shape: {sv.shape}", file=sys.stderr)

    rows = report_global_importance(model, sv, feature_importance)
    weak = report_weak_signals(rows, threshold_pct=0.5)

    print("=== partial dependence on top {} ===".format(args.top_pd), file=sys.stderr)
    pd_results: dict[str, list] = {}
    for r in rows[:args.top_pd]:
        idx = ALL_FEATURES.index(r["feature"])
        pd_results[r["feature"]] = partial_dependence(model, X, idx)

    output = {
        "trained_from": meta.get("trained_from"),
        "trained_to": meta.get("trained_to"),
        "eval_from": args.from_date,
        "eval_to": args.to_date,
        "n_samples": len(X),
        "global_importance_rank": rows,
        "weak_signals": weak,
        "partial_dependence": pd_results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=== TOP 15 features by mean |SHAP| ===")
    for r in rows[:15]:
        mark = ""
        if r["gain_minus_shap"] > 0.5:
            mark = "  [overhyped: split>predict]"
        elif r["gain_minus_shap"] < -0.5:
            mark = "  [underused: predict>split]"
        print(
            f"  {r['feature']:30s} SHAP={r['shap_pct']:>5.2f}%% "
            f"gain={r['gain_pct']:>5.2f}%% "
            f"diff={r['gain_minus_shap']:>+6.2f}%%{mark}"
        )
    print()
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
