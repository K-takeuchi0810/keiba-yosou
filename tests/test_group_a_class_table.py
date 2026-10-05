"""scripts/group_a_class_table.py (Group A 専用のクラスの抽出) の挙動のテスト。"""
from __future__ import annotations

import csv
import json

import pytest

from jvlink_client import parser as P
from scripts import group_a_class_table as g


def _ra(ymd="20230603", tc="05", kai="03", nichi="01", rn="05", div="7",
        c2="701", c3="000", c4="000", c5="000", cmin="701") -> bytes:
    rec = bytearray(b" " * P.RA_LENGTH)

    def put(pos: int, text: str) -> None:
        b = text.encode("ascii")
        rec[pos - 1:pos - 1 + len(b)] = b

    put(1, "RA"); put(3, div); put(12, ymd[:4]); put(16, ymd[4:]); put(20, tc); put(22, kai); put(24, nichi)
    put(26, rn); put(623, c2); put(626, c3); put(629, c4); put(632, c5); put(635, cmin)
    put(698, "1600"); put(706, "11")
    return bytes(rec)


def _file(tmp_path, name, *recs):
    p = tmp_path / name
    p.write_bytes(b"".join(r + b"\r\n" for r in recs))
    return p


def test_reads_the_five_condition_codes_at_the_spec_positions(tmp_path):
    f = _file(tmp_path, "RAVM1.jvd", _ra(c2="000", c3="005", c4="005", c5="005", cmin="005"))
    t = g.extract([f])
    assert t == {"20230603_05_03_01_05": {"c2": "000", "c3": "005", "c4": "005", "c5": "005", "cmin": "005",
                                          "data_divs": {"7"}, "files": {"RAVM1.jvd"},
                                          "track_type_code": "11", "distance": 1600}}


def test_conflicting_codes_for_the_same_race_stop(tmp_path):
    a = _file(tmp_path, "RAVM1.jvd", _ra(cmin="701"))
    b = _file(tmp_path, "RASW1.jvd", _ra(cmin="703", c2="703"))
    with pytest.raises(g.ClassTableError, match="食い違う"):
        g.extract([a, b])


def test_same_codes_from_two_files_merge(tmp_path):
    a = _file(tmp_path, "RAVM1.jvd", _ra(div="2"))
    b = _file(tmp_path, "RASW1.jvd", _ra(div="7"))
    t = g.extract([a, b])["20230603_05_03_01_05"]
    assert t["data_divs"] == {"2", "7"} and t["files"] == {"RAVM1.jvd", "RASW1.jvd"}


def test_non_jra_and_out_of_range_are_skipped(tmp_path):
    f = _file(tmp_path, "RAVM1.jvd", _ra(tc="30"), _ra(ymd="20201231"), _ra(ymd="20260101"), _ra(tc="10", rn="01"))
    assert list(g.extract([f])) == ["20230603_10_03_01_01"]


@pytest.mark.parametrize("code", ["701", "703", "005", "010", "016", "999"])
def test_canonical_class_is_the_category(code):
    assert g.canonical_class(code) == code


@pytest.mark.parametrize("code", ["000", "   ", "100", "702", "099", "???"])
def test_unexpected_min_age_code_stops(code):
    with pytest.raises(g.ClassTableError, match="想定外"):
        g.canonical_class(code)


def test_build_stops_on_unexpected_code(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _file(raw, "RAVM1.jvd", _ra(cmin="000"))
    with pytest.raises(g.ClassTableError):
        g.build(raw, tmp_path / "out")


def test_build_writes_table_and_manifest(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _file(raw, "RAVM1.jvd", _ra(rn="01", c2="703", cmin="703"),
          _ra(rn="02", c2="000", c3="010", c4="010", c5="010", cmin="010"))
    m = g.build(raw, tmp_path / "out")
    rows = list(csv.DictReader((tmp_path / "out" / "class_table.csv").open(encoding="utf-8")))
    assert [(r["race_id"], r["canonical_class"]) for r in rows] == [
        ("20230603_05_03_01_01", "703"), ("20230603_05_03_01_02", "010")]
    assert rows[0]["source_sha256"] == g.sha256(raw / "RAVM1.jvd")
    assert m["n_races"] == 2 and m["mapping_version"] == "class_v1"
    assert m["counts_by_year_class"] == {"2023": {"703": 1, "010": 1}}
    assert m["class_table_sha256"] == g.sha256(tmp_path / "out" / "class_table.csv")
    assert json.loads((tmp_path / "out" / "MANIFEST.json").read_text(encoding="utf-8"))["n_races"] == 2


def test_age_slot_disagreement_is_counted(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _file(raw, "RAVM1.jvd", _ra(c2="000", c3="005", c4="010", c5="010", cmin="005"))
    assert g.build(raw, tmp_path / "out")["n_races_with_different_age_slot_codes"] == 1


def test_probe_checks_the_age_slot_as_well(tmp_path, monkeypatch):
    raw = tmp_path / "raw"; raw.mkdir()
    # 期待: 4 歳以上の 1 勝クラス。最若年は 005 で合うが、4 歳の欄 (c4) が違えば不合格
    _file(raw, "RAVM1.jvd", _ra(c2="000", c3="000", c4="010", c5="005", cmin="005"))
    monkeypatch.setattr(g, "_load_expected", lambda: {"20230603_05_03_01_05": ("005", 4)})
    rep = g.probe(raw)
    assert rep["ok"] is False and rep["mismatch"] == 1
    _file(raw, "RAVM1.jvd", _ra(c2="000", c3="000", c4="005", c5="005", cmin="005"))
    assert g.probe(raw)["ok"] is True


# --- 2026-10-05 レビューの指摘 (4 名) の反映 ---------------------------------------------------------

def test_short_record_stops(tmp_path):
    f = _file(tmp_path, "RAVM1.jvd", _ra()[:640])
    with pytest.raises(g.ClassTableError, match="短いレコード"):
        g.extract([f])


def test_cancelled_race_is_kept_with_its_data_div(tmp_path):
    f = _file(tmp_path, "RAVM1.jvd", _ra(div="9"))
    assert g.extract([f])["20230603_05_03_01_05"]["data_divs"] == {"9"}


def test_distance_conflict_for_the_same_race_stops(tmp_path):
    a = _file(tmp_path, "RAVM1.jvd", _ra())
    rec = bytearray(_ra()); rec[697:701] = b"1800"
    b = _file(tmp_path, "RASW1.jvd", bytes(rec))
    with pytest.raises(g.ClassTableError, match="食い違う"):
        g.extract([a, b])


def test_skipped_records_are_counted(tmp_path):
    f = _file(tmp_path, "RAVM1.jvd", _ra(tc="30"), _ra(ymd="20201231"), _ra(ymd="2023XX03"), _ra())
    counts = g.Counter()
    g.extract([f], counts=counts)
    assert counts == {"records_read": 4, "skipped_non_jra": 1, "skipped_out_of_range": 1,
                      "skipped_non_numeric_date": 1, "records_used": 1}


def test_empty_raw_dir_stops(tmp_path):
    with pytest.raises(g.ClassTableError, match=r"RA\*\.jvd が無い"):
        g.build(tmp_path, tmp_path / "out")


def test_failed_build_leaves_no_table(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _file(raw, "RAVM1.jvd", _ra(rn="01"), _ra(rn="02", cmin="000"))
    with pytest.raises(g.ClassTableError):
        g.build(raw, tmp_path / "out")
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_probe_reports_a_race_missing_from_raw(tmp_path, monkeypatch):
    raw = tmp_path / "raw"; raw.mkdir()
    _file(raw, "RAVM1.jvd", _ra())
    monkeypatch.setattr(g, "_load_expected", lambda: {"20230603_05_03_01_05": ("701", 2),
                                                      "20230603_05_03_01_06": ("703", 3)})
    rep = g.probe(raw)
    assert rep["mismatch"] == 1 and [r.get("reason") for r in rep["rows"]] == [None, "raw に無い"]


def test_git_provenance_is_unknown_when_git_fails(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(g.subprocess, "run", boom)
    p = g.git_provenance()
    assert p["git_sha"] == "unknown" and p["git_dirty"] is None and len(p["parser_sha256"]) == 64


def test_manifest_records_counts_and_provenance(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    _file(raw, "RAVM1.jvd", _ra(), _ra(rn="06", div="9", c2="703", cmin="703"))
    m = g.build(raw, tmp_path / "out", argv=["build", "--raw-dir", str(raw)])
    assert m["record_counts"] == {"records_read": 2, "records_used": 2}
    assert m["counts_by_year_class"] == {"2023": {"701": 1, "703": 1}}
    assert m["counts_by_year_class_data_div_7"] == {"2023": {"701": 1}}
    assert m["argv"][0] == "build" and m["raw_files"][0]["sha256"] == g.sha256(raw / "RAVM1.jvd")
    assert {"git_sha", "git_dirty", "parser_sha256", "built_at"} <= set(m)
