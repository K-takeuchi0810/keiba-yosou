"""gui/app.py の Python→JS dict キー契約テスト (P23, 2026-06-13)。

変更失敗モード FM-1 (v2 監査 code-quality 指摘): Python 側が組む dict のキーを
~1,300 行離れた埋め込み JS が `b.recommended_kelly` 等で読む。キー改名・typo は
例外にならず画面に undefined が出るだけで静かに壊れる。

このテストはソーステキストから両側のキー集合を抽出して包含を検証する。
gui.app の import は不要 (pywebview 非依存で venv64 の pytest から回る)。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "gui" / "app.py"
SRC = APP_PY.read_text(encoding="utf-8")

# JS 予約語・組み込みなど、プロパティ参照として誤検出しやすいものを除外
JS_BUILTINS = {"length", "map", "join", "filter", "push", "toFixed", "slice"}


def _python_keys(func_marker: str, dict_marker: str) -> set[str]:
    """関数定義 func_marker 以降で最初に現れる dict_marker ブロックのキー集合。"""
    start = SRC.index(func_marker)
    block_start = SRC.index(dict_marker, start)
    # ブロック終端: 開き波括弧と対応する深さ 0 の閉じ括弧
    depth = 0
    i = SRC.index("{", block_start)
    for j in range(i, len(SRC)):
        if SRC[j] == "{":
            depth += 1
        elif SRC[j] == "}":
            depth -= 1
            if depth == 0:
                break
    block = SRC[i:j]
    return set(re.findall(r'"(\w+)"\s*:', block))


def _js_props(var: str) -> set[str]:
    """CONTROL_HTML の JS 内で `<var>.xxx` として読まれるプロパティ集合。"""
    html_start = SRC.index('CONTROL_HTML = """')
    js = SRC[html_start:]
    props = set(re.findall(rf"\b{var}\.(\w+)\b", js))
    return props - JS_BUILTINS


def test_buy_candidate_item_keys_cover_js():
    py = _python_keys("def get_dashboard", "item = {")
    js = _js_props("b")
    missing = js - py
    assert not missing, (
        f"JS が参照する買い候補キー {sorted(missing)} が Python 側 item dict にない "
        f"(gui/app.py の get_dashboard と renderDashboard の契約乖離)")


def test_summary_keys_cover_js():
    py = _python_keys("def get_dashboard", '"summary": {')
    js = _js_props("s")
    missing = js - py
    assert not missing, (
        f"JS が参照する summary キー {sorted(missing)} が Python 側にない")


def test_backtest_keys_cover_js():
    start = SRC.index("def _recent_backtest(")
    end = SRC.index("\n    def ", start + 10)
    body = SRC[start:end]
    py = set(re.findall(r'"(\w+)"\s*:', body))
    js = _js_props("bt")
    missing = js - py
    assert not missing, (
        f"JS が参照する backtest キー {sorted(missing)} が _recent_backtest の返り値にない")


def test_portfolio_keys_cover_js():
    from predictor.portfolio import compute_day_portfolio
    sample = compute_day_portfolio([{
        "date": "2026/06/13", "recommended_kelly": 0.03, "buy": True,
    }])
    empty = compute_day_portfolio([])
    py = set(sample.keys()) | set(empty.keys())
    js = _js_props("bp")
    missing = js - py
    assert not missing, (
        f"JS が参照する portfolio キー {sorted(missing)} が compute_day_portfolio の返り値にない")


def test_control_html_js_parses():
    """JS シンタックスエラーで全ボタンが死ぬ既知バグクラス (4 回以上再発) の自動検査。

    従来は手動 skill (python-embedded-js) 頼みだった node --check を pytest に組込む。
    node が無い環境では skip。
    """
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    html_start = SRC.index('CONTROL_HTML = """')
    html_end = SRC.index('"""', html_start + 20)
    html = SRC[html_start:html_end]
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts, "CONTROL_HTML に <script> が見つからない"
    # 注意: ここで取れるのは「Python エスケープ解釈前」のソース。\\n 等は
    # 解釈後も同形なので node --check の構文判定には十分 (役割は import 不要の
    # 簡易ゲート。厳密な解釈後検証は python-embedded-js skill が担う)。
    js = "\n".join(scripts)
    with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        assert r.returncode == 0, f"CONTROL_HTML の JS が構文エラー:\n{r.stderr[:2000]}"
    finally:
        Path(path).unlink(missing_ok=True)
