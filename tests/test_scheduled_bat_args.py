from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULED_BATS = (
    ROOT / "scripts" / "auto_predict_daily.bat",
    ROOT / "weekly_monitor.bat",
)
MODULE_CALL_RE = re.compile(r"\s-m\s+(scripts\.[A-Za-z0-9_.]+)(?P<args>.*)$")
OPTION_RE = re.compile(r"(?<!\S)(--[A-Za-z0-9][A-Za-z0-9-]*)(?=[=\s]|$)")


def _declared_options(module_name: str) -> set[str]:
    source_path = ROOT.joinpath(*module_name.split(".")).with_suffix(".py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    options: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith("--"):
                    options.add(arg.value)
    return options


def _scheduled_module_calls(batch_path: Path) -> list[tuple[int, str, set[str]]]:
    calls = []
    for line_number, raw_line in enumerate(
        batch_path.read_text(encoding="ascii").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.upper().startswith("REM "):
            continue
        match = MODULE_CALL_RE.search(line)
        if match:
            calls.append(
                (
                    line_number,
                    match.group(1),
                    set(OPTION_RE.findall(match.group("args"))),
                )
            )
    return calls


def test_scheduled_bat_python_options_are_declared_by_argparse() -> None:
    invalid = []
    for batch_path in SCHEDULED_BATS:
        for line_number, module_name, passed_options in _scheduled_module_calls(batch_path):
            unknown = passed_options - _declared_options(module_name)
            if unknown:
                invalid.append(
                    f"{batch_path.relative_to(ROOT)}:{line_number}: "
                    f"{module_name} does not declare {sorted(unknown)}"
                )

    assert not invalid, "\n".join(invalid)


def test_weekly_monitor_runs_safety_checks_before_isolated_pytest() -> None:
    source = (ROOT / "weekly_monitor.bat").read_text(encoding="ascii")

    monitor_position = source.index("-m scripts.monitor")
    coverage_position = source.index("-m scripts.fresh_odds_coverage")
    pytest_position = source.index("Start-Process")
    assert monitor_position < coverage_position < pytest_position
    assert "WaitForExit(600*1000)" in source
    assert "exit 124" in source
    # PowerShell 5.1: $p.ExitCode is null after WaitForExit(ms) unless the process
    # Handle was touched first. Without this, a red pytest silently exits 0.
    assert "$null=$p.Handle" in source


def test_auto_predict_task_registers_both_daily_triggers() -> None:
    source = (ROOT / "scripts" / "register_auto_predict_task.ps1").read_text(
        encoding="ascii"
    )

    assert '[string]$StartTime = "09:30"' in source
    assert '[string]$SecondStartTime = "11:30"' in source
    assert source.count("New-ScheduledTaskTrigger -Daily -At") == 2
