"""`scripts/fetch_mining.py` がファイル指定でも起動できること (2026-09-25)。

JST 統一で `from jst import current_jst_daystamp` を足したとき、それが
`sys.path.insert` (repo ルートを通す行) より前にあったため、

    python scripts/fetch_mining.py --date today

の形で起動すると `ModuleNotFoundError: No module named 'jst'` で落ちた。
日次 bat は `-m scripts.fetch_mining` 形式なので本番は無事だったが、手で
取り直すときに使う形が壊れていた。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "fetch_mining.py"


def _env_without_pythonpath() -> dict:
    """pytest が通している import path に頼らない (素の起動と同じにする)。

    出力のエンコーディングは明示する。--help は日本語を含むので、呼び出し側の
    PYTHONIOENCODING 次第で cp932 / UTF-8 が入れ替わり、読み取りで落ちていた
    (変異テストを PYTHONIOENCODING=utf-8 で流したとき、このテストが変異に
    関係なく落ちて後ろのテストを隠した)。
    """
    env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_the_script_starts_from_another_directory(tmp_path):
    """別の作業ディレクトリからファイル指定で起動しても import で落ちないこと。"""
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"], cwd=tmp_path,
                       env=_env_without_pythonpath(), capture_output=True,
                       text=True, encoding="utf-8", timeout=60)

    assert r.returncode == 0, r.stderr
    assert "No module named" not in r.stderr
    assert "--date" in r.stdout


def test_the_module_form_still_starts():
    """日次 bat と同じ `-m` 形式も従来どおり起動すること。"""
    r = subprocess.run([sys.executable, "-m", "scripts.fetch_mining", "--help"],
                       cwd=REPO, env=_env_without_pythonpath(),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)

    assert r.returncode == 0, r.stderr
    assert "--date" in r.stdout
