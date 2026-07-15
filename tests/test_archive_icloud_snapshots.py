from __future__ import annotations

from scripts.archive_icloud_snapshots import archive_snapshots


def _snapshot(source, name, content):
    source.mkdir(parents=True, exist_ok=True)
    path = source / name
    path.write_bytes(content)
    return path


def test_dry_run_does_not_copy(tmp_path):
    source = tmp_path / "icloud"
    results = tmp_path / "results"
    _snapshot(source, "index_20260712_101608_000001.html", b"prediction")

    summary = archive_snapshots(source, results)

    assert summary["planned"] == {"2026-07-12": 1}
    assert not results.exists()


def test_execute_copies_snapshot_to_date_archive(tmp_path):
    source = tmp_path / "icloud"
    results = tmp_path / "results"
    original = _snapshot(source, "index_20260712_101608_000001.html", b"prediction")

    summary = archive_snapshots(source, results, execute=True)
    copied = results / "2026-07-12" / "archive" / original.name

    assert summary["copied"] == {"2026-07-12": 1}
    assert copied.read_bytes() == b"prediction"
    assert original.read_bytes() == b"prediction"


def test_duplicate_sha_is_skipped(tmp_path):
    source = tmp_path / "icloud"
    results = tmp_path / "results"
    _snapshot(source, "index_20260712_101608_000001.html", b"same")
    existing = results / "2026-07-12" / "predictions_source_existing.html"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"same")

    summary = archive_snapshots(source, results, execute=True)

    assert summary["skipped"] == {"2026-07-12": 1}
    assert not (results / "2026-07-12" / "archive").exists()
