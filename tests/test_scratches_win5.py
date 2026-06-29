"""競走馬除外 (JG) / 重勝式 WIN5 (WF) パーサとDB取り込みのテスト。

仕様書 docs/JV-Data4901.pdf §30 (WF), §31 (JG)。byte 位置は 1-indexed。
"""
from __future__ import annotations

import glob
import sqlite3
from pathlib import Path

from db import SCHEMA_PATH, upsert_race_scratch, upsert_win5
from jvlink_client.ingest import ingest_file_dispatch, _split_records
from jvlink_client.parser import (
    JG_LENGTH,
    WF_LENGTH,
    parse_jg,
    parse_jg_file,
    parse_wf,
)

RAW_RACE = Path(r"C:\Users\kizun\dev\keiba-yosou\data\raw\RACE")


def _put(buf: bytearray, pos: int, s: str) -> None:
    b = s.encode("cp932")
    buf[pos - 1 : pos - 1 + len(b)] = b


def test_parse_jg_byte_positions():
    buf = bytearray(b" " * JG_LENGTH)
    _put(buf, 1, "JG"); _put(buf, 3, "1"); _put(buf, 4, "20250502")
    _put(buf, 12, "2025"); _put(buf, 16, "0503"); _put(buf, 20, "04")
    _put(buf, 22, "01"); _put(buf, 24, "01"); _put(buf, 26, "11")
    _put(buf, 28, "2022100304")
    _put(buf, 38, "テスト馬")
    _put(buf, 74, "002"); _put(buf, 77, "9"); _put(buf, 78, "0")
    jg = parse_jg(bytes(buf))
    assert jg.record_type == "JG"
    assert jg.race_id == "20250503_04_01_01_11"
    assert jg.blood_register_num == "2022100304"
    assert jg.horse_name == "テスト馬"
    assert jg.accept_order == "002"
    assert jg.start_div == "9"
    assert jg.scratch_status == "0"


def test_parse_wf_byte_positions():
    buf = bytearray(b" " * WF_LENGTH)
    _put(buf, 1, "WF"); _put(buf, 3, "3"); _put(buf, 4, "20250504")
    _put(buf, 12, "2025"); _put(buf, 16, "0504")
    # 対象 5 レース pos22, 8 byte 毎 (track2/kaiji2/nichiji2/racenum2)
    for i, (tk, ka, ni, rn) in enumerate([
        ("05", "02", "04", "10"), ("08", "02", "04", "10"), ("04", "01", "02", "11"),
        ("05", "02", "04", "11"), ("08", "02", "04", "11"),
    ]):
        base = 22 + i * 8
        _put(buf, base, tk); _put(buf, base + 2, ka); _put(buf, base + 4, ni); _put(buf, base + 6, rn)
    _put(buf, 68, "00008604205")        # sale_votes
    _put(buf, 134, "0"); _put(buf, 135, "0"); _put(buf, 136, "1")  # flags
    _put(buf, 137, "000000000000000")   # carryover initial
    _put(buf, 152, "000000000000000")   # carryover remaining
    # 払戻 pos167, 29 byte 毎 (組番10/払戻9/的中票10)
    _put(buf, 167, "0604071206"); _put(buf, 177, "002176650"); _put(buf, 186, "0000000336")
    wf = parse_wf(bytes(buf))
    assert wf.record_type == "WF" and wf.win5_id == "20250504"
    assert wf.target_races == "05-02-04-10,08-02-04-10,04-01-02-11,05-02-04-11,08-02-04-11"
    assert wf.sale_votes == 8604205
    assert wf.established_flag == "1"
    assert wf.payouts == [("0604071206", 2176650, 336)]


def test_parse_wf_skips_empty_payout_combos():
    buf = bytearray(b" " * WF_LENGTH)
    _put(buf, 1, "WF"); _put(buf, 12, "2025"); _put(buf, 16, "0504")
    _put(buf, 167, "0000000000"); _put(buf, 177, "000000000"); _put(buf, 186, "0000000000")  # 未確定
    _put(buf, 196, "0604071206"); _put(buf, 206, "002176650"); _put(buf, 215, "0000000336")  # 有効
    wf = parse_wf(bytes(buf))
    assert wf.payouts == [("0604071206", 2176650, 336)]


def test_parse_jg_file_handles_crlf_delimited(tmp_path):
    """parse_*_file が実 raw (CRLF 区切り+末尾 NUL) で動く (旧 _split_fixed の罠回帰)。

    以前は _split_fixed が len%length!=0 で ValueError を投げ、CRLF 区切りの実 raw に
    対して parse_*_file が必ず死ぬトラップだった (2026-06-29 validation 監査指摘)。
    """
    def _rec(blood: str) -> bytes:
        buf = bytearray(b" " * JG_LENGTH)
        _put(buf, 1, "JG"); _put(buf, 12, "2025"); _put(buf, 16, "0503"); _put(buf, 20, "04")
        _put(buf, 22, "01"); _put(buf, 24, "01"); _put(buf, 26, "11"); _put(buf, 28, blood)
        return bytes(buf)
    # 実 raw 同様、各レコード末尾に \r\n、次レコード先頭に制御 NUL がぶら下がる形
    data = _rec("2022100304") + b"\r\n\x00" + _rec("2021100100") + b"\r\n"
    p = tmp_path / "JGDWtest.jvd"
    p.write_bytes(data)
    recs = parse_jg_file(p)
    assert [r.blood_register_num for r in recs] == ["2022100304", "2021100100"]


def _schema_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    return conn


def test_upsert_race_scratch_roundtrip():
    conn = _schema_conn()
    buf = bytearray(b" " * JG_LENGTH)
    _put(buf, 1, "JG"); _put(buf, 12, "2025"); _put(buf, 16, "0503"); _put(buf, 20, "04")
    _put(buf, 22, "01"); _put(buf, 24, "01"); _put(buf, 26, "11")
    _put(buf, 28, "2022100304"); _put(buf, 38, "テスト馬"); _put(buf, 77, "9")
    upsert_race_scratch(conn, parse_jg(bytes(buf)))
    row = conn.execute(
        "SELECT horse_name, start_div FROM race_scratches WHERE blood_register_num='2022100304'"
    ).fetchone()
    assert row == ("テスト馬", "9")


def test_upsert_win5_header_and_payouts():
    conn = _schema_conn()
    buf = bytearray(b" " * WF_LENGTH)
    _put(buf, 1, "WF"); _put(buf, 12, "2025"); _put(buf, 16, "0504")
    _put(buf, 22, "05"); _put(buf, 24, "02"); _put(buf, 26, "04"); _put(buf, 28, "10")
    _put(buf, 68, "00008604205"); _put(buf, 136, "1")
    _put(buf, 167, "0604071206"); _put(buf, 177, "002176650"); _put(buf, 186, "0000000336")
    n = upsert_win5(conn, parse_wf(bytes(buf)))
    assert n == 1
    hdr = conn.execute("SELECT sale_votes, established_flag FROM win5 WHERE race_month_day='0504'").fetchone()
    assert hdr == (8604205, "1")
    pay = conn.execute("SELECT payout, hit_votes FROM win5_payouts WHERE combo='0604071206'").fetchone()
    assert pay == (2176650, 336)


def test_ingest_dispatch_counts_jg_and_wf(tmp_path):
    conn = _schema_conn()
    jg = bytearray(b" " * JG_LENGTH)
    _put(jg, 1, "JG"); _put(jg, 12, "2025"); _put(jg, 16, "0503"); _put(jg, 20, "04")
    _put(jg, 22, "01"); _put(jg, 24, "01"); _put(jg, 26, "11"); _put(jg, 28, "2022100304")
    wf = bytearray(b" " * WF_LENGTH)
    _put(wf, 1, "WF"); _put(wf, 12, "2025"); _put(wf, 16, "0504")
    _put(wf, 22, "05"); _put(wf, 24, "02"); _put(wf, 26, "04"); _put(wf, 28, "10")
    _put(wf, 167, "0604071206"); _put(wf, 177, "002176650"); _put(wf, 186, "0000000336")
    data = b"\r\n".join([bytes(jg), bytes(wf)]) + b"\r\n"
    p = tmp_path / "RACEjgwf.jvd"
    p.write_bytes(data)
    extras: dict[str, int] = {}
    ingest_file_dispatch(conn, p, "RACE", extra_counts=extras)
    assert extras == {"JG": 1, "WF": 1}
    assert conn.execute("SELECT COUNT(*) FROM race_scratches").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM win5").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM win5_payouts").fetchone()[0] == 1


def test_real_jg_wf_regression():
    """実 raw データがあれば妥当性を確認 (synthetic だけに依存しない)。"""
    import pytest
    jg_files = sorted(glob.glob(str(RAW_RACE / "JG*.jvd")))
    wf_files = sorted(glob.glob(str(RAW_RACE / "WF*.jvd")))
    if not jg_files and not wf_files:
        pytest.skip("data/raw/RACE/JG*/WF* が無い環境")
    if jg_files:
        recs = [r for r in _split_records(Path(jg_files[0]).read_bytes()) if r[:2] == b"JG"]
        jg = parse_jg(recs[0])
        assert len(jg.blood_register_num) == 10 and jg.blood_register_num.isdigit()
    if wf_files:
        recs = [r for r in _split_records(Path(wf_files[0]).read_bytes()) if r[:2] == b"WF"]
        wf = parse_wf(recs[0])
        # 対象 5 レースが取れている
        assert wf.target_races.count(",") == 4
        # 確定済なら払戻組番は 10 桁
        for combo, _pay, _hit in wf.payouts:
            assert len(combo) == 10 and combo.isdigit()
