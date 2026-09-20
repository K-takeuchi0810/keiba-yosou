"""「今日」を各自で作る書き方が復活したら落ちるガード (2026-09-21)。

## なぜ正規表現をやめたのか

最初は 3 つの綴り (`date.today()` / `datetime.now().date()` / `datetime.today()`)
を正規表現で探していた。expert-review が独立に変異を植えたところ、**11 種中 9 種が
素通り**した:

    datetime.now(timezone.utc).date()      ← JST 07-11 時 = UTC 前日。朝の 3 起動が
                                              すべて前日を指す最悪の変異
    datetime.now().strftime("%Y%m%d")      ← repo で最も多い書き方
    datetime.now(JST).strftime("%Y%m%d")   ← この改修の **直前の原文**
    from datetime import date as _d; _d.today()
    time.strftime("%Y%m%d")

同時に、文字列リテラル `"date.today()"` を誤検出もしていた。禁止する綴りを記憶で
列挙したのが原因で、**実際に repo で使われている形を数えていなかった**。

## いまの方式

AST で「日付/時刻を作る呼び出し」を型として拾う。import の別名も追う
(`import datetime as dt` / `from datetime import date as d`)。

刻印 (`generated_at` のような「いつ処理したか」) は対象日ではないので、
**行番号ではなく「代入先の名前」** で見分ける。`today` / `day` / `date` に代入して
いるものが対象日で、それを各自の時計から作っていたら落とす。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: 対象日を決めていると見なす代入先の名前。
TARGET_NAMES = {"today", "day", "date", "target_date", "run_date", "rundate"}

#: 「今日」を作りうる呼び出し。(モジュール, 属性の連なり) で表す。
CLOCK_CALLS = {
    ("datetime", "now"), ("datetime", "today"), ("datetime", "utcnow"),
    ("datetime", "fromtimestamp"),
    ("date", "today"), ("date", "fromtimestamp"),
    ("time", "strftime"), ("time", "localtime"),
}

#: ここだけは各自で読んでよい (単一出典そのもの)。
ALLOWED_MODULES = {"jst.py"}

#: 対象日を単一出典に寄せたモジュール。ここが緩むとまた各自の日付に戻る。
GUARDED = [
    "scripts/auto_predict.py",
    "scripts/notify_dedup.py",
    "web/generator.py",
    "web/publish_safety.py",
    "scripts/fetch_mining.py",
    "gui/app.py",
]


def _imported_aliases(tree: ast.AST) -> dict[str, str]:
    """`import datetime as dt` や `from datetime import date as d` を解決する。"""
    alias: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias[a.asname or a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module in ("datetime", "time"):
            for a in node.names:
                alias[a.asname or a.name] = a.name
    return alias


def _clock_calls_assigned_to_a_day(path: Path) -> list[str]:
    """対象日らしき名前に、時計から作った値を代入している箇所を返す。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    alias = _imported_aliases(tree)
    found: list[str] = []

    def dotted(node: ast.AST) -> list[str] | None:
        """`dt.datetime.now` を ["dt", "datetime", "now"] にほどく。"""
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        parts.append(node.id)
        return list(reversed(parts))

    def reads_a_clock(node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            parts = dotted(sub.func)
            if not parts or len(parts) < 2:
                continue
            # 先頭の別名を解決する (`import datetime as dt` -> datetime)
            parts[0] = alias.get(parts[0], parts[0])
            # 末尾 2 つで判定するので `dt.datetime.now()` も
            # `datetime.now()` も同じように拾える
            if (parts[-2], parts[-1]) in CLOCK_CALLS:
                return True
        return False

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = {t.id for t in targets if isinstance(t, ast.Name)}
        names |= {t.attr for t in targets if isinstance(t, ast.Attribute)}
        if not (names & TARGET_NAMES):
            continue
        if node.value is not None and reads_a_clock(node.value):
            found.append(f"{path.name}:{node.lineno} {sorted(names & TARGET_NAMES)}")
    return found


@pytest.mark.parametrize("rel", GUARDED)
def test_no_module_builds_its_own_today(rel):
    """対象日を各自の時計から作っていないこと。"""
    path = REPO / rel
    if path.name in ALLOWED_MODULES:
        pytest.skip("単一出典そのもの")

    offenders = _clock_calls_assigned_to_a_day(path)

    assert not offenders, (
        f"{rel} が独自に対象日を作っている: {offenders}。"
        f"jst.current_jst_date / current_jst_daystamp を使うこと")


def test_the_guard_actually_catches_each_form(tmp_path):
    """ガード自身の対照実験。

    **禁止する綴りを記憶で列挙して取りこぼした**のが前回の失敗なので、
    実際に repo で見つかった書き方を 1 つずつ食わせて、全部落ちることを見る。
    """
    forms = [
        "from datetime import date\ntoday = date.today()",
        "from datetime import datetime\ntoday = datetime.now().date()",
        "from datetime import datetime\ntoday = datetime.now().strftime('%Y%m%d')",
        "from datetime import datetime, timezone\n"
        "today = datetime.now(timezone.utc).date()",
        "from datetime import datetime\nJST=None\n"
        "today = datetime.now(JST).strftime('%Y%m%d')",
        "from datetime import date as _d\nday = _d.today()",
        "import datetime as dt\ntoday = dt.datetime.now().date()",
        "import time\ntoday = time.strftime('%Y%m%d')",
        "from datetime import datetime\ndate = datetime.utcnow().date()",
    ]
    for i, src in enumerate(forms):
        f = tmp_path / f"m{i}.py"
        f.write_text(src, encoding="utf-8")
        assert _clock_calls_assigned_to_a_day(f), f"素通りした: {src!r}"


def test_the_guard_does_not_fire_on_timestamps_or_strings(tmp_path):
    """刻印と文字列リテラルでは落ちないこと (誤検出で無視されるようにしない)。

    前の正規表現版は文字列リテラル `"date.today()"` で誤検出していた。
    """
    benign = [
        "from datetime import datetime\n"
        "generated_at = datetime.now().isoformat()",           # 刻印
        "from datetime import datetime\n"
        "elapsed = datetime.now() - started",                   # 経過時間
        "msg = 'use date.today() instead'",                     # 文字列リテラル
        "from jst import current_jst_daystamp\n"
        "today = current_jst_daystamp()",                       # 正しい書き方
    ]
    for i, src in enumerate(benign):
        f = tmp_path / f"b{i}.py"
        f.write_text(src, encoding="utf-8")
        assert not _clock_calls_assigned_to_a_day(f), f"誤検出: {src!r}"
