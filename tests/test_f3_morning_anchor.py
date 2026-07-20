from __future__ import annotations

from pathlib import Path

from scripts import fetch_fresh_odds


ROOT = Path(__file__).resolve().parent.parent
MORNING_BAT = ROOT / "scripts" / "fetch_morning_odds.bat"
REGISTER_PS1 = ROOT / "scripts" / "register_morning_odds_task.ps1"


def test_morning_batch_has_fixed_effective_window_and_32bit_python() -> None:
    source = MORNING_BAT.read_text(encoding="ascii")
    assert ".venv32\\Scripts\\python.exe" in source
    assert "--window 600 --min-lead 0" in source
    assert 'findstr /C:"window=0-600min"' in source
    assert "min_lead=0 >>" in source
    assert "rc=%EXIT_CODE% >>" in source
    assert "fetch_morning_odds.log" in source
    assert "%*" not in source


def test_registration_is_daily_and_bounded() -> None:
    source = REGISTER_PS1.read_text(encoding="ascii")
    assert 'TaskName = "keiba-morning-odds"' in source
    assert 'StartTime = "08:45"' in source
    assert "New-ScheduledTaskTrigger -Daily" in source
    assert "ExecutionTimeLimit" in source
    assert "MultipleInstances IgnoreNew" in source
    assert "fetch_morning_odds.bat" in source


def test_live_and_morning_processes_share_single_run_lock(tmp_path, monkeypatch) -> None:
    lock_path = tmp_path / "fetch_fresh_odds.lock"
    monkeypatch.setattr(fetch_fresh_odds, "LOCK_PATH", lock_path)

    with fetch_fresh_odds.single_run_lock() as first:
        with fetch_fresh_odds.single_run_lock() as second:
            assert first is True
            assert second is False

    assert not lock_path.exists()


def test_new_scripts_are_ascii() -> None:
    MORNING_BAT.read_bytes().decode("ascii")
    REGISTER_PS1.read_bytes().decode("ascii")
