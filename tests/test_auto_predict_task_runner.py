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
            "-LogDir",
            str(tmp_path / "logs"),
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
            "-LogDir",
            str(tmp_path / "logs"),
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
            "-LogDir",
            str(tmp_path / "logs"),
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


def test_fetch_full_recovers_incremental_no_data_with_current_week(monkeypatch) -> None:
    from datetime import date
    from scripts import fetch_full

    calls = []
    ingested = []

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def fetch_all(self, **kwargs):
            calls.append(kwargs)
            if kwargs["option"] == 1:
                return [
                    {"dataspec": "RACE", "error": "JVOpen failed rc=-1"},
                    {"dataspec": "HOSE", "error": "JVOpen failed rc=-1"},
                ]
            return [{
                "dataspec": "RACE", "files_written": 1, "records_total": 20,
                "last_timestamp": "20260807112834", "bad_files": [],
                "filenames": ["RACE-WEEK.jvd"],
            }]

    monkeypatch.setattr(fetch_full, "JVLinkClient", FakeClient)
    monkeypatch.setattr(fetch_full, "_current_week_fromtime", lambda: "20260727000000")
    monkeypatch.setattr(
        fetch_full,
        "ingest_all",
        lambda **kwargs: ingested.append(kwargs) or {
            "files_processed": 1, "files_errored": 0, "errors": [],
            "RA": 1, "SE": 19, "HR": 0,
        },
    )
    monkeypatch.setattr(sys, "argv", ["fetch_full", "--ingest"])

    assert fetch_full.main() == 0
    assert calls[1]["option"] == 2
    assert calls[1]["fromtime"] == "20260727000000"
    assert calls[1]["dataspecs"] == ["RACE"]
    assert ingested == [{"dataspecs": ["RACE"], "only_files": {"RACE-WEEK.jvd"}}]


def test_current_week_fromtime_starts_on_previous_monday() -> None:
    from datetime import date
    from scripts.fetch_full import _current_week_fromtime

    assert _current_week_fromtime(date(2026, 8, 8)) == "20260727000000"
    assert _current_week_fromtime(date(2026, 8, 10)) == "20260803000000"


def test_no_data_detection_does_not_match_nearby_error_codes() -> None:
    from scripts.fetch_full import _is_no_data

    assert _is_no_data({"error": "JVOpen failed rc=-1 (該当データなし)"})
    for code in (-10, -101, -111, -116):
        assert not _is_no_data({"error": f"JVOpen failed rc={code}"})


def test_fetch_full_fails_when_catchup_still_has_no_race(monkeypatch) -> None:
    from scripts import fetch_full

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def fetch_all(self, **_kwargs):
            return [{"dataspec": "RACE", "error": "JVOpen failed rc=-1"}]

    monkeypatch.setattr(fetch_full, "JVLinkClient", FakeClient)
    monkeypatch.setattr(fetch_full, "_current_week_fromtime", lambda: "20260803000000")
    monkeypatch.setattr(sys, "argv", ["fetch_full", "--dataspecs", "RACE"])

    assert fetch_full.main() == 1


def _args_probe(tmp_path: Path) -> tuple[Path, Path]:
    """受け取った引数をファイルに書くだけの子コマンド。"""
    seen = tmp_path / "seen.txt"
    fixture = tmp_path / "record-args.cmd"
    fixture.write_text(f'@echo [%*]> "{seen}"\r\n@exit /b 0\r\n', encoding="ascii")
    return fixture, seen


def _run_runner(fixture: Path, *extra: str, timeout: str = "20") -> int:
    # ログは必ず子コマンドの隣の一時ディレクトリへ (本番の watchdog log を触らない)
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-File", str(RUNNER),
         "-TimeoutSeconds", timeout, "-CommandPath", str(fixture),
         "-LogDir", str(fixture.parent / "logs"), *extra],
        cwd=ROOT, check=False, timeout=60,
    ).returncode


import pytest  # noqa: E402


@pytest.mark.parametrize("subdir", ["plain", "with space (x86)", "a&b"])
def test_watchdog_forwards_dry_run_to_the_batch(tmp_path: Path, subdir: str) -> None:
    """-DryRun を付けたときだけ子の bat に --dry-run が渡ること (2026-09-25)。

    渡らないと「dry-run のつもりで本番の取り込み・通知・push が走る」。
    空白・括弧・`&` を含むパスでも見る。cmd は /c の文字列の引用符を条件次第で
    剥がすので、二重に包まないと `&` のところでコマンドが分断される
    (空白と括弧だけなら cmd が推測でたどれてしまい、壊れていても気付けない)。
    """
    d = tmp_path / subdir
    d.mkdir()
    fixture, seen = _args_probe(d)

    assert _run_runner(fixture, "-DryRun") == 0
    assert seen.read_text(encoding="ascii").strip() == "[--dry-run]"

    assert _run_runner(fixture, "-SkipNotification") == 0
    assert seen.read_text(encoding="ascii").strip() == "[]", (
        "-DryRun なしの起動に --dry-run が混ざっている")


def test_dry_run_through_the_scheduler_launcher(tmp_path: Path) -> None:
    """タスクスケジューラと同じ wscript → vbs 経由でも -DryRun が届くこと。

    vbs は引数を 1 つずつ引用符で包む。PowerShell がそれをスイッチとして
    解釈するかを、実際の起動経路で確かめる。
    """
    import os

    vbs = Path(os.environ.get("LOCALAPPDATA", "")) / "ScheduledTaskRunner" / \
        "run-scheduled-task-hidden.vbs"
    if not vbs.exists():
        import pytest
        pytest.skip("この環境には hidden runner (vbs) が無い")
    fixture, seen = _args_probe(tmp_path)
    # wscript は GUI サブシステムなので、終了コードは Start-Process で待って取る。
    ps = (
        f"$p = Start-Process -FilePath \"$env:SystemRoot\\System32\\wscript.exe\" "
        f"-ArgumentList '//B //NoLogo \"{vbs}\" ps1 \"{RUNNER}\" -CommandPath "
        f"\"{fixture}\" -LogDir \"{tmp_path / 'logs'}\" -DryRun' -PassThru; "
        f"$null = $p.Handle; "
        f"$p.WaitForExit(40000) | Out-Null; exit $p.ExitCode"
    )
    rc = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-Command", ps],
                        cwd=ROOT, check=False, timeout=60).returncode
    assert rc == 0
    assert seen.read_text(encoding="ascii").strip() == "[--dry-run]"


def _notify_stub(tmp_path: Path) -> tuple[Path, Path]:
    """watchdog の通知に使うプログラムの代わり。呼ばれたら引数を書き残す。"""
    marker = tmp_path / "notified.txt"
    stub = tmp_path / "notify-stub.cmd"
    stub.write_text(f'@echo %*>> "{marker}"\r\n@exit /b 0\r\n', encoding="ascii")
    return stub, marker


def _hang(tmp_path: Path) -> Path:
    fixture = tmp_path / "hang.cmd"
    fixture.write_text("@ping 127.0.0.1 -n 30 >nul\r\n", encoding="ascii")
    return fixture


def test_a_dry_run_timeout_never_notifies(tmp_path: Path) -> None:
    """★ -DryRun ならタイムアウトしても Discord へ送らないこと (2026-09-25)。

    以前は -DryRun で SkipNotification を立てるだけで、それを固定するテストが
    無かった (変異 P-4 が生存)。通知関数の中でも DryRun を見て止める。
    """
    stub, marker = _notify_stub(tmp_path)

    rc = _run_runner(_hang(tmp_path), "-DryRun", "-NotifyPython", str(stub),
                     timeout="1")

    assert rc == 124
    assert not marker.exists(), f"dry-run で通知した: {marker.read_text()}"
    log = (tmp_path / "logs" / "auto_predict_watchdog.log").read_text(encoding="ascii")
    assert "notification suppressed: dry-run" in log


def test_a_real_timeout_does_notify(tmp_path: Path) -> None:
    """対照: dry-run でない起動のタイムアウトは通知すること (止めすぎていない)。"""
    stub, marker = _notify_stub(tmp_path)

    rc = _run_runner(_hang(tmp_path), "-NotifyPython", str(stub), timeout="1")

    assert rc == 124
    assert marker.exists(), "本番のタイムアウトで通知していない"
    assert "scripts.notify_discord" in marker.read_text(encoding="ascii")


def test_runner_tests_leave_the_production_log_alone() -> None:
    """このファイルの runner 呼び出しが、すべてログを一時ディレクトリへ向けていること。

    runner は既定で「自分のリポジトリの data/logs」に書く。main でテストを
    回すと、本番の watchdog log (「沈黙 = 未起動」を読む運用ログ) にテストの
    行が混ざる (実測 1,396 行中 426 行)。実行時の確認は conftest の
    セッション fixture が行う。
    """
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            items = [ast.unparse(e) for e in node.elts]
            if "str(RUNNER)" in items:
                assert "'-LogDir'" in items, (
                    f"-LogDir の無い runner 呼び出し (line {node.lineno})")


def test_skip_notification_is_honoured_on_timeout(tmp_path: Path) -> None:
    """-SkipNotification (dry-run ではない) でもタイムアウト時に通知しないこと。

    既存のタイムアウトのテストは -SkipNotification を付けていたが、通知が
    実際に止まったかは見ていなかった (変異 A3 が見えなかった)。
    """
    stub, marker = _notify_stub(tmp_path)

    rc = _run_runner(_hang(tmp_path), "-SkipNotification", "-NotifyPython", str(stub),
                     timeout="1")

    assert rc == 124
    assert not marker.exists(), "-SkipNotification なのに通知した"
    log = (tmp_path / "logs" / "auto_predict_watchdog.log").read_text(encoding="ascii")
    assert "notification suppressed: -SkipNotification" in log
