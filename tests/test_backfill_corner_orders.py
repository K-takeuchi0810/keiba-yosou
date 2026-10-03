"""通過順位の backfill (scripts/backfill_corner_orders.py) の契約 (2026-10-04)。

- `CORNER_BYTES_VERIFIED` が False なら DB を開く前に止まる
- 既定は dry-run (書かない)
- `--apply` は corner 4 列だけを変える (`win_odds` / `odds_fetched_at` を含むほかの列は 1 ビットも変えない)
- raw に無い行は NULL のまま、範囲外の日付・地方・data_div 7 以外の raw は使わない
- raw の食い違い・検収の不合格・開催日は止める。検収が不合格なら rollback して部分適用を残さない
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
from db import SCHEMA_PATH
from scripts import backfill_corner_orders as bf

DATES = ("20240106", "20240203")        # 2 か月


@pytest.fixture(autouse=True)
def _small_range(monkeypatch):
    monkeypatch.setattr(bf, "FROM_DATE", "20240101")
    monkeypatch.setattr(bf, "TO_DATE", "20240229")


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    for ymd in DATES + ("20240302",):              # 3 月は範囲外
        for track in ("05", "30"):                 # 30 = 地方
            conn.execute("INSERT INTO races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, data_div)"
                         " VALUES (?,?,?,'01','01','01','7')", (ymd[:4], ymd[4:], track))
            for h, (fin, abn) in enumerate([(1, "0"), (2, "0"), (0, "4")], start=1):
                conn.execute(
                    "INSERT INTO horse_races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num,"
                    " blood_register_num, confirmed_order, abnormal_code, win_odds, odds_fetched_at, odds_dataspec,"
                    " jockey_code, burden_weight, horse_weight, finish_time, data_div)"
                    " VALUES (?,?,?,'01','01','01',?,?,?,?,?,?,?,?,?,?,?,'7')",
                    (ymd[:4], ymd[4:], track, f"{h:02d}", f"B{h:09d}", fin, abn, 35 + h,
                     "2024-01-01T10:00:00", "0B31", f"J{h}", 550, "480", 960 + h))
    conn.commit()
    conn.close()
    return path


def _rec(ymd, track, horse, corners, data_div="7"):
    return SimpleNamespace(record_type="SE", data_div=data_div, year=ymd[:4], month_day=ymd[4:], track_code=track,
                           kaiji="01", nichiji="01", race_num="01", horse_num=f"{horse:02d}",
                           corner_order_1=corners[0], corner_order_2=corners[1], corner_order_3=corners[2],
                           corner_order_4=corners[3])


def _records():
    out = []
    for ymd in DATES + ("20240302",):
        for track in ("05", "30"):
            out += [_rec(ymd, track, 1, (2, 2, 1, 1)), _rec(ymd, track, 2, (1, 1, 2, 2)),
                    _rec(ymd, track, 3, (3, 3, 3, 0))]
    return out


def _snapshot(path: Path) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = {tuple(r[c] for c in bf.PK): dict(r) for r in conn.execute("SELECT * FROM horse_races")}
    conn.close()
    return rows


def _digest(path: Path) -> str:
    return hashlib.sha256(repr(sorted(_snapshot(path).items())).encode()).hexdigest()


def test_unverified_flag_stops_before_opening_the_db(tmp_path, monkeypatch):
    path = tmp_path / "never_created.db"
    monkeypatch.setattr(config, "CORNER_BYTES_VERIFIED", False)
    with pytest.raises(config.CornerBytesNotVerified):
        bf.run(path, _records(), apply=True, today="20240101")
    assert not path.exists()
    with pytest.raises(config.CornerBytesNotVerified):
        bf.main(["--db", str(path), "--report", str(tmp_path / "r.json"), "--raw-dir", str(tmp_path)])
    assert not path.exists()


def test_dry_run_writes_nothing(tmp_path):
    path = _db(tmp_path)
    before = _digest(path)
    rep = bf.run(path, _records(), apply=False, today="20240101")
    assert rep["result"] == "dry_run" and rep["planned_updates"] == 6      # JRA × 2 か月 × 3 頭
    assert rep["acceptance_planned"]["ok"] is True
    assert _digest(path) == before


def test_apply_changes_only_the_corner_columns(tmp_path):
    path = _db(tmp_path)
    before = _snapshot(path)
    rep = bf.run(path, _records(), apply=True, today="20240101")
    assert rep["result"] == "applied" and rep["updated_rows"] == 6
    after = _snapshot(path)
    assert set(before) == set(after)
    for key, row in after.items():
        diff = {c for c in row if row[c] != before[key][c]}
        in_scope = key[1] in ("0106", "0203") and key[2] == "05"
        assert diff <= set(bf.CORNERS) if in_scope else diff == set(), (key, diff)
        # PIT の事故の防止: オッズとその刻印は変わらない
        assert (row["win_odds"], row["odds_fetched_at"], row["odds_dataspec"]) == \
               (before[key]["win_odds"], before[key]["odds_fetched_at"], before[key]["odds_dataspec"])
    jra = after[("2024", "0106", "05", "01", "01", "01", "01")]
    assert (jra["corner_order_1"], jra["corner_order_4"]) == (2, 1)
    # 範囲外 (3 月) と地方は触らない
    assert after[("2024", "0302", "05", "01", "01", "01", "01")]["corner_order_4"] is None
    assert after[("2024", "0106", "30", "01", "01", "01", "01")]["corner_order_4"] is None


def test_rows_without_raw_stay_null_and_are_counted(tmp_path):
    path = _db(tmp_path)
    recs = [r for r in _records() if not (r.month_day == "0203" and r.horse_num == "03")]
    rep = bf.run(path, recs, apply=True, today="20240101")
    assert rep["null_remaining_after"] == 1 and rep["updated_rows"] == 5
    assert _snapshot(path)[("2024", "0203", "05", "01", "01", "01", "03")]["corner_order_4"] is None


def test_non_confirmed_raw_records_are_not_used(tmp_path):
    path = _db(tmp_path)
    recs = [_rec(r_ymd, "05", 1, (9, 9, 9, 9), data_div="2") for r_ymd in DATES] + _records()
    rep = bf.run(path, recs, apply=False, today="20240101")
    assert rep["planned_updates"] == 6 and rep["raw_records_used"] == 6


def test_conflicting_raw_values_stop_before_writing(tmp_path):
    path = _db(tmp_path)
    before = _digest(path)
    recs = _records() + [_rec("20240106", "05", 1, (2, 2, 1, 3))]
    with pytest.raises(bf.BackfillError, match="食い違う"):
        bf.run(path, recs, apply=True, today="20240101")
    assert _digest(path) == before


def test_failed_acceptance_rolls_back_without_partial_writes(tmp_path):
    path = _db(tmp_path)
    before = _digest(path)
    # 2 月の 4 角がすべて 0 → 被覆率 0% で検収が不合格
    recs = [_rec(r.year + r.month_day, r.track_code, int(r.horse_num), (1, 1, 1, 0))
            if r.month_day == "0203" else r for r in _records()]
    rep = bf.run(path, recs, apply=False, today="20240101")
    assert rep["acceptance_planned"]["failed_months"] == ["202402"]
    with pytest.raises(bf.BackfillError, match="検収"):
        bf.run(path, recs, apply=True, today="20240101")
    assert _digest(path) == before


def test_out_of_field_positions_fail_acceptance(tmp_path):
    path = _db(tmp_path)
    before = _digest(path)
    # 出走頭数は 3 (取消・除外なし。競走中止の 3 番は出走に数える)。4 位は範囲外
    recs = [_rec("20240106", "05", 1, (4, 2, 1, 1)) if (r.month_day == "0106" and r.track_code == "05"
            and r.horse_num == "01") else r for r in _records()]
    with pytest.raises(bf.BackfillError, match="over=1"):
        bf.run(path, recs, apply=True, today="20240101")
    assert _digest(path) == before


def test_apply_is_refused_on_a_race_day(tmp_path):
    path = _db(tmp_path)
    before = _digest(path)
    with pytest.raises(bf.BackfillError, match="開催日"):
        bf.run(path, _records(), apply=True, today="20240106")
    assert _digest(path) == before
    # dry-run は開催日でも読むだけなので通す
    assert bf.run(path, _records(), apply=False, today="20240106")["result"] == "dry_run"


def test_rerun_is_idempotent(tmp_path):
    path = _db(tmp_path)
    bf.run(path, _records(), apply=True, today="20240101")
    once = _digest(path)
    bf.run(path, _records(), apply=True, today="20240101")
    assert _digest(path) == once


def test_scratched_horses_do_not_count_toward_the_field(tmp_path):
    """出走頭数は取消・除外 (1/2/3) を除く。3 頭のうち 1 頭が取消なら出走 2 頭で、3 位は範囲外。"""
    path = _db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("UPDATE horse_races SET abnormal_code='1', confirmed_order=0"
                 " WHERE race_month_day='0106' AND track_code='05' AND horse_num='03'")
    conn.commit()
    conn.close()
    recs = [_rec("20240106", "05", 2, (1, 1, 3, 2)) if (r.month_day == "0106" and r.track_code == "05"
            and r.horse_num == "02") else r for r in _records()]
    rep = bf.run(path, recs, apply=False, today="20240101")
    assert rep["acceptance_planned"]["over_field"] >= 1
