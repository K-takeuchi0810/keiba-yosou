"""scripts.check_fresh_odds_health の単体テスト。

PASS / FAIL / HOLD / NOT_EVALUABLE の全 4 状態と、contamination 検出 / DB 鮮度判定 /
scheduler 状態判定の網羅。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

import scripts.check_fresh_odds_health as mod


def _write_coverage(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False))
            f.write("\n")


def _setup_db(path: Path, fetched_at_values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE horse_races (
            race_year TEXT, race_month_day TEXT, track_code TEXT,
            kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT,
            win_odds INTEGER, win_popularity INTEGER, odds_fetched_at TEXT
        )
    """)
    for v in fetched_at_values:
        conn.execute(
            "INSERT INTO horse_races (odds_fetched_at) VALUES (?)",
            (v,),
        )
    conn.commit()
    conn.close()


def test_parse_dt_handles_iso_and_windows_format():
    assert mod._parse_dt("2026-06-20T09:00:00") == datetime(2026, 6, 20, 9, 0, 0)
    assert mod._parse_dt("2026/06/20 9:00:00") == datetime(2026, 6, 20, 9, 0, 0)
    # Windows epoch placeholder for "never run"
    assert mod._parse_dt("1999/11/30 0:00:00") is None
    assert mod._parse_dt(None) is None
    assert mod._parse_dt("") is None


def test_scheduler_evaluation_not_registered():
    out = mod.evaluate_scheduler({"registered": False}, "20260620", time(9, 0))
    assert out["registered"] is False
    assert out["ok"] is False
    assert "not registered" in out["reason"]


def test_scheduler_evaluation_never_run():
    out = mod.evaluate_scheduler(
        {"registered": True, "last_run_time": "1999/11/30 0:00:00", "last_task_result": 267011},
        "20260620", time(9, 0),
    )
    assert out["registered"] is True
    assert out["ok"] is False
    assert "never run" in out["reason"]


def test_scheduler_evaluation_ran_today_clean():
    out = mod.evaluate_scheduler(
        {"registered": True, "last_run_time": "2026-06-20T09:00:00", "last_task_result": 0},
        "20260620", time(9, 0),
    )
    assert out["ok"] is True
    assert out["ran_today_after_check_time"] is True


def test_scheduler_evaluation_ran_with_error():
    out = mod.evaluate_scheduler(
        {"registered": True, "last_run_time": "2026-06-20T09:10:00", "last_task_result": 1},
        "20260620", time(9, 0),
    )
    assert out["ok"] is False
    assert "last_task_result=1" in out["reason"]


def test_coverage_no_file(tmp_path):
    out = mod.evaluate_coverage(tmp_path / "missing.jsonl", "20260620", time(9, 0))
    assert out["exists"] is False
    assert out["ok"] is False


def test_coverage_contamination_detected(tmp_path):
    p = tmp_path / "coverage.jsonl"
    # 23:47 は scheduler 窓 (08:55-16:50) 外 → 汚染判定
    _write_coverage(p, [
        {"run_at": "2026-06-20T23:47:14", "target_date": "20260620",
         "eligible_races": 2, "ok_races": 1, "error_races": 1},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is True
    assert out["ok"] is False
    assert "contamination" in out["reason"]


def test_coverage_ok_within_window(tmp_path):
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T09:00:30", "target_date": "20260620",
         "eligible_races": 4, "ok_races": 3, "error_races": 1},
        {"run_at": "2026-06-20T09:10:30", "target_date": "20260620",
         "eligible_races": 5, "ok_races": 5, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["ok"] is True
    assert out["ok_races_today"] == 8
    assert out["error_races_today"] == 1
    assert out["runs_today"] == 2


def test_coverage_zero_ok_races_holds(tmp_path):
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T09:00:30", "target_date": "20260620",
         "eligible_races": 1, "ok_races": 0, "error_races": 1},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["ok"] is False
    assert "ok_races_today=0" in out["reason"]


def test_coverage_no_today_entries_holds(tmp_path):
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-19T15:00:00", "target_date": "20260619",
         "eligible_races": 4, "ok_races": 4, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["ok"] is False
    assert "no entries today" in out["reason"]


def test_db_no_file(tmp_path):
    out = mod.evaluate_db(tmp_path / "absent.db", "20260620", time(9, 0))
    assert out["reachable"] is False
    assert out["ok"] is False


def test_db_zero_fresh_rows(tmp_path):
    db = tmp_path / "test.db"
    _setup_db(db, ["2026-06-19T15:00:00"])  # 前日分のみ
    out = mod.evaluate_db(db, "20260620", time(9, 0))
    assert out["reachable"] is True
    assert out["fresh_horse_rows_since_check_time"] == 0
    assert out["ok"] is False


def test_db_has_fresh_rows(tmp_path):
    db = tmp_path / "test.db"
    _setup_db(db, [
        "2026-06-19T15:00:00",            # 前日 — カウントしない
        "2026-06-20T09:05:00",            # 当日 09:05 — カウント
        "2026-06-20T10:30:00",            # 当日 10:30 — カウント
        "2026-06-20T08:00:00",            # 当日早朝 — カウントしない
    ])
    out = mod.evaluate_db(db, "20260620", time(9, 0))
    assert out["reachable"] is True
    assert out["fresh_horse_rows_since_check_time"] == 2
    assert out["ok"] is True


def test_integrate_decision_pass():
    decision, _ = mod.integrate_decision(
        scheduler={"registered": True, "ran_today_after_check_time": True, "ok": True,
                   "last_task_result": 0, "last_run_time": "2026-06-20T09:00:00"},
        coverage={"exists": True, "contamination_detected": False,
                  "updated_today_after_check_time": True, "ok_races_today": 5, "ok": True},
        db={"reachable": True, "fresh_horse_rows_since_check_time": 13, "ok": True},
    )
    assert decision == "PASS"


def test_integrate_decision_not_evaluable_scheduler_missing():
    decision, reason = mod.integrate_decision(
        scheduler={"registered": False, "ok": False, "reason": "not registered"},
        coverage={"exists": True, "ok": True},
        db={"reachable": True, "ok": True},
    )
    assert decision == "NOT_EVALUABLE"
    assert "not registered" in reason


def test_integrate_decision_fail_contamination():
    decision, reason = mod.integrate_decision(
        scheduler={"registered": True, "ran_today_after_check_time": True, "ok": True,
                   "last_task_result": 0, "last_run_time": "2026-06-20T09:00:00"},
        coverage={"exists": True, "contamination_detected": True,
                  "updated_today_after_check_time": True, "ok_races_today": 5, "ok": False,
                  "reason": "contamination detected"},
        db={"reachable": True, "ok": True},
    )
    assert decision == "FAIL"
    assert "contamination" in reason


def test_integrate_decision_hold_scheduler_not_yet_fired():
    decision, _ = mod.integrate_decision(
        scheduler={"registered": True, "ran_today_after_check_time": False, "ok": False,
                   "last_task_result": 267011, "last_run_time": None,
                   "reason": "never run"},
        coverage={"exists": True, "ok": False},
        db={"reachable": True, "ok": False},
    )
    assert decision == "HOLD"


def test_integrate_decision_hold_when_scheduler_not_fired_and_coverage_absent():
    """pre-09:00 状態: scheduler 未稼働 + coverage 未生成は HOLD (NOT_EVALUABLE ではない)"""
    decision, reason = mod.integrate_decision(
        scheduler={"registered": True, "ran_today_after_check_time": False, "ok": False,
                   "last_task_result": 267011, "last_run_time": None,
                   "reason": "scheduler has never run"},
        coverage={"exists": False, "ok": False, "reason": "coverage JSONL not found"},
        db={"reachable": True, "ok": False},
    )
    assert decision == "HOLD"
    assert "not yet" in reason.lower() or "awaiting" in reason.lower()


def test_integrate_decision_not_evaluable_when_scheduler_fired_but_coverage_missing():
    """scheduler は fire したのに coverage が無い → data path 破綻 (NOT_EVALUABLE)"""
    decision, reason = mod.integrate_decision(
        scheduler={"registered": True, "ran_today_after_check_time": True, "ok": True,
                   "last_task_result": 0, "last_run_time": "2026-06-20T09:00:00"},
        coverage={"exists": False, "ok": False, "reason": "coverage JSONL not found"},
        db={"reachable": True, "ok": True},
    )
    assert decision == "NOT_EVALUABLE"
    assert "data path" in reason.lower() or "broken" in reason.lower()


def test_integrate_decision_hold_zero_db_rows():
    decision, _ = mod.integrate_decision(
        scheduler={"registered": True, "ran_today_after_check_time": True, "ok": True,
                   "last_task_result": 0, "last_run_time": "2026-06-20T09:00:00"},
        coverage={"exists": True, "contamination_detected": False,
                  "updated_today_after_check_time": True, "ok_races_today": 5, "ok": True},
        db={"reachable": True, "fresh_horse_rows_since_check_time": 0, "ok": False,
            "reason": "no fresh rows yet"},
    )
    assert decision == "HOLD"


def test_atomic_write_json_replaces_correctly(tmp_path):
    target = tmp_path / "out.json"
    mod.atomic_write_json(target, {"a": 1})
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    # 上書き
    mod.atomic_write_json(target, {"b": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"b": 2}
    # tempfile が残っていないこと
    leftover = list(tmp_path.glob("out.*.tmp"))
    assert not leftover, f"tempfiles leaked: {leftover}"


def test_main_writes_latest_and_history(monkeypatch, tmp_path):
    """end-to-end: 正常系で latest と history の両方が保存される"""
    # tmp 環境を構築
    coverage = tmp_path / "coverage.jsonl"
    _write_coverage(coverage, [
        {"run_at": "2026-06-20T09:00:30", "target_date": "20260620",
         "eligible_races": 4, "ok_races": 3, "error_races": 1},
    ])
    db = tmp_path / "test.db"
    _setup_db(db, ["2026-06-20T09:05:00"])
    runtime_dir = tmp_path / "runtime"

    scheduler_info = {
        "registered": True,
        "last_run_time": "2026-06-20T09:00:00",
        "last_task_result": 0,
        "next_run_time": "2026-06-20T09:10:00",
    }
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_fresh_odds_health.py",
            "--scheduler-json", json.dumps(scheduler_info),
            "--date", "20260620",
            "--check-after-time", "09:00",
            "--runtime-dir", str(runtime_dir),
            "--coverage-path", str(coverage),
            "--db-path", str(db),
            "--quiet",
        ],
    )
    exit_code = mod.main()
    assert exit_code == mod.EXIT_PASS
    latest = runtime_dir / "fresh_odds_health_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["decision"] == "PASS"
    # history も書かれている
    histories = list(runtime_dir.glob("fresh_odds_health_*.json"))
    # latest + history の少なくとも 2 ファイル
    assert len(histories) >= 2
