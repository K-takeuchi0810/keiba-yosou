from __future__ import annotations

import sys
from datetime import datetime, timedelta

import scripts.fetch_fresh_odds as mod


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def execute(self, *_args, **_kwargs):
        return _Rows(self._rows)


class _FakeJV:
    def __init__(self):
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def fetch_realtime(self, _dataspec, _key):
        self.calls += 1
        if self.calls == 1:
            return {
                "records_total": 2,
                "files_written": 1,
                "filenames": ["O1_fresh.jvd"],
            }
        raise RuntimeError("rt fetch failed")


class _FailingJV:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def fetch_realtime(self, _dataspec, _key):
        raise RuntimeError("all failed")


def test_fetch_fresh_odds_ingests_successful_files_even_if_later_race_fails(
    monkeypatch, tmp_path, capsys
):
    start = datetime.now() + timedelta(minutes=10)
    target_date = start.strftime("%Y%m%d")
    ymd = start.strftime("%Y%m%d")
    rows = [
        {
            "race_year": ymd[:4],
            "race_month_day": ymd[4:],
            "track_code": "05",
            "kaiji": "01",
            "nichiji": "01",
            "race_num": "01",
            "start_time": start.strftime("%H%M"),
        },
        {
            "race_year": ymd[:4],
            "race_month_day": ymd[4:],
            "track_code": "05",
            "kaiji": "01",
            "nichiji": "01",
            "race_num": "02",
            "start_time": start.strftime("%H%M"),
        },
    ]
    ingest_calls = []

    monkeypatch.setattr(mod, "LOCK_PATH", tmp_path / "fetch_fresh_odds.lock")
    monkeypatch.setattr(mod, "open_db", lambda: _Conn(rows))
    monkeypatch.setattr(mod, "JVLinkClient", _FakeJV)
    monkeypatch.setattr(mod, "ingest_all", lambda **kw: ingest_calls.append(kw) or {"ok": True})
    monkeypatch.setattr(
        sys,
        "argv",
        ["fetch_fresh_odds.py", "--date", target_date],
    )

    assert mod.main() == 0
    assert ingest_calls == [{"dataspecs": ["0B31"], "only_files": {"O1_fresh.jvd"}}]
    out = capsys.readouterr().out
    assert "error RuntimeError: rt fetch failed" in out
    assert "done: races=1 errors=1 records=2 files=1" in out


def test_fetch_fresh_odds_returns_nonzero_when_all_fetches_fail(monkeypatch, tmp_path):
    start = datetime.now() + timedelta(minutes=10)
    target_date = start.strftime("%Y%m%d")
    ymd = start.strftime("%Y%m%d")
    rows = [
        {
            "race_year": ymd[:4],
            "race_month_day": ymd[4:],
            "track_code": "05",
            "kaiji": "01",
            "nichiji": "01",
            "race_num": "01",
            "start_time": start.strftime("%H%M"),
        }
    ]
    ingest_calls = []

    monkeypatch.setattr(mod, "LOCK_PATH", tmp_path / "fetch_fresh_odds.lock")
    monkeypatch.setattr(mod, "open_db", lambda: _Conn(rows))
    monkeypatch.setattr(mod, "JVLinkClient", _FailingJV)
    monkeypatch.setattr(mod, "ingest_all", lambda **kw: ingest_calls.append(kw) or {"ok": True})
    monkeypatch.setattr(
        sys,
        "argv",
        ["fetch_fresh_odds.py", "--date", target_date],
    )

    assert mod.main() == 1
    assert ingest_calls == []
