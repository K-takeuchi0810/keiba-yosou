"""calibrator の expected_rules_version 互換テーブルのテスト。

CALIBRATOR_COMPATIBLE_RULES_VERSIONS に列挙された旧 rules-version は
warning ではなく info でログされ、運用ノイズにならないことを保証する。
互換と判定する根拠 (Brier 差、データ量など) は dict の値に必ず書く。

横断 #2 (2026-06-17): 失効トリガ (fresh_rate / bonus_candidate_rate / 期限) で
warning 昇格することも保証する。
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
    rules._LATEST_BACKTEST_SNAPSHOT_CACHE = None
    yield
    rules._CALIBRATOR_CACHE = None
    rules._LATEST_BACKTEST_SNAPSHOT_CACHE = None


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
    # 失効トリガ判定で backtest dir を見ないように latest snapshot を空に
    monkeypatch.setattr(rules, "_latest_backtest_market_snapshot", lambda: None)

    with caplog.at_level(logging.INFO, logger="predictor.rules"):
        loaded = rules._load_calibrator()

    assert loaded is not None
    assert loaded.get("expected_rules_version") == legacy_version
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    warn_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("compat" in r.getMessage() for r in info_records), (
        "互換テーブルにある旧版なら info ログが出るべき"
    )
    assert not any("EXPIRED" in r.getMessage() or "mismatch" in r.getMessage()
                   for r in warn_records), (
        "互換テーブルにある旧版なら mismatch/EXPIRED warning は抑制されるべき"
    )


def test_compat_unknown_version_still_warns(monkeypatch, tmp_path, caplog, _reset_calibrator_cache):
    from predictor import rules
    calib_path = _write_calibrator(tmp_path, "totally-unknown-rules-2099")
    monkeypatch.setattr(rules, "CALIBRATOR_PATH", calib_path)
    monkeypatch.setattr(rules, "_latest_backtest_market_snapshot", lambda: None)

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
        for legacy, entry in compat.items():
            assert isinstance(entry, dict), (
                f"{current} <- {legacy} の値は dict 必須 (rationale/max_*/expires_on を持つ)"
            )
            rationale = entry.get("rationale")
            assert isinstance(rationale, str) and len(rationale) >= 60, (
                f"{current} <- {legacy} の rationale が短すぎる。"
                "Brier/データ量等の計量根拠を書くこと"
            )


def test_evaluate_compat_returns_match_when_versions_equal():
    from predictor.rules import evaluate_calibrator_compat
    status, _ = evaluate_calibrator_compat("rules-X", "rules-X")
    assert status == "match"


def test_evaluate_compat_mismatch_for_unknown_legacy():
    from predictor.rules import evaluate_calibrator_compat
    status, msg = evaluate_calibrator_compat("rules-X", "rules-unknown")
    assert status == "mismatch"
    assert "mismatch" in msg


def test_evaluate_compat_expired_by_date():
    """互換テーブルに登録されていても expires_on を過ぎたら expired"""
    from predictor.rules import evaluate_calibrator_compat, RULES_VERSION, CALIBRATOR_COMPATIBLE_RULES_VERSIONS
    table = CALIBRATOR_COMPATIBLE_RULES_VERSIONS.get(RULES_VERSION) or {}
    if not table:
        pytest.skip("RULES_VERSION に互換テーブル登録なし")
    legacy, entry = next(iter(table.items()))
    expires = entry.get("expires_on")
    if not expires:
        pytest.skip(f"{legacy} に expires_on が無い")
    status, msg = evaluate_calibrator_compat(
        RULES_VERSION, legacy, market_snapshot=None, today="2099-12-31"
    )
    assert status == "expired"
    assert "EXPIRED" in msg


def test_evaluate_compat_expired_by_fresh_rate():
    """fresh_horses / horses_total が max_fresh_rate を超えると expired"""
    from predictor.rules import evaluate_calibrator_compat, RULES_VERSION, CALIBRATOR_COMPATIBLE_RULES_VERSIONS
    table = CALIBRATOR_COMPATIBLE_RULES_VERSIONS.get(RULES_VERSION) or {}
    if not table:
        pytest.skip("RULES_VERSION に互換テーブル登録なし")
    legacy, entry = next(iter(table.items()))
    max_fresh = entry.get("max_fresh_rate")
    if max_fresh is None:
        pytest.skip(f"{legacy} に max_fresh_rate が無い")
    snapshot = {
        "horses": 1000,
        "fresh_horses": int(1000 * max_fresh * 1.5),
        "popularity_bonus_candidate_horses": 0,
    }
    status, msg = evaluate_calibrator_compat(
        RULES_VERSION, legacy, market_snapshot=snapshot, today="2026-06-17"
    )
    assert status == "expired"
    assert "fresh_rate" in msg


def test_evaluate_compat_expired_by_bonus_candidate_rate():
    """bonus_candidate_horses / horses が max_bonus_candidate_rate 超で expired"""
    from predictor.rules import evaluate_calibrator_compat, RULES_VERSION, CALIBRATOR_COMPATIBLE_RULES_VERSIONS
    table = CALIBRATOR_COMPATIBLE_RULES_VERSIONS.get(RULES_VERSION) or {}
    if not table:
        pytest.skip("RULES_VERSION に互換テーブル登録なし")
    legacy, entry = next(iter(table.items()))
    max_bonus = entry.get("max_bonus_candidate_rate")
    if max_bonus is None:
        pytest.skip(f"{legacy} に max_bonus_candidate_rate が無い")
    snapshot = {
        "horses": 1000,
        "fresh_horses": 0,
        "popularity_bonus_candidate_horses": int(1000 * max_bonus * 2.0),
    }
    status, msg = evaluate_calibrator_compat(
        RULES_VERSION, legacy, market_snapshot=snapshot, today="2026-06-17"
    )
    assert status == "expired"
    assert "bonus_candidate_rate" in msg


def test_evaluate_compat_passes_with_low_rates_and_today_before_expiry():
    """閾値未満 + 期限内なら compat"""
    from predictor.rules import evaluate_calibrator_compat, RULES_VERSION, CALIBRATOR_COMPATIBLE_RULES_VERSIONS
    table = CALIBRATOR_COMPATIBLE_RULES_VERSIONS.get(RULES_VERSION) or {}
    if not table:
        pytest.skip("RULES_VERSION に互換テーブル登録なし")
    legacy, _ = next(iter(table.items()))
    snapshot = {
        "horses": 1000,
        "fresh_horses": 4,  # 0.4%
        "popularity_bonus_candidate_horses": 0,
    }
    status, _ = evaluate_calibrator_compat(
        RULES_VERSION, legacy, market_snapshot=snapshot, today="2026-06-17"
    )
    assert status == "compat"
