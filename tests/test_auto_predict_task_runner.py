from __future__ import annotations

import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_auto_predict_daily.ps1"
REGISTER = ROOT / "scripts" / "register_auto_predict_task.ps1"
DAILY = ROOT / "scripts" / "auto_predict_daily.bat"


def test_watchdog_preserves_child_exit_code(tmp_path: Path) -> None:
    fixture = tmp_path / "exit-seven.cmd"
    fixture.write_text("@exit /b 7\r\n", encoding="ascii")
    got = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-TimeoutSeconds",
            "10",
            "-CommandPath",
            str(fixture),
        ],
        cwd=ROOT,
        check=False,
        timeout=20,
    )
    assert got.returncode == 7


def test_watchdog_times_out_and_returns_124(tmp_path: Path) -> None:
    fixture = tmp_path / "hang.cmd"
    fixture.write_text("@ping 127.0.0.1 -n 30 >nul\r\n", encoding="ascii")
    started = time.monotonic()
    got = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-TimeoutSeconds",
            "1",
            "-CommandPath",
            str(fixture),
        ],
        cwd=ROOT,
        check=False,
        timeout=15,
    )
    assert got.returncode == 124
    assert time.monotonic() - started < 10


def test_watchdog_has_bounded_tree_termination() -> None:
    text = RUNNER.read_text(encoding="ascii")
    assert "$process.WaitForExit($TimeoutSeconds * 1000)" in text
    assert "taskkill.exe /PID $process.Id /T /F" in text
    assert "$killExitCode -ne 0 -and -not $process.HasExited" in text
    assert "tree still running after termination" in text
    assert "exit 125" in text
    assert "exit 124" in text


def test_registered_task_uses_watchdog_before_first_race() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    assert '[string]$StartTime = "08:00"' in text
    assert '[string]$SecondStartTime = "09:00"' in text
    assert "run_auto_predict_daily.ps1" in text
    assert "-Trigger $trigger" in text
    assert "-Trigger $triggers" not in text


def test_daily_fetch_logs_progress_without_buffering() -> None:
    text = DAILY.read_text(encoding="utf-8")
    assert ".venv32\\Scripts\\python.exe -u -m scripts.fetch_full" in text
