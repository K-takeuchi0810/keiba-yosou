from __future__ import annotations

from scripts import auto_predict


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
