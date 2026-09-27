"""「今日」を JST の時計から取る箇所の **挙動** テスト (2026-09-28 JST 最終ゲートの follow-up)。

## なぜ要るか

JST 最終ゲートのレビューで、レビュー担当が作った変異のうち次が生き残った:

- M2: `scripts/fetch_mining.normalize_date("today")` を前日にする
- M3: `gui/app.py` `Api._date_range` の「今日」を前日にする
- M4: `scripts/notify_dedup` をローカル時計にする (AST ガードでだけ撃墜)

`tests/test_today_single_source.py` の AST ガードは「独自の時計を作っていないか」を形で見る
だけなので、`current_jst_daystamp()` の結果を 1 日ずらす変異は素通りする。
ここでは JST の時計を **現実と離れた日付** に固定して、実際に返る日付を確かめる。
ローカル時計に戻すと現実の日付が、1 日ずらすと前日が出てくるので、どちらも落ちる。

`JST_EARLY` は JST 00:30 = UTC では前日 15:30。UTC ホストでローカル時計を読む実装は
ここで前日を返す。
"""
from __future__ import annotations

import contextlib
import importlib
import json
import sqlite3
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

import jst

JST = timezone(timedelta(hours=9))
FROZEN = datetime(2026, 1, 15, 10, 0, 0, tzinfo=JST)          # 現実と離れた日付
JST_EARLY = datetime(2026, 1, 15, 0, 30, 0, tzinfo=JST)       # UTC では 01-14 15:30


def _freeze(monkeypatch, at: datetime) -> None:
    """`jst` が読む現在時刻を `at` に固定する (tests/test_generator_today.py と同じ形)。"""
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return at.astimezone().replace(tzinfo=None)
            return at.astimezone(tz)

    monkeypatch.setattr(jst, "datetime", Frozen)


# --- M2: fetch_mining --------------------------------------------------------------

@pytest.mark.parametrize("at", [FROZEN, JST_EARLY], ids=["daytime", "jst_0030"])
@pytest.mark.parametrize("value", ["today", "TODAY", None, ""])
def test_fetch_mining_today_is_the_jst_date(monkeypatch, at, value):
    from scripts.fetch_mining import normalize_date

    _freeze(monkeypatch, at)
    assert normalize_date(value) == "20260115"


def test_fetch_mining_explicit_date_is_not_shifted(monkeypatch):
    from scripts.fetch_mining import normalize_date

    _freeze(monkeypatch, FROZEN)
    assert normalize_date("2026-01-10") == "20260110"


# --- M3: gui/app.py Api._date_range ------------------------------------------------

@pytest.fixture()
def gui_app(monkeypatch):
    """`gui.app` を読み込む。pywebview は venv64 に無いので空のモジュールで代える。

    `_date_range` は `webview` を使わないので、代えても挙動は変わらない。
    """
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    return importlib.import_module("gui.app")


def _races_db(days: list[str]):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT)")
    conn.executemany("INSERT INTO races VALUES (?, ?)", [(d[:4], d[4:]) for d in days])

    @contextlib.contextmanager
    def fake_open_db(*_a, **_k):
        yield conn
    return fake_open_db


@pytest.mark.parametrize("at", [FROZEN, JST_EARLY], ids=["daytime", "jst_0030"])
def test_gui_default_range_is_the_jst_today_when_it_has_races(gui_app, monkeypatch, at):
    """前日・当日・未来にレースがある DB。正しい実装は当日を返す。

    前日にずらす変異は 20260114 を、ローカル時計 (現実の日付) に戻す変異は
    「今日のレースが無い」側に落ちて最新日 20260120 を返すので、どちらも落ちる。
    """
    _freeze(monkeypatch, at)
    monkeypatch.setattr(gui_app, "open_db", _races_db(["20260114", "20260115", "20260120"]))
    assert gui_app.Api._date_range(object(), {}) == ("20260115", "20260115")


def test_gui_default_range_falls_back_to_the_latest_race_day(gui_app, monkeypatch):
    _freeze(monkeypatch, FROZEN)
    monkeypatch.setattr(gui_app, "open_db", _races_db(["20260110", "20260112"]))
    assert gui_app.Api._date_range(object(), {}) == ("20260112", "20260112")


def test_gui_explicit_range_is_used_as_given(gui_app, monkeypatch):
    _freeze(monkeypatch, FROZEN)
    monkeypatch.setattr(gui_app, "open_db", _races_db(["20260115"]))
    got = gui_app.Api._date_range(object(), {"from_date": "2026-01-01", "to_date": "2026-01-03"})
    assert got == ("20260101", "20260103")


# --- M4: notify_dedup ------------------------------------------------------------------

@pytest.mark.parametrize("at", [FROZEN, JST_EARLY], ids=["daytime", "jst_0030"])
def test_notify_dedup_records_the_jst_date(tmp_path, monkeypatch, at):
    from scripts import notify_dedup

    _freeze(monkeypatch, at)
    state = tmp_path / "state.json"
    assert notify_dedup.record("generation_complete", "20260115", {"n": 1}, path=state)
    saved = json.loads(state.read_text(encoding="utf-8"))
    (entry,) = saved.values()
    assert entry["date_jst"] == "20260115"
    assert entry["sent_at"].startswith(at.strftime("%Y-%m-%dT%H:%M"))
    assert entry["sent_at"].endswith("+09:00")


def test_notify_dedup_prunes_by_the_jst_today(tmp_path, monkeypatch):
    """保持期間の外の記録は、JST の今日を基準に捨てる (ローカル時計だと現実の日付基準になる)。"""
    from scripts import notify_dedup

    state = tmp_path / "state.json"
    _freeze(monkeypatch, FROZEN)
    assert notify_dedup.record("generation_complete", "20260115", {"n": 1}, path=state)
    # 同じ JST の日のうちは同じ中身を抑止する
    assert notify_dedup.decide("generation_complete", "20260115", {"n": 1}, "t", path=state).should_send is False
    # 保持期間を過ぎた JST の日には、同じ中身でも初回として扱う
    later = FROZEN + timedelta(days=notify_dedup.RETENTION_DAYS + 1)
    _freeze(monkeypatch, later)
    assert notify_dedup.decide("generation_complete", "20260115", {"n": 1}, "t", path=state).should_send is True
