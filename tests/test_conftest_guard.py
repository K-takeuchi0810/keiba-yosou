"""conftest の「テストが運用ログ置き場を変えない」見張りが本当に働くこと (2026-09-26)。

見張り (`tests/conftest.py` の `_tests_do_not_touch_runtime_logs`) を無効にする
変異が生存した (レビューの V-E3)。見張り自身をテストで固定する。

方法: 一時ディレクトリに **本物の conftest をそのままコピー** し、`data/logs` に
書くテストと書かないテストを別々の pytest として流す。書く方だけが失敗すること。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _mini_repo(root: Path, test_body: str) -> Path:
    (root / "tests").mkdir(parents=True)
    (root / "data" / "logs").mkdir(parents=True)
    (root / "data" / "runtime").mkdir()
    (root / "data" / "logs" / "existing.log").write_text("before\n")
    shutil.copy(REPO / "tests" / "conftest.py", root / "tests" / "conftest.py")
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_x.py").write_text(test_body)
    return root


def _pytest(root: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
    env["PYTHONIOENCODING"] = "utf-8"
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
