from __future__ import annotations

import sys

import scripts.fetch_mining as mod


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0]


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def execute(self, *_args, **_kwargs):
        return _Rows([(36,)])


class _FakeJV:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def fetch_realtime(self, dataspec, key):
        return {
            "dataspec": dataspec,
            "key": key,
            "records_total": 1,
            "files_written": 1,
            "filenames": [f"{dataspec}.jvd"],
        }


class _FailingJV:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def fetch_realtime(self, _dataspec, _key):
        raise RuntimeError("all failed")


def test_fetch_mining_fetches_dm_and_tm_for_target_date(monkeypatch, capsys):
    ingest_calls = []

    monkeypatch.setattr(mod, "open_db", lambda: _Conn())
    monkeypatch.setattr(mod, "JVLinkClient", _FakeJV)
    monkeypatch.setattr(mod, "ingest_all", lambda **kw: ingest_calls.append(kw) or {"ok": True})
    monkeypatch.setattr(sys, "argv", ["fetch_mining.py", "--date", "20260621"])

    assert mod.main() == 0
    assert {"dataspecs": ["0B13"], "only_files": {"0B13.jvd"}} in ingest_calls
    assert {"dataspecs": ["0B17"], "only_files": {"0B17.jvd"}} in ingest_calls
    out = capsys.readouterr().out
    assert "fetch_mining date=20260621 races=36" in out
    assert "fetching 0B13 key=20260621" in out
    assert "fetching 0B17 key=20260621" in out


def test_fetch_mining_returns_nonzero_when_all_fetches_fail(monkeypatch):
    ingest_calls = []

    monkeypatch.setattr(mod, "open_db", lambda: _Conn())
    monkeypatch.setattr(mod, "JVLinkClient", _FailingJV)
    monkeypatch.setattr(mod, "ingest_all", lambda **kw: ingest_calls.append(kw) or {"ok": True})
    monkeypatch.setattr(sys, "argv", ["fetch_mining.py", "--date", "20260621"])

    assert mod.main() == 1
    assert ingest_calls == []
