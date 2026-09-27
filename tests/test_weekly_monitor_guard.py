"""週次監視 (`weekly_monitor.bat`) と conftest の見張りが両立すること (2026-09-26)。

## なぜ要るか

`tests/conftest.py` の見張りは、テストの前後で `data/logs` / `data/runtime` が
変われば失敗する。週次監視は本番 checkout で `pytest tests/` を回し、しかも
日曜 10:00 は fresh odds の取得 (10 分ごと) などが同じ `data/logs` に書くので、
この見張りは必ず落ちる (2026-09-26 のレビューで再現)。

そこで見張りは 2 値にした:
  strict (既定) : 変化があれば失敗
  off           : 週次監視専用。この見張りだけを止める。未知の値は失敗

## 方法

一時ディレクトリに小さなリポジトリを作り、**本物の weekly_monitor.bat と
本物の conftest** を置く。bat が呼ぶ `scripts.monitor` などは記録だけする
スタブ。別スレッドで `data/logs` に書き続けて、同時刻の正規タスクを模す。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from runtime_guard import RUNTIME_GUARD_ENV, child_pytest_env

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe が要る")

REPO = Path(__file__).resolve().parents[1]
VENV = Path(sys.executable).resolve().parents[1]

_STUB = """import sys, pathlib
p = pathlib.Path(__file__).resolve().parents[1] / "calls.txt"
with p.open("a", encoding="utf-8") as f:
    f.write(__name__ + " " + " ".join(sys.argv[1:]) + chr(10))
"""

#: 仮のリポジトリの中で流れるテスト。off でも通知の状態ファイルの隔離は
#: 効いていること (見張り以外の安全策は止まらないこと) を中から確かめる。
_INNER_TEST = """import os, pathlib

def test_notification_state_is_still_isolated(tmp_path):
    state = os.environ.get("NOTIFY_STATE_PATH", "")
    assert state and pathlib.Path(state).parent == tmp_path

def test_ok():
    assert True

def test_takes_a_moment():
    # 本物の週次監視の pytest は数分かかる。0.5 秒あれば、20 ms ごとに書く
    # 「同時刻の別タスク」が必ずセッションの途中に書き込む。
    import time
    time.sleep(0.5)
"""


@pytest.fixture()
def weekly_repo(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "data" / "logs").mkdir(parents=True)
    (root / "data" / "runtime").mkdir()
    shutil.copy(REPO / "weekly_monitor.bat", root / "weekly_monitor.bat")
    shutil.copy(REPO / "tests" / "conftest.py", root / "tests" / "conftest.py")
    shutil.copy(REPO / "runtime_guard.py", root / "runtime_guard.py")
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_inner.py").write_text(_INNER_TEST, encoding="utf-8")
    (root / "scripts" / "__init__.py").write_text("")
    for m in ("monitor", "fresh_odds_coverage", "notify_discord"):
        (root / "scripts" / f"{m}.py").write_text(_STUB.replace("__name__", repr(m)),
                                                 encoding="utf-8")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(root / ".venv64"), str(VENV)],
                   check=True, capture_output=True)
    yield root
    os.rmdir(root / ".venv64")


class _ConcurrentWriter:
    """同じ時間帯に data/logs へ書く別の定期タスクの代わり。"""

    def __init__(self, logs: Path):
        self._path = logs / "fresh_odds_concurrent.log"
        self._stop = threading.Event()
        self.writes = 0
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            with self._path.open("a", encoding="ascii") as f:
                f.write(f"tick {self.writes}\n")
            self.writes += 1
            time.sleep(0.02)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()


def _env(guard: str | None = None) -> dict:
    """子プロセスの環境。runtime_guard.child_pytest_env (見張りは strict) を基にする。

    `guard` を渡したときだけ見張りのモードを書き換える (未知の値の確認など)。
    """
    env = child_pytest_env()
    if guard is not None:
        env[RUNTIME_GUARD_ENV] = guard
    return env


def _calls(root: Path) -> list[str]:
    p = root / "calls.txt"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def test_the_weekly_monitor_passes_while_others_write_logs(weekly_repo):
    """★ 同時刻に別のタスクが data/logs に書いていても、週次監視は exit 0 で終わること。

    9/27 (日) 10:00 と同じ条件 (本番 checkout で pytest、同じ時間帯に
    fresh odds などが data/logs へ書く) の再現。
    """
    with _ConcurrentWriter(weekly_repo / "data" / "logs") as w:
        r = subprocess.run(["cmd", "/d", "/c", str(weekly_repo / "weekly_monitor.bat")],
                           cwd=weekly_repo.parent, env=_env(), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
    assert w.writes > 0, "同時書き込みが起きていない (再現になっていない)"

    assert r.returncode == 0, r.stdout[-1500:]
    assert not any(c.startswith("'notify_discord'") or c.startswith("notify_discord")
                   for c in _calls(weekly_repo)), "緑なのに警告を送った"


def test_pytest_output_does_not_go_to_data_logs(weekly_repo):
    """★ 週次監視の pytest の出力は data/logs に書かず、data/monitor_runs に書くこと。"""
    subprocess.run(["cmd", "/d", "/c", str(weekly_repo / "weekly_monitor.bat")],
                   cwd=weekly_repo.parent, env=_env(), capture_output=True,
                   timeout=300)

    runs = list((weekly_repo / "data" / "monitor_runs").glob("weekly_pytest_*.log"))
    assert len(runs) == 1, runs
    assert "passed" in runs[0].read_text(encoding="utf-8", errors="replace")
    weekly_logs = list((weekly_repo / "data" / "logs").glob("weekly_monitor_*.log"))
    assert len(weekly_logs) == 1
    text = weekly_logs[0].read_text(encoding="utf-8", errors="replace")
    assert "passed" not in text, "pytest の出力が data/logs の週次ログに入っている"
    assert "runtime_guard=off pytest_exit=0 full_output=" in text, (
        "週次ログに見張りのモード・pytest の結果・出力の置き場所が残っていない")
    assert "weekly_pytest_" in text
    assert not list((weekly_repo / "data" / "monitor_runs").glob("*.stderr")), (
        "空の .stderr を残している")


def test_the_same_writes_fail_a_strict_run(weekly_repo):
    """対照: 同じ同時書き込みの下で strict (既定) の pytest は失敗すること。

    off が効いているから緑になるのであって、見張り自体が壊れて緑になっている
    わけではないことを確かめる。
    """
    with _ConcurrentWriter(weekly_repo / "data" / "logs"):
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "--rootdir", str(weekly_repo), str(weekly_repo / "tests")],
                           cwd=weekly_repo, env=_env(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)

    assert r.returncode != 0
    assert "運用ログ置き場を変更した" in r.stdout


@pytest.mark.parametrize("value", ["foo", "warn", "OFFF", "0"])
def test_an_unknown_guard_value_stops_pytest(weekly_repo, value):
    """★ 未知の値は黙って off にせず、テストを 1 本も流さずに止めること。"""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "--rootdir", str(weekly_repo), str(weekly_repo / "tests")],
                       cwd=weekly_repo, env=_env(guard=value),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)

    assert r.returncode != 0
    assert "KEIBA_RUNTIME_GUARD" in (r.stdout + r.stderr)
    assert "passed" not in r.stdout, "未知の値なのにテストが流れた"


@pytest.mark.parametrize("value", ["strict", "STRICT", ""])
def test_strict_is_the_default_and_detects_changes(weekly_repo, value):
    """strict (明示・大文字・空) では、ログ置き場への書き込みを検出して失敗すること。"""
    (weekly_repo / "tests" / "test_leak.py").write_text(
        "import pathlib\n"
        "def test_leak():\n"
        "    root = pathlib.Path(__file__).resolve().parents[1]\n"
        "    (root / 'data' / 'logs' / 'leak.log').write_text('x')\n")

    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "--rootdir", str(weekly_repo), str(weekly_repo / "tests")],
                       cwd=weekly_repo, env=_env(guard=value),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)

    assert r.returncode != 0
    assert "運用ログ置き場を変更した" in r.stdout


def _run_weekly(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["cmd", "/d", "/c", str(root / "weekly_monitor.bat")],
                          cwd=root.parent, env=_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)


def _weekly_log(root: Path) -> str:
    logs = list((root / "data" / "logs").glob("weekly_monitor_*.log"))
    assert len(logs) == 1, logs
    return logs[0].read_text(encoding="utf-8", errors="replace")


def test_the_real_conftest_guard_tests_pass_under_the_weekly_monitor(weekly_repo):
    """★ 本物の tests/test_conftest_guard.py を含めても、週次監視 (外側 off) が exit 0 で終わること。

    このテストは中で pytest を起動し「ログに書くテストは失敗する」ことを確かめる。
    外側の off が入れ子に届くと、ここが週次監視でだけ落ちる (2026-09-26 に 3 名が再現)。
    別スレッドの同時書き込みも併せる (9/27 10:00 と同じ条件)。
    """
    shutil.copy(REPO / "tests" / "test_conftest_guard.py",
                weekly_repo / "tests" / "test_conftest_guard.py")

    with _ConcurrentWriter(weekly_repo / "data" / "logs") as w:
        r = _run_weekly(weekly_repo)
    assert w.writes > 0

    log = _weekly_log(weekly_repo)
    out = (weekly_repo / "data" / "monitor_runs").glob("weekly_pytest_*.log")
    detail = "".join(p.read_text(encoding="utf-8", errors="replace") for p in out)
    assert r.returncode == 0, f"{log[-600:]}\n{detail[-1500:]}"
    assert "runtime_guard=off pytest_exit=0" in log
    assert "test_conftest_guard" not in detail or "failed" not in detail


def test_a_red_pytest_sets_bit_2_and_notifies(weekly_repo):
    """★ pytest が赤ければ、週次監視の終了コードにビット 2 が立ち、通知の経路へ進むこと。

    pytest を流しているだけでは「失敗を運用側へ伝えている」ことにならない。
    終了コードを捨てる変異 (V-W26 / B7) が生存していた。
    """
    (weekly_repo / "tests" / "test_red.py").write_text(
        "def test_red():\n    assert False, 'intentionally red'\n", encoding="utf-8")

    r = _run_weekly(weekly_repo)

    assert r.returncode == 2, f"pytest の失敗がビット 2 になっていない: exit {r.returncode}"
    log = _weekly_log(weekly_repo)
    assert "runtime_guard=off pytest_exit=1" in log
    notified = [c for c in _calls(weekly_repo) if c.startswith("notify_discord")]
    assert notified and "pytest=1" in notified[0], (
        f"pytest の失敗で通知の経路に進んでいない: {_calls(weekly_repo)}")


def test_pytest_stderr_is_kept_in_the_same_log(weekly_repo):
    """pytest の stderr も同じ 1 つのログに残り、.stderr ファイルは残さないこと。

    未知の見張りの値のような利用上の誤りは stderr にしか出ない。別ファイルのままだと、
    週次ログが指す「full output」に原因が無くなる。
    """
    # pytest はテスト中の stderr をファイル記述子ごと捕まえるので、捕捉が外れた後
    # (プロセスの終了時) に書く。利用上の誤りのように、pytest の外側で出る stderr の代わり。
    (weekly_repo / "tests" / "test_stderr.py").write_text(
        "import atexit, os\n\n"
        "def test_writes_stderr_at_exit():\n"
        "    atexit.register(lambda: os.write(2, b'MARKER-ON-STDERR' + bytes([10])))\n",
        encoding="utf-8")

    _run_weekly(weekly_repo)

    runs = weekly_repo / "data" / "monitor_runs"
    text = "".join(p.read_text(encoding="utf-8", errors="replace")
                   for p in runs.glob("weekly_pytest_*.log"))
    assert "MARKER-ON-STDERR" in text, "stderr が full_output のログに無い"
    assert "--- stderr ---" in text
    assert not list(runs.glob("*.stderr")), ".stderr が残っている"
