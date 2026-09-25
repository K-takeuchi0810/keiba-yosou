"""確定払戻の滞留監視 (2026-09-23)。

2026-09-19 から 4 開催日ぶんの確定払戻が届かないまま 3 日以上経過していたのに
誰も気付かなかった。評価側は「データが不完全なら評価しない」という安全側の
設計にしたが、黙って止まるだけだと永久に気付けない。

**検出だけでは不十分**で、届いたら自動で解消することまで見る。手動でフラグを
消す設計にはしない。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

from scripts import payout_finality_monitor as mon

JST = timezone(timedelta(hours=9), "JST")


def _db(tmp_path, *, day="20260919", cancelled=0, executed=2,
        finished=None, payout_final=0, payout_prelim=None):
    """開催 1 日ぶんの最小 DB。

    `finished` は着順が確定したレース数 (既定は実施レース全部)。
    `payout_prelim` は速報払戻のレース数 (既定は確定していないぶん全部)。
    """
    finished = executed if finished is None else finished
    path = tmp_path / f"{day}.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " data_div TEXT)")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " horse_num TEXT, confirmed_order INTEGER, abnormal_code TEXT)")
    conn.execute("CREATE TABLE payouts (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " data_div TEXT)")
    n = 0
    for _ in range(cancelled):
        n += 1
        conn.execute("INSERT INTO races VALUES (?,?,'06','01','01',?,'9')",
                     (day[:4], day[4:], f"{n:02d}"))
        # 中止レースにも出走馬は登録されている
        conn.execute("INSERT INTO horse_races VALUES (?,?,'06','01','01',?,'01',0,'0')",
                     (day[:4], day[4:], f"{n:02d}"))
    prelim = executed if payout_prelim is None else payout_prelim
    for i in range(executed):
        n += 1
        rn = f"{n:02d}"
        conn.execute("INSERT INTO races VALUES (?,?,'06','01','01',?,'6')",
                     (day[:4], day[4:], rn))
        order = 1 if i < finished else 0
        for hn in ("01", "02"):
            conn.execute(
                "INSERT INTO horse_races VALUES (?,?,'06','01','01',?,?,?,'0')",
                (day[:4], day[4:], rn, hn, order if hn == "01" else (2 if order else 0)))
        if i < payout_final:
            conn.execute("INSERT INTO payouts VALUES (?,?,'06','01','01',?,'2')",
                         (day[:4], day[4:], rn))
        elif i < prelim:
            conn.execute("INSERT INTO payouts VALUES (?,?,'06','01','01',?,'1')",
                         (day[:4], day[4:], rn))
    conn.commit()
    conn.close()
    return str(path)


def _at(day: str, plus_hours: float) -> datetime:
    """開催日の 24:00 (JST) から `plus_hours` 経過した時刻。"""
    return (datetime.strptime(day, "%Y%m%d").replace(tzinfo=JST)
            + timedelta(days=1, hours=plus_hours))


# --- 検出 -----------------------------------------------------------------

def test_a_preliminary_only_day_is_pending(tmp_path):
    """速報払戻しか無い日は滞留として検出されること。"""
    db = _db(tmp_path, executed=2, payout_final=0)

    r = mon.build(days=3650, db_path=db, now=_at("20260919", 1))

    assert r["pending_race_count"] == 2
    assert r["pending_reason"] == "payout_not_yet_final"
    assert r["oldest_pending_race_date"] == "20260919"
    assert r["days"][0]["payout_preliminary"] == 2
    assert r["days"][0]["payout_final"] == 0
    assert r["days"][0]["evaluable"] == 0


@pytest.mark.parametrize("hours,want", [
    (1, "INFO"),     # 開催当日中
    (23, "INFO"),
    (30, "WARN"),    # 翌日
    (47, "WARN"),
    (49, "ERROR"),   # 48 時間超
    (72, "ERROR"),
])
def test_severity_rises_with_age(tmp_path, hours, want):
    """経過時間で深刻度が上がること (当日 INFO / 翌日 WARN / 48h 超 ERROR)。"""
    db = _db(tmp_path, executed=1, payout_final=0)

    r = mon.build(days=3650, db_path=db, now=_at("20260919", hours))

    assert r["status"] == want, f"{hours} 時間経過で {r['status']}"


def test_the_exit_code_matches_the_status():
    """Task Scheduler から検知できるよう exit code が対応すること。"""
    assert mon.EXIT_CODES["OK"] == 0
    assert mon.EXIT_CODES["INFO"] == 0      # 当日中は正常扱い
    assert mon.EXIT_CODES["WARN"] == 1
    assert mon.EXIT_CODES["ERROR"] == 2


# --- 中止を滞留に数えない -------------------------------------------------

def test_cancelled_races_are_never_pending(tmp_path):
    """★ 中止レースを滞留に数えないこと。

    中止レースの払戻は永久に来ないので、数えると鳴り続けて監視が死ぬ。
    2026-09-21 の中山 12R がまさにこれ。
    """
    db = _db(tmp_path, day="20260921", cancelled=12, executed=12,
             payout_final=12)

    r = mon.build(days=3650, db_path=db, now=_at("20260921", 72))

    assert r["status"] == "OK", f"中止を滞留に数えている: {r['pending_race_ids']}"
    assert r["pending_race_count"] == 0
    d = r["days"][0]
    assert (d["scheduled"], d["cancelled"], d["executed"]) == (24, 12, 12)
    assert d["evaluable"] == 12


def test_a_fully_cancelled_day_never_alerts(tmp_path):
    """全レース中止の日も鳴らないこと。"""
    db = _db(tmp_path, day="20260921", cancelled=12, executed=0)

    r = mon.build(days=3650, db_path=db, now=_at("20260921", 240))

    assert r["status"] == "OK"
    assert r["days"][0]["cancelled"] == 12
    assert r["days"][0]["executed"] == 0


# --- 回復 (指示された「到着したら自動で解消」) ----------------------------

def test_the_alert_clears_when_the_final_payout_arrives(tmp_path):
    """★ 確定払戻が届いたら **自動で** 解消すること。

    手動でフラグを消す設計にはしない。検出だけして解消しないと、次は
    「鳴りっぱなしなので無視する」運用になって監視の意味が消える。
    """
    db = _db(tmp_path, executed=2, payout_final=0)
    before = mon.build(days=3650, db_path=db, now=_at("20260919", 72))
    assert before["status"] == "ERROR"
    assert before["pending_race_count"] == 2

    # 確定払戻が到着 (速報行を確定に置き換える)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE payouts SET data_div='2'")
    conn.commit()
    conn.close()

    after = mon.build(days=3650, db_path=db, now=_at("20260919", 72))

    assert after["status"] == "OK", "到着しても解消していない"
    assert after["pending_race_count"] == 0
    assert after["oldest_pending_race_date"] is None
    assert after["pending_reason"] is None
    assert after["days"][0]["evaluable"] == 2


def test_a_partial_arrival_still_reports_the_rest(tmp_path):
    """一部だけ届いた場合、残りは滞留のままであること。"""
    db = _db(tmp_path, executed=4, payout_final=3)

    r = mon.build(days=3650, db_path=db, now=_at("20260919", 72))

    assert r["status"] == "ERROR"
    assert r["pending_race_count"] == 1
    assert r["days"][0]["payout_final"] == 3


# --- 出力に必要な項目 -----------------------------------------------------

def test_the_report_carries_everything_needed_to_act(tmp_path):
    """一目で原因が分かる項目がそろっていること。

    「9/19 開催分から final payout 未到着、最古 72 時間」が分かる状態にする。
    """
    db = _db(tmp_path, executed=2, payout_final=0)

    r = mon.build(days=3650, db_path=db, now=_at("20260919", 72))

    for key in ("oldest_pending_race_date", "pending_race_count",
                "pending_race_ids", "pending_reason", "age_hours",
                "latest_race_source_timestamp"):
        assert key in r, f"{key} が出力に無い"
    assert r["oldest_pending_race_date"] == "20260919"
    assert r["age_hours"] == pytest.approx(72, abs=1)
    assert len(r["pending_race_ids"]) == 2
    assert all(rid.startswith("20260919-") for rid in r["pending_race_ids"])


def test_the_source_timestamp_is_reported(monkeypatch, tmp_path):
    """JV-Link 側の last_timestamp を出すこと。

    「供給が遅れている」と「取り込みが壊れている」を取り違えないために要る。
    timestamp が進んでいないなら前者、進んでいるのに DB に入らないなら後者。
    """
    import jvlink_client.state as state

    monkeypatch.setattr(state, "load_state", lambda: {"RACE": "20260921112857"})

    assert mon.latest_race_source_timestamp() == "20260921112857"


def test_a_missing_state_file_does_not_crash(monkeypatch):
    """state が読めなくても監視自体は動くこと (欠落で落ちない)。"""
    import jvlink_client.state as state

    def boom():
        raise OSError("no such file")

    monkeypatch.setattr(state, "load_state", boom)

    assert mon.latest_race_source_timestamp() is None


def test_a_race_without_a_result_is_not_pending(tmp_path):
    """着順がまだのレースを「払戻滞留」に数えないこと。

    払戻速報だけ先に来ている状態でも、着順が確定していなければ待つべきは
    結果であって払戻ではない。ここを混ぜると、どちらを待っているのか
    分からない警告になる。

    fixture は 2 レース:
      R1 着順確定 + 確定払戻 -> 評価可
      R2 着順未確定 + 速報払戻のみ -> 滞留ではない (結果待ち)
    """
    db = _db(tmp_path, executed=2, finished=1, payout_final=1, payout_prelim=2)

    r = mon.build(days=3650, db_path=db, now=_at("20260919", 72))

    assert r["status"] == "OK", (
        f"結果待ちを払戻滞留に数えている: {r['pending_race_ids']}")
    assert r["pending_race_count"] == 0
    d = r["days"][0]
    assert d["result_final"] == 1
    assert d["payout_final"] == 1
    assert d["payout_preliminary"] == 1, "速報が残っている状態のはず"
    assert d["evaluable"] == 1


def test_the_report_never_leaks_race_outcomes(tmp_path):
    """★ 出力に成績を混ぜないこと。

    このスクリプトは封印の門 (`guard_analysis_window`) を通さず
    `GATE_EXEMPT` に入れてある。根拠は「件数しか見ない」ことなので、
    その前提が崩れたらここで落とす。口約束の免除にしない。

    出す内容は「どれだけ揃ったか」であって「何が起きたか」ではない。
    """
    db = _db(tmp_path, executed=3, finished=2, payout_final=1)

    r = mon.build(days=3650, db_path=db, now=_at("20260919", 72))

    leaked = set()
    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                # 着順・配当・オッズ・馬番・的中に類する語を出さない
                if any(w in k for w in ("order", "payout_yen", "odds", "horse",
                                        "win", "profit", "hit", "return")):
                    leaked.add(f"{path}{k}")
                walk(v, f"{path}{k}.")
        elif isinstance(node, list):
            for v in node:
                walk(v, path)

    walk(r)
    assert not leaked, f"監視の出力に成績が混ざっている: {sorted(leaked)}"

    # キー名だけでは足りない。値に成績を埋め込む変異 (pending_race_ids に
    # 1 着馬番を付ける) と、blacklist 外の語のキー (first_place_by_race) を
    # 追加する変異が素通りした (2026-09-23 最終ゲート G1 / G2)。
    # **キー集合を完全一致で固定し、値の形も全部検査する**。
    _assert_report_is_counts_only(r)


# --- 免除の根拠 (成績を出さない) を値と text 出力で固定 --------------------

_RACE_ID = re.compile(r"^\d{8}-\d{2}-\d{2}$")          # 開催日-場-R だけ
_DAYSTAMP = re.compile(r"^\d{8}$")

_TOP_KEYS = {
    "generated_at", "status", "oldest_pending_race_date", "pending_race_count",
    "pending_race_ids", "pending_reason", "age_hours",
    "latest_race_source_timestamp", "pending_scan_from", "days",
}
_DAY_KEYS = {
    "date", "scheduled", "cancelled", "executed", "result_final",
    "payout_preliminary", "payout_final", "evaluable", "pending_race_ids",
}


def _assert_report_is_counts_only(r):
    """出力が「件数・レース ID・時刻・状態」だけであること。"""
    assert set(r) == _TOP_KEYS, f"top-level のキーが増減した: {set(r) ^ _TOP_KEYS}"
    datetime.fromisoformat(r["generated_at"])
    assert r["status"] in mon.STATUS_ORDER
    assert r["oldest_pending_race_date"] is None or _DAYSTAMP.match(
        r["oldest_pending_race_date"])
    assert type(r["pending_race_count"]) is int
    assert r["pending_reason"] in (None, mon.PENDING_REASON)
    assert type(r["age_hours"]) is float
    ts = r["latest_race_source_timestamp"]
    assert ts is None or re.fullmatch(r"\d{8,14}", ts), ts
    assert _DAYSTAMP.match(r["pending_scan_from"])
    for rid in r["pending_race_ids"]:
        assert _RACE_ID.match(rid), f"レース ID の形でない (成績の混入?): {rid!r}"
    assert len(r["pending_race_ids"]) == r["pending_race_count"]
    assert isinstance(r["days"], list)
    for d in r["days"]:
        assert set(d) == _DAY_KEYS, f"days のキーが増減した: {set(d) ^ _DAY_KEYS}"
        assert _DAYSTAMP.match(d["date"])
        for k in _DAY_KEYS - {"date", "pending_race_ids"}:
            assert type(d[k]) is int, f"days.{k} が件数でない: {d[k]!r}"
        for rid in d["pending_race_ids"]:
            assert _RACE_ID.match(rid), f"レース ID の形でない: {rid!r}"


#: text 出力で許す行。これ以外の行が出たら落とす (出力の形を増やすときは
#: ここも増やす = 免除の根拠を見直す機会になる)。
_TEXT_LINES = [
    re.compile(r"^payout finality: (OK|INFO|WARN|ERROR)$"),
    re.compile(r"^  \d{8}  予定 *\d+ 中止 *\d+ 実施 *\d+ 着順確定 *\d+"
               r" 払戻速報 *\d+ 払戻確定 *\d+ 評価可 *\d+( ←滞留)?$"),
    re.compile(r"^  最古の滞留: \d{8} 開催分から payout_not_yet_final、\d+ 時間経過 "
               r"\(\d+ レース\)( ※表示窓の外)?$"),
    re.compile(r"^  滞留の検出範囲: \d{8} 以降の全開催日 \(表示窓 --days とは独立\)$"),
    re.compile(r"^  JV-Link RACE last_timestamp: (None|\d{8,14})$"),
]


def _run_cli(monkeypatch, capsys, db, now, *args):
    monkeypatch.setattr(mon, "DB_PATH", db)
    real_build = mon.build
    monkeypatch.setattr(mon, "build", lambda days: real_build(days=days, now=now))
    monkeypatch.setattr(sys, "argv", ["payout_finality_monitor", *args])
    rc = mon.main()
    return rc, capsys.readouterr().out


def test_the_text_output_carries_no_outcomes(tmp_path, monkeypatch, capsys):
    """★ text 出力も「件数だけ」であること (G1 / G2 の text 版)。

    dict だけ検査しても、`main()` の print に 1 着馬番を足せば素通りする。
    許可した行の形以外が 1 行でも出たら落とす。
    """
    db = _db(tmp_path, executed=3, finished=2, payout_final=1)

    rc, out = _run_cli(monkeypatch, capsys, db, _at("20260919", 72), "--days", "3650")

    assert rc == mon.EXIT_CODES["ERROR"]
    lines = out.splitlines()
    assert lines, "何も出ていない"
    for line in lines:
        assert any(p.match(line) for p in _TEXT_LINES), (
            f"許可していない形の行が出ている (成績の混入?): {line!r}")
    assert any("←滞留" in l for l in lines), "滞留の行が出ていない (対照)"


def test_the_json_output_carries_no_outcomes(tmp_path, monkeypatch, capsys):
    """`--json` 出力にも同じ検査を掛けること。"""
    db = _db(tmp_path, executed=3, finished=2, payout_final=1)

    rc, out = _run_cli(monkeypatch, capsys, db, _at("20260919", 72),
                       "--days", "3650", "--json")

    assert rc == mon.EXIT_CODES["ERROR"]
    _assert_report_is_counts_only(json.loads(out))


# --- 表示の窓と検出の範囲 -------------------------------------------------

def test_an_old_pending_day_stays_loud_outside_the_window(tmp_path):
    """★ 表示窓を過ぎた滞留が **OK に戻らない** こと。

    検出を `--days` の窓に縛っていた頃は、15 日放置すると滞留日が窓から
    外れて OK に戻った (実 DB で `--days 14` → OK / `--days 30` → ERROR)。
    黙って落ちないための監視が、放置するほど黙るのでは逆になる。
    """
    db = _db(tmp_path, day="20260919", executed=2, payout_final=0)
    now = _at("20260919", 20 * 24)                    # 20 日放置

    r = mon.build(days=14, db_path=db, now=now)

    assert r["status"] == "ERROR", "窓を過ぎた滞留が黙っている"
    assert r["oldest_pending_race_date"] == "20260919"
    assert r["pending_race_count"] == 2
    assert r["days"] == [], "表は窓の中だけ (表示と検出は別)"


def test_the_text_output_says_the_oldest_is_outside_the_window(
        tmp_path, monkeypatch, capsys):
    """表に出ていない日の滞留だと分かる印が付くこと (表だけ見て見逃さない)。"""
    db = _db(tmp_path, day="20260919", executed=2, payout_final=0)

    rc, out = _run_cli(monkeypatch, capsys, db, _at("20260919", 20 * 24),
                       "--days", "14")

    assert rc == mon.EXIT_CODES["ERROR"]
    assert "最古の滞留: 20260919" in out
    assert "※表示窓の外" in out


def test_days_before_the_scan_floor_are_not_pending(tmp_path):
    """下限より前は検出しないこと (除外しすぎ・鳴らしすぎの対照)。

    2020 年より前は払戻を取り込んでいないので、見ると永久に ERROR になる
    (実 DB で 1954-1985 の 58 レース)。鳴りっぱなしの監視は無視される。
    """
    db = _db(tmp_path, day="20191228", executed=2, payout_final=0)

    r = mon.build(days=3650, db_path=db, now=_at("20191228", 72))

    assert r["status"] == "OK"
    assert r["pending_race_count"] == 0
    assert r["days"][0]["pending_race_ids"], "日別の表には滞留として残す (隠さない)"
