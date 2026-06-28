from __future__ import annotations

import sys

import scripts.fetch_results as mod


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
        self.keys = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def fetch_realtime(self, dataspec, key):
        self.keys.append((dataspec, key))
        if key.endswith("01"):
            return {"records_total": 18, "files_written": 1, "filenames": ["0B12_01.jvd"]}
        raise RuntimeError("rt fetch failed")


class _FailingJV:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def fetch_realtime(self, _dataspec, _key):
        raise RuntimeError("all failed")


def test_race_result_key_uses_short_jvlink_race_key():
    assert mod.race_result_key(
        {
            "race_year": "2026",
            "race_month_day": "0620",
            "track_code": "05",
            "kaiji": "03",
            "nichiji": "04",
            "race_num": "11",
        }
    ) == "202606200511"


def test_fetch_results_ingests_successful_files_even_if_later_race_fails(monkeypatch, capsys):
    rows = [
        {
            "race_year": "2026",
            "race_month_day": "0620",
            "track_code": "05",
            "kaiji": "03",
            "nichiji": "04",
            "race_num": "01",
        },
        {
            "race_year": "2026",
            "race_month_day": "0620",
            "track_code": "05",
            "kaiji": "03",
            "nichiji": "04",
            "race_num": "02",
        },
    ]
    ingest_calls = []

    monkeypatch.setattr(mod, "open_db", lambda: _Conn(rows))
    monkeypatch.setattr(mod, "JVLinkClient", _FakeJV)
    monkeypatch.setattr(mod, "ingest_all", lambda **kw: ingest_calls.append(kw) or {"ok": True})
    monkeypatch.setattr(sys, "argv", ["fetch_results.py", "--date", "20260620"])

    assert mod.main() == 0
    assert ingest_calls == [{"dataspecs": ["0B12"], "only_files": {"0B12_01.jvd"}}]
    out = capsys.readouterr().out
    assert "fetching 1/2 05 01R key=202606200501" in out
    assert "error RuntimeError: rt fetch failed" in out


def test_fetch_results_returns_nonzero_when_all_fetches_fail(monkeypatch):
    rows = [
        {
            "race_year": "2026",
            "race_month_day": "0620",
            "track_code": "05",
            "kaiji": "03",
            "nichiji": "04",
            "race_num": "01",
        }
    ]
    ingest_calls = []

    monkeypatch.setattr(mod, "open_db", lambda: _Conn(rows))
    monkeypatch.setattr(mod, "JVLinkClient", _FailingJV)
    monkeypatch.setattr(mod, "ingest_all", lambda **kw: ingest_calls.append(kw) or {"ok": True})
    monkeypatch.setattr(sys, "argv", ["fetch_results.py", "--date", "20260620"])

    assert mod.main() == 1
    assert ingest_calls == []
