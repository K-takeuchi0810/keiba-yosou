"""通過順位のバイト位置の検証フラグをコードで強制する (2026-10-04)。

`config.CORNER_BYTES_VERIFIED` はこれまでコメントの規約で、コードでは強制されていなかった
(読むのは webapp のラベルだけで、`compute_features` は通過順位が 1 行でもあれば計算していた)。
probe を JRA 公式の値で緑化して True にした (data/backtest/corner_probe_20261004/) のと同時に、
False なら通過順位の利用と backfill が止まるようにした。固定すること:

- False → `recent_corner_stats` と `require_corner_bytes_verified` は止まる (例外)
- False → `compute_features` は通過順位の特徴だけを計算しない (既定値 None / 0)。ほかの特徴は True のときと同じ
- True → `compute_features` の通過順位の特徴は `recent_corner_stats` の値と一致する (従来どおり)
- True でも通過順位が全行 NULL なら、0 で埋めずに None / 0 のまま
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import config
from db import SCHEMA_PATH
from predictor import features
from scripts import analyze_misses

CORNER_KEYS = ("recent_4corner_avg_position", "recent_4corner_position_change", "recent_4corner_samples")


def _conn(with_corners: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    for i, (md, c4, fin) in enumerate([("0107", 2, 1), ("0211", 5, 3), ("0310", 3, 4)]):
        conn.execute(
            "INSERT INTO races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, track_type_code,"
            " distance, starter_count, turf_condition, dirt_condition) VALUES ('2024',?,'05','01','01',?,'11',1600,10,'1','0')",
            (md, f"{i + 1:02d}"))
        conn.execute(
            "INSERT INTO horse_races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num,"
            " blood_register_num, confirmed_order, finish_time, final_3f, corner_order_4)"
            " VALUES ('2024',?,'05','01','01',?,'01','A000000001',?,960,340,?)",
            (md, f"{i + 1:02d}", fin, c4 if with_corners else None))
    conn.execute(
        "INSERT INTO races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, track_type_code,"
        " distance, starter_count, turf_condition, dirt_condition) VALUES ('2024','0601','05','01','01','01','11',1600,10,'1','0')")
    return conn


HORSE = {"horse_num": "01", "blood_register_num": "A000000001"}
RACE = {"race_year": "2024", "race_month_day": "0601", "track_code": "05", "kaiji": "01", "nichiji": "01",
        "race_num": "01", "track_type_code": "11", "distance": 1600, "starter_count": 10,
        "turf_condition": "1", "dirt_condition": "0"}


def test_the_flag_is_true_after_the_green_probe():
    assert config.CORNER_BYTES_VERIFIED is True
    config.require_corner_bytes_verified("test")   # 止まらない


def test_unverified_flag_stops_direct_corner_reads(monkeypatch):
    monkeypatch.setattr(config, "CORNER_BYTES_VERIFIED", False)
    with pytest.raises(config.CornerBytesNotVerified):
        config.require_corner_bytes_verified("backfill")
    with pytest.raises(config.CornerBytesNotVerified):
        features.recent_corner_stats(_conn(), "A000000001", "20240601")


def test_verified_compute_features_matches_the_corner_stats():
    conn = _conn()
    feat = features.compute_features(conn, HORSE, RACE)
    avg, chg, n = features.recent_corner_stats(conn, "A000000001", "20240601")
    assert (feat["recent_4corner_avg_position"], feat["recent_4corner_position_change"],
            feat["recent_4corner_samples"]) == (avg, chg, n)
    assert n == 3 and avg == round((2 + 5 + 3) / 3, 2)


def test_unverified_compute_features_skips_only_the_corner_features(monkeypatch):
    conn = _conn()
    on = features.compute_features(conn, HORSE, RACE)
    monkeypatch.setattr(config, "CORNER_BYTES_VERIFIED", False)
    off = features.compute_features(conn, HORSE, RACE)
    assert (off["recent_4corner_avg_position"], off["recent_4corner_position_change"],
            off["recent_4corner_samples"]) == (None, None, 0)
    assert on["recent_4corner_samples"] == 3
    # ほかの特徴は同じ (止めるのは通過順位だけ)
    assert {k: v for k, v in on.items() if k not in CORNER_KEYS} == {k: v for k, v in off.items() if k not in CORNER_KEYS}


def test_verified_but_all_null_corners_stay_missing_not_zero():
    feat = features.compute_features(_conn(with_corners=False), HORSE, RACE)
    assert (feat["recent_4corner_avg_position"], feat["recent_4corner_position_change"],
            feat["recent_4corner_samples"]) == (None, None, 0)


def test_the_miss_analysis_does_not_show_unverified_corners(monkeypatch):
    conn = _conn()
    conn.execute("UPDATE horse_races SET corner_order_1=1, corner_order_2=2, corner_order_3=3 WHERE race_month_day='0107'")
    on = analyze_misses.horse_context(conn, "20240107", "05", "01", "01")
    assert (on["c1"], on["c4"]) == (1, 2)
    monkeypatch.setattr(config, "CORNER_BYTES_VERIFIED", False)
    off = analyze_misses.horse_context(conn, "20240107", "05", "01", "01")
    assert (off["c1"], off["c2"], off["c3"], off["c4"]) == (None, None, None, None)
    assert off["fin"] == on["fin"]


# 通過順位 (corner_order_*) を書く・読むことを許すファイル。ここに無いファイルが corner_order_ を含んだら落ちる
# (新しく読む処理がガードを呼び忘れても静かに素通りしないように。code-quality レビュー 2026-10-04)。
# 足すときは、そのファイルが config.require_corner_bytes_verified() を通る (または取り込みだけ) ことを確かめる。
CORNER_FILES = {
    "config.py",                       # フラグとガードの定義 (docstring)
    "db.py",                           # 列の migration と取り込みの upsert (取り込みはガードしない)
    "jvlink_client/parser.py",         # SE の parse (取り込み)
    "predictor/pit_view.py",           # 発走後の列として除外するリスト (読まない)
    "predictor/features.py",           # recent_corner_stats (ガード) / compute_features (フラグで計算しない)
    "scripts/analyze_misses.py",       # 診断の表示 (フラグで表示しない)
    "scripts/probe_corner_offsets.py",  # バイト位置の検証 (raw を読む)
}


def test_only_known_files_touch_corner_columns():
    root = Path(__file__).resolve().parents[1]
    found = set()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("tests/", ".claude/", ".venv", "data/")):
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "corner_order_" in src:
            found.add(rel)
    assert found == CORNER_FILES, f"許可リストとの違い: 余分 {sorted(found - CORNER_FILES)} / 不足 {sorted(CORNER_FILES - found)}"
