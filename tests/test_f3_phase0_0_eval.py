from __future__ import annotations

import json
import numpy as np
import pytest

from scripts.f3_phase0_0_eval import (
    BLOCKED_FEATURES,
    DEFAULT_OUTPUT,
    HISTORICAL_CALIBRATOR_PATH,
    OOS_REFERENCE_PATH,
    PHASE_METRICS_PATH,
    PROJECT_ROOT,
    _block_bootstrap_roi,
    _guard_cache_race_keys,
    _guard_paired_output_paths,
    _guard_unsealed,
    _require_project_path,
    _paired_roi_bootstrap,
    _saved_pair_validation_check,
    _top1_hit_rate,
    _zero_live_channels,
    run_paired_oos,
)


def test_blocked_allowlist_is_exactly_preregistered_three():
    assert BLOCKED_FEATURES == (
        "same_day_bias_score",
        "leg_quality_available",
        "same_day_bias_available",
    )


def test_zero_live_channels_changes_only_preregistered_columns():
    features = ["safe", *BLOCKED_FEATURES, "safe2"]
    X = np.asarray([[9.0, 4.0, 1.0, 1.0, 8.0]], dtype=np.float32)
    out = _zero_live_channels(X, features)
    assert out.tolist() == [[9.0, 0.0, 0.0, 0.0, 8.0]]
    assert X.tolist() == [[9.0, 4.0, 1.0, 1.0, 8.0]], "input must not be mutated"


def test_sealed_window_is_rejected():
    _guard_unsealed("20260101", "20260614")
    with pytest.raises(ValueError, match="sealed holdout access denied"):
        _guard_unsealed("20260901", "20261001")


def test_cache_race_keys_are_checked_independently_of_declared_window():
    _guard_cache_race_keys(["20210105_06_01_01_01", "20231228_09_05_09_12"])
    with pytest.raises(ValueError, match="sealed holdout access denied"):
        _guard_cache_race_keys(["20210105_06_01_01_01", "20261001_09_04_01_01"])


def test_external_paths_are_rejected():
    assert _require_project_path(PROJECT_ROOT / "data", "output") == (PROJECT_ROOT / "data").resolve()
    with pytest.raises(ValueError, match="must stay inside the project"):
        _require_project_path(PROJECT_ROOT.parent / "outside", "output")


def test_top1_is_calculated_per_race():
    y = np.asarray([0, 1, 0, 1, 0], dtype=np.int8)
    p = np.asarray([0.2, 0.7, 0.1, 0.4, 0.6])
    assert _top1_hit_rate(y, p, [3, 2]) == 0.5


def test_day_block_bootstrap_is_deterministic():
    daily = {"20260101": [0, 300], "20260102": [0], "20260103": [200]}
    first = _block_bootstrap_roi(daily, samples=1000, seed=123)
    second = _block_bootstrap_roi(daily, samples=1000, seed=123)
    assert first == second
    assert first[0] <= first[1]


def test_paired_bootstrap_uses_one_day_sample_and_zero_diff_for_identical_ledgers():
    joined = [
        {
            "day": "20260101",
            "control": {"is_bet": True, "payout": 300, "payout_present": True},
            "treatment": {"is_bet": True, "payout": 300, "payout_present": True},
        },
        {
            "day": "20260102",
            "control": {"is_bet": True, "payout": 0, "payout_present": True},
            "treatment": {"is_bet": True, "payout": 0, "payout_present": True},
        },
    ]
    result = _paired_roi_bootstrap(joined, basis="self_selected", samples=1000, seed=7)
    assert result["control"] == result["treatment"]
    assert result["paired_diff_control_minus_treatment"]["point"] == 0.0
    assert result["paired_diff_control_minus_treatment"]["ci95"] == [0.0, 0.0]
    assert result["paired_diff_control_minus_treatment"]["contains_zero"] is True
    with pytest.raises(ValueError, match="must be positive"):
        _paired_roi_bootstrap(joined, basis="self_selected", samples=0, seed=7)


def test_paired_outputs_cannot_overwrite_inputs_or_each_other():
    cache = PROJECT_ROOT / "data" / "lgbm_cache" / "w2021_2023_v6feat_fixed.npz"
    safe_json = PROJECT_ROOT / "data" / "f3_phase0_0" / "paired_oos.json"
    safe_report = PROJECT_ROOT / "docs" / "F3_phase0_0b_result.md"
    _guard_paired_output_paths(safe_json, safe_report, cache, DEFAULT_OUTPUT)
    with pytest.raises(ValueError, match="protected"):
        _guard_paired_output_paths(
            PROJECT_ROOT / "predictor" / "lgbm_model.txt",
            safe_report,
            cache,
            DEFAULT_OUTPUT,
        )
    with pytest.raises(ValueError, match="must differ"):
        _guard_paired_output_paths(safe_json, safe_json, cache, DEFAULT_OUTPUT)
    for protected_input in (OOS_REFERENCE_PATH, HISTORICAL_CALIBRATOR_PATH):
        with pytest.raises(ValueError, match="protected"):
            _guard_paired_output_paths(
                protected_input, safe_report, cache, DEFAULT_OUTPUT
            )


def test_paired_run_rejects_invalid_bootstrap_count_before_oos():
    with pytest.raises(ValueError, match="must be positive"):
        run_paired_oos(bootstrap_samples=0)


def test_saved_pair_reproduces_frozen_validation_auc():
    phase_metrics = json.loads(PHASE_METRICS_PATH.read_text(encoding="utf-8"))
    check, *_models = _saved_pair_validation_check(phase_metrics, output_dir=DEFAULT_OUTPUT)
    assert check["passed"] is True
    assert check["control"]["actual_auc"] == pytest.approx(0.7913195089, abs=1e-10)
    assert check["treatment"]["actual_auc"] == pytest.approx(0.7887806982, abs=1e-10)
