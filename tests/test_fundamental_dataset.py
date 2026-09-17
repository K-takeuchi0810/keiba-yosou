"""Fundamental Model の標本定義の契約テスト (憲法 Phase 0.5-3)。

## なぜ要るか

初版は「horse_races に行がある = 1 頭の出走」とみなしていた。実際には

- **出走取消** の馬にも行がある (`abnormal_code='1'`、馬体重 `000`、オッズ 0)
- **結果が取り込まれていないレース** にも行がある (勝ち馬が 1 頭もいない)

前者は T−10 の市場にも居ないので、標本に入れると市場と頭数が食い違う。
後者は全頭 `won=0` になるので、**「このレースでは誰も勝たない」を学習**する。
2026-09-18 の突合で 933 レースのはずが 923 になったことから発覚した。

一方 **発走除外 / 競走除外 (`'2'` / `'3'`) は残す**。ゲート前後の除外なので
T−10 時点ではまだ買えた。「その後除外された」は当時知りえない情報であり、
それを理由に標本から落とすと後知恵の選択になる。
"""
from __future__ import annotations

import sqlite3

import pytest

from scripts.fundamental_model import DID_NOT_START, FEATURES, build_dataset

DDL = """
CREATE TABLE horse_races (
  race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
  nichiji TEXT, race_num TEXT, horse_num TEXT, blood_register_num TEXT,
  jockey_code TEXT, trainer_code TEXT, age TEXT, sex_code TEXT,
  burden_weight TEXT, waku_num TEXT, horse_weight TEXT,
  weight_change_sign TEXT, weight_change_diff TEXT, blinker TEXT,
  confirmed_order INTEGER, abnormal_code TEXT);
CREATE TABLE races (
  race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
  nichiji TEXT, race_num TEXT, distance INTEGER, track_type_code TEXT,
  turf_condition TEXT, dirt_condition TEXT, weather_code TEXT,
  grade_code TEXT, starter_count INTEGER);
CREATE TABLE horse_masters (
  blood_register_num TEXT, sire_breeding_num TEXT);
"""


def _add_race(conn, date8: str, race_num: str, horses: list[tuple]) -> None:
    """horses = [(馬番, 確定着順, 異常コード), ...]"""
    y, md = date8[:4], date8[4:]
    conn.execute(
        "INSERT INTO races VALUES (?,?,'05','01','01',?,1600,'1','1','0','1','',?)",
        (y, md, race_num, len(horses)))
    for hn, fin, abn in horses:
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,'05','01','01',?,?,?,"
            "'J1','T1','04','1','550','1','470','+','2','0',?,?)",
            (y, md, race_num, hn, f"H{hn}{date8}{race_num}", fin, abn))


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    yield conn, str(path)
    conn.close()


def test_scratched_horse_is_excluded(db):
    """出走取消の馬は標本に入らない。市場にも居ないため。"""
    conn, path = db
    _add_race(conn, "20260601", "01",
              [("01", 1, "0"), ("02", 2, "0"), ("03", 0, "1")])
    conn.commit()

    rows, stats = build_dataset("20260101", "20261231", db_path=path)

    assert {r["horse_num"] for r in rows} == {"01", "02"}
    assert stats["skip_did_not_start"] == 1


def test_gate_excluded_horse_is_kept_as_a_loser(db):
    """競走除外は残す。T−10 時点ではまだ買えたから。

    ここを取り違えると **後知恵で標本を絞る** ことになる。
    """
    conn, path = db
    _add_race(conn, "20260601", "01",
              [("01", 1, "0"), ("02", 2, "0"), ("03", 0, "3")])
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    assert {r["horse_num"] for r in rows} == {"01", "02", "03"}
    assert next(r for r in rows if r["horse_num"] == "03")["won"] == 0
    assert "2" not in DID_NOT_START and "3" not in DID_NOT_START


def test_race_without_a_winner_is_excluded(db):
    """結果が未取込のレースは丸ごと使わない。

    全頭 won=0 のまま学習すると「誰も勝たない」を教えることになる。
    """
    conn, path = db
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    _add_race(conn, "20260601", "02", [("01", 0, "0"), ("02", 0, "0")])
    conn.commit()

    rows, stats = build_dataset("20260101", "20261231", db_path=path)

    assert {r["race_id"].split("-")[-1] for r in rows} == {"01"}
    assert stats["skip_race_without_result"] == 2


def test_did_not_start_rows_do_not_count_as_a_career_start(db):
    """取消は「出走」ではない。過去成績の分母に入れない。"""
    conn, path = db
    # 同一馬 (血統登録番号を揃える) が 1 戦目は取消、2 戦目に出走
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 0, "1")])
    _add_race(conn, "20260608", "01", [("01", 2, "0"), ("02", 1, "0")])
    conn.execute("UPDATE horse_races SET blood_register_num='SAME' "
                 "WHERE horse_num='02'")
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    second = next(r for r in rows
                  if r["horse_num"] == "02" and r["date"] == "20260608")
    assert second["h_starts"] == 0, "取消が 1 戦としてカウントされている"


def test_a_race_with_a_winner_survives_intact(db):
    """正常なレースはそのまま残る (除外規則が効きすぎていないか)。"""
    conn, path = db
    _add_race(conn, "20260601", "01",
              [("01", 1, "0"), ("02", 2, "0"), ("03", 0, "4")])   # 4=競走中止
    conn.commit()

    rows, stats = build_dataset("20260101", "20261231", db_path=path)

    assert len(rows) == 3
    assert sum(r["won"] for r in rows) == 1
    assert stats["skip_did_not_start"] == 0
    assert stats["skip_race_without_result"] == 0


def test_every_declared_feature_is_produced(db):
    """FEATURES に挙げた列が実際に全部揃うこと。"""
    conn, path = db
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    missing = [f for f in FEATURES if f not in rows[0]]
    assert not missing, f"生成されない特徴: {missing}"
