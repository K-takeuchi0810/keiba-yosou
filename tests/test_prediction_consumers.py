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


def test_production_consumers_use_fail_closed_wrapper_not_raw_filter():
    """production 経路が raw is_buy_candidate に戻る回帰を配線レベルで pin する。

    filter.py の二層契約 (production=wrapper / 分析=raw) は docstring だけでは守れない。
    誰かが production を raw に戻しても、通常系テストは全て green のまま
    「異常時に買い候補が出る」状態に静かに退行するため、ここで固定する。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    production_paths = [
        root / "web" / "generator.py",
        root / "gui" / "app.py",
        root / "scripts" / "predict.py",
    ]
    for path in production_paths:
        source = path.read_text(encoding="utf-8")
        assert "is_production_buy_candidate" in source, (
            f"{path.name} が fail-closed wrapper を使っていない"
        )
        # raw 呼び出しが残っていないこと (import 行・wrapper 名の部分一致は除く)
        stripped = source.replace("is_production_buy_candidate", "")
        assert "is_buy_candidate(" not in stripped.replace("_is_buy_candidate(", ""), (
            f"{path.name} に raw is_buy_candidate( の呼び出しが残っている"
        )


def test_analysis_paths_keep_raw_filter_for_frozen_baseline():
    """分析系は raw のままであること (fail-closed の遡及適用で凍結ベースラインが壊れる)。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("backtest.py", "f3_phase0_0_eval.py"):
        source = (root / "scripts" / name).read_text(encoding="utf-8")
        assert "is_production_buy_candidate" not in source, (
            f"{name} に production wrapper が混入している "
            "(歴史データで E02/E03 が常時発火し bets≈0 になる)"
        )
