"""LightGBM 二値分類モデルを学習し、推論用アーティファクトを保存する。

usage:
    python -m scripts.train_lgbm --from 20210101 --to 20231231 --save --n-trials 100
    python -m scripts.train_lgbm --from 20210101 --to 20231231 --save --no-optuna

設計:
- 入力: predictor.features.compute_features(...) の dict 75 個 → flat vec
- ターゲット: y = 1 if confirmed_order == 1 else 0 (per (race, horse))
- 目的関数: binary (LightGBM)。EV 計算用に絶対確率が必要。lambdarank は採用しない。
- カテゴリ: track_code / current_bucket / surface_family / going / leg_code を
  LightGBM native categorical (int code) として渡す。
- リーク防止: compute_features 内で before_date 厳格カット (< race_date) 済。
- Optuna: 100-300 trial で hp 最適化、目的 = val Brier。CV は時系列 split。
- 保存: predictor/lgbm_model.txt / lgbm_features.json / lgbm_meta.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from config import PROJECT_ROOT
from db import open_db
from predictor.features import compute_features
from scripts.backtest import horses_for_race, list_races

logger = logging.getLogger(__name__)

# ===== Feature 定義 (推論時にも同じ順序で再現必須) =====

# Numeric features (None → np.nan 扱い)
NUMERIC_FEATURES: list[str] = [
    "past_count", "recent_avg_finish", "recent_avg_finish_rate", "recent_best_finish",
    "recent_top3_count", "recent_win_count", "last_finish", "days_since_last",
    "burden_delta", "current_starter_count", "current_race_level", "current_distance",
    "best_top3_race_level",
    "same_bucket_runs", "same_bucket_top3", "same_bucket_wins",
    "estimated_leg_samples",
    "class_level_runs", "class_level_wins", "class_level_top3",
    "class_condition_top3", "class_rise_points", "class_drop_points",
    "high_grade_close_loss", "high_grade_midfield_close", "recent_trend_delta",
    "same_track_type_runs", "same_track_type_wins", "same_track_type_top3",
    "same_distance_runs", "same_distance_top3",
    "same_course_runs", "same_course_wins", "same_course_top3",
    "same_course_distance_runs", "same_course_distance_top3",
    "same_going_runs", "same_going_top3",
    "best_final_3f", "avg_final_3f", "best_time_per_100m",
    "best_relative_time_diff", "best_final_3f_rank",
    "jockey_win_rate", "jockey_rides", "trainer_win_rate", "trainer_runs",
    "same_day_bias_score", "same_day_gate_bias_score",
    "sire_surface_top3_rate", "sire_surface_samples",
    "sire_distance_top3_rate", "sire_distance_samples",
    "dam_sire_surface_top3_rate", "dam_sire_surface_samples",
    "dam_sire_distance_top3_rate", "dam_sire_distance_samples",
    "sire_going_top3_rate", "sire_going_samples",
    "dam_sire_going_top3_rate", "dam_sire_going_samples",
    # Phase 1 MING (2026-05-13): JRA-VAN マイニング予想を baseline 信号として追加
    "mining_dm_rank", "mining_dm_time", "mining_tm_rank", "mining_tm_score",
    # Phase 6 Tier 1 (2026-05-14): 場 × エンティティの文脈特徴量
    "jockey_track_top3_rate", "jockey_track_samples",
    "trainer_track_top3_rate", "trainer_track_samples",
    "horse_track_top3_rate", "horse_track_samples",
    "sire_track_top3_rate", "sire_track_samples",
    "race_month",
    # Phase 6 Tier 2.3 (2026-05-16): rolling 統計 30/90 日 (時系列適応)
    "track_recent_30d_top3_rate", "track_recent_30d_samples", "track_recent_30d_avg_winning_pop",
    "track_recent_90d_top3_rate", "track_recent_90d_samples", "track_recent_90d_avg_winning_pop",
    "jockey_recent_30d_top3_rate", "jockey_recent_30d_samples",
    "jockey_recent_90d_top3_rate", "jockey_recent_90d_samples",
    "trainer_recent_30d_top3_rate", "trainer_recent_30d_samples",
    "horse_recent_90d_top3_rate", "horse_recent_90d_samples",
]

BOOLEAN_FEATURES: list[str] = [
    "leg_quality_available", "same_day_bias_available", "had_grade_run",
    "bloodline_data_available",
]

# Categorical (LightGBM native categorical = int code)
# 安定した辞書として固定 (推論時に同じ index を引けるよう)
CATEGORICAL_MAPS: dict[str, dict[str, int]] = {
    "current_bucket": {"sprint": 0, "mile": 1, "middle": 2, "long": 3},
    "current_track_code": {f"{i:02d}": i for i in range(1, 11)},
    "current_surface_family": {"turf": 0, "dirt": 1, "other": 2, "obstacle": 3},
    "current_going": {"1": 0, "2": 1, "3": 2, "4": 3, "0": 4},
    "leg_code": {"1": 0, "2": 1, "3": 2, "4": 3, "0": 4},
    "estimated_leg_code": {"1": 0, "2": 1, "3": 2, "4": 3, "": 4, "0": 4},
}
CATEGORICAL_FEATURES: list[str] = list(CATEGORICAL_MAPS.keys())

ALL_FEATURES: list[str] = NUMERIC_FEATURES + BOOLEAN_FEATURES + CATEGORICAL_FEATURES


def _encode_categorical(name: str, value) -> int:
    """カテゴリ値を int に変換。未知値は最後の index (= "その他") に。"""
    mapping = CATEGORICAL_MAPS[name]
    return mapping.get(str(value or ""), len(mapping))


def _feature_vector(feat: dict) -> list[float]:
    """compute_features 戻り値を ALL_FEATURES の順序で flat list 化。"""
    vec: list[float] = []
    for k in NUMERIC_FEATURES:
        v = feat.get(k)
        if v is None:
            vec.append(np.nan)
        elif isinstance(v, bool):
            vec.append(1.0 if v else 0.0)
        else:
            vec.append(float(v))
    for k in BOOLEAN_FEATURES:
        v = feat.get(k)
        vec.append(1.0 if v else 0.0)
    for k in CATEGORICAL_FEATURES:
        vec.append(float(_encode_categorical(k, feat.get(k))))
    return vec


def build_dataset(
    conn,
    from_date: str,
    to_date: str,
    jra_only: bool = True,
    progress_every: int = 500,
) -> tuple[np.ndarray, np.ndarray, list[int], list[str]]:
    """期間内全レース × 全馬を巡回し X (n×d), y (n,), groups (race_id 単位の馬数)。

    戻り: (X, y, groups, race_keys)
        groups: 各 race の馬数 (LightGBM ranker 互換、binary でも参考用)
        race_keys: 各 group の identifier (リーク確認用)
    """
    races = list_races(conn, from_date, to_date, jra_only=jra_only)
    started = time.time()
    X_rows: list[list[float]] = []
    y_list: list[int] = []
    groups: list[int] = []
    race_keys: list[str] = []
    feature_cache: dict = {}
    skipped_no_winner = 0
    for i, race in enumerate(races, 1):
        if progress_every and i % progress_every == 0:
            elapsed = time.time() - started
            rate = i / elapsed if elapsed else 0
            print(
                f"  [{i}/{len(races)}] {rate:.1f} races/s, "
                f"valid={len(groups)}, skipped={skipped_no_winner} ...",
                file=sys.stderr,
            )
        horses = horses_for_race(conn, race)
        if not horses:
            continue
        # 確定順位が無いレース (= 未確定 / 中止 / 旧 bootstrap 不完全) は学習対象外
        n_winners = sum(1 for h in horses if (h.get("confirmed_order") or 0) == 1)
        if n_winners == 0:
            skipped_no_winner += 1
            continue
        row_features: list[list[float]] = []
        row_labels: list[int] = []
        for h in horses:
            try:
                feat = compute_features(conn, h, race, cache=feature_cache)
            except Exception as e:
                logger.warning("compute_features failed: %s", e)
                continue
            row_features.append(_feature_vector(feat))
            row_labels.append(1 if (h.get("confirmed_order") or 0) == 1 else 0)
        if not row_features or sum(row_labels) == 0:
            skipped_no_winner += 1
            continue
        X_rows.extend(row_features)
        y_list.extend(row_labels)
        groups.append(len(row_features))
        race_keys.append(
            f"{race['race_year']}{race['race_month_day']}_{race['track_code']}_"
            f"{race['kaiji']}_{race['nichiji']}_{race['race_num']}"
        )
    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_list, dtype=np.int8)
    elapsed = time.time() - started
    print(
        f"  built dataset: X={X.shape}, y mean={y.mean():.4f}, races={len(groups)} "
        f"({elapsed:.1f}s)",
        file=sys.stderr,
    )
    return X, y, groups, race_keys


def _categorical_indexes() -> list[int]:
    """ALL_FEATURES 内でカテゴリ列の index list を返す (LightGBM 用)。"""
    offset = len(NUMERIC_FEATURES) + len(BOOLEAN_FEATURES)
    return [offset + i for i in range(len(CATEGORICAL_FEATURES))]


def train_lgbm(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    params: dict | None = None,
    num_boost_round: int = 2000,
    early_stopping_rounds: int = 50,
):
    """1 回の LightGBM 訓練。戻り: (model, best_iter, val_brier)。"""
    import lightgbm as lgb

    cat_idx = _categorical_indexes()
    train_set = lgb.Dataset(X_train, label=y_train, categorical_feature=cat_idx)
    val_set = lgb.Dataset(X_val, label=y_val, categorical_feature=cat_idx, reference=train_set)

    default_params = {
        "objective": "binary",
        "metric": ["binary_logloss"],
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 100,
        "feature_fraction": 0.85,
        "bagging_fraction": 0.85,
        "bagging_freq": 5,
        "lambda_l1": 0.1,
        "lambda_l2": 0.5,
        "verbose": -1,
        "feature_pre_filter": False,
    }
    merged = {**default_params, **(params or {})}
    model = lgb.train(
        merged,
        train_set,
        num_boost_round=num_boost_round,
        valid_sets=[val_set],
        callbacks=[
            lgb.early_stopping(early_stopping_rounds, verbose=False),
            lgb.log_evaluation(0),
        ],
    )
    preds = model.predict(X_val, num_iteration=model.best_iteration)
    brier = float(np.mean((preds - y_val) ** 2))
    return model, int(model.best_iteration or 0), brier


def optimize_with_optuna(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    n_trials: int = 100,
) -> dict:
    """Optuna でハイパーパラメータ探索。戻り: best_params。"""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 16, 64),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 50, 500),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 0.95),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.6, 0.95),
            "bagging_freq": trial.suggest_int("bagging_freq", 1, 7),
            "lambda_l1": trial.suggest_float("lambda_l1", 0.0, 5.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 5.0),
        }
        _, _, brier = train_lgbm(X_train, y_train, X_val, y_val, params=params)
        return brier

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    print(f"  Optuna best val Brier: {study.best_value:.6f}", file=sys.stderr)
    return study.best_params


def time_split_indices(race_groups: list[int], val_fraction: float = 0.2) -> tuple[slice, slice]:
    """時系列を保ったまま train/val split (リーク防止)。

    race_groups の末尾 val_fraction を validation に。
    戻り: (train_slice, val_slice) → X / y への適用用。
    """
    n_races = len(race_groups)
    val_start_race = int(n_races * (1 - val_fraction))
    train_end = sum(race_groups[:val_start_race])
    return slice(0, train_end), slice(train_end, None)


def save_artifacts(
    model, params: dict, args, n_train: int, n_val: int,
    train_brier: float, val_brier: float, val_logloss: float,
    feature_importance: dict | None = None,
) -> tuple[Path, Path, Path]:
    out_dir = PROJECT_ROOT / "predictor"
    model_path = out_dir / "lgbm_model.txt"
    features_path = out_dir / "lgbm_features.json"
    meta_path = out_dir / "lgbm_meta.json"

    model.save_model(str(model_path))
    features_path.write_text(
        json.dumps(
            {
                "numeric": NUMERIC_FEATURES,
                "boolean": BOOLEAN_FEATURES,
                "categorical": CATEGORICAL_FEATURES,
                "categorical_maps": CATEGORICAL_MAPS,
                "all_features": ALL_FEATURES,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    meta_path.write_text(
        json.dumps(
            {
                "trained_from": args.from_date,
                "trained_to": args.to_date,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "rule_version": args.rule_version,
                "n_train_rows": n_train,
                "n_val_rows": n_val,
                "train_brier": train_brier,
                "val_brier": val_brier,
                "val_logloss": val_logloss,
                "params": params,
                "best_iteration": int(model.best_iteration or 0),
                "feature_importance": feature_importance,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return model_path, features_path, meta_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    ap.add_argument("--rule-version", default="lgbm-v1")
    ap.add_argument("--n-trials", type=int, default=100,
                    help="Optuna trials. 0 or --no-optuna で default params を使用")
    ap.add_argument("--no-optuna", action="store_true",
                    help="Optuna を skip し default params で 1 回だけ学習")
    ap.add_argument("--val-fraction", type=float, default=0.2,
                    help="末尾を validation に割り当てる割合")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    print(f"=== build dataset {args.from_date} - {args.to_date} ===", file=sys.stderr)
    with open_db() as conn:
        X, y, groups, _ = build_dataset(conn, args.from_date, args.to_date)
    if len(X) == 0:
        print("ERROR: empty dataset", file=sys.stderr)
        return 1

    train_sl, val_sl = time_split_indices(groups, val_fraction=args.val_fraction)
    X_train, y_train = X[train_sl], y[train_sl]
    X_val, y_val = X[val_sl], y[val_sl]
    print(f"  train: {X_train.shape}, val: {X_val.shape}", file=sys.stderr)

    # Optuna or default
    if args.no_optuna or args.n_trials <= 0:
        params: dict = {}
    else:
        print(f"=== Optuna {args.n_trials} trials ===", file=sys.stderr)
        params = optimize_with_optuna(X_train, y_train, X_val, y_val, n_trials=args.n_trials)

    print("=== final training ===", file=sys.stderr)
    model, best_iter, val_brier = train_lgbm(X_train, y_train, X_val, y_val, params=params)
    val_preds = model.predict(X_val, num_iteration=model.best_iteration)
    eps = 1e-15
    val_logloss = float(
        -np.mean(
            y_val * np.log(np.clip(val_preds, eps, 1 - eps))
            + (1 - y_val) * np.log(np.clip(1 - val_preds, eps, 1 - eps))
        )
    )
    train_preds = model.predict(X_train, num_iteration=model.best_iteration)
    train_brier = float(np.mean((train_preds - y_train) ** 2))

    print(f"  train Brier: {train_brier:.6f}", file=sys.stderr)
    print(f"  val   Brier: {val_brier:.6f}", file=sys.stderr)
    print(f"  val LogLoss: {val_logloss:.6f}", file=sys.stderr)
    print(f"  best_iter:   {best_iter}", file=sys.stderr)

    feat_imp = {
        ALL_FEATURES[i]: int(v)
        for i, v in enumerate(model.feature_importance(importance_type="gain"))
    }
    feat_imp_sorted = dict(sorted(feat_imp.items(), key=lambda x: -x[1])[:30])

    if args.save:
        mp, fp, jp = save_artifacts(
            model, params, args, len(X_train), len(X_val),
            train_brier, val_brier, val_logloss,
            feature_importance=feat_imp_sorted,
        )
        print(f"  saved: {mp.name}, {fp.name}, {jp.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
