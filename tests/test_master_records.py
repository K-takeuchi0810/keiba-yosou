"""マスタ系レコード (KS/CH/BR/BN) パーサのバイト位置テスト。

仕様書 docs/JV-Data4901.pdf §14-17。byte 位置は 1-indexed。
"""
from __future__ import annotations

from jvlink_client.parser import (
    BN_LENGTH,
    BR_LENGTH,
    CH_LENGTH,
    KS_LENGTH,
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