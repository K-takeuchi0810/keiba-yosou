from __future__ import annotations

import subprocess
import sys
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
            "-SkipNotification",
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
            "-SkipNotification",
        ],
        cwd=ROOT,
        check=False,
        timeout=15,
    )
    assert got.returncode == 124
    assert time.monotonic() - started < 10


def test_watchdog_removes_a_grandchild_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    quoted_pid_file = str(pid_file).replace("'", "''")
    fixture = tmp_path / "hang-with-grandchild.cmd"
    fixture.write_text(
        '@start "" /b powershell.exe -NoLogo -NoProfile -NonInteractive '
        f'-Command "$PID | Set-Content -LiteralPath \'{quoted_pid_file}\'; '
        'Start-Sleep -Seconds 30"\r\n'
        '@ping 127.0.0.1 -n 30 >nul\r\n',
        encoding="ascii",
    )
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
            "2",
            "-CommandPath",
            str(fixture),
            "-SkipNotification",
        ],
        cwd=ROOT,
        check=False,
        timeout=15,
    )
    assert got.returncode == 124
    assert pid_file.exists()
    child_pid = int(pid_file.read_text(encoding="utf-8").strip())
    probe = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"if (Get-Process -Id {child_pid} -ErrorAction SilentlyContinue) {{ exit 1 }}",
        ],
        check=False,
        timeout=10,
    )
    assert probe.returncode == 0


def test_watchdog_has_bounded_tree_termination() -> None:
    text = RUNNER.read_text(encoding="ascii")
    assert "$process.WaitForExit($TimeoutSeconds * 1000)" in text
    assert "taskkill.exe /PID $process.Id /T /F" in text
    assert "$killExitCode -ne 0 -and -not $process.HasExited" in text
    assert "tree still running after termination" in text
    assert "exit 125" in text
    assert "exit 124" in text
    assert "scripts.notify_discord" in text
    assert "Send-WatchdogAlert" in text


def test_registered_task_uses_watchdog_before_first_race() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    assert '[string]$StartTime = "08:00"' in text
    assert '[string]$SecondStartTime = "09:00"' in text
    assert "run_auto_predict_daily.ps1" in text
    assert "-Trigger $trigger" in text
    assert "-Trigger $triggers" not in text


def test_daily_fetch_logs_progress_without_buffering() -> None:
    text = DAILY.read_text(encoding="utf-8")
    assert ".venv32\\Scripts\\python.exe -u -m scripts.fetch_full --ingest" in text


def test_fetch_full_ingests_only_the_fetched_files(monkeypatch) -> None:
    from scripts import fetch_full

    summaries = [{
        "dataspec": "RACE",
        "files_written": 1,
        "records_total": 10,
        "last_timestamp": "20260808090000",
        "bad_files": [],
        "filenames": ["RATEST.jvd"],
    }]
    calls = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def fetch_all(self, **_kwargs):
            return summaries

    def fake_ingest_all(**kwargs):
        calls.append(kwargs)
        return {"files_processed": 1, "files_errored": 0, "errors": [],
                "RA": 1, "SE": 9, "HR": 0}

    monkeypatch.setattr(fetch_full, "JVLinkClient", FakeClient)
    monkeypatch.setattr(fetch_full, "ingest_all", fake_ingest_all)
    monkeypatch.setattr(sys, "argv", ["fetch_full", "--dataspecs", "RACE", "--ingest"])
    assert fetch_full.main() == 0
    assert calls == [{"dataspecs": ["RACE"], "only_files": {"RATEST.jvd"}}]


def test_fetch_full_returns_nonzero_for_caught_jvlink_error(monkeypatch) -> None:
    from scripts import fetch_full

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def fetch_all(self, **_kwargs):
            return [{"dataspec": "RACE", "error": "JVOpen failed"}]

    monkeypatch.setattr(fetch_full, "JVLinkClient", FakeClient)
    monkeypatch.setattr(sys, "argv", ["fetch_full", "--dataspecs", "RACE", "--ingest"])
    assert fetch_full.main() == 1


def test_fetch_full_returns_nonzero_for_ingest_error(monkeypatch) -> None:
    from scripts import fetch_full

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def fetch_all(self, **_kwargs):
            return [{
                "dataspec": "RACE", "files_written": 1, "records_total": 1,
                "last_timestamp": "20260808090000", "bad_files": [],
                "filenames": ["BROKEN.jvd"],
            }]

    monkeypatch.setattr(fetch_full, "JVLinkClient", FakeClient)
    monkeypatch.setattr(
        fetch_full,
        "ingest_all",
        lambda **_kwargs: {
            "files_processed": 0, "files_errored": 1,
            "errors": [{"file": "BROKEN.jvd", "error": "bad record"}],
            "RA": 0, "SE": 0, "HR": 0,
        },
    )
    monkeypatch.setattr(sys, "argv", ["fetch_full", "--dataspecs", "RACE", "--ingest"])
    assert fetch_full.main() == 2


def test_fetch_full_returns_nonzero_for_bad_raw_file(monkeypatch) -> None:
    from scripts import fetch_full

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def fetch_all(self, **_kwargs):
            return [{
                "dataspec": "RACE", "files_written": 0, "records_total": 0,
                "last_timestamp": "20260808090000",
                "bad_files": ["CORRUPT.jvd"], "filenames": [],
            }]

    monkeypatch.setattr(fetch_full, "JVLinkClient", FakeClient)
    monkeypatch.setattr(sys, "argv", ["fetch_full", "--dataspecs", "RACE"])
    assert fetch_full.main() == 1
