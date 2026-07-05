"""db.init_db の migration 順序 regression。

schema.sql の idx_horse_masters_dam_sire は dam_sire_breeding_num を参照するため、
「テーブルはあるが列が無い」旧 DB では列補修を executescript より先に行わないと
index 作成が no such column で落ち、writer が起動不能になる
(2026-07-05 data-pipeline 監査 R1 で dead code + crash を実証 → 順序修正)。
"""

from __future__ import annotations

import sqlite3
import sys

sys.path.insert(0, ".")

from db import init_db


def test_init_db_repairs_missing_dam_sire_column_before_index():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # 旧 DB 相当: horse_masters は存在するが dam_sire_breeding_num 列が無い
    conn.execute(
        "CREATE TABLE horse_masters (blood_register_num TEXT PRIMARY KEY, "
        "data_div TEXT, data_created TEXT, horse_name TEXT, sex_code TEXT, "
        "breed_code TEXT, sire_breeding_num TEXT, sire_name TEXT, "
        "dam_sire_name TEXT, leg_tendency_code TEXT)"
    )
    conn.execute("INSERT INTO horse_masters (blood_register_num, sire_name) VALUES ('B1','ディープインパクト')")
    init_db(conn)  # 旧実装は idx_horse_masters_dam_sire 作成で OperationalError
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(horse_masters)").fetchall()}
    assert "dam_sire_breeding_num" in cols
    # 既存データは保持され、index も作成されている
    assert conn.execute("SELECT sire_name FROM horse_masters").fetchone()["sire_name"] == "ディープインパクト"
    idx = {r["name"] for r in conn.execute("PRAGMA index_list(horse_masters)").fetchall()}
    assert "idx_horse_masters_dam_sire" in idx


def test_init_db_fresh_database_still_works():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)  # テーブル無しからの新規作成 (列補修は skip される)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(horse_masters)").fetchall()}
    assert "dam_sire_breeding_num" in cols


def test_init_db_idempotent_on_current_schema():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    init_db(conn)  # 2 回目も落ちない (IF NOT EXISTS + 補修 skip)


def test_hs_skeleton_does_not_clobber_um_row():
    """HS (骨組み行) が UM フル行を空文字で潰さない (2026-07-05 data-pipeline R2)。

    raw 全量再構築の取込順は DIFN(UM) < HOSE(HS) なので、旧 INSERT OR REPLACE の
    ままだと再構築のたびに市場取引馬のマスタが空になる (順序依存の非収束)。
    """
    from db import insert_horse_master_if_absent, upsert_horse_master
    from jvlink_client.parser import HorseMaster

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    um = HorseMaster(
        record_type="UM", data_div="1", data_created="20260101",
        blood_register_num="B1", horse_name="テスト馬", sex_code="1", breed_code="1",
        sire_breeding_num="S1", sire_name="ディープインパクト",
        dam_sire_breeding_num="D1", dam_sire_name="キングカメハメハ",
        leg_tendency_code="0000",
        sire_dam_sire_breeding_num="SD1", sire_dam_sire_name="ノーザンテースト",
        dam_dam_sire_breeding_num="DD1", dam_dam_sire_name="トニービン",
    )
    hs = HorseMaster(
        record_type="HS", data_div="1", data_created="20260102",
        blood_register_num="B1", horse_name="", sex_code="", breed_code="",
        sire_breeding_num="S1x", sire_name="",
        dam_sire_breeding_num="D1x", dam_sire_name="", leg_tendency_code="",
    )
    # UM → HS の順: HS は no-op で UM のフル行が残る
    upsert_horse_master(conn, um)
    insert_horse_master_if_absent(conn, hs)
    row = conn.execute("SELECT sire_name, sire_dam_sire_name, horse_name FROM horse_masters").fetchone()
    assert row["sire_name"] == "ディープインパクト"
    assert row["sire_dam_sire_name"] == "ノーザンテースト"
    assert row["horse_name"] == "テスト馬"
    # HS → UM の順: 後から来た UM フル行が REPLACE で勝つ (順序非依存に収束)
    conn.execute("DELETE FROM horse_masters")
    insert_horse_master_if_absent(conn, hs)
    upsert_horse_master(conn, um)
    row = conn.execute("SELECT sire_name FROM horse_masters").fetchone()
    assert row["sire_name"] == "ディープインパクト"
