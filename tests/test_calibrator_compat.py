"""calibrator の expected_rules_version 互換テーブルのテスト。

CALIBRATOR_COMPATIBLE_RULES_VERSIONS に列挙された旧 rules-version は
warning ではなく info でログされ、運用ノイズにならないことを保証する。
互換と判定する根拠 (Brier 差、データ量など) は dict の値に必ず書く。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


@pytest.fixture
def _reset_calibrator_cache():
    from predictor import rules
    rules._CALIBRATOR_CACHE = None
    yield
    rules._CALIBRATOR_CACHE = None


def _write_calibrator(tmp_path: Path, expected_version: str) -> Path:
    payload = {
        "type": "isotonic",
        "x_knots": [0.0, 0.5, 1.0],
        "y_knots": [0.0, 0.5, 1.0],
        "source_count": 1000,
        "brier_score": 0.06,
        "log_loss": 0.20,
        "trained_from": "20250101",
        "trained_to": "20251231",
        "generated_at": "2026-06-13T00:00:00",
        "rule_version": "test_isotonic",
        "expected_rules_version": expected_version,
    }
    path = tmp_path / "calibrator.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_compat_known_version_logs_info(monkeypatch, tmp_path, caplog, _reset_calibrator_cache):
    from predictor import rules
    compat_table = rules.CALIBRATOR_COMPATIBLE_RULES_VERSIONS.get(rules.RULES_VERSION) or {}
    assert compat_table, (
        f"RULES_VERSION={rules.RULES_VERSION} の互換テーブルが空。"
        "テスト前提が壊れているのでテーブル設計を見直してください。"
    )
    legacy_version = next(iter(compat_table.keys()))

    calib_path = _write_calibrator(tmp_path, legacy_version)
    monkeypatch.setattr(rules, "CALIBRATOR_PATH", calib_path)

    with caplog.at_level(logging.INFO, logger="predictor.rules"):
        loaded = rules._load_calibrator()

    assert loaded is not None
    assert loaded.get("expected_rules_version") == legacy_version
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    warn_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("compat" in r.getMessage() for r in info_records), (
        "互換テーブルにある旧版なら info ログが出るべき"
    )
    assert not any("mismatch" in r.getMessage() for r in warn_records), (
        "互換テーブルにある旧版なら mismatch warning は抑制されるべき"
    )


def test_compat_unknown_version_still_warns(monkeypatch, tmp_path, caplog, _reset_calibrator_cache):
    from predictor import rules
    calib_path = _write_calibrator(tmp_path, "totally-unknown-rules-2099")
    monkeypatch.setattr(rules, "CALIBRATOR_PATH", calib_path)

    with caplog.at_level(logging.WARNING, logger="predictor.rules"):
        loaded = rules._load_calibrator()

    assert loaded is not None
    warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("mismatch" in r.getMessage() for r in warn_records), (
        "互換テーブルに無い旧版なら従来通り mismatch warning が出るべき"
    )


def test_compat_rationale_is_substantive():
    from predictor import rules
    for current, compat in rules.CALIBRATOR_COMPATIBLE_RULES_VERSIONS.items():
        for legacy, rationale in compat.items():
            assert isinstance(rationale, str) and len(rationale) >= 60, (
                f"{current} <- {legacy} の rationale が短すぎる。"
                "Brier/データ量等の計量根拠を書くこと"
            )
