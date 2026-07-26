"""F3 Phase 0 fail-closed characterization and contract tests."""
from __future__ import annotations

from dataclasses import asdict

import pytest

from predictor import rules


HORSES = [
    {"horse_num": "01", "win_odds": 100, "win_popularity": 1},
    {"horse_num": "02", "win_odds": 150, "win_popularity": 2},
]
RACE = {
    "race_year": "2026",
    "race_month_day": "0726",
    "start_time": "1200",
}


def _complete_features(_conn, _horse, _race, cache=None):
    return {
        "current_race_date": "20260726",
        "current_start_time": "1200",
        "leg_quality_available": True,
        "same_day_bias_available": True,
    }


def _patch_working_model(monkeypatch):
    monkeypatch.setattr("predictor.ml_model.load_lgbm", lambda: object())
    monkeypatch.setattr(
        "predictor.ml_model.predict_lgbm_probs",
        lambda horses, *_args, **_kwargs: {
            str(h["horse_num"]): 1.0 / len(horses) for h in horses
        },
    )


def test_characterization_lgbm_exception_is_now_blocked(monkeypatch):
    """G1 green: the former silent rule-only path is structurally blocked."""
    monkeypatch.setattr(rules, "compute_features", _complete_features)
    monkeypatch.setattr(rules, "_live_odds_errors", lambda *_args: [])
    monkeypatch.setattr("predictor.ml_model.load_lgbm", lambda: object())
    monkeypatch.setattr(
        "predictor.ml_model.predict_lgbm_probs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")),
    )

    predictions = rules.predict_race(HORSES, conn=object(), race=RACE)

    assert len(predictions) == 2
    assert rules.prediction_status(predictions) == (
        "blocked", [rules.E04_FEATURES_INCOMPLETE]
    )


def test_e01_model_missing_is_observation(monkeypatch):
    monkeypatch.setattr(rules, "compute_features", _complete_features)
    monkeypatch.setattr(rules, "_live_odds_errors", lambda *_args: [])
    monkeypatch.setattr("predictor.ml_model.load_lgbm", lambda: None)

    predictions = rules.predict_race(HORSES, conn=object(), race=RACE)

    assert len(predictions) == 2
    assert rules.prediction_status(predictions) == (
        "observation", [rules.E01_MODEL_MISSING]
    )
    assert all(p.prediction_mode == "observation" for p in predictions)


@pytest.mark.parametrize(
    "reason",
    [rules.E02_STALE_ODDS, rules.E03_PIT_VIOLATION],
)
def test_odds_failures_are_observation(monkeypatch, reason):
    monkeypatch.setattr(rules, "compute_features", _complete_features)
    monkeypatch.setattr(rules, "_live_odds_errors", lambda *_args: [reason])
    _patch_working_model(monkeypatch)

    predictions = rules.predict_race(HORSES, conn=object(), race=RACE)

    assert len(predictions) == 2
    assert rules.prediction_status(predictions) == ("observation", [reason])


def test_e04_feature_preflight_is_blocked(monkeypatch):
    monkeypatch.setattr(rules, "_live_odds_errors", lambda *_args: [])
    monkeypatch.setattr(
        rules,
        "compute_features",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad feature")),
    )

    predictions = rules.predict_race(HORSES, conn=object(), race=RACE)

    assert len(predictions) == 2
    assert rules.prediction_status(predictions) == (
        "blocked", [rules.E04_FEATURES_INCOMPLETE]
    )


def test_e04_post_race_feature_warning_is_blocked(monkeypatch):
    def warned_features(*_args, **_kwargs):
        return {
            **_complete_features(None, None, None),
            "needs_post_race_data": ["leg_quality_code"],
        }

    monkeypatch.setattr(rules, "compute_features", warned_features)
    monkeypatch.setattr(rules, "_live_odds_errors", lambda *_args: [])
    _patch_working_model(monkeypatch)

    predictions = rules.predict_race(HORSES, conn=object(), race=RACE)

    assert len(predictions) == 2
    assert rules.prediction_status(predictions) == (
        "blocked", [rules.E04_FEATURES_INCOMPLETE]
    )


def test_e04_blocked_has_priority_over_e01_observation(monkeypatch):
    def warned_features(*_args, **_kwargs):
        return {
            **_complete_features(None, None, None),
            "needs_post_race_data": ["leg_quality_code"],
        }

    monkeypatch.setattr(rules, "compute_features", warned_features)
    monkeypatch.setattr(rules, "_live_odds_errors", lambda *_args: [])
    monkeypatch.setattr("predictor.ml_model.load_lgbm", lambda: None)

    predictions = rules.predict_race(HORSES, conn=object(), race=RACE)

    assert rules.prediction_status(predictions) == (
        "blocked",
        [rules.E04_FEATURES_INCOMPLETE, rules.E01_MODEL_MISSING],
    )


def test_error_reason_contract_is_closed():
    with pytest.raises(ValueError, match="unknown prediction error"):
        rules.PredictionBatch(
            prediction_mode="observation",
            error_reasons=["free text"],
        )
    with pytest.raises(ValueError, match="full prediction mode"):
        rules.PredictionBatch(
            prediction_mode="full",
            error_reasons=[rules.E04_FEATURES_INCOMPLETE],
        )
    with pytest.raises(ValueError, match="requires an error reason"):
        rules.PredictionBatch(prediction_mode="blocked")
    with pytest.raises(ValueError, match="conflicts with reasons"):
        rules.PredictionBatch(
            prediction_mode="observation",
            error_reasons=[rules.E04_FEATURES_INCOMPLETE],
        )


def test_batch_rejects_member_status_conflict():
    member = rules.Prediction(
        horse_num="01",
        score=1,
        rank=1,
        mark="◎",
        rationale="test",
        confidence="high",
    )

    with pytest.raises(ValueError, match="member status"):
        rules.PredictionBatch(
            [member],
            prediction_mode="observation",
            error_reasons=[rules.E01_MODEL_MISSING],
        )


def test_batch_rejects_mismatched_member_mutation():
    batch = rules.PredictionBatch(
        prediction_mode="observation",
        error_reasons=[rules.E01_MODEL_MISSING],
    )
    full_member = rules.Prediction(
        horse_num="01",
        score=1,
        rank=1,
        mark="◎",
        rationale="test",
    )

    with pytest.raises(ValueError, match="member status"):
        batch.append(full_member)
    with pytest.raises(ValueError, match="member status"):
        batch.extend([full_member])
    with pytest.raises(ValueError, match="member status"):
        batch.insert(0, full_member)
    with pytest.raises(ValueError, match="member status"):
        batch += [full_member]


def test_normal_rule_only_existing_fields_golden():
    """G3 baseline: all pre-existing Prediction fields are bit-for-bit fixed."""
    horses = [
        {"horse_num": "01", "mining_predicted_order": 1,
         "win_odds": 100, "win_popularity": 1},
        {"horse_num": "02", "mining_predicted_order": 2,
         "win_odds": 150, "win_popularity": 2},
        {"horse_num": "03", "mining_predicted_order": 3,
         "win_odds": 200, "win_popularity": 3},
    ]

    new_fields = {"prediction_mode", "error_reasons"}
    actual = [
        {key: value for key, value in asdict(p).items() if key not in new_fields}
        for p in rules.predict_race(horses)
    ]

    assert actual == [
        {
            "horse_num": "01", "score": 18.8, "rank": 1, "mark": "◎",
            "rationale": "マイニング1位; 信頼度=混戦(2位差1.2)",
            "confidence": "混戦", "confidence_gap": 1.1999999999999993,
            "value_score": 187.9, "win_probability": 0.3179,
            "fair_odds": 3.15, "expected_value": 3.179,
            "kelly_fraction": 0.2421, "feature_warnings": [],
            "raw_blended_probability": 0.339372,
        },
        {
            "horse_num": "02", "score": 17.6, "rank": 2, "mark": "○",
            "rationale": "マイニング2位", "confidence": "混戦",
            "confidence_gap": 1.1999999999999993, "value_score": 238.3,
            "win_probability": 0.2456, "fair_odds": 4.07,
            "expected_value": 3.683, "kelly_fraction": 0.1917,
            "feature_warnings": [], "raw_blended_probability": 0.333253,
        },
        {
            "horse_num": "03", "score": 16.4, "rank": 3, "mark": "▲",
            "rationale": "マイニング3位", "confidence": "混戦",
            "confidence_gap": 1.1999999999999993, "value_score": 308.4,
            "win_probability": 0.2192, "fair_odds": 4.56,
            "expected_value": 4.384, "kelly_fraction": 0.1781,
            "feature_warnings": [], "raw_blended_probability": 0.327375,
        },
    ]


def test_normal_full_lgbm_path_existing_numeric_fields_golden(monkeypatch):
    """G3: the modified production/full path preserves its old numeric outputs."""
    monkeypatch.setattr(rules, "compute_features", _complete_features)
    monkeypatch.setattr(rules, "_live_odds_errors", lambda *_args: [])
    _patch_working_model(monkeypatch)

    predictions = rules.predict_race(HORSES, conn=object(), race=RACE)
    actual = [
        {
            key: getattr(prediction, key)
            for key in (
                "horse_num",
                "score",
                "rank",
                "win_probability",
                "expected_value",
                "kelly_fraction",
                "raw_blended_probability",
            )
        }
        for prediction in predictions
    ]

    assert rules.prediction_status(predictions) == ("full", [])
    assert actual == [
        {
            "horse_num": "01",
            "score": 50.0,
            "rank": 1,
            "win_probability": 0.472,
            "expected_value": 4.72,
            "kelly_fraction": 0.4133,
            "raw_blended_probability": 0.5,
        },
        {
            "horse_num": "02",
            "score": 50.0,
            "rank": 2,
            "win_probability": 0.3244,
            "expected_value": 4.866,
            "kelly_fraction": 0.2761,
            "raw_blended_probability": 0.5,
        },
    ]
