"""式別オッズ (O2-O6) / 票数 (H1/H6) パーサとDB取り込みのテスト。

仕様書 docs/JV-Data4901.pdf §5-6 (票数), §8-12 (オッズ)。byte 位置は 1-indexed。
配列は全式別とも pos 41 (オッズ) / 各ブロック先頭 (票数) 開始。
"""
from __future__ import annotations

import glob
import logging
import sqlite3
from pathlib import Path

from db import SCHEMA_PATH, upsert_exotic_odds, upsert_vote_counts
from jvlink_client import ingest as ingest_mod
from jvlink_client.ingest import ingest_file_dispatch, _split_records
from jvlink_client.parser import (
    H1_LENGTH,
    H6_LENGTH,
    O2_LENGTH,
    O3_LENGTH,
    O5_LENGTH,
    O6_LENGTH,
    parse_h1,
    parse_h6,
    parse_o2,
    parse_o3,
    parse_o5,
    parse_o6,
)

RAW_RACE = Path(r"C:\Users\kizun\dev\keiba-yosou\data\raw\RACE")


def _put(buf: bytearray, pos: int, s: str) -> None:
    """仕様書 1-indexed 位置に cp932 で書き込む。"""
    b = s.encode("cp932")
    buf[pos - 1 : pos - 1 + len(b)] = b


def _odds_header(buf: bytearray, rec_id: str) -> None:
    """O2-O6 共通ヘッダ (レース複合キー + flag)。"""
    _put(buf, 1, rec_id)
    _put(buf, 3, "5")          # data_div = 確定
    _put(buf, 4, "20250503")   # data_created
    _put(buf, 12, "2025")      # year
    _put(buf, 16, "0503")      # month_day
    _put(buf, 20, "04")        # track
    _put(buf, 22, "01")        # kaiji
    _put(buf, 24, "01")        # nichiji
    _put(buf, 26, "01")        # race_num
    _put(buf, 28, "00000000")  # announced_time
    _put(buf, 40, "1")         # 発売フラグ


def test_parse_o2_single_odds_byte_positions():
    buf = bytearray(b" " * O2_LENGTH)
    _odds_header(buf, "O2")
    # 配列 pos41, item13: 組番(1)4 オッズ(5)6 人気(11)3
    _put(buf, 41, "0102"); _put(buf, 45, "009675"); _put(buf, 51, "072")
    _put(buf, 54, "0103"); _put(buf, 58, "005150"); _put(buf, 64, "056")
    o = parse_o2(bytes(buf))
    assert o.record_type == "O2" and o.bet_type == "quinella"
    assert o.race_id == "20250503_04_01_01_01"
    assert o.entries[:2] == [("0102", 9675, 0, 72), ("0103", 5150, 0, 56)]


def test_parse_o3_wide_has_low_high():
    buf = bytearray(b" " * O3_LENGTH)
    _odds_header(buf, "O3")
    # 配列 pos41, item17: 組番(1)4 最低(5)5 最高(10)5 人気(15)3
    _put(buf, 41, "0102"); _put(buf, 45, "02467"); _put(buf, 50, "02548"); _put(buf, 55, "075")
    o = parse_o3(bytes(buf))
    assert o.bet_type == "wide"
    assert o.entries[0] == ("0102", 2467, 2548, 75)


def test_parse_o5_trio_six_digit_combo():
    buf = bytearray(b" " * O5_LENGTH)
    _odds_header(buf, "O5")
    # 配列 pos41, item15: 組番(1)6 オッズ(7)6 人気(13)3
    _put(buf, 41, "010203"); _put(buf, 47, "031074"); _put(buf, 53, "233")
    o = parse_o5(bytes(buf))
    assert o.bet_type == "trio"
    assert o.entries[0] == ("010203", 31074, 0, 233)


def test_parse_o6_trifecta_seven_digit_odds():
    buf = bytearray(b" " * O6_LENGTH)
    _odds_header(buf, "O6")
    # 配列 pos41, item17: 組番(1)6 オッズ(7)7 人気(14)4
    _put(buf, 41, "010204"); _put(buf, 47, "0284567"); _put(buf, 54, "1503")
    o = parse_o6(bytes(buf))
    assert o.bet_type == "trifecta"
    assert o.entries[0] == ("010204", 284567, 0, 1503)


def test_parse_o2_skips_unsold_and_presale():
    """空欄(登録なし)/'------'(発売前)/0倍 は除外される。"""
    buf = bytearray(b" " * O2_LENGTH)
    _odds_header(buf, "O2")
    _put(buf, 41, "0102"); _put(buf, 45, "------"); _put(buf, 51, "---")  # 発売前
    _put(buf, 54, "0103"); _put(buf, 58, "000000"); _put(buf, 64, "000")  # 0倍
    _put(buf, 67, "0104"); _put(buf, 71, "009675"); _put(buf, 77, "072")  # 有効
    o = parse_o2(bytes(buf))
    assert o.entries == [("0104", 9675, 0, 72)]


def test_parse_h1_all_pools_byte_positions():
    buf = bytearray(b" " * H1_LENGTH)
    _put(buf, 1, "H1"); _put(buf, 3, "5"); _put(buf, 4, "20250503")
    _put(buf, 12, "2025"); _put(buf, 16, "0503"); _put(buf, 20, "04")
    _put(buf, 22, "01"); _put(buf, 24, "01"); _put(buf, 26, "01")
    # 単勝 pos84, item15: 馬番(1)2 票数(3)11 人気(14)2
    _put(buf, 84, "01"); _put(buf, 86, "00000007374"); _put(buf, 97, "07")
    # 馬連 pos1464, item18: 組番(1)4 票数(5)11 人気(16)3
    _put(buf, 1464, "0102"); _put(buf, 1468, "00000000153"); _put(buf, 1479, "075")
    # 三連複 pos12480, item20: 組番(1)6 票数(7)11 人気(18)3
    _put(buf, 12480, "010203"); _put(buf, 12486, "00000000066"); _put(buf, 12497, "233")
    o = parse_h1(bytes(buf))
    assert o.record_type == "H1"
    by = {(bt, combo): (v, p) for bt, combo, v, p in o.entries}
    assert by[("win", "01")] == (7374, 7)
    assert by[("quinella", "0102")] == (153, 75)
    assert by[("trio", "010203")] == (66, 233)


def test_parse_h6_trifecta_votes():
    buf = bytearray(b" " * H6_LENGTH)
    _put(buf, 1, "H6"); _put(buf, 3, "5"); _put(buf, 4, "20250503")
    _put(buf, 12, "2025"); _put(buf, 16, "0503"); _put(buf, 20, "04")
    _put(buf, 22, "01"); _put(buf, 24, "01"); _put(buf, 26, "01")
    # 三連単 pos51, item21: 組番(1)6 票数(7)11 人気(18)4
    _put(buf, 51, "010203"); _put(buf, 57, "00000000066"); _put(buf, 68, "0870")
    o = parse_h6(bytes(buf))
    assert o.entries[0] == ("trifecta", "010203", 66, 870)


def _schema_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    return conn


def test_upsert_exotic_odds_roundtrip_and_idempotent():
    """dataclass↔schema の列整合を実DBで検証。再 upsert は冪等 (行数不変)。"""
    conn = _schema_conn()
    buf = bytearray(b" " * O3_LENGTH)
    _odds_header(buf, "O3")
    _put(buf, 41, "0102"); _put(buf, 45, "02467"); _put(buf, 50, "02548"); _put(buf, 55, "075")
    o = parse_o3(bytes(buf))
    assert upsert_exotic_odds(conn, o) == 1
    upsert_exotic_odds(conn, o)  # 再取込
    assert conn.execute("SELECT COUNT(*) FROM exotic_odds").fetchone()[0] == 1
    row = conn.execute(
        "SELECT bet_type, odds_low, odds_high, popularity FROM exotic_odds WHERE combo='0102'"
    ).fetchone()
    assert row == ("wide", 2467, 2548, 75)


def test_upsert_vote_counts_roundtrip():
    conn = _schema_conn()
    buf = bytearray(b" " * H6_LENGTH)
    _put(buf, 1, "H6"); _put(buf, 3, "5"); _put(buf, 4, "20250503")
    _put(buf, 12, "2025"); _put(buf, 16, "0503"); _put(buf, 20, "04")
    _put(buf, 22, "01"); _put(buf, 24, "01"); _put(buf, 26, "01")
    _put(buf, 51, "010203"); _put(buf, 57, "00000000066"); _put(buf, 68, "0870")
    o = parse_h6(bytes(buf))
    assert upsert_vote_counts(conn, o) == 1
    row = conn.execute(
        "SELECT bet_type, votes, popularity FROM vote_counts WHERE combo='010203'"
    ).fetchone()
    assert row == ("trifecta", 66, 870)


def test_ingest_dispatch_counts_odds_and_votes_by_row(tmp_path):
    """O2/H6 は組合せ行数で extra_counts に計上される (byte drift で 0 行になれば検出可)。"""
    conn = _schema_conn()
    o2 = bytearray(b" " * O2_LENGTH)
    _odds_header(o2, "O2")
    _put(o2, 41, "0102"); _put(o2, 45, "009675"); _put(o2, 51, "072")
    _put(o2, 54, "0103"); _put(o2, 58, "005150"); _put(o2, 64, "056")
    h6 = bytearray(b" " * H6_LENGTH)
    _put(h6, 1, "H6"); _put(h6, 3, "5"); _put(h6, 4, "20250503")
    _put(h6, 12, "2025"); _put(h6, 16, "0503"); _put(h6, 20, "04")
    _put(h6, 22, "01"); _put(h6, 24, "01"); _put(h6, 26, "01")
    _put(h6, 51, "010203"); _put(h6, 57, "00000000066"); _put(h6, 68, "0870")
    data = b"\r\n".join([bytes(o2), bytes(h6)]) + b"\r\n"
    p = tmp_path / "RACEtest.jvd"
    p.write_bytes(data)
    extras: dict[str, int] = {}
    ingest_file_dispatch(conn, p, "RACE", extra_counts=extras)
    assert extras == {"O2": 2, "H6": 1}, "オッズ/票数は行数で計上"
    assert conn.execute("SELECT COUNT(*) FROM exotic_odds").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM vote_counts").fetchone()[0] == 1


def test_ingest_dispatch_logs_odds_parse_failure(tmp_path, monkeypatch, caplog):
    conn = _schema_conn()
    def _boom(rec):
        raise ValueError("byte drift")
    monkeypatch.setattr(ingest_mod, "parse_o6", _boom)
    o6 = bytearray(b" " * O6_LENGTH)
    _odds_header(o6, "O6")
    _put(o6, 41, "010203"); _put(o6, 47, "0073297"); _put(o6, 54, "0870")
    p = tmp_path / "O6test.jvd"
    p.write_bytes(bytes(o6) + b"\r\n")
    with caplog.at_level(logging.WARNING):
        _, _, _, _, _, skipped = ingest_file_dispatch(conn, p, "RACE", extra_counts={})
    assert skipped == 1
    assert any("parse failed" in r.getMessage() for r in caplog.records)


def test_real_race_data_regression():
    """実 raw データ (data/raw/RACE) があれば組番・件数の妥当性を確認 (synthetic だけに依存しない)。

    raw が無い環境 ではスキップ。
    """
    import pytest
    o6_files = sorted(glob.glob(str(RAW_RACE / "O6*.jvd")))
    if not o6_files:
        pytest.skip("data/raw/RACE/O6*.jvd が無い環境")
    recs = _split_records(Path(o6_files[0]).read_bytes())
    o6_recs = [r for r in recs if r[:2] == b"O6"]
    assert o6_recs, "O6 レコードが見つからない"
    o = parse_o6(o6_recs[0])
    assert o.entries, "三連単オッズが 0 件 (byte 位置 drift の疑い)"
    # 三連単の組番は 6 桁数字 (馬番3つ)、最大 18*17*16=4896 通り
    assert len(o.entries) <= 4896
    for combo, odds_low, _high, _pop in o.entries[:50]:
        assert len(combo) == 6 and combo.isdigit(), f"不正な組番: {combo!r}"
        assert odds_low > 0
