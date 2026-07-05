"""Phase 4: SE コーナー順位 / RA ラップ parse のオフセット算術 + 先行力指標のテスト。

バイト位置の仕様根拠は parser.py の dataclass 注記参照 (実データ検証済アンカーからの
逆算 + 公開実装のフィールド順確認)。最終確認は実 .jvd での
scripts/probe_corner_offsets.py --expect (公式成績の既知値突合)。
"""

from __future__ import annotations

import sqlite3

from jvlink_client.parser import RA_LENGTH, SE_LENGTH, parse_ra, parse_se
from predictor.features import recent_corner_stats


def _put(buf: bytearray, pos1: int, width: int, val: int) -> None:
    s = str(val).rjust(width, "0").encode("ascii")
    buf[pos1 - 1: pos1 - 1 + width] = s


def _se_record_with_corners(c1, c2, c3, c4) -> bytes:
    """SE_LENGTH の生レコードを組み、コーナー順位を指定位置に書く。

    _int は 1-indexed。corner_order_1=pos352,2 / _2=354 / _3=356 / _4=358
    (着差コード×3 の直後、単勝オッズ 360 の直前)。
    """
    buf = bytearray(b"0" * SE_LENGTH)
    buf[0:2] = b"SE"
    _put(buf, 352, 2, c1)
    _put(buf, 354, 2, c2)
    _put(buf, 356, 2, c3)
    _put(buf, 358, 2, c4)
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


def test_parse_se_corner_not_in_winner_blood_num():
    # 回帰: 旧バグは 394-401 (1着馬血統登録番号の先頭) を誤読していた。
    # 394-403 に血統番号らしき 10 桁を置いても corner には混入しないこと。
    buf = bytearray(_se_record_with_corners(1, 2, 3, 4))
    _put(buf, 394, 10, 2019104123)  # KettoNum1
    se = parse_se(bytes(buf))
    assert (se.corner_order_1, se.corner_order_2, se.corner_order_3, se.corner_order_4) == (1, 2, 3, 4)


def _ra_record_with_laps(front3f, front4f, last3f, last4f, laps) -> bytes:
    """RA_LENGTH の生レコード。ラップ (891 + 3i) とハロン (970/973/976/979)。"""
    buf = bytearray(b"0" * RA_LENGTH)
    buf[0:2] = b"RA"
    for i, lap in enumerate(laps):
        _put(buf, 891 + i * 3, 3, lap)
    _put(buf, 970, 3, front3f)
    _put(buf, 973, 3, front4f)
    _put(buf, 976, 3, last3f)
    _put(buf, 979, 3, last4f)
    return bytes(buf)


def test_parse_ra_laps_and_harons():
    # 1600m 想定: 8 ハロン、テン3F=34.5 前4F=46.2 後3F=352? → 現実的な値で往復確認
    laps = [122, 108, 115, 118, 119, 120, 113, 118]
    ra = parse_ra(_ra_record_with_laps(345, 462, 348, 466, laps))
    assert ra.record_type == "RA"
    assert ra.front3f_time == 345
    assert ra.front4f_time == 462
    assert ra.last3f_time == 348
    assert ra.last4f_time == 466
    parsed = [int(x) for x in ra.lap_times.split(",")]
    assert len(parsed) == 25
    assert parsed[:8] == laps
    assert all(v == 0 for v in parsed[8:])  # 未使用ハロンは 0


def test_parse_ra_laps_backward_compat_zero():
    # ラップ未収録 (全て 0) でも落ちず 0 で埋まる
    ra = parse_ra(_ra_record_with_laps(0, 0, 0, 0, []))
    assert ra.front3f_time == 0 and ra.lap_times.count("0") >= 25


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
