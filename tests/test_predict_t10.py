"""scripts.predict_t10 — T−10 ランナーの契約テスト (改革 R1-1 step3)。

固定する不変条件:
  1. 対象選定は「発走まで gate 分以内 (または発走後)」— それより前は処理しない
  2. 発走後に処理した記録は actionable=False (「買えたはず」と主張しない)
  3. 冪等: 同じレースを二度記録しない
  4. state ファイルは原子的差し替え (壊れたファイルを残さない)
"""
from __future__ import annotations

from datetime import datetime

import pytest

from scripts import predict_t10

RACE_A = {"race_year": "2026", "race_month_day": "0822", "track_code": "05",
          "kaiji": "01", "nichiji": "01", "race_num": "01", "start_time": "1500"}
RACE_B = {**RACE_A, "race_num": "02", "start_time": "1530"}
RACE_NO_TIME = {**RACE_A, "race_num": "03", "start_time": ""}


def test_due_races_only_inside_gate():
    """14:55 時点では 15:00 発走のみ対象 (15:30 はまだ早い)。"""
    now = datetime(2026, 8, 22, 14, 55)

    got = predict_t10.due_races([RACE_A, RACE_B], now, gate_minutes=10)

    assert [r["race_num"] for r, _ in got] == ["01"]
    assert got[0][1] == pytest.approx(5.0)


def test_due_races_excludes_far_future():
    """14:00 時点ではどちらも対象外 (T−10 に達していない)。"""
    now = datetime(2026, 8, 22, 14, 0)
    assert predict_t10.due_races([RACE_A, RACE_B], now, gate_minutes=10) == []


def test_due_races_includes_after_start():
    """発走後も対象に残す (記録目的。cutoff は T−n なので入力は同一)。"""
    now = datetime(2026, 8, 22, 15, 10)

    got = predict_t10.due_races([RACE_A], now, gate_minutes=10)

    assert got and got[0][1] == pytest.approx(-10.0)


def test_due_races_all_day_ignores_time():
    now = datetime(2026, 8, 22, 6, 0)

    got = predict_t10.due_races([RACE_A, RACE_B], now, gate_minutes=10, all_day=True)

    assert len(got) == 2


def test_due_races_skips_unknown_start_time():
    """start_time 不明は対象外 (T−n を定義できないので安全側)。"""
    now = datetime(2026, 8, 22, 14, 55)

    got = predict_t10.due_races([RACE_NO_TIME], now, gate_minutes=10, all_day=True)

    assert got == []


def test_state_roundtrip_and_idempotency_key(tmp_path, monkeypatch):
    monkeypatch.setattr(predict_t10, "OUT_DIR", tmp_path)
    key = predict_t10._race_key(RACE_A)
    state = predict_t10.load_state("20260822")
    state["races"][key] = {"race_key": key, "actionable": True}

    predict_t10.save_state("20260822", state)
    again = predict_t10.load_state("20260822")

    assert key in again["races"], "記録済みレースは再読込で残る (冪等の出典)"
    assert not list(tmp_path.glob("*.tmp")), "一時ファイルを残さない"


def test_corrupt_state_is_quarantined_not_fatal(tmp_path, monkeypatch):
    """壊れた state で運用を止めない (退避して新規で続行)。"""
    monkeypatch.setattr(predict_t10, "OUT_DIR", tmp_path)
    (tmp_path / "20260822.json").write_text("{not json", encoding="utf-8")

    state = predict_t10.load_state("20260822")

    assert state["races"] == {}
    assert (tmp_path / "20260822.json.bad").exists(), "壊れたファイルは .bad に退避"


def test_race_key_is_stable_and_unique():
    assert predict_t10._race_key(RACE_A) == "20260822-05-01-01-01"
    assert predict_t10._race_key(RACE_A) != predict_t10._race_key(RACE_B)
