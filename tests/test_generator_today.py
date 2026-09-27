"""予想ページの既定の日付と、完全性アラートの基準日の **挙動** テスト (2026-09-26)。

## なぜ要るか

`web/generator.py` の `build_view_model` は、`from_date` / `to_date` を省略すると
「今日 ±14 日」を窓にし、その「今日」を `assess_race_completeness` (公開前の
完全性アラート) の基準日にも渡す。`tests/test_today_single_source.py` の AST ガードは
「今日を独自の時計から作っていないか」を代入先の名前で見るだけなので、

    別名で import したローカル時計に戻す / 1 日前にずらす

といった変異は素通りした (2026-09-25 の再レビューで 3 変異が 3/3 生存)。
ここでは JST の時計を **現実と離れた日付** に固定し、実際に計算された窓と基準日を
確かめる。ローカル時計を読む実装に戻ると、現実の日付が出てきて食い違う。
"""
from __future__ import annotations

import contextlib
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import jst

REPO = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))

#: 固定する時刻。現実の今日と十分に離しておく (ローカル時計の変異と区別するため)。
FROZEN = datetime(2026, 1, 15, 10, 0, 0, tzinfo=JST)


@pytest.fixture()
def frozen_jst(monkeypatch):
    """`jst` が読む現在時刻を FROZEN に固定する。"""
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return FROZEN.astimezone().replace(tzinfo=None)
            return FROZEN.astimezone(tz)

    monkeypatch.setattr(jst, "datetime", Frozen)
    return FROZEN


@pytest.fixture()
def empty_db(tmp_path, monkeypatch):
    """スキーマだけの空 DB に generator をつなぎ、最初の races クエリの窓を記録する。"""
    import web.generator as g

    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.executescript((REPO / "data" / "schema.sql").read_text(encoding="utf-8"))
    conn.close()
    seen: dict = {}

    class Recording:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if "FROM races" in sql and "window" not in seen:
                seen["window"] = tuple(params)
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    @contextlib.contextmanager
    def fake_open():
        real = sqlite3.connect(db)
        real.row_factory = sqlite3.Row
        try:
            yield Recording(real)
        finally:
            real.close()

    monkeypatch.setattr(g, "open_db_readonly", fake_open)
    return seen


@pytest.fixture()
def completeness_calls(monkeypatch):
    """generator が完全性アラートに渡した `today` を記録する。"""
    import web.publish_safety as ps

    calls: list = []
    real = ps.assess_race_completeness

    def recording(days, *, today=None, **kwargs):
        calls.append(today)
        return real(days, today=today, **kwargs)

    monkeypatch.setattr(ps, "assess_race_completeness", recording)
    return calls


# --- generator の既定の窓 ---------------------------------------------------

def test_the_default_window_is_jst_today_plus_minus_14(frozen_jst, empty_db,
                                                       completeness_calls):
    """★ from/to を省略すると、JST の今日 ±14 日が窓になること。"""
    from web.generator import build_view_model

    build_view_model()

    assert empty_db["window"] == ("20260101", "20260129"), (
        f"既定の窓が JST の今日 (2026-01-15) ±14 日でない: {empty_db['window']}")


def test_the_completeness_alert_gets_the_same_jst_today(frozen_jst, empty_db,
                                                        completeness_calls):
    """★ 完全性アラートの基準日も同じ JST の今日であること。

    窓と基準日が別の時計から作られると、「窓は 1/15 基準、アラートは 1/14 を見る」
    のような食い違いになる。
    """
    from web.generator import build_view_model

    build_view_model()

    assert completeness_calls == [date(2026, 1, 15)], completeness_calls


def test_an_explicit_window_is_used_as_given(frozen_jst, empty_db, completeness_calls):
    """対照: from/to を渡せばその窓を使う (既定の窓を強制していない)。"""
    from web.generator import build_view_model

    build_view_model(from_date="20250301", to_date="20250302")

    assert empty_db["window"] == ("20250301", "20250302")
    # 完全性アラートの基準日は窓ではなく「今日」のまま
    assert completeness_calls == [date(2026, 1, 15)]


# --- publish_safety の基準日 -------------------------------------------------

def _days():
    """1/15 は 2 レース中 1 レースが空、1/20 は 1 レースすべて空、現実の今日は空 0。"""
    real_today = date.today().strftime("%Y%m%d")
    return [
        {"date": "20260115", "races": [{"horses": []}, {"horses": [{"n": 1}]}]},
        {"date": "20260120", "races": [{"horses": []}]},
        {"date": real_today, "races": [{"horses": [{"n": 1}]}] * 3},
    ]


def test_the_default_base_date_is_jst_today(frozen_jst):
    """★ today を省略すると JST の今日 (1/15) だけを数えること。

    `date.today()` (OS のローカル日付) に戻すと、現実の今日のレースを数えて
    ここで食い違う。
    """
    from web.publish_safety import assess_race_completeness

    r = assess_race_completeness(_days())

    assert (r["total_races"], r["empty_races"]) == (2, 1), r
    assert r["alert"] is True


def test_an_injected_base_date_wins(frozen_jst):
    """today を渡せば、その日だけを数えること (注入が既定より優先)。"""
    from web.publish_safety import assess_race_completeness

    r = assess_race_completeness(_days(), today=date(2026, 1, 20))

    assert (r["total_races"], r["empty_races"]) == (1, 1), r
