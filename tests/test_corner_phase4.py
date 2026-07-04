"""Phase 4: SE コーナー順位 parse のオフセット算術 + 先行力指標のテスト。

注意: parse_se のバイト位置 (394-401) 自体の**仕様適合**は実 .jvd での
scripts/probe_corner_offsets.py 検証が必須 (本テストは offset 算術と
正規化・後方互換・特徴量ロジックを固定するもので、仕様正しさの保証ではない)。
"""

from __future__ import annotations

import sqlite3

from jvlink_client.parser import SE_LENGTH, parse_se
from predictor.features import recent_corner_stats


def _se_record_with_corners(c1, c2, c3, c4) -> bytes:
    """SE_LENGTH の生レコードを組み、コーナー順位を指定位置に書く。

    _int は 1-indexed。corner_order_1=pos394,2 / _2=396 / _3=398 / _4=400。
    レコード種別 "SE" を先頭に置き、必須の数値位置以外は '0' 埋め。
    """
    buf = bytearray(b"0" * SE_LENGTH)
    buf[0:2] = b"SE"

    def put(pos1: int, width: int, val: int):
        s = str(val).rjust(width, "0").encode("ascii")
        buf[pos1 - 1: pos1 - 1 + width] = s

    put(394, 2, c1)
    put(396, 2, c2)
    put(398, 2, c3)
    put(400, 2, c4)
    return bytes(buf)


def test_parse_se_corner_offsets_roundtrip():
    rec = _se_record_with_corners(3, 4, 5, 7)
    se = parse_se(rec)
    assert se.record_type == "SE"
    assert (se.corner_order_1, se.corner_order_2, se.corner_order_3, se.corner_order_4) == (3, 4, 5, 7)


def test_parse_se_corner_length_normalization():
    # 短いレコードでも落ちず 0 埋めされる (BSTR ラウンドトリップ耐性)
    short = _se_record_with_corners(1, 2, 3, 4)[:500]
    se = parse_se(short)
    # 切られた位置次第だが例外を出さないことが主眼
    assert isinstance(se.corner_order_4, int)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, "
        "blood_register_num TEXT, corner_order_4 INTEGER, confirmed_order INTEGER)"
    )
    return conn


def test_recent_corner_stats_leak_safe_and_math():
    conn = _db()
    # 対象馬 B1 の過去3走: 4角(2,4,3) 着(1,2,5)
    for md, c4, order in [("0101", 2, 1), ("0201", 4, 2), ("0301", 3, 5)]:
        conn.execute("INSERT INTO horse_races VALUES ('2025',?, 'B1', ?, ?)", (md, c4, order))
    # before_date より後のレースはリークになるので無視される
    conn.execute("INSERT INTO horse_races VALUES ('2025','0601','B1', 1, 1)")
    conn.commit()
    avg_pos, avg_chg, n = recent_corner_stats(conn, "B1", "20250401")
    assert n == 3
    assert avg_pos == round((2 + 4 + 3) / 3, 2)      # 3.0
    # position_change = 4角 - 着順: (2-1)+(4-2)+(3-5) = 1+2-2 = 1 → 平均 0.33
    assert avg_chg == round((1 + 2 - 2) / 3, 2)


def test_recent_corner_stats_backward_compat_no_data():
    conn = _db()
    # corner_order_4 が全て 0 (未 ingest) → samples 0, None
    conn.execute("INSERT INTO horse_races VALUES ('2025','0101','B1', 0, 1)")
    conn.commit()
    avg_pos, avg_chg, n = recent_corner_stats(conn, "B1", "20250401")
    assert (avg_pos, avg_chg, n) == (None, None, 0)


def test_recent_corner_stats_empty_blood():
    conn = _db()
    assert recent_corner_stats(conn, "", "20250401") == (None, None, 0)
    assert recent_corner_stats(conn, "0000000000", "20250401") == (None, None, 0)
