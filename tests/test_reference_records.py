"""参照系・速報系レコード (RC/CS/YS/BT/HY/WE/AV/TC) パーサと取り込みのテスト。

仕様書 docs/JV-Data4901.pdf §21(RC) §27(CS) §25(YS,HY) §26(BT) §102(WE) §103(AV) §105(TC)。
byte 位置は 1-indexed。BT のみ実 BLOD データに合わせて系統名 pos50 開始。
"""
from __future__ import annotations

import glob
import sqlite3
from pathlib import Path

from db import (
    SCHEMA_PATH,
    upsert_course_info,
    upsert_horse_name_origin,
    upsert_lineage,
    upsert_race_cancellation,
    upsert_record_master,
    upsert_schedule,
    upsert_start_time_change,
    upsert_weather_going,
)
from jvlink_client.ingest import ingest_file_dispatch, _split_records
from jvlink_client.parser import (
    AV_LENGTH,
    BT_LENGTH,
    CS_LENGTH,
    HY_LENGTH,
    RC_LENGTH,
    TC_LENGTH,
    WE_LENGTH,
    YS_LENGTH,
    parse_av,
    parse_bt,
    parse_cs,
    parse_hy,
    parse_rc,
    parse_tc,
    parse_we,
    parse_ys,
)


def _put(buf: bytearray, pos: int, s: str) -> None:
    b = s.encode("cp932")
    buf[pos - 1 : pos - 1 + len(b)] = b


def test_parse_rc_byte_positions():
    buf = bytearray(b" " * RC_LENGTH)
    _put(buf, 1, "RC"); _put(buf, 3, "1"); _put(buf, 12, "1")
    _put(buf, 13, "2025"); _put(buf, 17, "0503"); _put(buf, 21, "05")
    _put(buf, 23, "02"); _put(buf, 25, "03"); _put(buf, 27, "11")
    _put(buf, 33, "テストカップ"); _put(buf, 93, "B"); _put(buf, 96, "1400")
    _put(buf, 100, "11"); _put(buf, 103, "1183"); _put(buf, 110, "2019106526")
    _put(buf, 120, "トウシンマカオ")
    rc = parse_rc(bytes(buf))
    assert rc.record_type == "RC" and rc.record_id_kubun == "1"
    assert rc.track_code == "05" and rc.distance == 1400 and rc.track_type_code == "11"
    assert rc.record_time == "1183" and rc.grade_code == "B"
    assert rc.holder_blood_num == "2019106526"
    assert rc.holder_horse_name == "トウシンマカオ"


def test_parse_cs_byte_positions():
    buf = bytearray(b" " * CS_LENGTH)
    _put(buf, 1, "CS"); _put(buf, 12, "01"); _put(buf, 14, "1000")
    _put(buf, 18, "17"); _put(buf, 20, "19900609"); _put(buf, 28, "スタート地点は…")
    cs = parse_cs(bytes(buf))
    assert cs.track_code == "01" and cs.distance == 1000 and cs.track_type_code == "17"
    assert cs.revision_date == "19900609"
    assert cs.description.startswith("スタート地点は")


def test_parse_ys_byte_positions():
    buf = bytearray(b" " * YS_LENGTH)
    _put(buf, 1, "YS"); _put(buf, 12, "2026"); _put(buf, 16, "0104")
    _put(buf, 20, "06"); _put(buf, 22, "01"); _put(buf, 24, "01"); _put(buf, 26, "2")
    ys = parse_ys(bytes(buf))
    assert ys.year == "2026" and ys.track_code == "06" and ys.weekday_code == "2"


def test_parse_bt_lineage_name_at_pos50():
    """系統名は実 BLOD データで pos50 開始 (keito_id len28)。"""
    buf = bytearray(b" " * BT_LENGTH)
    _put(buf, 1, "BT"); _put(buf, 12, "1110057602"); _put(buf, 22, "010201")
    _put(buf, 50, "パーソロン"); _put(buf, 88, "系統説明テキスト")
    bt = parse_bt(bytes(buf))
    assert bt.breeding_reg_num == "1110057602"
    assert bt.keito_id == "010201"
    assert bt.keito_name == "パーソロン"
    assert bt.description.startswith("系統説明")


def test_parse_hy_byte_positions():
    buf = bytearray(b" " * HY_LENGTH)
    _put(buf, 1, "HY"); _put(buf, 12, "2019106526")
    _put(buf, 22, "トウシンマカオ"); _put(buf, 58, "意味由来テキスト")
    hy = parse_hy(bytes(buf))
    assert hy.blood_register_num == "2019106526"
    assert hy.horse_name == "トウシンマカオ"
    assert hy.name_origin.startswith("意味由来")


def test_parse_we_current_and_prev():
    buf = bytearray(b" " * WE_LENGTH)
    _put(buf, 1, "WE"); _put(buf, 3, "1"); _put(buf, 12, "2026"); _put(buf, 16, "0509")
    _put(buf, 20, "04"); _put(buf, 22, "01"); _put(buf, 24, "03")
    _put(buf, 26, "05091000"); _put(buf, 34, "2")
    _put(buf, 35, "4"); _put(buf, 36, "1"); _put(buf, 37, "1")
    _put(buf, 38, "1"); _put(buf, 39, "1"); _put(buf, 40, "1")
    we = parse_we(bytes(buf))
    assert we.announced_time == "05091000" and we.change_id == "2"
    assert we.weather_code == "4" and we.going_turf == "1" and we.going_dirt == "1"
    assert we.prev_weather_code == "1"


def test_parse_av_scratch():
    buf = bytearray(b" " * AV_LENGTH)
    _put(buf, 1, "AV"); _put(buf, 3, "2"); _put(buf, 12, "2026"); _put(buf, 16, "0509")
    _put(buf, 20, "08"); _put(buf, 22, "03"); _put(buf, 24, "05"); _put(buf, 26, "01")
    _put(buf, 28, "05090954"); _put(buf, 36, "09"); _put(buf, 38, "グーフィー"); _put(buf, 74, "001")
    av = parse_av(bytes(buf))
    assert av.data_div == "2" and av.horse_num == "09"
    assert av.horse_name == "グーフィー" and av.reason_code == "001"


def test_parse_tc_start_time_change():
    buf = bytearray(b" " * TC_LENGTH)
    _put(buf, 1, "TC"); _put(buf, 3, "1"); _put(buf, 12, "2026"); _put(buf, 16, "0509")
    _put(buf, 20, "04"); _put(buf, 22, "01"); _put(buf, 24, "03"); _put(buf, 26, "12")
    _put(buf, 28, "05090820"); _put(buf, 36, "1601"); _put(buf, 40, "1600")
    tc = parse_tc(bytes(buf))
    assert tc.race_num == "12" and tc.new_start_time == "1601" and tc.old_start_time == "1600"


def _schema_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    return conn


def test_upsert_reference_roundtrips():
    """dataclass↔schema 列整合を実 DB で検証 (drift で OperationalError)。"""
    conn = _schema_conn()
    # RC
    rc = bytearray(b" " * RC_LENGTH)
    _put(rc, 1, "RC"); _put(rc, 12, "1"); _put(rc, 21, "05"); _put(rc, 100, "11")
    _put(rc, 96, "1400"); _put(rc, 103, "1183"); _put(rc, 93, "B")
    upsert_record_master(conn, parse_rc(bytes(rc)))
    assert conn.execute("SELECT record_time FROM record_master").fetchone()[0] == "1183"
    # BT (entity-keyed)
    bt = bytearray(b" " * BT_LENGTH)
    _put(bt, 1, "BT"); _put(bt, 12, "1110057602"); _put(bt, 22, "010201"); _put(bt, 50, "パーソロン")
    upsert_lineage(conn, parse_bt(bytes(bt)))
    assert conn.execute("SELECT keito_name FROM horse_lineages").fetchone()[0] == "パーソロン"
    # HY, CS, WE, AV, TC, YS upsert は OperationalError が出ないことだけ確認
    hy = bytearray(b" " * HY_LENGTH); _put(hy, 1, "HY"); _put(hy, 12, "2019106526")
    upsert_horse_name_origin(conn, parse_hy(bytes(hy)))
    cs = bytearray(b" " * CS_LENGTH); _put(cs, 1, "CS"); _put(cs, 12, "01"); _put(cs, 14, "1000"); _put(cs, 18, "17"); _put(cs, 20, "19900609")
    upsert_course_info(conn, parse_cs(bytes(cs)))
    we = bytearray(b" " * WE_LENGTH); _put(we, 1, "WE"); _put(we, 12, "2026"); _put(we, 16, "0509"); _put(we, 20, "04"); _put(we, 22, "01"); _put(we, 24, "03"); _put(we, 26, "05091000")
    upsert_weather_going(conn, parse_we(bytes(we)))
    av = bytearray(b" " * AV_LENGTH); _put(av, 1, "AV"); _put(av, 12, "2026"); _put(av, 16, "0509"); _put(av, 20, "08"); _put(av, 22, "03"); _put(av, 24, "05"); _put(av, 26, "01"); _put(av, 36, "09")
    upsert_race_cancellation(conn, parse_av(bytes(av)))
    tc = bytearray(b" " * TC_LENGTH); _put(tc, 1, "TC"); _put(tc, 12, "2026"); _put(tc, 16, "0509"); _put(tc, 20, "04"); _put(tc, 22, "01"); _put(tc, 24, "03"); _put(tc, 26, "12"); _put(tc, 28, "05090820")
    upsert_start_time_change(conn, parse_tc(bytes(tc)))
    ys = bytearray(b" " * YS_LENGTH); _put(ys, 1, "YS"); _put(ys, 12, "2026"); _put(ys, 16, "0104"); _put(ys, 20, "06"); _put(ys, 22, "01"); _put(ys, 24, "01")
    upsert_schedule(conn, parse_ys(bytes(ys)))
    assert conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 1


def test_ingest_dispatch_counts_reference_records(tmp_path):
    conn = _schema_conn()
    bt = bytearray(b" " * BT_LENGTH); _put(bt, 1, "BT"); _put(bt, 12, "1110057602"); _put(bt, 50, "パーソロン")
    hy = bytearray(b" " * HY_LENGTH); _put(hy, 1, "HY"); _put(hy, 12, "2019106526")
    zz = b"ZZ" + b" " * 60
    data = b"\r\n".join([bytes(bt), bytes(hy), zz]) + b"\r\n"
    p = tmp_path / "BLODtest.jvd"
    p.write_bytes(data)
    extras: dict[str, int] = {}
    _, _, _, _, _, skipped = ingest_file_dispatch(conn, p, "BLOD", extra_counts=extras)
    assert extras == {"BT": 1, "HY": 1}
    assert skipped == 1
    assert conn.execute("SELECT COUNT(*) FROM horse_lineages").fetchone()[0] == 1


def test_real_reference_data_regression():
    """実 raw があれば妥当性を確認 (synthetic だけに依存しない)。"""
    import pytest
    checks = [
        ("BLOD", b"BT", parse_bt, lambda o: len(o.breeding_reg_num) == 10 and bool(o.keito_name)),
        ("HOYU", b"HY", parse_hy, lambda o: len(o.blood_register_num) == 10),
        ("0B14", b"WE", parse_we, lambda o: o.weather_code != ""),
        ("DIFN", b"RC", parse_rc, lambda o: o.distance > 0 and o.record_time != ""),
    ]
    ran = 0
    for ds, rt, fn, ok in checks:
        files = sorted(glob.glob(rf"data/raw/{ds}/*.jvd"))
        if not files:
            continue
        for f in files:
            recs = [r for r in _split_records(Path(f).read_bytes()) if r[:2] == rt]
            if recs:
                assert ok(fn(recs[0])), f"{rt!r} 妥当性 NG"
                ran += 1
                break
    if ran == 0:
        pytest.skip("data/raw に参照系 raw が無い環境")
