"""pytest 共通設定。

リポジトリルートの import path 追加は pyproject.toml の
`[tool.pytest.ini_options] pythonpath = ["."]` が担う
(predictor.portfolio が `from config import ...` するため)。
このファイルは tests/ を pytest のテストパッケージとして明示する役割のみ。
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_notification_state(tmp_path, monkeypatch):
    """通知の状態ファイルを **本番から切り離す**。

    これが無いと、`auto_predict.main()` を通すテストが本番の
    `data/runtime/notification_state.json` に架空の payload を書き込み、
    当日の本物の中止通知がその中身と一致して抑止されうる。
    導入直後に実際に起きた (架空の `total: 2` が本番状態に残った)。
    """
    monkeypatch.setenv("NOTIFY_STATE_PATH",
                       str(tmp_path / "notification_state.json"))
    yield
    os.environ.pop("NOTIFY_STATE_PATH", None)
