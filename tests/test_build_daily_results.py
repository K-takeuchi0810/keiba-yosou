import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from scripts import build_daily_results

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
    starter_count: int = 18,
    registered_count: int = 18,
) -> Path:
    db_path = tmp_path / "daily_results.sqlite3"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
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
          track_type_code TEXT, grade_code TEXT, registered_count INTEGER,
          starter_count INTEGER,
          turf_condition TEXT, dirt_condition TEXT, weather_code TEXT,
          start_time TEXT
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
        "INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            *common, "テスト競走", 1200, "24", "",
            registered_count, starter_count, "", "1", "1", "1100",
        ),
    )
    conn.commit()
    conn.close()

    html_path = tmp_path / "predictions.html"
    html_path.write_text(html_text or _html_fragment(), encoding="utf-8")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_daily_results",
            "--date", "20260712",
            "--html", str(html_path),
            "--db", str(db_path),
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


def test_entries_data_attributes_take_priority_over_display_text():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(
        _html_fragment(
            odds_html=(
                '<span class="pick-reason">18人気</span>'
            )
        ).replace(
            "<td><span",
            '<td class="col-odds" data-odds="7.5" data-popularity="3"><span',
        )
    )

    horse = parser.races[0]["horses"][0]
    assert horse["odds"] == 7.5
    assert horse["popularity"] == 3


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

    assert "morning_popularity outside registered/starter limit" in capsys.readouterr().err
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
        "schema": 2,
        "excluded_placeholder_rows": 1,
        "null_odds_fetched_at_rows": 0,
        "post_start_stamped_rows": 0,
        "post_start_unclassified_rows": 0,
        "morning_popularity_populated_rows": 1,
    }

    _run_main(tmp_path, monkeypatch)
    second = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert second["supersedes_manifest_sha256"] == hashlib.sha256(first_bytes).hexdigest()


def test_race_num_of_is_directly_testable():
    assert build_daily_results.race_num_of(1) == "01"
    assert build_daily_results.race_num_of("12") == "12"


def test_post_start_stamped_rows_counts_only_late_odds():
    races = [{
        "track_code": "02", "kaiji": "01", "nichiji": "01",
        "race_num": "1", "start_time": "1100",
    }]
    horses = [
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "1",
         "odds_fetched_at": "2026-07-12T10:59:00"},
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "1",
         "odds_fetched_at": "2026-07-12T11:01:00"},
    ]
    assert build_daily_results.count_post_start_stamped_rows(
        horses, races, "20260712"
    ) == 1


def test_post_start_unclassified_counts_missing_or_invalid_start():
    horses = [
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "1",
         "odds_fetched_at": "2026-07-12T10:59:00"},
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "2",
         "odds_fetched_at": "2026-07-12T10:59:00"},
    ]
    races = [{
        "track_code": "02", "kaiji": "01", "nichiji": "01",
        "race_num": "1", "start_time": "bad",
    }]
    assert build_daily_results.classify_post_start_rows(
        horses, races, "20260712"
    ) == (0, 2)


def test_popularity_quality_gate_allows_withdrawal_gap(tmp_path, monkeypatch):
    output_dir = _run_main(
        tmp_path,
        monkeypatch,
        html_text=_html_fragment(
            odds_html='7.7<br><span class="pick-reason">14人気</span>'
        ),
        starter_count=13,
        registered_count=14,
    )
    assert (output_dir / "predictions.csv").exists()


def test_popularity_quality_gate_rejects_true_abnormality():
    errors = build_daily_results.validate_output_quality(
        [{"race_id": "R1", "horse_num": "1", "morning_popularity": 20}],
        popularity_limit_by_race={
            "R1": (14, "max(starter_count=13, registered_count=14)")
        },
    )
    assert errors == [
        "morning_popularity outside registered/starter limit: 1 rows; "
        "R1 limit=14 (max(starter_count=13, registered_count=14))"
    ]
