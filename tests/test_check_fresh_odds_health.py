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


def test_coverage_morning_source_not_contamination(tmp_path):
    """朝の一括取得 (source=morning, 08:45) を混入と誤検知しないこと。

    keiba-morning-odds が発走直前バッチと同じ JSONL に 08:45 (稼働窓 08:55-16:50 外)
    で書くため、時刻窓だけで判定すると開催日は毎回 FAIL する。source ベース判定で回避。
    """
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T08:45:03", "target_date": "20260620",
         "source": "morning", "eligible_races": 36, "ok_races": 36, "error_races": 0},
        {"run_at": "2026-06-20T16:20:01", "target_date": "20260620",
         "source": "fresh", "eligible_races": 2, "ok_races": 2, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is False
    assert out["ok"] is True
    assert out["runs_today_by_source"] == {"morning": 1, "fresh": 1}


def test_coverage_unknown_source_is_contamination(tmp_path):
    """未知の source (例: test 由来の pytest) は混入として検知し続けること。"""
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T10:00:00", "target_date": "20260620",
         "source": "fresh", "eligible_races": 1, "ok_races": 1, "error_races": 0},
        {"run_at": "2026-06-20T03:00:00", "target_date": "20260620",
         "source": "pytest", "eligible_races": 1, "ok_races": 1, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is True
    assert out["ok"] is False
    assert out["contamination_examples"][0]["why"] == "unknown_source"


def test_coverage_untagged_outside_windows_is_contamination(tmp_path):
    """source 無し (旧形式) で fresh/morning いずれの窓にも入らない深夜 run_at は混入。"""
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T10:00:00", "target_date": "20260620",
         "source": "fresh", "eligible_races": 1, "ok_races": 1, "error_races": 0},
        {"run_at": "2026-06-20T03:00:00", "target_date": "20260620",
         "eligible_races": 1, "ok_races": 1, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is True
    assert out["contamination_examples"][0]["why"] == "untagged_outside_known_windows"


def test_coverage_untagged_in_morning_window_not_contamination(tmp_path):
    """後方互換: 旧 bat が書いた無タグ morning 行 (08:40-08:54) を混入としないこと。

    untagged の正当帯を morning 窓ぶん拡大した意図的変更点。将来のリファクタで
    この救済が壊れると開催日の恒久誤検知が復活するため回帰固定する。
    """
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        # 旧 bat が書いた無タグ morning 行 (check_after 09:00 より前 = ok 集計外)
        {"run_at": "2026-06-20T08:47:03", "target_date": "20260620",
         "eligible_races": 36, "ok_races": 36, "error_races": 0},
        # 窓内の有効行 (ok=True 成立用)
        {"run_at": "2026-06-20T09:10:00", "target_date": "20260620",
         "eligible_races": 5, "ok_races": 5, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is False  # 08:47 untagged は morning 窓で救済
    assert out["ok"] is True


def test_coverage_known_source_outside_window_is_warn_not_fail(tmp_path):
    """既知 source (fresh) が窓外 → 混入 (FAIL) でなく source_time_mismatch (WARN)。

    現実の混入ベクタ (pytest が default --source fresh で深夜に書く) を可視化しつつ、
    decision は不変 (alert fatigue 再発防止)。
    """
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T10:00:00", "target_date": "20260620",
         "source": "fresh", "eligible_races": 1, "ok_races": 1, "error_races": 0},
        {"run_at": "2026-06-20T03:00:00", "target_date": "20260620",
         "source": "fresh", "eligible_races": 1, "ok_races": 0, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is False
    assert out["ok"] is True  # WARN は decision を変えない
    assert len(out["source_time_mismatch_examples"]) == 1
    assert out["source_time_mismatch_examples"][0]["why"] == "fresh_outside_window"
    assert "WARN" in out["reason"]


def test_coverage_manual_source_is_time_unrestricted(tmp_path):
    """source=manual は意図的な任意時刻実行なので時刻不問 (混入も mismatch もなし)。"""
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T10:00:00", "target_date": "20260620",
         "source": "fresh", "eligible_races": 1, "ok_races": 1, "error_races": 0},
        {"run_at": "2026-06-20T03:00:00", "target_date": "20260620",
         "source": "manual", "eligible_races": 1, "ok_races": 0, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is False
    assert out["source_time_mismatch_examples"] == []


def test_coverage_dry_run_row_excluded_from_detection(tmp_path):
    """dry-run 行 (プレビュー、実取得なし) は混入/mismatch 判定から除外されること。"""
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-06-20T10:00:00", "target_date": "20260620",
         "source": "fresh", "eligible_races": 1, "ok_races": 1, "error_races": 0},
        {"run_at": "2026-06-20T17:02:00", "target_date": "20260620",
         "source": "morning", "dry_run": True,
         "eligible_races": 6, "ok_races": 0, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260620", time(9, 0))
    assert out["contamination_detected"] is False
    assert out["source_time_mismatch_examples"] == []


def test_coverage_fresh_summer_evening_within_extended_window(tmp_path):
    """夏季後ろ倒し対応で fresh 窓を 19:10 まで延長。18:00 の fresh 実行は正当 (mismatch でない)、
    19:30 は窓外 → mismatch WARN。et (register_fresh_odds_task.ps1) と窓終端の同期を固定する。
    """
    p = tmp_path / "coverage.jsonl"
    _write_coverage(p, [
        {"run_at": "2026-07-25T10:00:00", "target_date": "20260725",
         "source": "fresh", "eligible_races": 1, "ok_races": 1, "error_races": 0},
        {"run_at": "2026-07-25T18:00:00", "target_date": "20260725",
         "source": "fresh", "eligible_races": 1, "ok_races": 1, "error_races": 0},
        {"run_at": "2026-07-25T19:30:00", "target_date": "20260725",
         "source": "fresh", "eligible_races": 1, "ok_races": 0, "error_races": 0},
    ])
    out = mod.evaluate_coverage(p, "20260725", time(9, 0))
    assert out["contamination_detected"] is False
    mm = out["source_time_mismatch_examples"]
    assert len(mm) == 1 and mm[0]["run_at"] == "2026-07-25T19:30:00"


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
