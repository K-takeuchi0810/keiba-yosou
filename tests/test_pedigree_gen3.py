"""UM 3 代血統 (父母父/母母父) と HN 産地情報のパーサ regression。

バイト位置の根拠:
- UM: 3 代血統配列 (pos 205, 46 byte × 14 頭) の幅優先順。idx0=父 / idx4=母父は
  実運用 DB で検証済みアンカーで、SK パーサの docstring にも同順序の記載がある。
  idx8=父母父 / idx12=母母父 は同一配列の算術導出。
- HN: 205 持込区分 / 206-209 輸入年 / 210-229 産地名は、検証済みアンカー
  203-204 (毛色) と 230 (父繁殖番号) の間隙 25 byte にちょうど適合。

重要: 本テストは synthetic 往復 = 「書いた位置から読める」というパーサ内部の
自己整合の回帰であり、**実レコードでのバイト位置の正しさの証拠ではない**
(位置仮定が全体でずれていても green になる)。実データ証拠は実機での血統表
突合・産地目視 (docs/OPERATION.md「3代血統・産地の検証」) で取る。
"""

from __future__ import annotations

from jvlink_client.parser import HN_LENGTH, UM_LENGTH, parse_hn, parse_um


def _put_ascii(buf: bytearray, pos1: int, text: str) -> None:
    b = text.encode("ascii")
    buf[pos1 - 1: pos1 - 1 + len(b)] = b


def _put_cp932(buf: bytearray, pos1: int, text: str, width: int) -> None:
    b = text.encode("cp932")
    b = b + "　".encode("cp932") * ((width - len(b)) // 2)  # 全角空白パディング
    buf[pos1 - 1: pos1 - 1 + len(b)] = b


def _um_record() -> bytes:
    buf = bytearray(b"0" * UM_LENGTH)
    _put_ascii(buf, 1, "UM")
    _put_ascii(buf, 12, "2020104321")           # blood_register_num
    _put_cp932(buf, 47, "テスト馬", 36)
    # 3 代血統: idx0=父, idx4=母父, idx8=父母父, idx12=母母父
    for idx, (num, name) in {
        0: ("1111111111", "ディープインパクト"),
        4: ("4444444444", "キングカメハメハ"),
        8: ("8888888888", "ノーザンテースト"),
        12: ("2222222222", "トニービン"),
    }.items():
        pos = 205 + idx * 46
        _put_ascii(buf, pos, num)
        _put_cp932(buf, pos + 10, name, 36)
    return bytes(buf)


def test_parse_um_gen3_roundtrip():
    um = parse_um(_um_record())
    assert um.record_type == "UM"
    assert (um.sire_breeding_num, um.sire_name) == ("1111111111", "ディープインパクト")
    assert (um.dam_sire_breeding_num, um.dam_sire_name) == ("4444444444", "キングカメハメハ")
    assert (um.sire_dam_sire_breeding_num, um.sire_dam_sire_name) == ("8888888888", "ノーザンテースト")
    assert (um.dam_dam_sire_breeding_num, um.dam_dam_sire_name) == ("2222222222", "トニービン")


def test_parse_um_gen3_empty_slots_backward_compat():
    # 3 代血統が未収録 (NUL 埋め) でも落ちず、名前は空文字に劣化する
    buf = bytearray(b"\x00" * UM_LENGTH)
    buf[0:2] = b"UM"
    um = parse_um(bytes(buf))
    assert um.sire_dam_sire_name == ""
    assert um.dam_dam_sire_name == ""


def _hn_record() -> bytes:
    # 2026-07-06 実 .jvd で確定した -2 補正後のオフセットで組む
    # (旧 197/205/206/210/230/240 は tail 全体が +2 ずれていた誤り)。
    buf = bytearray(b"0" * HN_LENGTH)
    _put_ascii(buf, 1, "HN")
    _put_ascii(buf, 12, "8888888888")           # breeding_num
    _put_cp932(buf, 41, "ノーザンテースト", 36)
    _put_ascii(buf, 195, "1971")                # birth_year
    _put_ascii(buf, 201, "01")                  # coat
    _put_ascii(buf, 203, "1")                   # 持込区分
    _put_ascii(buf, 204, "1972")                # 輸入年
    _put_cp932(buf, 208, "米", 20)              # 産地名
    _put_ascii(buf, 228, "7777777777")          # sire_breeding_num
    _put_ascii(buf, 238, "6666666666")          # dam_breeding_num
    return bytes(buf)


def test_parse_hn_birthplace_roundtrip():
    hn = parse_hn(_hn_record())
    assert hn.record_type == "HN"
    assert hn.breeding_num == "8888888888"
    assert hn.horse_name == "ノーザンテースト"
    assert hn.mochikomi_kubun == "1"
    assert hn.import_year == "1972"
    assert hn.birthplace == "米"
    # 産地追加で既存アンカーがズレていないこと (前後フィールドの回帰)
    assert hn.coat_code == "01"
    assert hn.sire_breeding_num == "7777777777"
    assert hn.dam_breeding_num == "6666666666"


def test_parse_hn_domestic_no_import():
    buf = bytearray(_hn_record())
    _put_ascii(buf, 203, "0")
    _put_ascii(buf, 204, "0000")
    _put_cp932(buf, 208, "安平町", 20)
    hn = parse_hn(bytes(buf))
    assert hn.birthplace == "安平町"
    assert hn.import_year == "0000"


def test_parse_hn_real_record_offsets():
    """実 .jvd (probe_hn_offsets, HNVM2020…) の国内産レコードを模した固定バイト列で
    -2 補正後のオフセットを固定する。従来 (210/230) では birthplace が '平町…11' と
    先頭欠け+繁殖番号混入していた回帰を防ぐ。決め手: 持込区分=0(国内)+産地あり の相関。"""
    buf = bytearray(b"0" * HN_LENGTH)
    _put_ascii(buf, 1, "HN")
    _put_ascii(buf, 12, "1234567890")           # breeding_num (PK)
    _put_cp932(buf, 41, "イデオロレイ", 36)
    _put_ascii(buf, 195, "2014")                # birth_year
    _put_ascii(buf, 199, "1")                   # sex
    _put_ascii(buf, 200, "1")                   # breed
    _put_ascii(buf, 201, "03")                  # coat
    _put_ascii(buf, 203, "0")                   # 持込区分 = 国内
    _put_ascii(buf, 204, "0000")                # 輸入年
    _put_cp932(buf, 208, "安平町", 20)          # 産地名
    _put_ascii(buf, 228, "1120200612")          # sire_breeding_num
    _put_ascii(buf, 238, "2594851243")          # dam_breeding_num
    hn = parse_hn(bytes(buf))
    assert hn.birth_year == "2014"
    assert hn.mochikomi_kubun == "0"
    assert hn.birthplace == "安平町"            # 208 で先頭欠けなく読める
    assert hn.sire_breeding_num == "1120200612" # 228。traversal はこの列を辿る
    assert hn.dam_breeding_num == "2594851243"  # 238
