"""conftest の「テストが運用ログ置き場を変えない」見張りが本当に働くこと (2026-09-26)。

見張り (`tests/conftest.py` の `_tests_do_not_touch_runtime_logs`) を無効にする
変異が生存した (レビューの V-E3)。見張り自身をテストで固定する。

方法: 一時ディレクトリに **本物の conftest をそのままコピー** し、`data/logs` に
書くテストと書かないテストを別々の pytest として流す。書く方だけが失敗すること。

子の pytest の環境は `runtime_guard.child_pytest_env()` で作る。外側 (このテスト自身) が
週次監視の `KEIBA_RUNTIME_GUARD=off` で動いていても、内側は strict で見張りが働く。
以前は PYTHONPATH だけを落としていたので off が内側に届き、ここの 4 本が週次監視で
だけ落ちた (2026-09-26 の再レビューで 3 名が再現)。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from runtime_guard import RUNTIME_GUARD_ENV, child_pytest_env

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(params=["unset", "off"], autouse=True)
def outer_guard(request, monkeypatch):
    """★ 外側の見張りが未設定の場合と off の場合の両方で、全部のテストを流す。

    週次監視は外側を off にして tests/ 全体を流す。そこでもここのテストが
    同じ結果になること (= 内側は strict) を、各テストで確かめる。
    """
    if request.param == "off":
        monkeypatch.setenv(RUNTIME_GUARD_ENV, "off")
    else:
        monkeypatch.delenv(RUNTIME_GUARD_ENV, raising=False)
    return request.param


def _mini_repo(root: Path, test_body: str) -> Path:
    (root / "tests").mkdir(parents=True)
    (root / "data" / "logs").mkdir(parents=True)
    (root / "data" / "runtime").mkdir()
    (root / "data" / "logs" / "existing.log").write_text("before\n")
    shutil.copy(REPO / "tests" / "conftest.py", root / "tests" / "conftest.py")
    shutil.copy(REPO / "runtime_guard.py", root / "runtime_guard.py")
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_x.py").write_text(test_body)
    return root


def _pytest(root: Path) -> subprocess.CompletedProcess:
    env = child_pytest_env()                       # 内側は常に strict
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "--rootdir", str(root), str(root / "tests")],
                          cwd=root, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


@pytest.mark.parametrize("where,body", [
    ("logs", "open(ROOT / 'data' / 'logs' / 'leak.log', 'w').write('x')"),
    ("logs-append", "open(ROOT / 'data' / 'logs' / 'existing.log', 'a').write('x')"),
    ("runtime", "open(ROOT / 'data' / 'runtime' / 'state.json', 'w').write('{}')"),
])
def test_a_test_that_writes_runtime_logs_fails_the_session(tmp_path, where, body):
    """★ ログ置き場に書くテストがあれば、セッションが失敗すること。"""
    root = _mini_repo(tmp_path / "r", (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n\n"
        "def test_leaks():\n"
        f"    {body}\n"))

    r = _pytest(root)

    assert r.returncode != 0, f"{where} への書き込みを見逃した:\n{r.stdout[-800:]}"
    assert "運用ログ置き場を変更した" in r.stdout, r.stdout[-800:]


def test_a_clean_session_passes(tmp_path):
    """対照: ログ置き場に触れないテストだけなら、セッションは成功すること。"""
    root = _mini_repo(tmp_path / "r", "def test_ok():\n    assert True\n")

    r = _pytest(root)

    assert r.returncode == 0, r.stdout[-800:]


def test_a_same_size_overwrite_fails_the_session(tmp_path):
    """★ 既存のログを **同じサイズで** 上書きするテストも検出すること。

    サイズだけを見る見張りに壊すと (変異 K19 / E3c)、中身を書き換えても通ってしまう。
    `existing.log` は "before" + 改行。同じ長さの "BEFORE" + 改行で上書きする
    (どちらもテキストモードで書くので、改行の変換を含めてサイズは同じ)。
    """
    root = _mini_repo(tmp_path / "r", (
        "import time\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n\n"
        "def test_overwrites():\n"
        "    time.sleep(0.05)\n"
        "    (ROOT / 'data' / 'logs' / 'existing.log').write_text('BEFORE' + chr(10))\n"))

    r = _pytest(root)

    assert r.returncode != 0, r.stdout[-800:]
    assert "運用ログ置き場を変更した" in r.stdout


def test_a_leak_into_a_subdirectory_fails_the_session(tmp_path):
    """ログ置き場の **サブディレクトリ** への書き込みも検出すること (rglob → glob の変異)。"""
    root = _mini_repo(tmp_path / "r", (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n\n"
        "def test_leaks():\n"
        "    (ROOT / 'data' / 'logs' / 'sub' / 'leak.log').write_text('x')\n"))
    (root / "data" / "logs" / "sub").mkdir()

    r = _pytest(root)

    assert r.returncode != 0, r.stdout[-800:]
    assert "運用ログ置き場を変更した" in r.stdout


@pytest.mark.parametrize("value", ["warn", "foo"])
def test_an_unknown_value_is_rejected_at_configure_time(tmp_path, value):
    """未知の値は `pytest_configure` の段階で止めること (後段の fixture に頼らない)。

    2026-09-28 の最終ゲートで、`pytest_configure` の検査を外す変異 (V3) が生き残った。
    後ろの session fixture でも拒否されるのでテストは流れないが、止まり方が違う:
    configure で止まれば終了コード 4 (使い方の誤り、テストを 1 本も集めない)、
    fixture だけだと 1 (各テストがエラー)。二重の防御の 1 枚目を固定する。
    """
    root = _mini_repo(tmp_path / "r", "def test_a():\n    assert True\n")
    env = child_pytest_env()
    env[RUNTIME_GUARD_ENV] = value                 # 子に未知の値をわざと渡す
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "--rootdir", str(root), str(root / "tests")],
                       cwd=root, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)

    assert r.returncode == pytest.ExitCode.USAGE_ERROR, (r.returncode, r.stdout[-800:], r.stderr[-800:])
    assert RUNTIME_GUARD_ENV in (r.stdout + r.stderr)
    assert "test_a" not in r.stdout, "未知の値なのにテストを集めた"
