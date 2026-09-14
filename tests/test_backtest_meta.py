"""backtest 成果物の再現性メタデータの門 (2026-09-14)。

## なぜ要るか

環境変数で予想の挙動が変わるのに、その事実が成果物に残らないと、後から
「この数字は何を設定して出したのか」が分からなくなる。

実例: `PRED_RANK_BY` (印をルールスコア順に付けるか確率順に付けるか) が
登録簿に無かったため、同じ期間・同じ設定に見える 2 本の backtest が
**4.4 ポイント違う** (p29 70.5% vs p30 74.9%) のに、違いの理由が成果物から
読み取れなかった。数字を比べる土台が壊れている状態だった。

## 落ちたときの直し方

`scripts/backtest.py` の `TRACKED_ENV_KEYS` に、その環境変数を足す。
「記録しなくてよい」と判断したものは下の IGNORED に理由付きで足す。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from scripts.backtest import TRACKED_ENV_KEYS

ROOT = Path(__file__).resolve().parent.parent

# 予想の挙動を変えうるコードが置かれている場所
PREDICTION_PATHS = [ROOT / "predictor", ROOT / "scripts" / "backtest.py"]

# 記録しなくてよい環境変数 (挙動ではなく実行環境に関するもの)。
IGNORED = {
    "PYTHONIOENCODING", "PYTHONUTF8", "PATH", "TMP", "TEMP",
    "AUTO_PREDICT_MIN_ENTRY_COVERAGE",   # 生成の中止閾値。予想の中身は変えない
}


def _env_reads(path: Path) -> set[str]:
    """`os.environ.get("X")` / `os.environ["X"]` で読まれるキー名を集める。"""
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # os.environ.get("X", ...)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            target = node.func.value
            if (isinstance(target, ast.Attribute) and target.attr == "environ") or (
                    isinstance(target, ast.Name) and target.id == "environ"):
                names.add(node.args[0].value)
        # os.environ["X"]
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                and node.value.attr == "environ"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            names.add(node.slice.value)
    return names


def _all_prediction_env_reads() -> set[str]:
    found: set[str] = set()
    for base in PREDICTION_PATHS:
        files = [base] if base.is_file() else sorted(base.rglob("*.py"))
        for f in files:
            found |= _env_reads(f)
    return found


def test_every_behaviour_changing_env_var_is_recorded():
    """予想経路が読む環境変数が、すべて成果物に記録される登録簿に載っていること。"""
    read = _all_prediction_env_reads() - IGNORED
    # PRED_W_* (重み個別上書き) は前方一致で丸ごと記録される
    read = {k for k in read if not k.startswith("PRED_W_")}

    missing = sorted(read - set(TRACKED_ENV_KEYS))

    assert not missing, (
        "予想の挙動を変える環境変数が成果物に記録されない:\n  "
        + "\n  ".join(missing)
        + "\nscripts/backtest.py の TRACKED_ENV_KEYS に足すこと "
          "(挙動を変えないものは本テストの IGNORED に理由付きで足す)。"
    )


def test_rank_by_is_tracked():
    """PRED_RANK_BY が登録されていること (2026-09-14 に発見した実バグの回帰)。

    印をルールスコア順に付けるか確率順に付けるかで回収率が 4.4pt 変わるのに、
    成果物にその設定が残っていなかった。
    """
    assert "PRED_RANK_BY" in TRACKED_ENV_KEYS


def test_snapshot_meta_records_a_set_override(monkeypatch):
    """実際に設定した値が meta に載ること (登録簿が使われていることの確認)。"""
    from scripts import backtest

    monkeypatch.setenv("PRED_RANK_BY", "probability")
    meta = backtest.snapshot_meta()

    assert meta["env_overrides"].get("PRED_RANK_BY") == "probability"


def test_snapshot_meta_is_empty_when_nothing_is_set(monkeypatch):
    """何も設定していなければ空 dict = 既定挙動の証明になること。"""
    from scripts import backtest

    for key in TRACKED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    meta = backtest.snapshot_meta()

    leftovers = {k: v for k, v in meta["env_overrides"].items()
                 if not k.startswith("PRED_W_")}
    assert leftovers == {}, f"設定していないのに記録されている: {leftovers}"
