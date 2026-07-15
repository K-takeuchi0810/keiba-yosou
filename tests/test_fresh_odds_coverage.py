"""scripts.fresh_odds_coverage の単体テスト。

P25 Plan Step 4 の「fresh odds 取得の安定稼働確認」を運用する監視スクリプト。
JSONL を読んで集計し、ok_rate や eligible 累計を CLI 出力する。
"""
from __future__ import annotations

import json
from datetime import datetime

import scripts.fresh_odds_coverage as mod


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")


def test_load_records_skips_empty_and_invalid_lines(tmp_path):
    p = tmp_path / "cov.jsonl"
    p.write_text(
        '{"target_date": "20260620", "eligible_races": 5}\n'
        "\n"
        "not-valid-json\n"
        '{"target_date": "20260621", "eligible_races": 3}\n',
        encoding="utf-8",
    )
    recs = mod._load_records(p)
    assert len(recs) == 2
    assert recs[0]["target_date"] == "20260620"
    assert recs[1]["target_date"] == "20260621"


def test_aggregate_computes_rates_and_failed_reasons():
    runs = [
        {"eligible_races": 4, "fetched_races": 4, "ok_races": 4, "error_races": 0,
         "total_records": 320, "failed_reason": {}, "lock_skipped": False},
        {"eligible_races": 6, "fetched_races": 5, "ok_races": 4, "error_races": 1,
         "total_records": 410, "failed_reason": {"TimeoutError": 1}, "lock_skipped": False},
        {"eligible_races": 5, "fetched_races": 3, "ok_races": 2, "error_races": 2,
         "total_records": 180, "failed_reason": {"ComError": 1, "TimeoutError": 1},
         "lock_skipped": False},
    ]
    agg = mod._aggregate(runs)
    assert agg["runs"] == 3
    assert agg["eligible_total"] == 15
    assert agg["fetched_total"] == 12
    assert agg["ok_total"] == 10
    assert agg["fetched_rate_pct"] == 80.0  # 12/15
    assert agg["ok_rate_pct"] == round(10 / 15 * 100, 1)  # 66.7
    assert agg["failed_reasons"] == {"TimeoutError": 2, "ComError": 1}
    assert agg["total_records"] == 910


def test_filter_records_by_target_date():
    records = [
        {"target_date": "20260620"},
        {"target_date": "20260621"},
        {"target_date": "20260621"},
    ]
    filtered = mod._filter_records(records, last_days=None, target_date="20260621")
    assert len(filtered) == 2
    assert all(r["target_date"] == "20260621" for r in filtered)


def test_group_by_date_sorts_keys():
    records = [
        {"target_date": "20260621", "eligible_races": 4},
        {"target_date": "20260620", "eligible_races": 5},
        {"target_date": "20260620", "eligible_races": 6},
    ]
    grouped = mod._group_by_date(records)
    assert list(grouped.keys()) == ["20260620", "20260621"]
    assert len(grouped["20260620"]) == 2


def test_aggregate_handles_empty_records():
    agg = mod._aggregate([])
    assert agg["runs"] == 0
    assert agg["fetched_rate_pct"] == 0.0
    assert agg["failed_reasons"] == {}


def test_main_with_missing_file(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "does_not_exist.jsonl"
    monkeypatch.setattr(mod, "COVERAGE_LOG_PATH", missing)
    monkeypatch.setattr("sys.argv", ["fresh_odds_coverage.py"])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "no coverage records" in out


def test_main_prints_report_with_aggregate(monkeypatch, tmp_path, capsys):
    p = tmp_path / "cov.jsonl"
    _write_jsonl(p, [
        {"target_date": "20260620", "eligible_races": 4, "fetched_races": 4, "ok_races": 4,
         "error_races": 0, "total_records": 320, "failed_reason": {}, "lock_skipped": False},
        {"target_date": "20260620", "eligible_races": 3, "fetched_races": 2, "ok_races": 2,
         "error_races": 1, "total_records": 150, "failed_reason": {"TimeoutError": 1},
         "lock_skipped": False},
    ])
    monkeypatch.setattr(mod, "COVERAGE_LOG_PATH", p)
    monkeypatch.setattr("sys.argv", ["fresh_odds_coverage.py"])
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "20260620" in out
    assert "TimeoutError" in out
    # Plan Step 4 参考表示
    assert "Plan Step 4 参考" in out


def test_find_run_gaps_detects_only_intervals_over_15_minutes():
    rows = [
        {"run_at": "2026-07-12T09:00:03"},
        {"run_at": "2026-07-12T09:10:03"},
        {"run_at": "2026-07-12T09:30:03"},
    ]

    gaps = mod._find_run_gaps(rows, now=datetime(2026, 7, 12, 9, 30))
    assert len(gaps) == 1
    assert gaps[0][0].strftime("%H:%M") == "09:10"
    assert gaps[0][1].strftime("%H:%M") == "09:30"
    assert gaps[0][2] == 20


def test_find_run_gaps_detects_missing_morning_edge():
    rows = [
        {"target_date": "20260712", "run_at": "2026-07-12T09:20:00"},
        {"target_date": "20260712", "run_at": "2026-07-12T16:40:00"},
    ]
    gaps = mod._find_run_gaps(rows)
    assert (gaps[0][0].strftime("%H:%M"), gaps[0][1].strftime("%H:%M"), gaps[0][2]) == (
        "09:00", "09:20", 20
    )


def test_find_run_gaps_detects_missing_evening_edge():
    rows = [
        {"target_date": "20260712", "run_at": "2026-07-12T09:00:00"},
        {"target_date": "20260712", "run_at": "2026-07-12T16:20:00"},
    ]
    gaps = mod._find_run_gaps(rows)
    assert (gaps[-1][0].strftime("%H:%M"), gaps[-1][1].strftime("%H:%M"), gaps[-1][2]) == (
        "16:20", "16:40", 20
    )


def test_main_warns_when_open_day_has_zero_runs(monkeypatch, tmp_path, capsys):
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "_load_open_dates", lambda *_: {"20260712"})
    monkeypatch.setattr(
        "sys.argv",
        ["fresh_odds_coverage.py", "--path", str(p), "--date", "20260712", "--check-gaps"],
    )
    assert mod.main() == 1
    assert "WARNING: all runs missing 20260712" in capsys.readouterr().out


def test_main_does_not_warn_for_non_open_day(monkeypatch, tmp_path, capsys):
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "_load_open_dates", lambda *_: set())
    monkeypatch.setattr(
        "sys.argv",
        ["fresh_odds_coverage.py", "--path", str(p), "--date", "20260713", "--check-gaps"],
    )
    assert mod.main() == 0
    assert "WARNING:" not in capsys.readouterr().out


def test_main_check_gaps_warns_and_returns_one(monkeypatch, tmp_path, capsys):
    p = tmp_path / "cov.jsonl"
    _write_jsonl(p, [
        {"target_date": "20260712", "run_at": "2026-07-12T11:50:03"},
        {"target_date": "20260712", "run_at": "2026-07-12T14:00:03"},
    ])
    monkeypatch.setattr(
        "sys.argv",
        ["fresh_odds_coverage.py", "--path", str(p), "--date", "20260712", "--check-gaps"],
    )
    monkeypatch.setattr(mod, "_load_open_dates", lambda *_: {"20260712"})

    assert mod.main() == 1
    assert "WARNING: gap 11:50->14:00 (130m)" in capsys.readouterr().out


def test_main_gap_check_is_opt_in(monkeypatch, tmp_path, capsys):
    p = tmp_path / "cov.jsonl"
    _write_jsonl(p, [
        {"target_date": "20260712", "run_at": "2026-07-12T11:50:03"},
        {"target_date": "20260712", "run_at": "2026-07-12T14:00:03"},
    ])
    monkeypatch.setattr(
        "sys.argv",
        ["fresh_odds_coverage.py", "--path", str(p), "--date", "20260712"],
    )

    assert mod.main() == 0
    assert "WARNING: gap" not in capsys.readouterr().out
