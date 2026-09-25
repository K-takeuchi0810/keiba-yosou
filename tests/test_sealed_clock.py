"""封印の開始日判定 (`config.sealed_window_started`) の時計 (2026-09-25)。

## なぜ要るか

以前は `date.today()` = **OS のローカル日付**で「今日」を作っていた。UTC のホストでは
JST 10/01 00:00-08:59 がまだ 9/30 と判定され、封印窓の最初の 9 時間を dev 窓として
扱う (モデルを変えてよい・結果を見てよい側に倒れる)。いまは `SEALED_FROM=None`
(開始日未定) なので実害は出ていないが、開始日を入れた瞬間から効く。

## 何を固定するか

- 境界: JST 9/30 00:00 / 9/30 23:59:59 / 10/01 00:00:00 の直前・ちょうど・直後
- UTC で渡しても同じ判定 (UTC 9/30 15:00:00 = JST 10/01 00:00:00)
- **既定経路** (`now` を渡さない) も同じ時計を通ること。注入テストだけ緑で既定経路が
  壊れている、という過去の失敗を繰り返さない
- **OS のタイムゾーンを変えても**結果が変わらないこと (subprocess で TZ を変える)
- `SEALED_FROM=None` は日付によらず始まらない。日付指定とは **別の fixture** で見る
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import config
import jst

REPO = Path(__file__).resolve().parents[1]
JST = timezone(timedelta(hours=9))
UTC = timezone.utc


@pytest.fixture()
def sealed_from_1001(monkeypatch):
    """封印開始日を 2026-10-01 にした状態 (判定は未実施)。"""
    monkeypatch.setattr(config, "SEALED_FROM", "20261001")
    monkeypatch.setattr(config, "SEALED_UNTIL", "20260930")
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", False)


@pytest.fixture()
def sealed_unset(monkeypatch):
    """封印開始日が未定の状態 (現在の本番設定と同じ)。"""
    monkeypatch.setattr(config, "SEALED_FROM", None)
    monkeypatch.setattr(config, "SEALED_UNTIL", None)
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", False)


def _freeze_jst_clock(monkeypatch, instant: datetime):
    """`jst` が読む現在時刻を `instant` に固定する (既定経路のテスト用)。

    tz 無しで `now()` を呼ばれたら **OS のローカル時刻として** 返す (本物と同じ)。
    実装がローカル時刻に頼る形へ戻ると、OS のタイムゾーン次第で答えが変わる。
    """
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return instant.astimezone().replace(tzinfo=None)
            return instant.astimezone(tz)

    monkeypatch.setattr(jst, "datetime", FrozenDatetime)


# --- 境界 (now を注入) -----------------------------------------------------

@pytest.mark.parametrize("now,want", [
    (datetime(2026, 9, 30, 0, 0, 0, tzinfo=JST), False),         # JST 9/30 00:00
    (datetime(2026, 9, 30, 23, 59, 59, tzinfo=JST), False),      # 開始前の最後の 1 秒
    (datetime(2026, 9, 30, 23, 59, 59, 999999, tzinfo=JST), False),  # 直前
    (datetime(2026, 10, 1, 0, 0, 0, tzinfo=JST), True),          # 開始ちょうど
    (datetime(2026, 10, 1, 0, 0, 1, tzinfo=JST), True),          # 直後
    (datetime(2026, 9, 30, 14, 59, 59, tzinfo=UTC), False),      # = JST 9/30 23:59:59
    (datetime(2026, 9, 30, 15, 0, 0, tzinfo=UTC), True),         # = JST 10/01 00:00:00
    (datetime(2026, 10, 1, 8, 59, 59, tzinfo=JST), True),        # UTC ではまだ 9/30
])
def test_the_seal_starts_at_jst_midnight(sealed_from_1001, now, want):
    """封印は JST 10/01 00:00:00 ちょうどに始まること (UTC で渡しても同じ)。"""
    assert config.sealed_window_started(now=now) is want, now.isoformat()


def test_a_naive_now_is_rejected(sealed_from_1001):
    """tz 無しの時刻は受け付けないこと (UTC かローカルか分からないので)。"""
    with pytest.raises(ValueError):
        config.sealed_window_started(now=datetime(2026, 10, 1, 0, 0, 0))


def test_an_explicit_day_still_works(sealed_from_1001):
    """既存の呼び方 (YYYYMMDD を渡す) を壊していないこと。"""
    assert config.sealed_window_started("20260930") is False
    assert config.sealed_window_started("20261001") is True


# --- 既定経路 (now を渡さない) ---------------------------------------------

@pytest.mark.parametrize("instant,want", [
    (datetime(2026, 9, 30, 14, 59, 59, tzinfo=UTC), False),
    (datetime(2026, 9, 30, 15, 0, 0, tzinfo=UTC), True),
])
def test_the_default_path_reads_the_jst_clock(sealed_from_1001, monkeypatch,
                                              instant, want):
    """★ 引数なしの呼び出しも JST の時計を通ること。

    注入テストだけ緑で既定経路が `date.today()` のまま、という状態を捕まえる。
    `date.today()` は固定した時計を見ないので、ここで食い違う。
    """
    _freeze_jst_clock(monkeypatch, instant)

    assert config.sealed_window_started() is want


def test_the_default_path_matches_the_injected_path(sealed_from_1001, monkeypatch):
    """既定経路と注入経路が同じ答えを出すこと。"""
    for instant in (datetime(2026, 9, 30, 14, 59, 59, tzinfo=UTC),
                    datetime(2026, 9, 30, 15, 0, 0, tzinfo=UTC),
                    datetime(2026, 10, 1, 3, 0, 0, tzinfo=UTC)):
        _freeze_jst_clock(monkeypatch, instant)
        assert config.sealed_window_started() is config.sealed_window_started(
            now=instant), instant.isoformat()


# --- 未定 (別 fixture) ------------------------------------------------------

@pytest.mark.parametrize("now", [
    datetime(2026, 9, 30, 23, 59, 59, tzinfo=JST),
    datetime(2026, 10, 1, 0, 0, 0, tzinfo=JST),
    datetime(2027, 1, 1, 0, 0, 0, tzinfo=JST),
])
def test_an_unset_start_never_starts(sealed_unset, monkeypatch, now):
    """開始日が未定 (None) なら、どの日付でも始まらないこと (既定経路も)。"""
    assert config.sealed_window_started(now=now) is False
    _freeze_jst_clock(monkeypatch, now)
    assert config.sealed_window_started() is False


def test_the_real_setting_is_still_unset():
    """本番設定は開始日未定のままであること (時計の修正と設定変更を混ぜない)。

    封印開始日を入れるなら別のコミットで行う。ここが落ちたら、その変更が
    時計の修正に紛れ込んでいないかを確認する。
    """
    assert config.SEALED_FROM is None
    assert config.SEALED_UNTIL is None


# --- OS のタイムゾーンを変える (subprocess) --------------------------------

_PROBE = r"""
import json, sys, time
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
import config, jst

config.SEALED_FROM, config.SEALED_UNTIL, config.SEALED_JUDGMENT_DONE = "20261001", "20260930", False
out = {"timezone": time.timezone, "results": []}
for iso in sys.argv[2:]:
    instant = datetime.fromisoformat(iso)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return instant.astimezone().replace(tzinfo=None)
            return instant.astimezone(tz)

    jst.datetime = Frozen
    out["results"].append(config.sealed_window_started())
print(json.dumps(out))
"""

_INSTANTS = [
    "2026-09-30T14:59:59+00:00",     # JST 9/30 23:59:59
    "2026-09-30T15:00:00+00:00",     # JST 10/01 00:00:00
    "2026-10-01T08:59:59+09:00",     # UTC ではまだ 9/30
]


def _probe(tz: str) -> dict:
    env = {**os.environ, "TZ": tz}
    r = subprocess.run([sys.executable, "-c", _PROBE, str(REPO), *_INSTANTS],
                       capture_output=True, text=True, env=env, cwd=REPO, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_the_os_timezone_does_not_change_the_answer():
    """★ OS のタイムゾーンを UTC / JST / 米太平洋に変えても答えが同じこと。

    まず TZ が本当に効いていることを確かめる (効いていなければこのテストは無意味)。
    """
    runs = {tz: _probe(tz) for tz in ("UTC0", "JST-9", "PST8PDT")}

    offsets = {tz: r["timezone"] for tz, r in runs.items()}
    assert len(set(offsets.values())) == 3, (
        f"TZ が子プロセスに効いていない (テストが成立しない): {offsets}")
    for tz, r in runs.items():
        assert r["results"] == [False, True, True], (
            f"OS のタイムゾーン {tz} で封印の判定が変わる: {r['results']}")


# --- 月の途中の開始日 (日単位で比べていること) ----------------------------

@pytest.fixture()
def sealed_from_1015(monkeypatch):
    """封印開始日を月の途中 (2026-10-15) にした状態。

    開始日が月初 (10/01) だけだと、「月単位で比べる」ように壊れても
    10/01 の境界では結果が変わらず気付けない (変異 S-f が生存)。
    """
    monkeypatch.setattr(config, "SEALED_FROM", "20261015")
    monkeypatch.setattr(config, "SEALED_UNTIL", "20261014")
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", False)


@pytest.mark.parametrize("now,want", [
    (datetime(2026, 10, 1, 0, 0, 0, tzinfo=JST), False),        # 同じ月の月初
    (datetime(2026, 10, 14, 0, 0, 0, tzinfo=JST), False),
    (datetime(2026, 10, 14, 23, 59, 59, tzinfo=JST), False),     # 開始前の最後の 1 秒
    (datetime(2026, 10, 15, 0, 0, 0, tzinfo=JST), True),         # 開始ちょうど
    (datetime(2026, 10, 14, 14, 59, 59, tzinfo=UTC), False),     # = JST 10/14 23:59:59
    (datetime(2026, 10, 14, 15, 0, 0, tzinfo=UTC), True),        # = JST 10/15 00:00:00
    (datetime(2026, 10, 31, 12, 0, 0, tzinfo=JST), True),
    (datetime(2026, 9, 30, 12, 0, 0, tzinfo=JST), False),        # 前の月
])
def test_a_mid_month_start_is_compared_by_day(sealed_from_1015, now, want):
    """★ 開始日が月の途中でも日単位で判定すること (10/14 は前、10/15 から)。"""
    assert config.sealed_window_started(now=now) is want, now.isoformat()


def test_a_mid_month_start_on_the_default_path(sealed_from_1015, monkeypatch):
    """月の途中の境界を既定経路 (now なし) でも見る。"""
    _freeze_jst_clock(monkeypatch, datetime(2026, 10, 14, 14, 59, 59, tzinfo=UTC))
    assert config.sealed_window_started() is False
    _freeze_jst_clock(monkeypatch, datetime(2026, 10, 14, 15, 0, 0, tzinfo=UTC))
    assert config.sealed_window_started() is True


# --- 不正な引数はその場で落とす (fail-fast) --------------------------------

def test_today_and_now_together_are_rejected(sealed_from_1001):
    """today と now を同時に渡したら ValueError (どちらが勝ったか見えないため)。"""
    with pytest.raises(ValueError, match="同時"):
        config.sealed_window_started(
            "20260930", now=datetime(2026, 10, 1, 0, 0, 0, tzinfo=JST))


@pytest.mark.parametrize("bad", [
    "2026-10-01",      # "-" < "1" で静かに False になっていた形
    "2026/10/01",
    "261001",
    "202610011",
    "",
    "20261332",        # 実在しない日付
    "20260230",
    20261001,          # 文字列でない
])
def test_a_malformed_today_is_rejected(sealed_from_1001, bad):
    """YYYYMMDD でない / 実在しない日付の today は ValueError。"""
    with pytest.raises(ValueError):
        config.sealed_window_started(bad)


def test_a_malformed_today_is_rejected_even_when_unset(sealed_unset):
    """封印が未定でも不正な引数は通さないこと (未定のあいだ隠れて、開始後に出る)。"""
    with pytest.raises(ValueError):
        config.sealed_window_started("2026-10-01")
    with pytest.raises(ValueError):
        config.sealed_window_started(
            "20261001", now=datetime(2026, 10, 1, 0, 0, 0, tzinfo=JST))


@pytest.mark.parametrize("bad_from", ["2026-10-01", "20261301", "261001"])
def test_a_malformed_sealed_from_is_rejected(monkeypatch, bad_from):
    """設定の SEALED_FROM が YYYYMMDD でなければ ValueError (静かに比べない)。"""
    monkeypatch.setattr(config, "SEALED_FROM", bad_from)
    monkeypatch.setattr(config, "SEALED_JUDGMENT_DONE", False)

    with pytest.raises(ValueError, match="SEALED_FROM"):
        config.sealed_window_started(now=datetime(2026, 10, 1, 0, 0, 0, tzinfo=JST))
