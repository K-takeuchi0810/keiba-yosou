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


def test_a_leak_caused_only_by_the_mutant_aborts(tmp_path, prod):
    """★ 変異を植えたときだけ本番に書く場合も止めること (変異の後の検査)。

    変異なしの実行で漏れる形は事前の検査が先に捕まえるので、変異の後の検査を
    試すには「変異が入ったときだけ漏れる」テストが要る (変異 X3 が生存した)。
    植える文字列には本番のパスを含めない (含めると REFUSED で止まってしまう)。
    """
    copy = _project(tmp_path / "copy")
    leak = prod / "data" / "logs" / "leak.log"
    (copy / "tests" / "test_calc.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n"
        "from calc import add\n\n"
        "def test_add():\n"
        "    r = add(2, 3)\n"
        f"    if r != 5:\n        pathlib.Path({str(leak)!r}).write_text('leaked')\n"
        "    assert r == 5\n")

    with pytest.raises(ms.SandboxError, match="変異 'M1' の実行で本番が変わった"):
        ms.run_mutants(copy, [("M1", "calc.py", "return a + b", "return a - b")],
                       ["tests/test_calc.py"], production_root=prod)


def test_every_run_gets_a_fresh_bytecode_cache(tmp_path, prod):
    """★ 実行ごとに .pyc の置き場が設定され、毎回違うこと。

    同じ置き場を使い回すと、サイズの変わらない変異が古い .pyc で「生存」に
    見えうる。時間の偶然に頼らず、置き場そのものを記録して確かめる。
    """
    copy = _project(tmp_path / "copy")
    seen = tmp_path / "prefixes.txt"
    (copy / "tests" / "test_prefix.py").write_text(
        "import os\n\n"
        "def test_prefix():\n"
        f"    with open({str(seen)!r}, 'a') as f:\n"
        "        f.write(os.environ.get('PYTHONPYCACHEPREFIX', '') + chr(10))\n")
    mutants = [("M1", "calc.py", "return a + b", "return a - b"),
               ("M2", "calc.py", "return a + b", "return a * b")]

    ms.run_mutants(copy, mutants, ["tests/test_prefix.py", "tests/test_calc.py"],
                   production_root=prod)

    prefixes = seen.read_text().splitlines()
    assert len(prefixes) == 3, prefixes          # 変異なし + 変異 2 つ
    assert all(prefixes), f"置き場が設定されていない実行がある: {prefixes}"
    assert len(set(prefixes)) == 3, f"置き場を使い回している: {prefixes}"


def test_a_reader_touching_the_wal_is_not_a_change(prod):
    """DB を読むだけの接続で WAL の更新時刻が動いても「本番が変わった」にしない。

    2026-09-26 00:05 に、別プロジェクトの常駐プロセスが DB を開いただけで
    WAL の時刻が動き、無関係の変異で全体が ABORT した。
    """
    wal = prod / "data" / "keiba.db-wal"
    wal.write_bytes(b"")
    before = ms.snapshot_production(prod)
    os.utime(wal, (1_900_000_000, 1_900_000_000))           # 時刻だけ動く

    assert ms.diff_snapshots(before, ms.snapshot_production(prod)) == []


@pytest.mark.parametrize("write", ["db", "wal"])
def test_a_db_write_is_a_change(prod, write):
    """対照: 本体の更新や WAL の増加 (= 書き込み) は検出すること。"""
    wal = prod / "data" / "keiba.db-wal"
    wal.write_bytes(b"")
    before = ms.snapshot_production(prod)
    if write == "db":
        (prod / "data" / "keiba.db").write_bytes(b"db2")
    else:
        wal.write_bytes(b"page")

    assert ms.diff_snapshots(before, ms.snapshot_production(prod))


def test_an_abort_keeps_the_results_so_far(tmp_path, prod):
    """途中で止めても、それまでの変異の結果は捨てないこと。"""
    copy = _project(tmp_path / "copy")
    leak = prod / "data" / "logs" / "leak.log"
    (copy / "tests" / "test_calc.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\n"
        "from calc import add\n\n"
        "def test_add():\n"
        "    r = add(2, 3)\n"
        f"    if r == 6:\n        pathlib.Path({str(leak)!r}).write_text('leaked')\n"
        "    assert r == 5\n")
    mutants = [("M1", "calc.py", "return a + b", "return a - b"),     # 撃墜 (漏れない)
               ("M2", "calc.py", "return a + b", "return a + b + 1")]  # 漏れる

    with pytest.raises(ms.SandboxError) as e:
        ms.run_mutants(copy, mutants, ["tests/test_calc.py"], production_root=prod)

    assert [(r.name, r.status) for r in e.value.results] == [
        ("M1", "KILLED"), ("M2", "ABORTED")]


# --- 変異の対象パス (書く前に拒否) -----------------------------------------

@pytest.mark.parametrize("make_rel", [
    lambda outside: str(outside),                                   # 絶対パス
    lambda outside: str(outside).replace("\\", "/"),                # 区切り文字違い
    lambda outside: str(outside).upper(),                           # 大文字小文字違い
    lambda outside: "../" + outside.parent.name + "/" + outside.name,   # ..
    lambda outside: "sub/../../" + outside.parent.name + "/" + outside.name,
    lambda outside: "..\\" + outside.parent.name + "\\" + outside.name,
    lambda outside: "/" + outside.name,                             # ルート始まり
    lambda outside: "\\\\server\\share\\" + outside.name,        # UNC
    lambda outside: outside.drive + outside.name,                   # ドライブ付き相対
])
def test_a_target_outside_the_copy_is_refused_before_writing(tmp_path, prod, make_rel):
    """★ コピーの外を指す対象パスは、書き込む前に REFUSED にすること。

    「書いてから戻す」は安全策にしない。外のファイルは 1 バイトも変わらないこと。
    """
    copy = _project(tmp_path / "copy")
    outside = tmp_path / "outside.py"
    outside.write_text("def add(a, b):\n    return a + b\n")
    before = outside.read_bytes(), outside.stat().st_mtime_ns

    results = ms.run_mutants(copy, [("OUT", make_rel(outside), "return a + b", "return a - b")],
                             ["tests/test_calc.py"], production_root=prod)

    assert results[0].status == "REFUSED", results
    assert (outside.read_bytes(), outside.stat().st_mtime_ns) == before, "外のファイルに書いた"


@pytest.mark.skipif(sys.platform != "win32", reason="ジャンクションは Windows のみ")
def test_a_target_through_the_venv_junction_is_refused(tmp_path, prod):
    """`.venv64` はジャンクション (実体はコピーの外) なので、その中は対象にさせない。"""
    copy = _project(tmp_path / "copy")
    real_venv = tmp_path / "real-venv"
    real_venv.mkdir()
    (real_venv / "site.py").write_text("x = 1\n")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(copy / ".venv64"), str(real_venv)],
                   check=True, capture_output=True)
    try:
        results = ms.run_mutants(copy, [("V", ".venv64/site.py", "x = 1", "x = 2")],
                                 ["tests/test_calc.py"], production_root=prod)
        assert results[0].status == "REFUSED", results
        assert (real_venv / "site.py").read_text() == "x = 1\n"
    finally:
        os.rmdir(copy / ".venv64")


def test_a_target_inside_the_copy_is_accepted(tmp_path, prod):
    """対照: コピーの中の相対パス (区切り文字はどちらでも) は流す。"""
    copy = _project(tmp_path / "copy")
    (copy / "pkg").mkdir()
    (copy / "pkg" / "m.py").write_text("V = 1\n")
    assert ms.refuses_target("pkg/m.py", copy) is None
    assert ms.refuses_target("pkg\\m.py", copy) is None
    assert ms.refuses_target("calc.py", copy) is None


# --- 本番の監視を始められないなら流さない -----------------------------------

def _marker_project(tmp_path):
    """テストが 1 回でも走ったら印を残すプロジェクト (流していないことの確認用)。"""
    copy = _project(tmp_path / "copy")
    ran = tmp_path / "ran.txt"
    (copy / "tests" / "test_marker.py").write_text(
        f"def test_marker():\n    open({str(ran)!r}, 'a').write('x')\n")
    return copy, ran


def test_a_missing_production_root_refuses_to_start(tmp_path):
    """★ 本番 checkout が見つからなければ、変異なしの実行より前に止まること。

    見つからないまま進むと「監視対象 0 件 = 安全」に化け、枠が黙って何も守らない。
    """
    copy, ran = _marker_project(tmp_path)

    with pytest.raises(ms.SandboxError, match="本番 checkout が見つからない"):
        ms.run_mutants(copy, [("M1", "calc.py", "return a + b", "return a - b")],
                       ["tests/test_marker.py"], production_root=tmp_path / "no-such-root")
    assert not ran.exists(), "本番の監視を始められないのにテストを流した"


@pytest.mark.parametrize("missing", ["data/logs", "data/runtime", "data/keiba.db"])
def test_a_missing_watch_target_refuses_to_start(tmp_path, prod, missing):
    """監視対象 (ログ置き場・runtime・DB) のどれかが無ければ止まること。"""
    import shutil

    target = prod / missing
    shutil.rmtree(target) if target.is_dir() else target.unlink()
    copy, ran = _marker_project(tmp_path)

    with pytest.raises(ms.SandboxError, match="本番の監視対象が無い"):
        ms.run_mutants(copy, [("M1", "calc.py", "return a + b", "return a - b")],
                       ["tests/test_marker.py"], production_root=prod)
    assert not ran.exists()


# --- 監視対象を外す変異を落とす ---------------------------------------------

def test_a_leak_into_runtime_is_detected(tmp_path, prod):
    """data/runtime への漏れも止めること (監視から runtime を外す変異 V-Xc を落とす)。"""
    copy = _project(tmp_path / "copy", writes_to=prod / "data" / "runtime")

    with pytest.raises(ms.SandboxError, match="本番が変わった"):
        ms.run_mutants(copy, [("M1", "calc.py", "return a + b", "return a - b")],
                       ["tests/test_calc.py"], production_root=prod)


def test_a_leak_in_the_baseline_run_is_reported_as_such(tmp_path, prod):
    """変異なしの実行で漏れたら、その時点で「変異なしの実行で」と止めること。

    事前実行の差分を無視する変異 (V-Xj) は、漏れを最初の変異のせいにして
    しまう。どの段で漏れたかを取り違えないことを見る。
    """
    copy = _project(tmp_path / "copy", writes_to=prod / "data" / "logs")

    with pytest.raises(ms.SandboxError, match="変異なしの実行で本番が変わった"):
        ms.run_mutants(copy, [("M1", "calc.py", "return a + b", "return a - b")],
                       ["tests/test_calc.py"], production_root=prod)
