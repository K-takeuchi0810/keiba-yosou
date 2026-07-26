from __future__ import annotations

from pathlib import Path
from scripts import auto_predict
from types import SimpleNamespace

import pytest


def test_stage_publish_artifacts_includes_prediction_archive(tmp_path, monkeypatch):
    pages = tmp_path / "docs" / "index.html"
    marker = tmp_path / "docs" / "predictions_latest.md"
    archive = (
        tmp_path / "data" / "results" / "2026-07-12" /
        "predictions_source_20260712_100000_gitabc.html"
    )
    pages.parent.mkdir(parents=True)
    pages.write_text("page", encoding="utf-8")
    (pages.parent / ".nojekyll").write_text("", encoding="utf-8")
    marker.write_text("marker", encoding="utf-8")
    archive.parent.mkdir(parents=True)
    archive.write_text("prediction", encoding="utf-8")
    monkeypatch.setattr(auto_predict, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(auto_predict, "PAGES_HTML", pages)
    monkeypatch.setattr(auto_predict, "MARKER", marker)
    calls = []
    monkeypatch.setattr(
        auto_predict.subprocess, "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    paths = auto_predict._stage_publish_artifacts(
        "20260712", sync_status_path=tmp_path / "missing_status.json"
    )

    assert archive in paths
    assert str(archive) in calls[0][0]
    assert calls[0][1]["check"] is True


def test_stage_publish_artifacts_uses_archive_from_sync_status(tmp_path, monkeypatch):
    pages = tmp_path / "docs" / "index.html"
    marker = tmp_path / "docs" / "predictions_latest.md"
    archive = tmp_path / "custom_archive" / "actual_generated.html"
    status_path = tmp_path / "icloud" / "_sync_status.json"
    pages.parent.mkdir(parents=True)
    pages.write_text("page", encoding="utf-8")
    (pages.parent / ".nojekyll").write_text("", encoding="utf-8")
    marker.write_text("marker", encoding="utf-8")
    archive.parent.mkdir(parents=True)
    archive.write_text("prediction", encoding="utf-8")
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        __import__("json").dumps({"repository_archive": str(archive)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(auto_predict, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(auto_predict, "PAGES_HTML", pages)
    monkeypatch.setattr(auto_predict, "MARKER", marker)
    calls = []
    monkeypatch.setattr(
        auto_predict.subprocess, "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    paths = auto_predict._stage_publish_artifacts(
        "20260712", sync_status_path=status_path
    )

    assert archive in paths
    assert str(archive) in calls[0][0]


def test_generation_status_uses_new_mode_failure_bit_contract():
    result = SimpleNamespace(
        returncode=auto_predict.EXIT_MODE_FAILURE,
        stdout='{"prediction_mode":"blocked","error_reasons":["E04_FEATURES_INCOMPLETE"]}\n',
    )

    mode, reasons = auto_predict._parse_generation_status(result)

    assert mode == "blocked"
    assert reasons == ["E04_FEATURES_INCOMPLETE"]
    assert auto_predict.EXIT_MODE_FAILURE == 8
    assert auto_predict.EXIT_GENERATION_FAILURE == 2
    assert "E04_FEATURES_INCOMPLETE" in auto_predict._mode_notice(mode, reasons)


def test_generation_status_accepts_full_with_empty_reasons():
    result = SimpleNamespace(
        returncode=0,
        stdout='{"prediction_mode":"full","error_reasons":[]}\n',
    )

    assert auto_predict._parse_generation_status(result) == ("full", [])


def test_daily_batch_preserves_prediction_mode_exit_bit():
    batch = (
        Path(__file__).parents[1] / "scripts" / "auto_predict_daily.bat"
    ).read_text(encoding="utf-8")

    assert "if %PREDICTCODE% EQU 8 (" in batch
    assert "set /a EXITCODE+=8" in batch


def test_generation_status_missing_payload_fails_closed():
    result = SimpleNamespace(returncode=0, stdout="not-json\n")

    with pytest.raises(RuntimeError, match="status JSON missing"):
        auto_predict._parse_generation_status(result)


def test_generation_status_rejects_mode_reason_conflict():
    result = SimpleNamespace(
        returncode=0,
        stdout='{"prediction_mode":"full","error_reasons":["E04_FEATURES_INCOMPLETE"]}\n',
    )

    with pytest.raises(RuntimeError, match="status contract invalid"):
        auto_predict._parse_generation_status(result)
