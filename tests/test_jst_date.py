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

def test_dedup_and_the_target_day_agree():
    """dedup 側と生成対象日側が同じ日付を返すこと。"""
    from scripts import auto_predict, notify_dedup

    assert notify_dedup.jst_today() == current_jst_daystamp()
    assert auto_predict.current_jst_date() == current_jst_date()
    assert notify_dedup.jst_today() == current_jst_date().strftime("%Y%m%d")


def test_the_final_attempt_hour_is_judged_in_jst():
    """最終起動の判定も JST で行い、now を注入できること。"""
    from scripts import auto_predict

    # UTC 01:00 = JST 10:00 → まだ最終起動ではない
    assert auto_predict._is_final_attempt(
        now=datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc)) is False
    # UTC 02:00 = JST 11:00 → 最終起動
    assert auto_predict._is_final_attempt(
        now=datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc)) is True


@pytest.mark.parametrize("rel", [
    "scripts/auto_predict.py",
    "scripts/notify_dedup.py",
    "web/generator.py",
])
def test_no_module_makes_its_own_today(rel):
    """「今日」を各自で作る書き方が復活していないこと。

    ここが緩むと、また 4 箇所が別々の日付を持つ状態に戻る。生成時刻の刻印
    (`generated_at` など) は対象日ではないので対象外。
    """
    src = (REPO / rel).read_text(encoding="utf-8")
    src = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))

    for pattern in (r"date\.today\(\)", r"datetime\.now\(\)\.date\(\)",
                    r"datetime\.today\(\)"):
        assert not re.search(pattern, src), (
            f"{rel} が独自に今日を作っている ({pattern})。"
            f"jst.current_jst_date / current_jst_daystamp を使うこと")


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
