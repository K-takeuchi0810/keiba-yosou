"""F3 Phase 0-0: post-race leak 3-channel quantification.

This is an experiment-only evaluator.  It never overwrites production model
artifacts and refuses to evaluate the sealed window (2026-10-01 or later).

Usage:
    .venv64/Scripts/python.exe -m scripts.f3_phase0_0_eval
    .venv64/Scripts/python.exe -m scripts.f3_phase0_0_eval --skip-oos
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import numpy as np

from config import PROJECT_ROOT
from db import open_db_readonly
from predictor import is_tentative, predict_race
from predictor.filter import is_buy_candidate
from scripts.backtest import get_payout_with_presence, horses_for_race, list_races
from scripts.train_lgbm import CATEGORICAL_MAPS, time_split_indices


TRAIN_FROM = "20210101"
TRAIN_TO = "20231231"
OOS_FROM = "20260101"
OOS_TO = "20260614"
SEALED_START = "20261001"
VAL_FRACTION = 0.20
FIXED_SEED = 20260720
BOOTSTRAP_SEED = 20260720
BOOTSTRAP_SAMPLES = 10_000

BLOCKED_FEATURES = (
    "same_day_bias_score",
    "leg_quality_available",
    "same_day_bias_available",
)
LIVE_VALUES = {
    "same_day_bias_score": 0.0,
    "leg_quality_available": 0.0,
    "same_day_bias_available": 0.0,
}

DEFAULT_CACHE = PROJECT_ROOT / "data" / "lgbm_cache" / "w2021_2023_v6feat_fixed.npz"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "f3_phase0_0"
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "F3_phase0_0_result.md"
PHASE_METRICS_PATH = DEFAULT_OUTPUT / "metrics.json"
PAIRED_OOS_OUTPUT = DEFAULT_OUTPUT / "paired_oos.json"
PAIRED_OOS_REPORT = PROJECT_ROOT / "docs" / "F3_phase0_0b_result.md"
OOS_REFERENCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "backtest"
    / "20260628_131245_tan_p25-pop-0-0-0-oos-rerun-filtered.json"
)
PRODUCTION_ARTIFACTS = (
    PROJECT_ROOT / "predictor" / "lgbm_model.txt",
    PROJECT_ROOT / "predictor" / "lgbm_features.json",
    PROJECT_ROOT / "predictor" / "lgbm_meta.json",
    PROJECT_ROOT / "predictor" / "calibrator.json",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact_hashes() -> dict[str, str]:
    return {str(p.relative_to(PROJECT_ROOT)): _sha256(p) for p in PRODUCTION_ARTIFACTS}


def _guard_unsealed(from_date: str, to_date: str) -> None:
    if len(from_date) != 8 or len(to_date) != 8 or not (from_date + to_date).isdigit():
        raise ValueError("evaluation dates must be YYYYMMDD")
    if from_date > to_date:
        raise ValueError("evaluation from_date must be <= to_date")
    if from_date >= SEALED_START or to_date >= SEALED_START:
        raise ValueError(
            f"sealed holdout access denied: requested={from_date}-{to_date}, "
            f"sealed_start={SEALED_START}"
        )


def _require_project_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the project: {resolved}") from exc
    return resolved


def _guard_cache_race_keys(race_keys: list[str]) -> None:
    if not race_keys or any(len(key) < 8 or not key[:8].isdigit() for key in race_keys):
        raise ValueError("training cache contains an invalid race key")
    first_date = min(key[:8] for key in race_keys)
    last_date = max(key[:8] for key in race_keys)
    _guard_unsealed(first_date, last_date)
    if first_date < TRAIN_FROM or last_date > TRAIN_TO:
        raise ValueError(
            f"training cache race dates exceed preregistered window: {first_date}-{last_date}"
        )


def _load_cache(path: Path) -> tuple[np.ndarray, np.ndarray, list[int], list[str], list[str]]:
    z = np.load(path, allow_pickle=False)
    window = [str(x) for x in z["window"]]
    if window != [TRAIN_FROM, TRAIN_TO]:
        raise ValueError(f"training cache window mismatch: {window}")
    features = [str(x) for x in z["features"]]
    if len(features) != 112 or any(name not in features for name in BLOCKED_FEATURES):
        raise ValueError("training cache does not contain the preregistered 112-feature schema")
    race_keys = [str(x) for x in z["race_keys"]]
    _guard_cache_race_keys(race_keys)
    return z["X"], z["y"], [int(x) for x in z["groups"]], features, race_keys


def _zero_live_channels(X: np.ndarray, features: list[str]) -> np.ndarray:
    out = np.array(X, copy=True)
    for name, value in LIVE_VALUES.items():
        out[:, features.index(name)] = value
    return out


def _pooled_auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p, kind="mergesort")
    sorted_p = p[order]
    ranks = np.empty(len(p), dtype=np.float64)
    start = 0
    while start < len(p):
        end = start + 1
        while end < len(p) and sorted_p[end] == sorted_p[start]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    positives = y == 1
    n1 = int(positives.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[positives].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _top1_hit_rate(y: np.ndarray, p: np.ndarray, groups: list[int]) -> float:
    pos = 0
    hits = 0
    valid = 0
    for group_size in groups:
        segment = slice(pos, pos + group_size)
        if int(y[segment].sum()) > 0:
            valid += 1
            hits += int(y[pos + int(np.argmax(p[segment]))] == 1)
        pos += group_size
    if pos != len(y):
        raise ValueError(f"group rows {pos} != labels {len(y)}")
    return hits / valid if valid else float("nan")


def _classification_metrics(y: np.ndarray, p: np.ndarray, groups: list[int]) -> dict[str, float]:
    clipped = np.clip(np.asarray(p, dtype=np.float64), 1e-15, 1 - 1e-15)
    return {
        "auc": _pooled_auc(y, clipped),
        "brier": float(np.mean((clipped - y) ** 2)),
        "logloss": float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))),
        "top1_hit_rate": _top1_hit_rate(y, clipped, groups),
    }


def _categorical_indexes(features: list[str]) -> list[int]:
    return [i for i, name in enumerate(features) if name in CATEGORICAL_MAPS]


def _training_params(meta: dict) -> dict:
    params = {
        "objective": "binary",
        "metric": ["binary_logloss"],
        "verbose": -1,
        "feature_pre_filter": False,
        **meta["params"],
        "seed": FIXED_SEED,
        "bagging_seed": FIXED_SEED,
        "feature_fraction_seed": FIXED_SEED,
        "data_random_seed": FIXED_SEED,
        "deterministic": True,
        "force_col_wise": True,
    }
    return params


def _train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    features: list[str],
    params: dict,
    rounds: int,
):
    import lightgbm as lgb

    dataset = lgb.Dataset(
        X_train,
        label=y_train,
        categorical_feature=_categorical_indexes(features),
        feature_name=features,
        free_raw_data=False,
    )
    return lgb.train(params, dataset, num_boost_round=rounds, callbacks=[lgb.log_evaluation(0)])


def _direct_diff(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    return {name: float(left[name] - right[name]) for name in left}


def _save_feature_definition(path: Path, features: list[str], source_definition: dict) -> None:
    numeric = [x for x in source_definition.get("numeric", []) if x in features]
    boolean = [x for x in source_definition.get("boolean", []) if x in features]
    categorical = [x for x in source_definition.get("categorical", []) if x in features]
    payload = {
        "numeric": numeric,
        "boolean": boolean,
        "categorical": categorical,
        "categorical_maps": {
            key: value
            for key, value in source_definition.get("categorical_maps", {}).items()
            if key in categorical
        },
        "all_features": features,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_reference() -> dict:
    data = json.loads(OOS_REFERENCE_PATH.read_text(encoding="utf-8"))
    if [data.get("from_date"), data.get("to_date")] != [OOS_FROM, OOS_TO]:
        raise ValueError("historical OOS reference window changed")
    return data


@contextmanager
def _temporary_environment(overrides: dict[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _block_bootstrap_roi(
    daily_returns: dict[str, list[int]],
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> list[float]:
    days = sorted(daily_returns)
    if not days:
        return [float("nan"), float("nan")]
    stakes = np.asarray([100 * len(daily_returns[day]) for day in days], dtype=np.float64)
    returns = np.asarray([sum(daily_returns[day]) for day in days], dtype=np.float64)
    rng = np.random.default_rng(seed)
    values = np.empty(samples, dtype=np.float64)
    for i in range(samples):
        idx = rng.integers(0, len(days), len(days))
        stake = float(stakes[idx].sum())
        values[i] = float(returns[idx].sum() / stake) if stake else math.nan
    return [float(np.nanpercentile(values, 2.5)), float(np.nanpercentile(values, 97.5))]


def _evaluate_oos(
    model,
    feature_definition: dict,
    reference: dict,
    bootstrap_samples: int,
    *,
    include_ledger: bool = False,
    model_label: str = "treatment",
) -> dict:
    """Run the treatment booster through the historical buy-only stack, read-only."""
    _guard_unsealed(OOS_FROM, OOS_TO)
    import predictor.ml_model as ml_model
    import predictor.rules as rules

    fixed_filter = dict(reference["buy_filter"])
    old_calibrator = PROJECT_ROOT / "predictor" / "calibrator.json.bak"
    if not old_calibrator.exists():
        raise FileNotFoundError(
            "historical calibrator predictor/calibrator.json.bak is required for the fixed OOS"
        )

    original_loader = ml_model.load_lgbm
    original_calibrator_path = rules.CALIBRATOR_PATH
    original_calibrator_cache = rules._CALIBRATOR_CACHE
    ml_model.load_lgbm = lambda: (
        model,
        feature_definition,
        {"rule_version": f"f3-phase0-0-{model_label}"},
    )
    rules.CALIBRATOR_PATH = old_calibrator
    rules._CALIBRATOR_CACHE = None

    env = {
        "PRED_W_POPULARITY_FIRST": "0",
        "PRED_W_POPULARITY_SECOND": "0",
        "PRED_W_POPULARITY_THIRD": "0",
        "PRED_BLEND_W_RULE": "0.5",
        "PRED_BLEND_MODE": "linear",
        "PRED_DISABLE_LGBM": None,
        "PRED_DISABLE_CALIBRATOR": None,
        "PRED_DISABLE_BLEND": None,
        "PRED_DISABLE_DISCOUNT": None,
    }
    daily_returns: dict[str, list[int]] = defaultdict(list)
    ledger: list[dict] = []
    races_total = 0
    races_scored = 0
    feature_cache: dict = {}
    started = time.time()
    try:
        with _temporary_environment(env), open_db_readonly() as conn:
            races = list_races(conn, OOS_FROM, OOS_TO, jra_only=True, require_confirmed=True)
            races_total = len(races)
            for i, race in enumerate(races, start=1):
                horses = horses_for_race(conn, race)
                if not horses:
                    continue
                preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
                tentative = is_tentative(preds)
                top = next((p for p in preds if p.rank == 1 and p.mark), None)
                if top is None:
                    continue
                races_scored += 1
                top_horse = next((h for h in horses if h.get("horse_num") == top.horse_num), None)
                if top_horse is None:
                    continue
                is_bet = is_buy_candidate(
                    top, top_horse, tentative, race=race, filter_spec=fixed_filter
                )
                payout = 0
                present = False
                if include_ledger or is_bet:
                    payout, present = get_payout_with_presence(
                        conn, race, top.horse_num, "tan"
                    )
                if is_bet and present:
                    day = f"{race['race_year']}{race['race_month_day']}"
                    daily_returns[day].append(int(payout or 0))
                if include_ledger:
                    ledger.append(
                        {
                            "race_id": "_".join(
                                str(race.get(key) or "")
                                for key in (
                                    "race_year", "race_month_day", "track_code",
                                    "kaiji", "nichiji", "race_num",
                                )
                            ),
                            "day": f"{race['race_year']}{race['race_month_day']}",
                            "horse_num": str(top.horse_num),
                            "win_probability": float(top.win_probability),
                            "odds": float((top_horse.get("win_odds") or 0) / 10.0),
                            "is_bet": bool(is_bet and present),
                            "payout": int(payout or 0) if present else None,
                            "payout_present": bool(present),
                        }
                    )
                if not is_bet:
                    continue
                if i % 200 == 0:
                    print(f"  OOS {i}/{races_total}", flush=True)
    finally:
        ml_model.load_lgbm = original_loader
        rules.CALIBRATOR_PATH = original_calibrator_path
        rules._CALIBRATOR_CACHE = original_calibrator_cache

    bets = sum(len(values) for values in daily_returns.values())
    hits = sum(1 for values in daily_returns.values() for payout in values if payout > 0)
    returned = sum(sum(values) for values in daily_returns.values())
    result = {
        "from_date": OOS_FROM,
        "to_date": OOS_TO,
        "sealed_start_guard": SEALED_START,
        "reference_path": str(OOS_REFERENCE_PATH.relative_to(PROJECT_ROOT)),
        "reference_git_sha": (reference.get("meta") or {}).get("git_sha"),
        "reference_races_total": reference.get("races_total"),
        "reference_buy_only_bets": reference["buy_only_bets"],
        "reference_buy_only_return_rate": reference["buy_only_return_rate"],
        "reference_buy_only_return_rate_ci95": reference["buy_only_return_rate_ci95"],
        "buy_filter": fixed_filter,
        "env_overrides": {k: v for k, v in env.items() if v is not None},
        "calibrator_path": str(old_calibrator.relative_to(PROJECT_ROOT)),
        "calibrator_sha256": _sha256(old_calibrator),
        "races_total": races_total,
        "races_scored": races_scored,
        "days": len(daily_returns),
        "buy_only_bets": bets,
        "buy_only_hits": hits,
        "buy_only_return_total": returned,
        "buy_only_return_rate": returned / (100 * bets) if bets else math.nan,
        "buy_only_return_rate_ci95_day_block": _block_bootstrap_roi(
            daily_returns, samples=bootstrap_samples
        ),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "elapsed_sec": time.time() - started,
        "comparability_note": (
            "Window, buy filter, popularity overrides and historical calibrator match the 70.7% "
            "reference, but predictor/rules.py uses the reviewed commit rather than the historical "
            "git SHA. Race and bet counts also differ, so the OOS percentage-point difference is "
            "not a paired estimate of leak contribution."
        ),
    }
    if include_ledger:
        result["_ledger"] = ledger
    return result


def _saved_pair_validation_check(
    phase_metrics: dict,
    cache_path: Path = DEFAULT_CACHE,
    output_dir: Path = DEFAULT_OUTPUT,
) -> tuple[dict, object, dict, object, dict]:
    """Load saved M2 artifacts and reproduce their frozen validation AUCs."""
    cache_path = _require_project_path(cache_path, "cache")
    output_dir = _require_project_path(output_dir, "output_dir")
    X, y, groups, features, _race_keys = _load_cache(cache_path)
    _train_slice, val_slice = time_split_indices(groups, VAL_FRACTION)
    val_start_race = int(len(groups) * (1 - VAL_FRACTION))
    val_groups = groups[val_start_race:]
    X_val, y_val = X[val_slice], y[val_slice]

    import lightgbm as lgb

    control_model_path = output_dir / "m2_control_model.txt"
    treatment_model_path = output_dir / "m2_treatment_model.txt"
    control_features_path = output_dir / "m2_control_features.json"
    treatment_features_path = output_dir / "m2_treatment_features.json"
    control_definition = json.loads(control_features_path.read_text(encoding="utf-8"))
    treatment_definition = json.loads(treatment_features_path.read_text(encoding="utf-8"))
    control_features = list(control_definition.get("all_features") or [])
    treatment_features = list(treatment_definition.get("all_features") or [])
    if control_features != features:
        raise ValueError("saved M2-control feature order differs from the Phase 0-0 cache")
    expected_treatment = [name for name in features if name not in BLOCKED_FEATURES]
    if treatment_features != expected_treatment:
        raise ValueError("saved M2-treatment is not the preregistered exact-3 ablation")

    control = lgb.Booster(model_file=str(control_model_path))
    treatment = lgb.Booster(model_file=str(treatment_model_path))
    treatment_indices = [features.index(name) for name in treatment_features]
    actual_control = _classification_metrics(
        y_val,
        np.asarray(control.predict(X_val), dtype=np.float64),
        val_groups,
    )
    actual_treatment = _classification_metrics(
        y_val,
        np.asarray(treatment.predict(X_val[:, treatment_indices]), dtype=np.float64),
        val_groups,
    )
    expected_control = phase_metrics["validation_models"]["M2_control"]
    expected_treatment_metrics = phase_metrics["validation_models"]["M2_treatment"]
    tolerance = 1e-5
    passed = (
        abs(actual_control["auc"] - expected_control["auc"]) <= tolerance
        and abs(actual_treatment["auc"] - expected_treatment_metrics["auc"]) <= tolerance
    )
    check = {
        "tolerance": tolerance,
        "control": {
            "expected_auc": expected_control["auc"],
            "actual_auc": actual_control["auc"],
            "artifact_sha256": _sha256(control_model_path),
            "features_sha256": _sha256(control_features_path),
        },
        "treatment": {
            "expected_auc": expected_treatment_metrics["auc"],
            "actual_auc": actual_treatment["auc"],
            "artifact_sha256": _sha256(treatment_model_path),
            "features_sha256": _sha256(treatment_features_path),
        },
        "passed": passed,
    }
    if not passed:
        raise RuntimeError("saved M2 artifacts failed the frozen validation AUC check")
    return check, control, control_definition, treatment, treatment_definition


def _paired_roi_bootstrap(
    joined: list[dict],
    *,
    basis: str,
    samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """Use one shared day-block resample for both ROI series and their difference."""
    if basis not in ("self_selected", "treatment_bet_races", "control_bet_races"):
        raise ValueError(f"unknown paired basis: {basis}")
    days = sorted({row["day"] for row in joined})
    day_index = {day: index for index, day in enumerate(days)}
    control_bets = np.zeros(len(days), dtype=np.float64)
    control_returns = np.zeros(len(days), dtype=np.float64)
    treatment_bets = np.zeros(len(days), dtype=np.float64)
    treatment_returns = np.zeros(len(days), dtype=np.float64)
    included_races = 0
    excluded_missing_payout = 0
    hits_control = 0
    hits_treatment = 0

    for row in joined:
        control = row["control"]
        treatment = row["treatment"]
        if basis == "self_selected":
            control_selected = bool(control["is_bet"])
            treatment_selected = bool(treatment["is_bet"])
            if not control_selected and not treatment_selected:
                continue
        elif basis == "treatment_bet_races":
            if not treatment["is_bet"]:
                continue
            if not control["payout_present"] or not treatment["payout_present"]:
                excluded_missing_payout += 1
                continue
            control_selected = treatment_selected = True
        else:
            if not control["is_bet"]:
                continue
            if not control["payout_present"] or not treatment["payout_present"]:
                excluded_missing_payout += 1
                continue
            control_selected = treatment_selected = True

        included_races += 1
        index = day_index[row["day"]]
        if control_selected:
            control_bets[index] += 1
            payout = float(control["payout"] or 0)
            control_returns[index] += payout
            hits_control += int(payout > 0)
        if treatment_selected:
            treatment_bets[index] += 1
            payout = float(treatment["payout"] or 0)
            treatment_returns[index] += payout
            hits_treatment += int(payout > 0)

    total_control_bets = float(control_bets.sum())
    total_treatment_bets = float(treatment_bets.sum())
    if total_control_bets == 0 or total_treatment_bets == 0:
        raise RuntimeError(f"paired basis {basis} has no bets for one model")
    control_roi = float(control_returns.sum() / (100.0 * total_control_bets))
    treatment_roi = float(treatment_returns.sum() / (100.0 * total_treatment_bets))

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(days), size=(samples, len(days)))
    sampled_control_bets = control_bets[indices].sum(axis=1)
    sampled_treatment_bets = treatment_bets[indices].sum(axis=1)
    valid = (sampled_control_bets > 0) & (sampled_treatment_bets > 0)
    sampled_control_roi = control_returns[indices].sum(axis=1)[valid] / (
        100.0 * sampled_control_bets[valid]
    )
    sampled_treatment_roi = treatment_returns[indices].sum(axis=1)[valid] / (
        100.0 * sampled_treatment_bets[valid]
    )
    sampled_diff = sampled_control_roi - sampled_treatment_roi
    percentile = lambda values: [
        float(np.percentile(values, 2.5)),
        float(np.percentile(values, 97.5)),
    ]
    return {
        "basis": basis,
        "n_races": included_races,
        "n_days": len(days),
        "excluded_missing_payout": excluded_missing_payout,
        "control": {
            "n_bets": int(total_control_bets),
            "n_hits": hits_control,
            "roi": control_roi,
            "ci95": percentile(sampled_control_roi),
        },
        "treatment": {
            "n_bets": int(total_treatment_bets),
            "n_hits": hits_treatment,
            "roi": treatment_roi,
            "ci95": percentile(sampled_treatment_roi),
        },
        "paired_diff_control_minus_treatment": {
            "point": control_roi - treatment_roi,
            "ci95": percentile(sampled_diff),
            "contains_zero": bool(
                float(np.percentile(sampled_diff, 2.5)) <= 0
                <= float(np.percentile(sampled_diff, 97.5))
            ),
        },
        "bootstrap_valid_samples": int(valid.sum()),
    }


def _write_phase0b_report(payload: dict, path: Path) -> None:
    self_basis = payload["basis"]["self_selected"]
    treatment_basis = payload["basis"]["treatment_bet_races"]
    control_basis = payload["basis"]["control_bet_races"]
    conclusion = payload["precommitted_decision"]["conclusion"]
    lines = [
        "# F3 Phase 0-0b paired control/treatment OOS ROI",
        "",
        f"**結論**: {conclusion}",
        "",
        f"OOS窓: `{OOS_FROM}`–`{OOS_TO}` / rules SHA: `{payload['rules_sha']}` / "
        f"bootstrap: day block, B={payload['bootstrap']['samples']}, seed={payload['bootstrap']['seed']}",
        "",
        "## 決定性チェック",
        "",
        "| model | expected val AUC | reproduced val AUC | artifact SHA-256 |",
        "|---|---:|---:|---|",
        f"| control | {payload['determinism_check']['control']['expected_auc']:.6f} | "
        f"{payload['determinism_check']['control']['actual_auc']:.6f} | "
        f"`{payload['determinism_check']['control']['artifact_sha256']}` |",
        f"| treatment | {payload['determinism_check']['treatment']['expected_auc']:.6f} | "
        f"{payload['determinism_check']['treatment']['actual_auc']:.6f} | "
        f"`{payload['determinism_check']['treatment']['artifact_sha256']}` |",
        "",
        "## Paired OOS結果",
        "",
        "| basis | control bets/hits/ROI (CI) | treatment bets/hits/ROI (CI) | d=control−treatment (CI) |",
        "|---|---|---|---|",
    ]
    for label, result in (
        ("(a) 各モデル自己選択", self_basis),
        ("(b-1) treatment bet races", treatment_basis),
        ("(b-2) control bet races", control_basis),
    ):
        control = result["control"]
        treatment = result["treatment"]
        diff = result["paired_diff_control_minus_treatment"]
        lines.append(
            f"| {label} | {control['n_bets']}/{control['n_hits']}/{control['roi']:.4%} "
            f"([{control['ci95'][0]:.4%}, {control['ci95'][1]:.4%}]) | "
            f"{treatment['n_bets']}/{treatment['n_hits']}/{treatment['roi']:.4%} "
            f"([{treatment['ci95'][0]:.4%}, {treatment['ci95'][1]:.4%}]) | "
            f"{diff['point']:+.4%} ([{diff['ci95'][0]:+.4%}, {diff['ci95'][1]:+.4%}]) |"
        )
    lines += [
        "",
        "§3-4の事前コミット判定はbasis (a)に適用。95%CIが0を含む場合、"
        "3 POST-HIGHチャネルはROIに有意寄与しないと判定する。",
        "",
        "## T-10正本転記用・確定ベースライン案",
        "",
        "```text",
        f"control ROI = {self_basis['control']['roi']:.4%} "
        f"(95% CI [{self_basis['control']['ci95'][0]:.4%}, {self_basis['control']['ci95'][1]:.4%}])",
        f"treatment ROI = {self_basis['treatment']['roi']:.4%} "
        f"(95% CI [{self_basis['treatment']['ci95'][0]:.4%}, {self_basis['treatment']['ci95'][1]:.4%}])",
        f"paired d(control−treatment) = {self_basis['paired_diff_control_minus_treatment']['point']:+.4%} "
        f"(95% CI [{self_basis['paired_diff_control_minus_treatment']['ci95'][0]:+.4%}, "
        f"{self_basis['paired_diff_control_minus_treatment']['ci95'][1]:+.4%}])",
        "de-leaked baseline = M2-treatment (3チャネル遮断・再学習後)",
        "```",
        "",
        "production artifact不変、DB read-only、2026-10-01以降の封印未アクセス。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_paired_oos(
    cache_path: Path = DEFAULT_CACHE,
    output_dir: Path = DEFAULT_OUTPUT,
    output_path: Path = PAIRED_OOS_OUTPUT,
    report_path: Path = PAIRED_OOS_REPORT,
    bootstrap_samples: int = BOOTSTRAP_SAMPLES,
) -> dict:
    """Run saved treatment then control through the exact Phase 0-0 OOS harness."""
    _guard_unsealed(OOS_FROM, OOS_TO)
    cache_path = _require_project_path(cache_path, "cache")
    output_dir = _require_project_path(output_dir, "output_dir")
    output_path = _require_project_path(output_path, "paired_output")
    report_path = _require_project_path(report_path, "paired_report")
    production_before = _artifact_hashes()
    phase_metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    rules_sha = str(phase_metrics.get("git_sha") or "")
    if not rules_sha:
        raise ValueError("Phase 0-0 metrics has no rules SHA")
    rules_diff = subprocess.run(
        ["git", "diff", "--quiet", rules_sha, "--", "predictor/rules.py"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if rules_diff.returncode != 0:
        raise RuntimeError("predictor/rules.py differs from the Phase 0-0 rules SHA")

    check, control, control_definition, treatment, treatment_definition = (
        _saved_pair_validation_check(phase_metrics, cache_path, output_dir)
    )
    reference = _load_reference()
    treatment_oos = _evaluate_oos(
        treatment,
        treatment_definition,
        reference,
        bootstrap_samples,
        include_ledger=True,
        model_label="treatment",
    )
    frozen_treatment = phase_metrics["oos"]
    treatment_reproduced = (
        treatment_oos["buy_only_bets"] == frozen_treatment["buy_only_bets"] == 425
        and treatment_oos["buy_only_hits"] == frozen_treatment["buy_only_hits"] == 65
        and abs(
            treatment_oos["buy_only_return_rate"]
            - frozen_treatment["buy_only_return_rate"]
        )
        <= 1e-12
    )
    if not treatment_reproduced:
        raise RuntimeError("treatment OOS did not reproduce frozen 425/65/62.09%; control not run")

    control_oos = _evaluate_oos(
        control,
        control_definition,
        reference,
        bootstrap_samples,
        include_ledger=True,
        model_label="control",
    )
    control_by_race = {row["race_id"]: row for row in control_oos.pop("_ledger")}
    treatment_by_race = {row["race_id"]: row for row in treatment_oos.pop("_ledger")}
    if set(control_by_race) != set(treatment_by_race):
        raise RuntimeError("control/treatment OOS race ledgers differ")
    joined = [
        {
            "race_id": race_id,
            "day": treatment_by_race[race_id]["day"],
            "control": control_by_race[race_id],
            "treatment": treatment_by_race[race_id],
        }
        for race_id in sorted(control_by_race)
    ]
    basis = {
        name: _paired_roi_bootstrap(
            joined, basis=name, samples=bootstrap_samples, seed=BOOTSTRAP_SEED
        )
        for name in ("self_selected", "treatment_bet_races", "control_bet_races")
    }
    primary_diff = basis["self_selected"]["paired_diff_control_minus_treatment"]
    if primary_diff["contains_zero"]:
        decision = {
            "basis": "self_selected",
            "ci_contains_zero": True,
            "conclusion": (
                "paired差分95%CIは0を含むため、3 POST-HIGHチャネルはROIに"
                "有意寄与しない。correctness章を閉じる。"
            ),
            "correctness_chapter": "CLOSED",
        }
    else:
        decision = {
            "basis": "self_selected",
            "ci_contains_zero": False,
            "conclusion": (
                "paired差分95%CIは0を含まない。寄与量と符号を記録し、"
                "遮断allowlistは変更しない。"
            ),
            "correctness_chapter": "RECORDED_WITH_SIGNIFICANT_CONTRIBUTION",
        }
    production_after = _artifact_hashes()
    if production_before != production_after:
        raise RuntimeError("production artifact changed during Phase 0-0b")
    payload = {
        "experiment_id": "KEIBA-F3-PHASE0-0B-PAIRED-OOS",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rules_sha": rules_sha,
        "oos_window": {"from": OOS_FROM, "to": OOS_TO},
        "blocked_features": list(BLOCKED_FEATURES),
        "determinism_check": check,
        "treatment_oos_reproduced": treatment_reproduced,
        "models": {
            "control": {
                "n_bets": control_oos["buy_only_bets"],
                "n_hits": control_oos["buy_only_hits"],
                "roi": control_oos["buy_only_return_rate"],
                "ci95": basis["self_selected"]["control"]["ci95"],
            },
            "treatment": {
                "n_bets": treatment_oos["buy_only_bets"],
                "n_hits": treatment_oos["buy_only_hits"],
                "roi": treatment_oos["buy_only_return_rate"],
                "ci95": basis["self_selected"]["treatment"]["ci95"],
            },
        },
        "basis": basis,
        "bootstrap": {
            "block": "day",
            "samples": bootstrap_samples,
            "seed": BOOTSTRAP_SEED,
            "paired_shared_resample": True,
        },
        "precommitted_decision": decision,
        "methodology": {
            "oos_function": "scripts.f3_phase0_0_eval._evaluate_oos",
            "same_window_filter_calibrator_rules": True,
            "treatment_run_first_fail_closed": True,
        },
        "production_artifacts_before": production_before,
        "production_artifacts_after": production_after,
        "production_artifacts_unchanged": True,
        "sealed_holdout_accessed": False,
        "evaluator_sha256": _sha256(Path(__file__).resolve()),
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_phase0b_report(payload, report_path)
    return payload


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _write_report(metrics: dict, path: Path) -> None:
    models = metrics["validation_models"]
    oos = metrics.get("oos")
    lines = [
        "# F3 Phase 0-0 発走後リーク定量化結果",
        "",
        f"- 実行日時: {metrics['generated_at']}",
        f"- コードcommit: `{metrics['git_sha']}`",
        f"- 評価スクリプトSHA-256: `{metrics['evaluation_script_sha256']}`",
        f"- train/val: {TRAIN_FROM}〜{TRAIN_TO}、時系列末尾{VAL_FRACTION:.0%}をval",
        f"- 固定seed: {FIXED_SEED}、boosting rounds: {metrics['training']['boosting_rounds']}",
        "- 遮断対象: `same_day_bias_score`, `leg_quality_available`, `same_day_bias_available` の3件のみ",
        "",
        "## Validation",
        "",
        "| model | AUC | Brier | LogLoss | race top-1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for key in ("M0_public_v6", "M1_zero_fill", "M2_control", "M2_treatment"):
        m = models[key]
        lines.append(
            f"| {key} | {m['auc']:.6f} | {m['brier']:.6f} | "
            f"{m['logloss']:.6f} | {m['top1_hit_rate']:.6f} |"
        )
    lines += [
        "",
        "差分は左辺−右辺の直接差。AUC/top-1は正が左辺優位、Brier/LogLossは負が左辺優位。",
        "",
        f"- live skew（M0−M1）: `{json.dumps(metrics['differences']['public_v6_minus_M1'], ensure_ascii=False)}`",
        f"- 事前登録3チャネル差（M2-control−M2-treatment）: `{json.dumps(metrics['differences']['M2_control_minus_treatment'], ensure_ascii=False)}`",
        "",
    ]
    if oos:
        lo, hi = oos["buy_only_return_rate_ci95_day_block"]
        lines += [
            "## 固定pre-2026-07 OOS",
            "",
            f"- 期間: {oos['from_date']}〜{oos['to_date']}（封印開始 {SEALED_START} より前）",
            f"- M2-treatment: {oos['buy_only_bets']} bets / {oos['buy_only_hits']} hits / "
            f"回収率 {oos['buy_only_return_rate']:.4%}",
            f"- 開催日block bootstrap 95% CI: [{lo:.4%}, {hi:.4%}] "
            f"(B={oos['bootstrap_samples']}, seed={oos['bootstrap_seed']})",
            f"- 旧参照: {oos['reference_buy_only_bets']} bets / "
            f"回収率 {oos['reference_buy_only_return_rate']:.4%} / "
            f"CI {oos['reference_buy_only_return_rate_ci95']}",
            f"- 母集団差: 現行 {oos['races_total']} races / {oos['buy_only_bets']} bets、"
            f"旧参照 {oos['reference_races_total']} races / {oos['reference_buy_only_bets']} bets",
            f"- 比較上の注意: {oos['comparability_note']}",
            f"- OOS処理時間: {oos['elapsed_sec'] / 60:.1f}分。再実行は30分超pre-flight対象。",
            "",
        ]
    treatment = models["M2_treatment"]
    conclusion = (
        "同一split/seedで事前登録3チャネルだけを除外したときのAUC差は "
        f"{metrics['differences']['M2_control_minus_treatment']['auc']:+.6f}。"
        f"3チャネル除外validationはAUC≈{treatment['auc']:.6f}"
    )
    if oos:
        conclusion += (
            f" / OOS≈{oos['buy_only_return_rate']:.2%}"
            "（旧70.7%との差は非pairedで、全stackのリーク除去効果とはみなさない）"
        )
    conclusion += "。"
    lines += [
        "## 結論",
        "",
        conclusion,
        "",
        "production artifactはSHA-256前後一致。封印期間、DB書込み、Discord、production更新は実施していない。",
        "",
        "## 対象外の追加観察",
        "",
        "- treatmentにも `same_day_gate_bias_score`、rule側のsame-day/`leg_quality_code` 経路などは残る。事前登録どおり遮断対象を3チャネルから拡張せず、本結果を全リーク除去baselineとは呼ばない。",
        "- G-MINおよびPIT-UNPROVEN特徴は今回の対象外で、変更していない。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(cache_path: Path, output_dir: Path, report_path: Path, skip_oos: bool,
        bootstrap_samples: int) -> dict:
    _guard_unsealed(TRAIN_FROM, TRAIN_TO)
    _guard_unsealed(OOS_FROM, OOS_TO)
    cache_path = _require_project_path(cache_path, "cache")
    output_dir = _require_project_path(output_dir, "output_dir")
    report_path = _require_project_path(report_path, "report")
    output_dir.mkdir(parents=True, exist_ok=True)
    production_before = _artifact_hashes()

    X, y, groups, features, race_keys = _load_cache(cache_path)
    train_sl, val_sl = time_split_indices(groups, VAL_FRACTION)
    val_start_race = int(len(groups) * (1 - VAL_FRACTION))
    train_groups = groups[:val_start_race]
    val_groups = groups[val_start_race:]
    X_train, y_train = X[train_sl], y[train_sl]
    X_val, y_val = X[val_sl], y[val_sl]

    production_meta = json.loads(
        (PROJECT_ROOT / "predictor" / "lgbm_meta.json").read_text(encoding="utf-8")
    )
    source_features = json.loads(
        (PROJECT_ROOT / "predictor" / "lgbm_features.json").read_text(encoding="utf-8")
    )
    if X_train.shape[0] != production_meta["n_train_rows"] or X_val.shape[0] != production_meta["n_val_rows"]:
        raise ValueError("cache split does not reproduce production v6 train/val row counts")

    import lightgbm as lgb

    public_model = lgb.Booster(model_file=str(PROJECT_ROOT / "predictor" / "lgbm_model.txt"))
    m0_pred = np.asarray(public_model.predict(X_val), dtype=np.float64)
    m1_pred = np.asarray(public_model.predict(_zero_live_channels(X_val, features)), dtype=np.float64)

    params = _training_params(production_meta)
    rounds = int(production_meta["best_iteration"])
    control = _train_model(X_train, y_train, features, params, rounds)
    control_pred = np.asarray(control.predict(X_val), dtype=np.float64)

    treatment_features = [name for name in features if name not in BLOCKED_FEATURES]
    treatment_idx = [features.index(name) for name in treatment_features]
    treatment = _train_model(
        X_train[:, treatment_idx], y_train, treatment_features, params, rounds
    )
    treatment_pred = np.asarray(treatment.predict(X_val[:, treatment_idx]), dtype=np.float64)

    validation_models = {
        "M0_public_v6": _classification_metrics(y_val, m0_pred, val_groups),
        "M1_zero_fill": _classification_metrics(y_val, m1_pred, val_groups),
        "M2_control": _classification_metrics(y_val, control_pred, val_groups),
        "M2_treatment": _classification_metrics(y_val, treatment_pred, val_groups),
    }

    control_path = output_dir / "m2_control_model.txt"
    treatment_path = output_dir / "m2_treatment_model.txt"
    control.save_model(str(control_path))
    treatment.save_model(str(treatment_path))
    _save_feature_definition(output_dir / "m2_control_features.json", features, source_features)
    _save_feature_definition(
        output_dir / "m2_treatment_features.json", treatment_features, source_features
    )

    allowlist = {
        "experiment_id": "KEIBA-F3-PHASE0-0-POSTLEAK",
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "blocked_features": list(BLOCKED_FEATURES),
        "live_values": LIVE_VALUES,
        "rule": "exactly these three channels; no additions or removals in Phase 0-0",
    }
    (output_dir / "blocked_allowlist.json").write_text(
        json.dumps(allowlist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    metrics = {
        "experiment_id": "KEIBA-F3-PHASE0-0-POSTLEAK",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "evaluation_script_sha256": _sha256(Path(__file__).resolve()),
        "production_artifacts_before": production_before,
        "cache": {
            "path": str(cache_path.relative_to(PROJECT_ROOT)),
            "sha256": _sha256(cache_path),
            "features": len(features),
            "races": len(groups),
            "rows": len(y),
        },
        "split": {
            "method": "time ordered final 20% of race groups",
            "val_fraction": VAL_FRACTION,
            "train_rows": len(y_train),
            "val_rows": len(y_val),
            "train_races": len(train_groups),
            "val_races": len(val_groups),
            "val_first_race": race_keys[val_start_race],
            "val_last_race": race_keys[-1],
        },
        "training": {
            "params": params,
            "boosting_rounds": rounds,
            "fixed_seed": FIXED_SEED,
            "production_meta_params": production_meta["params"],
        },
        "blocked_features": list(BLOCKED_FEATURES),
        "live_values": LIVE_VALUES,
        "validation_models": validation_models,
        "differences": {
            "public_v6_minus_M1": _direct_diff(
                validation_models["M0_public_v6"], validation_models["M1_zero_fill"]
            ),
            "M2_control_minus_treatment": _direct_diff(
                validation_models["M2_control"], validation_models["M2_treatment"]
            ),
        },
        "experiment_artifacts": {
            "m2_control_model": str(control_path.relative_to(PROJECT_ROOT)),
            "m2_treatment_model": str(treatment_path.relative_to(PROJECT_ROOT)),
            "m2_control_features": "data/f3_phase0_0/m2_control_features.json",
            "m2_treatment_features": "data/f3_phase0_0/m2_treatment_features.json",
            "blocked_allowlist": "data/f3_phase0_0/blocked_allowlist.json",
        },
    }
    if not skip_oos:
        reference = _load_reference()
        treatment_definition = json.loads(
            (output_dir / "m2_treatment_features.json").read_text(encoding="utf-8")
        )
        metrics["oos"] = _evaluate_oos(
            treatment, treatment_definition, reference, bootstrap_samples
        )

    production_after = _artifact_hashes()
    metrics["production_artifacts_after"] = production_after
    metrics["production_artifacts_unchanged"] = production_before == production_after
    if not metrics["production_artifacts_unchanged"]:
        raise RuntimeError("production artifact changed during Phase 0-0")

    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_report(metrics, report_path)
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--skip-oos", action="store_true")
    parser.add_argument("--paired-oos", action="store_true")
    parser.add_argument("--paired-output", type=Path, default=PAIRED_OOS_OUTPUT)
    parser.add_argument("--paired-report", type=Path, default=PAIRED_OOS_REPORT)
    parser.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    args = parser.parse_args()
    if args.paired_oos:
        payload = run_paired_oos(
            args.cache.resolve(),
            args.output_dir.resolve(),
            args.paired_output.resolve(),
            args.paired_report.resolve(),
            args.bootstrap_samples,
        )
        print(json.dumps({
            "paired_output": str(args.paired_output.resolve()),
            "paired_report": str(args.paired_report.resolve()),
            "decision": payload["precommitted_decision"],
            "production_artifacts_unchanged": payload["production_artifacts_unchanged"],
        }, ensure_ascii=False))
        return 0
    metrics = run(
        args.cache.resolve(), args.output_dir.resolve(), args.report.resolve(),
        args.skip_oos, args.bootstrap_samples,
    )
    print(json.dumps({
        "metrics": str((args.output_dir / "metrics.json").resolve()),
        "report": str(args.report.resolve()),
        "production_artifacts_unchanged": metrics["production_artifacts_unchanged"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
