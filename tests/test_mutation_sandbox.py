"""変異テストの枠 (`scripts/mutation_sandbox.py`) が本番を守ること (2026-09-25)。

2026-09-25 に、隔離コピーで流した変異 (bat の cd 先を本番 checkout に戻す) が
本番の `data/logs` に 3 回書き込んだ。その同じ形を、ここでは **偽の本番** に
向けて再現し、枠が止めることを確かめる。本物の本番 checkout には触れない。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import mutation_sandbox as ms


@pytest.fixture()
def prod(tmp_path):
    """偽の本番 checkout (運用ログ置き場と DB を持つ)。"""
    root = tmp_path / "prod" / "keiba-yosou"
    (root / "data" / "logs").mkdir(parents=True)
    (root / "data" / "runtime").mkdir()
    (root / "data" / "keiba.db").write_bytes(b"db")
    (root / "data" / "logs" / "auto_predict_watchdog.log").write_text("x\n")
    return root


def _project(root: Path, *, writes_to: Path | None = None) -> Path:
    """小さな隔離コピー: 関数 1 つとそのテスト。

    `writes_to` を渡すと、テストがそのディレクトリにログを書く (本番汚染の再現)。
    """
    (root / "tests").mkdir(parents=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    body = ["import sys, pathlib",
            "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))",
            "from calc import add", "", "def test_add():"]
    if writes_to is not None:
        body.append(f"    pathlib.Path({str(writes_to)!r}).joinpath('leak.log')"
                    ".write_text('leaked')")
    body.append("    assert add(2, 3) == 5")
    (root / "tests" / "test_calc.py").write_text("\n".join(body) + "\n")
    return root


# --- 流す前の検査 ---------------------------------------------------------

def test_a_clean_copy_outside_production_is_accepted(tmp_path, prod):
    copy = _project(tmp_path / "copy")
    assert ms.check_sandbox(copy, prod) == []


def test_a_copy_inside_production_is_rejected(prod):
    """本番 checkout の中 (worktree を含む) はコピーとして使わせない。"""
    copy = _project(prod / ".claude" / "worktrees" / "x")
    assert any("本番 checkout の中" in p for p in ms.check_sandbox(copy, prod))


def test_the_production_checkout_itself_is_rejected(prod):
    assert ms.check_sandbox(prod, prod)


def test_a_copy_with_git_is_rejected(tmp_path, prod):
    copy = _project(tmp_path / "copy")
    (copy / ".git").mkdir()
    assert any(".git" in p for p in ms.check_sandbox(copy, prod))


def test_a_copy_with_the_webhook_is_rejected(tmp_path, prod):
    """webhook ファイルがあるコピーでは、通知経路の変異が本当に送信しうる。"""
    copy = _project(tmp_path / "copy")
    (copy / "data").mkdir()
    (copy / "data" / "discord_webhook.txt").write_text("https://example.invalid/")
    assert any("webhook" in p for p in ms.check_sandbox(copy, prod))


def test_a_hardlinked_production_db_is_rejected(tmp_path, prod):
    """コピーの DB が本番 DB と同じファイルなら、書き込みが本番に届く。"""
    copy = _project(tmp_path / "copy")
    (copy / "data").mkdir()
    try:
        os.link(prod / "data" / "keiba.db", copy / "data" / "keiba.db")
    except OSError:
        pytest.skip("ハードリンクを作れないファイルシステム")
    assert any("本番 DB" in p for p in ms.check_sandbox(copy, prod))


@pytest.mark.skipif(sys.platform != "win32", reason="ジャンクションは Windows のみ")
def test_only_the_venv_may_be_a_junction(tmp_path, prod):
    """`.venv64` のジャンクションは許すが、それ以外のリンクは許さない。"""
    copy = _project(tmp_path / "copy")
    target = tmp_path / "venv"
    target.mkdir()
    for name in (".venv64", "data_link"):
        subprocess.run(["cmd", "/c", "mklink", "/J", str(copy / name), str(target)],
                       check=True, capture_output=True)
    try:
        problems = ms.check_sandbox(copy, prod)
        assert any("data_link" in p for p in problems)
        assert not any(".venv64" in p for p in problems)
    finally:
        for name in (".venv64", "data_link"):
            os.rmdir(copy / name)


# --- 変異ごとの検査 -------------------------------------------------------

def test_a_mutant_pointing_at_production_is_refused(tmp_path, prod):
    """★ 2026-09-25 の B8 と同じ形 (cd 先を本番に戻す) は流さない。"""
    copy = _project(tmp_path / "copy")
    mutants = [("B8", "calc.py", "return a + b",
                f"import os; os.chdir(r'{prod}'); return a + b")]

    results = ms.run_mutants(copy, mutants, ["tests/test_calc.py"],
                             production_root=prod)

    assert results[0].status == "REFUSED", results


@pytest.mark.parametrize("text", [
    r"cd /d C:\Users\kizun\dev\keiba-yosou",
    "cd /c/Users/kizun/dev/keiba-yosou",
    "C:/Users/kizun/dev/keiba-yosou/data/keiba.db",
    "https://discord.com/api/webhooks/123/abc",
])
def test_the_real_production_markers_are_recognised(text):
    """本物の本番パス (区切り文字の違いも) と webhook を検出すること。"""
    assert ms.refuses(text) is not None


def test_a_dummy_path_is_allowed():
    """行き先をダミーにした変異は流してよい。"""
    assert ms.refuses(r"cd /d C:\nonexistent\keiba-yosou") is None


# --- 変異ごとの後の検査 ---------------------------------------------------

def test_a_leak_into_production_aborts_the_run(tmp_path, prod):
    """★ 変異の実行で本番のログ置き場が変わったら、そこで全体を止める。"""
    copy = _project(tmp_path / "copy", writes_to=prod / "data" / "logs")
    mutants = [("M1", "calc.py", "return a + b", "return a - b"),
               ("M2", "calc.py", "return a + b", "return a * b")]

    with pytest.raises(ms.SandboxError, match="本番が変わった"):
        ms.run_mutants(copy, mutants, ["tests/test_calc.py"], production_root=prod)

    # 変異は元に戻っている
    assert "return a + b" in (copy / "calc.py").read_text()


def test_a_normal_run_kills_and_restores(tmp_path, prod):
    """対照: 本番に触れない変異は普通に流れ、撃墜され、元に戻る。

    `+` → `-` は **ソースのサイズが変わらない** 変異で、変異なしの実行の直後
    (同じ 1 秒のうち) に植わる。古い .pyc を使い回すと「生存」に見える
    (2026-09-25 に実際に起きた)。ここが緑であることがその再発防止になる。
    """
    copy = _project(tmp_path / "copy")
    before = (copy / "calc.py").read_bytes()
    mutants = [("M1", "calc.py", "return a + b", "return a - b"),
               ("M2", "calc.py", "no such text", "x")]

    results = ms.run_mutants(copy, mutants, ["tests/test_calc.py"],
                             production_root=prod)

    assert [r.status for r in results] == ["KILLED", "NOT_APPLIED"]
    assert (copy / "calc.py").read_bytes() == before


def test_an_unsafe_copy_runs_nothing(tmp_path, prod):
    """隔離コピーとして使えなければ、変異を 1 つも流さない。"""
    copy = _project(prod / "inside")
    before = (copy / "calc.py").read_bytes()

    with pytest.raises(ms.SandboxError, match="隔離コピーとして使えない"):
        ms.run_mutants(copy, [("M1", "calc.py", "return a + b", "return a - b")],
                       ["tests/test_calc.py"], production_root=prod)
    assert (copy / "calc.py").read_bytes() == before


def test_a_red_baseline_runs_no_mutant(tmp_path, prod):
    """★ 変異なしでテストが赤ければ、変異を 1 つも流さない。

    赤いテストが 1 本あると、どの変異も「撃墜」に見え、その後ろのテストは
    一度も走らない (2026-09-25 実例: 9 変異の結果が偽の撃墜だった)。
    """
    copy = _project(tmp_path / "copy")
    (copy / "tests" / "test_red.py").write_text("def test_red():\n    assert False\n")

    with pytest.raises(ms.SandboxError, match="変異なしでテストが赤い"):
        ms.run_mutants(copy, [("M1", "calc.py", "return a + b", "return a - b")],
                       ["tests/test_red.py", "tests/test_calc.py"], production_root=prod)
