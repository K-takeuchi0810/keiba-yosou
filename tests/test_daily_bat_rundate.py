"""`scripts/auto_predict_daily.bat` を **実際に cmd で動かす** テスト (2026-09-25)。

## なぜ要るか

bat は起動日の「今日」を Python (`jst.current_jst_daystamp`) に聞いてログ名を作る。
以前は失敗したときの扱いが無く、

    Python が落ちる / import に失敗する -> RUNDATE が空
    -> data\\logs\\auto_predict_daily_.log へ黙って書く
    -> stderr はどこにも残らず、終了コードは後段の結果次第

となっていた。タスクスケジューラ経由 (wscript で非表示) だと画面にも出ないので、
「日付が取れずに走った」ことが後から分からない。

## 方法

一時ディレクトリに仮のリポジトリを作り、本物の bat をコピーして `cmd /c` で動かす。
`.venv64` / `.venv32` は本物の Python へのジャンクション。`jst.py` と、bat が
呼ぶ `scripts.*` は **引数を記録するだけのスタブ**に差し替えるので、DB・Discord・
Pages には一切触れない。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe が要る")

REPO = Path(__file__).resolve().parents[1]
BAT = REPO / "scripts" / "auto_predict_daily.bat"
VENV = Path(sys.executable).resolve().parents[1]      # .venv64

#: bat が呼ぶモジュール。呼ばれたら argv を calls.txt に 1 行書く。
#: 終了コードは環境変数 STUB_EXIT_<module> で指定できる (既定 0)。
_STUB = """import os, sys, pathlib
p = pathlib.Path(__file__).resolve().parents[1] / "calls.txt"
with p.open("a", encoding="utf-8") as f:
    f.write(__name__ + " " + " ".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("STUB_EXIT_" + __name__, "0")))
"""
_MODULES = ("fetch_full", "fetch_mining", "fresh_odds_coverage",
            "auto_predict", "notify_discord")


def _junction(link: Path, target: Path) -> None:
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                   check=True, capture_output=True)


@pytest.fixture()
def fake_repo(tmp_path):
    """本物の bat と、スタブの Python モジュールを置いた仮リポジトリ。"""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(BAT, root / "scripts" / BAT.name)
    (root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    for m in _MODULES:
        (root / "scripts" / f"{m}.py").write_text(
            _STUB.replace("__name__", repr(m)), encoding="utf-8")
    _junction(root / ".venv64", VENV)
    _junction(root / ".venv32", VENV)      # 32bit の代わり (スタブしか呼ばない)
    yield root
    # ジャンクションは中身ごと消さないよう、リンクだけ外す
    for name in (".venv64", ".venv32"):
        os.rmdir(root / name)


def _set_jst(root: Path, body: str) -> None:
    (root / "jst.py").write_text(body, encoding="utf-8")


def _run(root: Path, *args: str, env_extra: dict | None = None) -> int:
    env = {k: v for k, v in os.environ.items() if k.upper() != "RUNDATE"}
    env.update(env_extra or {})
    r = subprocess.run(["cmd", "/d", "/c", str(root / "scripts" / BAT.name), *args],
                       cwd=tmp_cwd(root), env=env, capture_output=True, text=True)
    return r.returncode


def tmp_cwd(root: Path) -> Path:
    """わざと別の場所から起動する (bat が自分の位置へ cd することを見る)。"""
    return root.parent


def _calls(root: Path) -> list[str]:
    p = root / "calls.txt"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def _logs(root: Path) -> set[str]:
    d = root / "data" / "logs"
    return {p.name for p in d.iterdir()} if d.exists() else set()


_OK = "def current_jst_daystamp():\n    return '20261001'\n"


# --- 正常系 ---------------------------------------------------------------

def test_dry_run_uses_the_jst_date_and_touches_nothing(fake_repo):
    """dry-run: JST 日付のログ名・対象日、取り込みと通知は呼ばない、exit 0。"""
    _set_jst(fake_repo, _OK)

    rc = _run(fake_repo, "--dry-run")

    assert rc == 0
    assert "auto_predict_daily_20261001_dryrun.log" in _logs(fake_repo)
    log = (fake_repo / "data" / "logs" / "auto_predict_daily_20261001_dryrun.log"
           ).read_text(encoding="ascii", errors="replace")
    assert "run date 20261001 (JST)" in log
    assert f"cwd={fake_repo}" in log, "bat が自分のリポジトリへ cd していない"
    calls = _calls(fake_repo)
    assert "auto_predict --dry-run" in calls
    assert "fresh_odds_coverage --last 1 --check-gaps" in calls, (
        "dry-run で --notify を付けている (Discord へ送る)")
    assert not any(c.startswith(("fetch_full", "fetch_mining", "notify_discord"))
                   for c in calls), f"dry-run で取り込み・通知を呼んでいる: {calls}"


def test_the_normal_run_keeps_the_production_steps(fake_repo):
    """dry-run でない起動は従来どおり (取り込み → coverage --notify → 生成)。"""
    _set_jst(fake_repo, _OK)

    rc = _run(fake_repo)

    assert rc == 0
    assert "auto_predict_daily_20261001.log" in _logs(fake_repo)
    calls = _calls(fake_repo)
    assert calls[0] == "fetch_full --ingest"
    assert "fetch_mining --date today" in calls
    assert "fresh_odds_coverage --last 1 --check-gaps --notify" in calls
    assert calls[-1] == "auto_predict ", "本番起動に --dry-run が混ざっている"


# --- 異常系: 日付が取れない ----------------------------------------------

@pytest.mark.parametrize("body,why", [
    ("raise ImportError('injected')\n", "import に失敗"),
    ("def current_jst_daystamp():\n    raise RuntimeError('boom')\n", "関数が例外"),
    ("def current_jst_daystamp():\n    return ''\n", "空文字"),
    ("def current_jst_daystamp():\n    return '2026-10-01'\n", "形式違い"),
    ("def current_jst_daystamp():\n    return '1026100'\n", "桁不足"),
])
@pytest.mark.parametrize("dry", [True, False])
def test_a_missing_date_aborts_loudly(fake_repo, body, why, dry):
    """★ 日付が取れなければ空の日付へ逃げず、stderr を残して exit 8 で止まる。"""
    _set_jst(fake_repo, body)

    rc = _run(fake_repo, *(["--dry-run"] if dry else []))

    assert rc == 8, f"{why}: exit {rc}"
    logs = _logs(fake_repo)
    assert "auto_predict_daily_.log" not in logs, f"{why}: 空の日付のログへ書いた"
    assert not any(n.startswith("auto_predict_daily_2") for n in logs), (
        f"{why}: 日付入りのログを作った: {logs}")
    fail = (fake_repo / "data" / "logs" / "auto_predict_daily_DATE_FAILURE.log"
            ).read_text(encoding="ascii", errors="replace")
    assert "could not determine the JST run date" in fail
    assert "abort exit=8" in fail
    pipeline = [c for c in _calls(fake_repo) if not c.startswith("notify_discord")]
    assert pipeline == [], f"{why}: 日付が無いのに後段を走らせた: {pipeline}"


def test_the_python_error_is_kept(fake_repo):
    """import 失敗の Traceback が失敗ログに残ること (非表示起動でも原因が追える)。"""
    _set_jst(fake_repo, "raise ImportError('injected: jst unavailable')\n")

    _run(fake_repo, "--dry-run")

    fail = (fake_repo / "data" / "logs" / "auto_predict_daily_DATE_FAILURE.log"
            ).read_text(encoding="ascii", errors="replace")
    assert "ImportError: injected: jst unavailable" in fail


def test_a_stale_rundate_in_the_environment_is_not_reused(fake_repo):
    """環境に古い RUNDATE が残っていても、失敗時にそれを使わないこと。"""
    _set_jst(fake_repo, "raise ImportError('injected')\n")

    rc = _run(fake_repo, "--dry-run", env_extra={"RUNDATE": "20200101"})

    assert rc == 8
    assert "auto_predict_daily_20200101_dryrun.log" not in _logs(fake_repo)


def test_the_failure_is_notified_only_outside_dry_run(fake_repo):
    """日付が取れないときの通知は本番起動だけ (dry-run では Discord に送らない)。"""
    _set_jst(fake_repo, "raise ImportError('injected')\n")
    _run(fake_repo, "--dry-run")
    assert not any(c.startswith("notify_discord") for c in _calls(fake_repo))

    _run(fake_repo)
    assert any(c.startswith("notify_discord") for c in _calls(fake_repo)), (
        "本番起動で日付が取れなかったことを通知していない")


# --- 終了コードの伝搬 (日付取得の後で Python が失敗する場合) --------------

@pytest.mark.parametrize("dry,fails,want", [
    (True, {"auto_predict": "1"}, 2),                       # 予想生成の失敗
    (True, {"fresh_odds_coverage": "1"}, 1),                # fresh odds の欠落
    (True, {"auto_predict": "3", "fresh_odds_coverage": "1"}, 3),
    (False, {"fetch_full": "1"}, 4),                        # 取り込みの失敗
    (False, {"fetch_full": "1", "auto_predict": "2"}, 6),
    (True, {}, 0),                                          # 対照: 全部成功
])
def test_a_later_python_failure_reaches_the_bat_exit_code(fake_repo, dry, fails, want):
    """★ 日付が取れた後の Python の非 0 が、bat の終了コードに載ること。

    スタブが全部 exit 0 だと、bat が最後に 0 を返すよう壊れても気付けない
    (変異 B-10 が生存)。ビットは 1=fresh odds / 2=予想 / 4=取り込み。
    """
    _set_jst(fake_repo, _OK)
    env = {f"STUB_EXIT_{m}": code for m, code in fails.items()}

    rc = _run(fake_repo, *(["--dry-run"] if dry else []), env_extra=env)

    assert rc == want, f"{fails} で exit {rc} (期待 {want})"


RUNNER = REPO / "scripts" / "run_auto_predict_daily.ps1"


def _run_via_runner(root: Path, env_extra: dict, *, through_wscript: bool) -> int:
    """本番と同じ起動器 (ps1、または wscript → vbs → ps1) から bat を動かす。"""
    env = {k: v for k, v in os.environ.items() if k.upper() != "RUNDATE"}
    env.update(env_extra)
    bat = root / "scripts" / BAT.name
    logs = root.parent / "watchdog-logs"
    ps1_args = ["-CommandPath", str(bat), "-LogDir", str(logs), "-DryRun"]
    if not through_wscript:
        return subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(RUNNER), *ps1_args],
            env=env, cwd=root.parent, check=False, timeout=120).returncode
    vbs = Path(os.environ.get("LOCALAPPDATA", "")) / "ScheduledTaskRunner" / \
        "run-scheduled-task-hidden.vbs"
    if not vbs.exists():
        pytest.skip("この環境には hidden runner (vbs) が無い")
    wscript = Path(os.environ["SystemRoot"]) / "System32" / "wscript.exe"
    arglist = " ".join(["//B", "//NoLogo", f'"{vbs}"', "ps1", f'"{RUNNER}"',
                        *(f'"{a}"' if " " in a else a for a in ps1_args)])
    ps = (f"$p = Start-Process -FilePath '{wscript}' -ArgumentList '{arglist}' "
          f"-PassThru; $null = $p.Handle; $p.WaitForExit(120000) | Out-Null; "
          f"exit $p.ExitCode")
    return subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-Command", ps],
                          env=env, cwd=root.parent, check=False, timeout=180).returncode


@pytest.mark.parametrize("through_wscript", [False, True])
def test_the_exit_code_reaches_the_scheduler(fake_repo, through_wscript):
    """★ Python の非 0 が bat → ps1 → (vbs / wscript) の最後まで届くこと。

    Task Scheduler の LastTaskResult で失敗を読めるかどうかはここで決まる。
    """
    _set_jst(fake_repo, _OK)

    rc = _run_via_runner(fake_repo, {"STUB_EXIT_auto_predict": "1"},
                         through_wscript=through_wscript)

    assert rc == 2, f"予想生成の失敗 (bat exit 2) が {rc} になった"


def test_the_date_failure_reaches_the_scheduler(fake_repo):
    """日付取得の失敗 (exit 8) も wscript まで届くこと。"""
    _set_jst(fake_repo, "raise ImportError('injected')\n")

    rc = _run_via_runner(fake_repo, {}, through_wscript=True)

    assert rc == 8
