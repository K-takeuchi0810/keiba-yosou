"""「今日」の決定が 1 箇所に集約されていることの契約テスト (2026-09-20)。

以前は 4 箇所がそれぞれ独自に日付を作っていた (auto_predict の対象日 /
notify_dedup の重複判定 / generator の既定窓 / bat のログ名)。JST を明示して
いたのは重複判定だけで、残りはシステムのローカル時刻任せだった。

同じ 1 回の起動の中で「今日」が 2 通り存在しうる状態で、境界をまたいだ瞬間に
「対象日は 9/20 なのに通知の記録は 9/21」のような食い違いが起きる。予想を出す日
そのものを決める値なので、ずれたら 1 日ぶんの予想を落とす。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from jst import (JST, current_jst_date, current_jst_datetime,
                 current_jst_daystamp)

REPO = Path(__file__).resolve().parents[1]


# --- 境界 -----------------------------------------------------------------

def test_the_utc_1500_boundary_flips_the_jst_day():
    """UTC 15:00 ちょうどで JST の日付が変わること。

    指示された境界そのもの。実行時刻に依存しないよう now を注入する。
    """
    before = datetime(2026, 9, 20, 14, 59, 59, tzinfo=timezone.utc)
    after = datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc)

    assert current_jst_daystamp(now=before) == "20260920"
    assert current_jst_daystamp(now=after) == "20260921"


def test_jst_midnight_is_the_boundary():
    """JST 00:00 の前後で日付が変わること (JST 側から見た境界)。"""
    eve = datetime(2026, 9, 20, 23, 59, 59, tzinfo=JST)
    midnight = datetime(2026, 9, 21, 0, 0, 0, tzinfo=JST)

    assert current_jst_date(now=eve) == date(2026, 9, 20)
    assert current_jst_date(now=midnight) == date(2026, 9, 21)


def test_a_utc_machine_still_gets_the_jst_day():
    """OS が UTC でも JST の日付になること。

    UTC 22:00 は JST では翌日 07:00。ローカル時刻を読んでいると 1 日ずれる。
    """
    utc_evening = datetime(2026, 9, 20, 22, 0, 0, tzinfo=timezone.utc)

    assert current_jst_daystamp(now=utc_evening) == "20260921"
    assert current_jst_datetime(now=utc_evening).hour == 7


def test_a_run_that_crosses_midnight_sees_the_new_day():
    """日付をまたいで実行が続いた場合、またいだ後は翌日を返すこと."""
    start = datetime(2026, 9, 20, 14, 59, 0, tzinfo=timezone.utc)
    later = start + timedelta(minutes=2)

    assert current_jst_daystamp(now=start) == "20260920"
    assert current_jst_daystamp(now=later) == "20260921"


def test_a_naive_datetime_is_refused():
    """tz の無い datetime は受け付けないこと。

    黙って受けると UTC なのかローカルなのかが呼び出し側にしか分からず、
    取り違えても誰も気付けない。
    """
    with pytest.raises(ValueError):
        current_jst_daystamp(now=datetime(2026, 9, 20, 15, 0, 0))


def test_a_tzinfo_without_an_offset_is_refused():
    """tzinfo は付いているが `utcoffset()` が None を返すものも拒否すること。

    `tzinfo is None` だけ見ていると、これが素通りして `astimezone` が
    ローカル時刻を仮定する。naive を拒否した意味が無くなる。
    """
    from datetime import datetime, tzinfo

    class NoOffset(tzinfo):
        def utcoffset(self, dt):
            return None

        def dst(self, dt):
            return None

    with pytest.raises(ValueError):
        current_jst_daystamp(now=datetime(2026, 9, 20, 15, 0, tzinfo=NoOffset()))


def test_now_defaults_to_utc_not_local_time():
    """既定の now がシステムのローカル時刻でないこと。

    `datetime.now()` (naive) を既定にしていると OS 設定で答えが変わる。
    """
    import jst as jst_module

    src = Path(jst_module.__file__).read_text(encoding="utf-8")
    body = src[src.index("def current_jst_datetime"):src.index("def current_jst_date(")]
    assert "datetime.now(timezone.utc)" in body
    assert "datetime.now()" not in body, "ローカル時刻を読んでいる"


# --- 集約されていること ---------------------------------------------------

def test_the_default_now_is_really_jst_now():
    """`now` を渡さない既定パスが、本当に JST の現在時刻を返すこと。

    **これが一番の穴だった**。境界テストはすべて `now` を注入しており、既定
    パスを見ているテストが 1 本も無かった。そのため 2026-09-21 に
    `datetime.now(timezone.utc) - timedelta(days=1)` という変異が作業ツリーに
    4 分間生き残っても、12 件すべて緑のままだった (実際に起きた)。

    実装の定数を使わず、テスト側で JST を **独立に組み立てて**突き合わせる。
    """
    from datetime import datetime, timedelta, timezone

    expected = datetime.now(timezone(timedelta(hours=9)))
    got = current_jst_datetime()

    drift = abs((got - expected).total_seconds())
    assert drift < 5, f"既定の now が {drift:.0f} 秒ずれている (1 日 = 86400)"
    assert got.utcoffset() == timedelta(hours=9)


def test_the_entry_point_uses_the_single_source(tmp_path, monkeypatch, capsys):
    """`main()` が実際に採る対象日が、単一出典の値と一致すること。

    以前ここは `current_jst_daystamp()` 同士を比べるだけの同語反復で、
    `main()` が何を見ているかを 1 つも検証していなかった。実際にエントリ
    ポイントを通して、出力された対象日を突き合わせる。
    """
    import sqlite3

    from scripts import auto_predict

    day = current_jst_daystamp()
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    # data_div は中止判定 (main 8a91d73) で必須。'6' = 実施予定。
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " data_div TEXT)")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " horse_num TEXT)")
    conn.execute("INSERT INTO races VALUES (?,?,'05','01','01','01','6')",
                 (day[:4], day[4:]))
    conn.commit()
    conn.close()

    monkeypatch.setattr(auto_predict, "DB_PATH", str(db))
    monkeypatch.setattr(auto_predict.subprocess, "run",
                        lambda command, **kwargs: None)
    monkeypatch.setattr("sys.argv", ["auto_predict", "--dry-run"])
    auto_predict.main()

    line = next(l for l in capsys.readouterr().out.splitlines()
                if l.startswith("generate:"))
    assert day in line, f"main() の対象日が単一出典とずれている: {line}"


def test_the_final_attempt_hour_is_judged_in_jst():
    """最終起動の判定も JST で行い、now を注入できること。"""
    from scripts import auto_predict

    # UTC 01:00 = JST 10:00 → まだ最終起動ではない
    assert auto_predict._is_final_attempt(
        now=datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc)) is False
    # UTC 02:00 = JST 11:00 → 最終起動
    assert auto_predict._is_final_attempt(
        now=datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc)) is True


# 「今日」を各自で作る書き方の検出は tests/test_today_single_source.py に
# 移した。正規表現版はここにあったが、実際に使われている書き方の
# 9 割を素通りさせていたので AST 版に置き換えた。


def test_the_batch_log_uses_the_same_source():
    """ログのファイル名の日付も同じ関数から採ること。

    ログ名だけ別の日付になると、その日の notify-audit を追うときに
    「どのファイルを見ればいいか」がずれる。
    """
    bat = (REPO / "scripts" / "auto_predict_daily.bat").read_text(
        encoding="utf-8", errors="replace")
    runline = next(l for l in bat.splitlines() if "set RUNDATE" in l)

    assert "current_jst_daystamp" in runline, f"bat が独自に日付を作っている: {runline}"
    assert "date.today()" not in runline
