import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from scripts import build_daily_results

_SQLITE_CONNECT = sqlite3.connect


def _html_fragment(
    *,
    horse_name_html: str = "テストホース",
    odds_html: str = '22.9<br><span class="pick-reason">6人気</span>',
) -> str:
    return f"""
    <details id="race-20260712-02-1" class="race">
      <table class="entries"><tbody><tr>
        <td class="mark-cell" title="テスト"></td>
        <td class="horse-num waku-1">1</td>
        <td class="horse-name">{horse_name_html}</td>
        <td>{odds_html}</td>
      </tr></tbody></table>
    </details>
    """


def _run_main(
    tmp_path: Path,
    monkeypatch,
    *,
    html_text: str | None = None,
    expected_rc: int = 0,
) -> Path:
    conn = _SQLITE_CONNECT(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE horse_races (
          race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
          nichiji TEXT, race_num TEXT, horse_num TEXT, horse_name TEXT,
          win_odds INTEGER, win_popularity INTEGER, confirmed_order INTEGER,
          odds_fetched_at TEXT
        );
        CREATE TABLE payouts (
          race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
          nichiji TEXT, race_num TEXT, tan_horse_num1 TEXT, tan_payout1 INTEGER,
          fuku_horse_num1 TEXT, fuku_payout1 INTEGER,
          fuku_horse_num2 TEXT, fuku_payout2 INTEGER,
          fuku_horse_num3 TEXT, fuku_payout3 INTEGER,
          fuku_horse_num4 TEXT, fuku_payout4 INTEGER,
          fuku_horse_num5 TEXT, fuku_payout5 INTEGER
        );
        CREATE TABLE races (
          race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
          nichiji TEXT, race_num TEXT, race_name TEXT, distance INTEGER,
          track_type_code TEXT, grade_code TEXT, starter_count INTEGER,
          turf_condition TEXT, dirt_condition TEXT, weather_code TEXT
        );
        """
    )
    common = ("2026", "0712", "02", "01", "01", "1")
    conn.execute(
        "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (*common, "00", "プレースホルダ", 0, 0, 0, None),
    )
    conn.execute(
        "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (*common, "01", "テストホース", 229, 6, 1, "2026-07-12T10:00:00"),
    )
    conn.execute(
        "INSERT INTO payouts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (*common, "01", 500, "01", 200, None, None, "00", 0, None, None, None, None),
    )
    conn.execute(
        "INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (*common, "テスト競走", 1200, "24", "", 1, "", "1", "1"),
    )
    conn.commit()

    html_path = tmp_path / "predictions.html"
    html_path.write_text(html_text or _html_fragment(), encoding="utf-8")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(build_daily_results.sqlite3, "connect", lambda _path: conn)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_daily_results",
            "--date", "20260712",
            "--html", str(html_path),
            "--db", ":memory:",
            "--output-dir", str(output_dir),
        ],
    )
    assert build_daily_results.main() == expected_rc
    return output_dir


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_entries_odds_and_popularity_are_parsed_separately():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(_html_fragment())

    horse = parser.races[0]["horses"][0]
    assert horse["odds"] == 22.9
    assert horse["popularity"] == 6


def test_horse_name_nested_span_does_not_insert_space():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(_html_fragment(horse_name_html="テスト<span>ホース</span>"))

    assert parser.races[0]["horses"][0]["name"] == "テストホース"


def test_popularity_only_cell_does_not_become_odds():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(
        _html_fragment(
            odds_html='<span class="pick-reason">6人気</span>'
        )
    )

    horse = parser.races[0]["horses"][0]
    assert horse["odds"] is None
    assert horse["popularity"] == 6


def test_placeholder_horse_num_00_is_excluded(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)

    for name in ("final_odds.csv", "race_results.csv"):
        rows = _read_csv(output_dir / name)
        assert len(rows) == 1
        assert {row["horse_num"] for row in rows} == {"1"}


def test_race_num_is_zero_padded_in_every_csv(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)

    for name in (
        "predictions.csv",
        "final_odds.csv",
        "race_results.csv",
        "payouts.csv",
        "evaluation_summary.csv",
    ):
        rows = _read_csv(output_dir / name)
        assert rows
        assert {row["race_num"] for row in rows} == {"01"}


def test_payout_horse_numbers_match_other_csv_representation(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)

    payout = _read_csv(output_dir / "payouts.csv")[0]
    prediction = _read_csv(output_dir / "predictions.csv")[0]
    assert payout["tan_horse_num1"] == prediction["horse_num"] == "1"
    assert payout["fuku_horse_num1"] == prediction["horse_num"]
    assert payout["fuku_horse_num3"] == ""


def test_quality_gate_rejects_out_of_range_popularity(tmp_path, monkeypatch, capsys):
    output_dir = _run_main(
        tmp_path,
        monkeypatch,
        html_text=_html_fragment(
            odds_html='77.3<br><span class="pick-reason">310人気</span>'
        ),
        expected_rc=1,
    )

    assert "morning_popularity outside 1..18: 1 rows" in capsys.readouterr().err
    assert not (output_dir / "predictions.csv").exists()


def test_manifest_records_builder_provenance_and_superseded_hash(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)
    manifest_path = output_dir / "manifest.json"
    first_bytes = manifest_path.read_bytes()
    first = json.loads(first_bytes)
    assert first["builder_git_sha"]
    assert isinstance(first["builder_git_dirty"], bool)
    assert first["supersedes_manifest_sha256"] is None
    assert first["warnings"] == {
        "excluded_placeholder_rows": 1,
        "null_odds_fetched_at_rows": 0,
    }

    _run_main(tmp_path, monkeypatch)
    second = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert second["supersedes_manifest_sha256"] == hashlib.sha256(first_bytes).hexdigest()
