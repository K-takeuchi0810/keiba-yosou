"""pytest 共通設定。

リポジトリルートの import path 追加は pyproject.toml の
`[tool.pytest.ini_options] pythonpath = ["."]` が担う
(predictor.portfolio が `from config import ...` するため)。
このファイルは tests/ を pytest のテストパッケージとして明示する役割のみ。
"""

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


_RUNTIME_DIRS = ("data/logs", "data/runtime")


def _snapshot_runtime_dirs(root):
    """本番の運用ログ置き場の中身 (名前・サイズ・更新時刻)。"""
    snap = {}
    for rel in _RUNTIME_DIRS:
        d = root / rel
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file():
                    st = p.stat()
                    snap[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return snap


@pytest.fixture(scope="session", autouse=True)
def _tests_do_not_touch_runtime_logs():
    """テスト全体で `data/logs` と `data/runtime` を 1 バイトも変えないこと (2026-09-25)。

    main で pytest を回すと、そこは Task Scheduler が毎朝読む本番ツリーそのもの。
    watchdog のテストが本番の `auto_predict_watchdog.log` に 426 行書き込んでいた
    (「沈黙 = 未起動」を読む運用ログ)。テストがログを出すなら tmp_path へ。

    まれに、テストと同時刻に本物の定期実行 (08:00 / 09:00 / 11:00 など) が走ると
    ここで落ちる。そのときは差分のファイル名が本番起動のものかを見て判断する。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    before = _snapshot_runtime_dirs(root)
    yield
    after = _snapshot_runtime_dirs(root)
    changed = sorted(k for k in before.keys() | after.keys()
                     if before.get(k) != after.get(k))
    assert not changed, (
        "テストが運用ログ置き場を変更した (本番 checkout なら運用ログの汚染): "
        f"{changed}")
