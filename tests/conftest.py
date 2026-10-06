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


# 見張りのモードは runtime_guard.py が唯一の出典 (環境変数名・値・子 pytest の環境)。
#   strict (既定) : 開発・worktree・変異テスト。変化があれば失敗
#   off           : 週次監視 (weekly_monitor.bat) の外側の pytest だけ
from runtime_guard import OFF, RUNTIME_GUARD_ENV  # noqa: E402
from runtime_guard import runtime_guard_mode as _runtime_guard_mode  # noqa: E402


def runtime_guard_mode() -> str:
    """見張りのモード。未知の値は黙って off にせず、その場で止める。"""
    try:
        return _runtime_guard_mode()
    except ValueError as e:
        raise pytest.UsageError(str(e)) from None


def pytest_configure(config):
    # 未知の値はテストを 1 本も流す前に止める (黙って見張りを外さない)
    runtime_guard_mode()


@pytest.fixture(scope="session", autouse=True)
def _tests_do_not_touch_runtime_logs():
    """テスト全体で `data/logs` と `data/runtime` を 1 バイトも変えないこと (2026-09-25)。

    main で pytest を回すと、そこは Task Scheduler が毎朝読む本番ツリーそのもの。
    watchdog のテストが本番の `auto_predict_watchdog.log` に 426 行書き込んでいた
    (「沈黙 = 未起動」を読む運用ログ)。テストがログを出すなら tmp_path へ。

    ## off にする場所は週次監視だけ

    前後の比較では **誰が書いたか** を区別できない。週次監視 (毎週日曜 10:00) は
    本番 checkout で pytest を回し、同じ時間帯に fresh odds の取得 (10 分ごと) なども
    data/logs に書くので、この見張りは必ず落ちる (2026-09-26 のレビューで再現)。
    そこで週次監視では `KEIBA_RUNTIME_GUARD=off` で **この見張りだけ** を止め、
    pytest の出力も data/logs の外に出す。警告に落とす方式は採らない (毎週ほぼ確実に
    出る警告は、テストの汚染か正規のタスクかを区別できず、読まれなくなる)。

    off で止まるのはこの見張りだけ。通知の状態ファイルの隔離 (上の fixture) や、
    変異テストの枠 (`scripts/mutation_sandbox.py`、子プロセスを常に strict で流す)
    は影響を受けない。
    """
    from pathlib import Path

    if runtime_guard_mode() == OFF:
        print(f"\n[{RUNTIME_GUARD_ENV}=off] 運用ログ置き場の前後比較を止めています "
              "(週次監視専用)")
        yield
        return
    root = Path(__file__).resolve().parents[1]
    before = _snapshot_runtime_dirs(root)
    yield
    after = _snapshot_runtime_dirs(root)
    changed = sorted(k for k in before.keys() | after.keys()
                     if before.get(k) != after.get(k))
    assert not changed, (
        "テストが運用ログ置き場を変更した (本番 checkout なら運用ログの汚染): "
        f"{changed}")


@pytest.fixture(scope="session", autouse=True)
def _isolate_research_window_log(tmp_path_factory):
    """研究の窓の関所の監査ログ (`config.RESEARCH_WINDOW_ACCESS_LOG`) を本番から切り離す (2026-10-06)。

    session 単位にする: module 単位の fixture (凍結物を一度だけ作るもの) が関所を通るので、関数単位の monkeypatch では間に合わない
    (実測: 関数単位では c_prime_run / group_d_run の module fixture が本物の data/runtime に書いた)。
    合成の DB で 2025 を読むテスト (目的の文字列 "test") だけは、凍結済みの runner の目的の一覧に足して通す。
    一覧の完全一致そのものは `tests/test_research_window.py` で確かめる (そこでは "test" 以外の文字列で止まることを見る)。
    """
    try:
        import config
        from scripts import research_window
    except ImportError:          # conftest を一時のリポジトリに写して試すテスト (test_conftest_guard 等) では関所が無い
        yield
        return
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "RESEARCH_WINDOW_ACCESS_LOG", tmp_path_factory.mktemp("research_window") / "access.jsonl")
    mp.setattr(research_window, "REPRODUCIBLE_PURPOSES", research_window.REPRODUCIBLE_PURPOSES | {"test"})
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _fresh_research_window_log_per_test(tmp_path, monkeypatch):
    """関数単位のテストは、自分の監査ログだけを見られるように tmp_path に向け直す。"""
    try:
        import config
    except ImportError:
        return
    if not hasattr(config, "RESEARCH_WINDOW_ACCESS_LOG"):
        return
    monkeypatch.setattr(config, "RESEARCH_WINDOW_ACCESS_LOG", tmp_path / "research_window_access.jsonl")
