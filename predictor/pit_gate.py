"""F3 PIT ゲート: 市場スナップショットの point-in-time フィルタ (唯一の出典)。

規律 (docs/F3_MARKET_RESIDUAL_DESIGN.md, 2026-07-03 ユーザ確定):
- 市場オッズ/票数を特徴に使ってよいのは
  「fetched_at が非 NULL かつ fetched_at ≤ 発走時刻 − PIT_GATE_MINUTES」のスナップのみ。
- NULL fetched_at (= 確定オッズ = 発走後) は市場特徴に**使用禁止**。
- backtest と live は必ず本モジュールを通す (直接 SQL で odds_snapshots を特徴用に
  読むことを禁止)。expert-review 降格宣言(2): ゲートを通さない参照は即 FAIL。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from config import PIT_GATE_MINUTES


def pit_cutoff(race_date: str, start_time: str, gate_minutes: int | None = None) -> str | None:
    """発走時刻 − gate 分の ISO8601 カットオフを返す。start_time 不明なら None (=使用不可)。

    race_date: YYYYMMDD, start_time: HHMM (races.start_time)。
    """
    raw = (start_time or "").strip()
    if not raw:  # 空を zfill すると "0000" (0時) に化けて前日カットオフを返してしまう
        return None
    st = raw.zfill(4)
    if len(race_date) != 8 or len(st) != 4 or not (race_date + st).isdigit():
        return None
    minutes = PIT_GATE_MINUTES if gate_minutes is None else gate_minutes
    start = datetime(int(race_date[:4]), int(race_date[4:6]), int(race_date[6:8]),
                     int(st[:2]), int(st[2:]))
    return (start - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def usable_snapshots(
    conn: sqlite3.Connection,
    race: dict,
    gate_minutes: int | None = None,
) -> list[dict]:
    """レースの PIT 適格スナップショットを時刻昇順で返す (特徴計算の唯一の入口)。

    - fetched_at IS NULL (確定=発走後) は SQL レベルで除外。
    - fetched_at > 発走 − gate 分 も除外。
    - start_time 不明レースは空 (安全側: 特徴は欠損になる)。
    """
    cutoff = pit_cutoff(
        f"{race.get('race_year','')}{race.get('race_month_day','')}",
        race.get("start_time") or "",
        gate_minutes,
    )
    if cutoff is None:
        return []
    rows = conn.execute(
        """
        SELECT horse_num, fetched_at, win_odds, win_popularity, source
          FROM odds_snapshots
         WHERE race_year=? AND race_month_day=? AND track_code=?
           AND kaiji=? AND nichiji=? AND race_num=?
           AND fetched_at IS NOT NULL
           AND fetched_at <= ?
         ORDER BY fetched_at ASC
        """,
        (race.get("race_year"), race.get("race_month_day"), race.get("track_code"),
         race.get("kaiji"), race.get("nichiji"), race.get("race_num"), cutoff),
    ).fetchall()
    return [dict(r) for r in rows]
