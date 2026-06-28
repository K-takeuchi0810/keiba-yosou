"""マスタ系レコード (KS/CH/BR/BN) パーサのバイト位置テスト。

仕様書 docs/JV-Data4901.pdf §14-17。byte 位置は 1-indexed。
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from db import SCHEMA_PATH, upsert_jockey_master
from jvlink_client import ingest as ingest_mod
from jvlink_client.ingest import ingest_file_dispatch
from jvlink_client.parser import (
    BN_LENGTH,
    BR_LENGTH,
    CH_LENGTH,
    KS_LENGTH,
    JockeyMaster,
    parse_bn,
    parse_br,
    parse_ch,
    parse_ks,
)


def _put(buf: bytearray, pos: int, s: str) -> None:
    """仕様書 1-indexed 位置に cp932 で書き込む。"""
    b = s.encode("cp932")
    buf[pos - 1 : pos - 1 + len(b)] = b


def test_parse_ks_byte_positions():
    buf = bytearray(b" " * KS_LENGTH)
    _put(buf, 1, "KS")
    _put(buf, 3, "0")
    _put(buf, 4, "20260101")
    _put(buf, 12, "05558")
    _put(buf, 17, "0")
    _put(buf, 34, "19900203")
    _put(buf, 42, "渡辺　竜也")
    _put(buf, 228, "1")
    _put(buf, 231, "3")
    _put(buf, 252, "01234")
    ks = parse_ks(bytes(buf))
    assert ks.record_type == "KS"
    assert ks.jockey_code == "05558"
    assert ks.birth_date == "19900203"
    assert ks.jockey_name == "渡辺　竜也"
    assert ks.sex_code == "1"
    assert ks.east_west_code == "3"
    assert ks.affiliation_trainer_code == "01234"


def test_parse_ch_byte_positions():
    buf = bytearray(b" " * CH_LENGTH)
    _put(buf, 1, "CH")
    _put(buf, 12, "05076")
    _put(buf, 42, "国枝　栄")
    _put(buf, 194, "1")
    _put(buf, 195, "1")
    ch = parse_ch(bytes(buf))
    assert ch.record_type == "CH"
    assert ch.trainer_code == "05076"
    assert ch.trainer_name == "国枝　栄"
    assert ch.east_west_code == "1"


def test_parse_br_byte_positions():
    buf = bytearray(b" " * BR_LENGTH)
    _put(buf, 1, "BR")
    _put(buf, 12, "78071100")
    _put(buf, 20, "ノーザンファーム")
    br = parse_br(bytes(buf))
    assert br.record_type == "BR"
    assert br.producer_code == "78071100"
    assert br.producer_name == "ノーザンファーム"


def test_parse_bn_byte_positions():
    buf = bytearray(b" " * BN_LENGTH)
    _put(buf, 1, "BN")
    _put(buf, 12, "172034")
    _put(buf, 18, "伊藤　義文")
    _put(buf, 296, "赤，白十字襷，青袖")
    bn = parse_bn(bytes(buf))
    assert bn.record_type == "BN"
    assert bn.owner_code == "172034"
    assert bn.owner_name == "伊藤　義文"
    assert bn.silks_desc == "赤，白十字襷，青袖"


def test_parse_handles_length_drift():
    """BSTR ラウンドトリップで ±数バイトずれても落ちない。"""
    short = b"KS" + b"0" + b"20260101" + b"05558" + b" " * 50
    ks = parse_ks(short)  # KS_LENGTH 未満 → ljust される
    assert ks.jockey_code == "05558"


def _ks_record(code: str, name: str) -> bytes:
    buf = bytearray(b" " * KS_LENGTH)
    _put(buf, 1, "KS"); _put(buf, 12, code); _put(buf, 42, name); _put(buf, 231, "3")
    return bytes(buf)


def _bn_record(code: str, name: str) -> bytes:
    buf = bytearray(b" " * BN_LENGTH)
    _put(buf, 1, "BN"); _put(buf, 12, code); _put(buf, 18, name)
    return bytes(buf)


def _schema_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    return conn


def test_upsert_master_db_roundtrip():
    """dataclass フィールドと schema.sql のカラムが一致していることを実 DB で検証。
    どちらかに drift があれば OperationalError で落ちる (変更失敗モードの早期検出)。
    """
    conn = _schema_conn()
    ks = JockeyMaster(
        record_type="KS", data_div="0", data_created="20260101", jockey_code="05558",
        retired="0", license_issued="", license_revoked="", birth_date="19900203",
        jockey_name="渡辺　竜也", jockey_name_kana="", jockey_name_abbr="",
        jockey_name_eng="", sex_code="1", riding_qual_code="", apprentice_code="",
        east_west_code="3", affiliation_trainer_code="01234",
    )
    upsert_jockey_master(conn, ks)
    row = conn.execute(
        "SELECT jockey_name, east_west_code FROM jockey_masters WHERE jockey_code='05558'"
    ).fetchone()
    assert row == ("渡辺　竜也", "3")


def test_ingest_dispatch_counts_masters_and_skips_unknown(tmp_path):
    conn = _schema_conn()
    data = b"\r\n".join([
        _ks_record("05558", "渡辺　竜也"),
        _bn_record("172034", "伊藤　義文"),
        b"ZZ" + b" " * 100,  # 未対応種別 → skipped
    ]) + b"\r\n"
    p = tmp_path / "DIFNtest.jvd"
    p.write_bytes(data)
    extras: dict[str, int] = {}
    ra, se, hr, o1, um, skipped = ingest_file_dispatch(conn, p, "DIFN", extra_counts=extras)
    assert extras == {"KS": 1, "BN": 1}, "master 件数が extra_counts に計上される"
    assert skipped == 1, "未対応 ZZ レコードのみ skip"
    assert conn.execute("SELECT COUNT(*) FROM jockey_masters").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM owner_masters").fetchone()[0] == 1


def test_ingest_dispatch_logs_parse_failure(tmp_path, monkeypatch, caplog):
    """parse 失敗 (byte 位置 drift 等) が warning で可視化される (サイレント握り潰し禁止)。"""
    conn = _schema_conn()
    def _boom(rec):
        raise ValueError("byte drift")
    monkeypatch.setattr(ingest_mod, "parse_ks", _boom)
    p = tmp_path / "x.jvd"
    p.write_bytes(_ks_record("05558", "x") + b"\r\n")
    with caplog.at_level(logging.WARNING):
        _, _, _, _, _, skipped = ingest_file_dispatch(conn, p, "DIFN", extra_counts={})
    assert skipped == 1
    assert any("parse failed" in r.getMessage() for r in caplog.records)