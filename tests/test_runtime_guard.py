"""`runtime_guard.py` の契約: 外側が off でも、子 pytest の見張りは必ず strict (2026-09-26)。

## 主防御は挙動

外側を `KEIBA_RUNTIME_GUARD=off` にしたまま、`child_pytest_env()` で **実際に子 pytest を
起動** し、子の中から見た見張りのモードが strict であることを確かめる。

## AST は補助

テストやスクリプトの中で `subprocess` から pytest を直接起動し、`child_pytest_env()` を
迂回していないかを見る。迂回すると、外側の off がそのまま子に届く (2026-09-26 に
tests/test_conftest_guard.py がこれで週次監視でだけ落ちた)。
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import runtime_guard as rg

REPO = Path(__file__).resolve().parents[1]


# --- モードの解釈 -------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    (None, "strict"), ("", "strict"), ("strict", "strict"), (" STRICT ", "strict"),
    ("off", "off"), ("OFF", "off"),
])
def test_known_modes(raw, want):
    env = {} if raw is None else {rg.RUNTIME_GUARD_ENV: raw}
    assert rg.runtime_guard_mode(env) == want


@pytest.mark.parametrize("raw", ["foo", "warn", "OFFF", "0", "false", "strict,off"])
def test_unknown_modes_are_rejected(raw):
    """未知の値は黙って off にも strict にもせず、ValueError。"""
    with pytest.raises(ValueError, match=rg.RUNTIME_GUARD_ENV):
        rg.runtime_guard_mode({rg.RUNTIME_GUARD_ENV: raw})


# --- 子 pytest の環境 ---------------------------------------------------------

def test_the_child_env_is_always_strict():
    """外側が off でも、上書きしようとしても、子の見張りは strict。"""
    base = {rg.RUNTIME_GUARD_ENV: "off", "PYTHONPATH": "x", "Pythonpath": "y", "KEEP": "1"}

    env = rg.child_pytest_env(base, **{rg.RUNTIME_GUARD_ENV: "off", "EXTRA": "2"})

    assert env[rg.RUNTIME_GUARD_ENV] == "strict"
    assert not any(k.upper() == "PYTHONPATH" for k in env), "PYTHONPATH が残っている"
    assert env["KEEP"] == "1" and env["EXTRA"] == "2"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert base[rg.RUNTIME_GUARD_ENV] == "off", "呼び出し元の環境を書き換えている"


def test_a_real_child_pytest_sees_strict_while_the_parent_is_off(tmp_path, monkeypatch):
    """★ 外側 off のまま子 pytest を実際に起動し、子の中で strict になっていること。"""
    monkeypatch.setenv(rg.RUNTIME_GUARD_ENV, "off")
    seen = tmp_path / "seen.txt"
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "test_probe.py").write_text(
        "import os\n\n"
        "def test_probe():\n"
        f"    open({str(seen)!r}, 'w').write(os.environ.get({rg.RUNTIME_GUARD_ENV!r}, ''))\n",
        encoding="utf-8")

    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "--rootdir", str(tmp_path), str(tmp_path / "t")],
                       cwd=tmp_path, env=rg.child_pytest_env(), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120)

    assert r.returncode == 0, r.stdout[-800:]
    assert seen.read_text() == "strict", f"子に {seen.read_text()!r} が届いた"


# --- 補助: pytest を直接起動して迂回していないか ------------------------------

def _pytest_subprocess_calls(path: Path):
    """`subprocess.run([... "pytest" ...], ...)` のような呼び出しを列挙する。"""
    import warnings

    # 他のファイルの無効なエスケープ (既存の "\S" など) の警告で落ちないように
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("run", "Popen", "call", "check_call",
                                       "check_output")):
            continue
        if not node.args or not isinstance(node.args[0], ast.List):
            continue
        consts = [e.value for e in node.args[0].elts
                  if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if "pytest" in consts:
            yield node


def test_every_child_pytest_goes_through_child_pytest_env():
    """テスト・スクリプトの中で pytest を起動する箇所は、env= を渡し、
    そのファイルが child_pytest_env を使っていること (迂回の検出)。"""
    offenders = []
    files = sorted((REPO / "tests").glob("*.py")) + sorted((REPO / "scripts").glob("*.py"))
    for path in files:
        calls = list(_pytest_subprocess_calls(path))
        if not calls:
            continue
        uses_helper = "child_pytest_env" in path.read_text(encoding="utf-8")
        for call in calls:
            has_env = any(k.arg == "env" for k in call.keywords)
            if not (has_env and uses_helper):
                offenders.append(f"{path.relative_to(REPO)}:{call.lineno}")
    assert not offenders, (
        "child_pytest_env を通さずに pytest を起動している (外側の off が子に届く): "
        f"{offenders}")


def test_the_ast_check_finds_a_bypass(tmp_path):
    """対照: AST の検査が、env を渡さない直接起動を実際に見つけること。"""
    bad = tmp_path / "bad.py"
    bad.write_text("import subprocess, sys\n"
                   "subprocess.run([sys.executable, '-m', 'pytest', 'tests'])\n",
                   encoding="utf-8")
    assert len(list(_pytest_subprocess_calls(bad))) == 1
