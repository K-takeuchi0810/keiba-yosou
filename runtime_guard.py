"""テストの「運用ログ置き場を変えない」見張りのモードと、子 pytest の環境 (2026-09-26)。

## 何を決めるか

`tests/conftest.py` の見張りは、テストの前後で `data/logs` / `data/runtime` が
変われば失敗する。モードは環境変数 `KEIBA_RUNTIME_GUARD` の 2 値だけ:

    strict (既定) : 開発・worktree・変異テスト。変化があれば失敗
    off           : 週次監視 (weekly_monitor.bat) の **外側の pytest だけ**

未知の値は黙って off にせず止める。

## なぜ子 pytest の環境をここで作るのか

環境変数は子プロセスに引き継がれる。週次監視が外側を off にすると、テストの中から
起動する **入れ子の pytest** にも off が届き、「見張りが働くこと」を確かめるテストが
逆に落ちた (2026-09-26 の再レビューで 3 名が再現。9/27 以降の日曜に警告が飛ぶ形)。
テストごとに環境変数を落とす書き方は、1 か所落とし忘れるだけで再発する。

そこで **子 pytest の環境は必ず `child_pytest_env()` で作り、内側は常に strict** にする。
テスト・変異の枠 (`scripts/mutation_sandbox.py`)・スクリプトのすべてがこれを使う。
`tests/test_runtime_guard.py` が、外側 off のまま実際に子 pytest を起動して内側が strict に
なることを確かめる (主防御)。直接 `subprocess` で pytest を書いて迂回していないかは AST で
補助的に見張る。
"""
from __future__ import annotations

import os
from typing import Mapping

#: 見張りのモードを決める環境変数の名前 (Python 側の唯一の出典)。
#: bat (`weekly_monitor.bat`) だけは文字列で書く。
RUNTIME_GUARD_ENV = "KEIBA_RUNTIME_GUARD"

STRICT = "strict"
OFF = "off"
MODES = (STRICT, OFF)


def runtime_guard_mode(environ: Mapping[str, str] | None = None) -> str:
    """見張りのモード。未設定・空は strict。未知の値は ValueError。"""
    env = os.environ if environ is None else environ
    raw = env.get(RUNTIME_GUARD_ENV, STRICT)
    mode = (raw or "").strip().lower() or STRICT
    if mode not in MODES:
        raise ValueError(
            f"{RUNTIME_GUARD_ENV}={raw!r} は使えない (使えるのは {', '.join(MODES)})")
    return mode


def child_pytest_env(base: Mapping[str, str] | None = None, **extra: str) -> dict:
    """テストやスクリプトの中から pytest を起動するときの環境。

    - 見張りは **必ず strict** (外側が off でも持ち込まない)
    - PYTHONPATH は落とす (呼び出し元の import path に頼らない)
    - 出力は UTF-8 (呼び出し側の PYTHONIOENCODING で読み取りが揺れないように)

    `extra` で上書きできるが、見張りのモードだけは上書きさせない。未知の値や off を
    子に渡したいテスト (fail-fast の確認など) は、返り値を自分で書き換えること。
    """
    env = dict(os.environ if base is None else base)
    for key in [k for k in env if k.upper() == "PYTHONPATH"]:   # 大文字小文字を問わず
        env.pop(key)
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    env[RUNTIME_GUARD_ENV] = STRICT
    return env
