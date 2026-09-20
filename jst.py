"""「今日」を決める唯一の場所 (2026-09-20)。

## なぜ 1 箇所にまとめるのか

以前は 4 箇所がそれぞれ独自に日付を作っていた。

    scripts/auto_predict.py      date.today()            ← 生成対象日
    scripts/notify_dedup.py      datetime.now(JST)       ← 重複判定の対象日
    web/generator.py             datetime.now().date()   ← 既定の生成窓
    scripts/auto_predict_daily.bat  date.today()         ← ログのファイル名

このうち JST を明示していたのは重複判定だけで、残りはシステムのローカル時刻
任せだった。いまは JST の機械なので実害は出ていないが、**同じ 1 回の起動の中で
「今日」が 2 通り存在しうる**状態で、境界をまたいだ瞬間に「対象日は 9/20 なのに
通知の記録は 9/21」のような食い違いが起きる。予想を出す日そのものを決める値なので、
ずれたら 1 日ぶんの予想を落とす。

## 使い方

    from jst import current_jst_date, current_jst_daystamp

    day = current_jst_daystamp()          # "20260920"
    d   = current_jst_date()              # date(2026, 9, 20)

## now を注入できること

`datetime.now()` を関数の内部で直接読むと、境界のテストが「実行した時刻に依存する」
脆いものになる。**必ず `now` を引数で渡せる形にしておく**。

    current_jst_daystamp(now=datetime(2026, 9, 20, 14, 59, 59, tzinfo=timezone.utc))
    -> "20260920"
    current_jst_daystamp(now=datetime(2026, 9, 20, 15,  0,  0, tzinfo=timezone.utc))
    -> "20260921"

`now` には **tz 付きの datetime だけ**を受け付ける。naive を黙って受けると、
それが UTC なのかローカルなのか呼び出し側にしか分からず、取り違えても誰も
気付けない。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

#: 日本標準時。夏時間は無いので固定オフセットで足りる。
JST = timezone(timedelta(hours=9), "JST")


def current_jst_datetime(now: datetime | None = None) -> datetime:
    """JST の現在時刻。`now` を渡せば固定できる。

    `now` を省略すると UTC の現在時刻を採る。**システムのローカル時刻は
    読まない** (OS が UTC でも JST でも同じ答えになるように)。
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError(
            "now には tz 付きの datetime を渡してください。naive だと UTC か "
            "ローカルかが呼び出し側にしか分からず、取り違えても気付けません。")
    return now.astimezone(JST)


def current_jst_date(now: datetime | None = None) -> date:
    """JST の今日。"""
    return current_jst_datetime(now).date()


def current_jst_daystamp(now: datetime | None = None) -> str:
    """JST の今日を YYYYMMDD で。DB のキーやファイル名に使う形。"""
    return current_jst_datetime(now).strftime("%Y%m%d")
