"""JVLinkClient._wait_download_complete のタイムアウト / ストール検出テスト。

非リアルタイム JVStatus polling が無制限待ちでハングしていた
(2026-06-16 scorecard 残リスク) 対策の単体テスト。

sleep/clock を差し替えて 1 秒も待たずに境界条件を検証する。
"""
from __future__ import annotations

import pytest

from jvlink_client.client import JVLinkClient, JVLinkError


class _FakeJV:
    """JVStatus が指定通りに値を返すフェイク。"""

    def __init__(self, status_sequence):
        self._seq = list(status_sequence)
        self.calls = 0

    def JVStatus(self):
        self.calls += 1
        if self._seq:
            return self._seq.pop(0)
        return self._seq[-1] if self._seq else 0


class _Clock:
    def __init__(self, start=0.0):
        self.t = start

    def __call__(self):
        return self.t


def _make_client(jv) -> JVLinkClient:
    c = JVLinkClient.__new__(JVLinkClient)
    c._jv = jv
    c._initialized = True
    return c


def test_wait_returns_when_status_reaches_downloadcount():
    jv = _FakeJV([0, 5, 10])  # 0→5→10/10 で完了
    client = _make_client(jv)
    clock = _Clock()

    def sleep(_s):
        clock.t += 1.0

    client._wait_download_complete(10, "RACE", sleep=sleep, clock=clock)
    assert jv.calls == 3  # 0,5,10 の 3 回 polling


def test_wait_raises_on_total_timeout(monkeypatch):
    monkeypatch.setenv("JVLINK_DOWNLOAD_TIMEOUT_SEC", "5")
    monkeypatch.setenv("JVLINK_DOWNLOAD_STALL_SEC", "999")  # ストールには引っかからせない
    # status が常に 3/10 (前進はする) で全体 timeout に届く
    jv = _FakeJV([1, 2, 3, 3, 3, 3, 3, 3, 3])
    client = _make_client(jv)
    clock = _Clock()

    def sleep(_s):
        clock.t += 2.0  # 1 ループ 2 秒進む

    with pytest.raises(JVLinkError, match="timed out"):
        client._wait_download_complete(10, "RACE", sleep=sleep, clock=clock)


def test_wait_raises_on_stall_timeout(monkeypatch):
    monkeypatch.setenv("JVLINK_DOWNLOAD_TIMEOUT_SEC", "999")  # 全体には届かせない
    monkeypatch.setenv("JVLINK_DOWNLOAD_STALL_SEC", "3")
    # status=5 で進捗が止まり続ける
    jv = _FakeJV([5] * 20)
    client = _make_client(jv)
    clock = _Clock()

    def sleep(_s):
        clock.t += 2.0

    with pytest.raises(JVLinkError, match="stalled"):
        client._wait_download_complete(10, "RACE", sleep=sleep, clock=clock)


def test_wait_raises_on_negative_status():
    jv = _FakeJV([-1])
    client = _make_client(jv)
    clock = _Clock()
    with pytest.raises(JVLinkError, match="JVStatus failed"):
        client._wait_download_complete(10, "RACE", sleep=lambda _s: None, clock=clock)


def test_progress_callback_receives_remaining():
    jv = _FakeJV([3, 7, 10])
    client = _make_client(jv)
    clock = _Clock()
    events = []

    def progress(stage, info):
        events.append((stage, info["remaining"]))

    def sleep(_s):
        clock.t += 1.0

    client._wait_download_complete(10, "RACE", on_progress=progress, sleep=sleep, clock=clock)
    assert events == [("download", 7), ("download", 3), ("download", 0)]
