"""F3 fail-closed contracts for CLI and monitoring consumers."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from predictor.rules import Prediction, PredictionBatch
from scripts import monitor
from scripts import predict as predict_cli


def test_predict_cli_observation_reports_stderr_and_exits_zero(
    monkeypatch, capsys
):
    rows = predict_cli.PredictionRows()
    rows.prediction_mode = "observation"
    rows.error_reasons = ["E01_MODEL_MISSING"]
    monkeypatch.setattr(predict_cli, "collect_predictions", lambda _args: rows)
    monkeypatch.setattr(
        predict_cli.sys, "argv", ["predict", "--format", "json"]
    )

    exit_code = predict_cli.main()

    assert exit_code == 0
    assert "prediction_mode=observation" in capsys.readouterr().err


def test_predict_cli_blocked_reports_stderr_and_exits_nonzero(
    monkeypatch, capsys
):
    rows = predict_cli.PredictionRows()
    rows.prediction_mode = "blocked"
    rows.error_reasons = ["E04_FEATURES_INCOMPLETE"]
    monkeypatch.setattr(predict_cli, "collect_predictions", lambda _args: rows)
    monkeypatch.setattr(
        predict_cli.sys, "argv", ["predict", "--format", "json"]
    )

    exit_code = predict_cli.main()

    assert exit_code == 8
    assert "E04_FEATURES_INCOMPLETE" in capsys.readouterr().err


def test_monitor_reports_mode_breakdown_without_excluding_observation(
    monkeypatch
):
    race = {"race_year": "2026", "race_month_day": "0726"}
    horses = [{"horse_num": "01", "confirmed_order": 1}]
    prediction = Prediction(
        horse_num="01",
        score=1.0,
        rank=1,
        mark="◎",
        rationale="test",
        win_probability=0.25,
        prediction_mode="observation",
        error_reasons=["E02_STALE_ODDS"],
    )
    batch = PredictionBatch(
        [prediction],
        prediction_mode="observation",
        error_reasons=["E02_STALE_ODDS"],
    )

    @contextmanager
    def fake_db():
        yield SimpleNamespace()

    monkeypatch.setattr(monitor, "open_db_readonly", fake_db)
    monkeypatch.setattr(monitor, "list_races", lambda *_args, **_kwargs: [race])
    monkeypatch.setattr(monitor, "horses_for_race", lambda *_args: horses)
    monkeypatch.setattr(monitor, "predict_race", lambda *_args, **_kwargs: batch)
    monkeypatch.setattr(
        monitor,
        "calibration_report",
        lambda records: {"brier_score": 0.1, "log_loss": 0.2},
    )

    result = monitor.measure_recent_brier(30)

    assert result["n_records"] == 1
    assert result["prediction_modes"]["observation"] == 1
    assert result["prediction_error_reasons"] == {"E02_STALE_ODDS": 1}
