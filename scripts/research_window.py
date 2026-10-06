"""研究の経路だけに効く窓の関所 (docs/LOCKBOX_GOVERNANCE.md、外部の指示者の決定 2026-10-06)。

本番の封印 (`config.SEALED_FROM` / `config.guard_analysis_window`) とは別物。本番の予想・monitor・GUI・ai-builder はここを通らない。
研究の読み込み (`scripts.group_a.load_races` / `scripts.c_prime.load_races` と、これから作る候補の runner) は、読む期間と目的
(purpose) をここに通し、許されない組み合わせは例外で止める (黙って打ち切らない)。

期間 (日付 YYYYMMDD):
- development: `config.DATA_SPLIT["train"]["to"]` (20241231) まで。2021 の burn-in を含む
- consumed: 2025-01-01 〜 RESERVED_FROM の前日。既に結果を見た期間 (2025 の主検定 2 回・strategy_dev など)
- reserved: RESERVED_FROM 〜 FRESH_FROM の前日 (RESERVED_UNTOUCHED)。どの目的でも読まない。FRESH_FROM が未確定の間は
  RESERVED_FROM 以降をすべて reserved として扱う
- fresh: FRESH_FROM 以降

目的:
- development: development の期間だけ
- reproduce_consumed: development と consumed (過去の成果物の再現。`reproduces` に何を再現するかを書く)。新しい候補の仕様の選択には使わない
- lockbox_count_only: fresh だけ、結果を読まない (`reads_outcomes=False`)。件数の点検だけ
- primary_after_unlock: 開封の手順 (候補の事前登録・錠・月末の点検) がまだ無いので、今は常に止める。最初の候補の事前登録と一緒に実装する
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import config

PURPOSES = ("development", "reproduce_consumed", "lockbox_count_only", "primary_after_unlock")
CONSUMED_FROM = "20250101"
ALLOWED_PERIODS = {
    "development": frozenset({"development"}),
    "reproduce_consumed": frozenset({"development", "consumed"}),
    "lockbox_count_only": frozenset({"fresh"}),
}


class ResearchWindowError(RuntimeError):
    """研究の経路が、許されない期間・目的で読もうとした。"""


def development_until() -> str:
    return config.DATA_SPLIT["train"]["to"]


def _day(label: str, value) -> str:
    return config._require_daystamp(f"research_window: {label}", value)


def _prev_day(ymd: str) -> str:
    d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])) - timedelta(days=1)
    return d.strftime("%Y%m%d")


def check_constants() -> None:
    """定数の不変条件。崩れていたら研究の読み込みを一切通さない。"""
    dev_to = development_until()
    reserved = _day("RESERVED_FROM", config.RESERVED_FROM)
    if not dev_to < CONSUMED_FROM <= reserved:
        raise ResearchWindowError(f"期間の順序が崩れている: development〜{dev_to} / consumed {CONSUMED_FROM}〜 / reserved {reserved}〜")
    if reserved <= config.consumed_until():
        raise ResearchWindowError(f"RESERVED_FROM {reserved} が消費済みの最後の日 {config.consumed_until()} より後でない")
    if config.FRESH_FROM is not None:
        fresh = _day("FRESH_FROM", config.FRESH_FROM)
        if fresh < _day("FRESH_FROM_NOT_BEFORE", config.FRESH_FROM_NOT_BEFORE):
            raise ResearchWindowError(f"FRESH_FROM {fresh} が規則の下限 {config.FRESH_FROM_NOT_BEFORE} より前")


def periods_spanned(from_date: str, to_date: str) -> frozenset[str]:
    """[from_date, to_date] が重なる期間の集合。"""
    f, t = _day("from_date", from_date), _day("to_date", to_date)
    if f > t:
        raise ResearchWindowError(f"from_date {f} > to_date {t}")
    check_constants()
    bounds = [("development", "00000101", development_until()),
              ("consumed", CONSUMED_FROM, _prev_day(config.RESERVED_FROM))]
    if config.FRESH_FROM is None:
        bounds.append(("reserved", config.RESERVED_FROM, "99991231"))
    else:
        bounds += [("reserved", config.RESERVED_FROM, _prev_day(config.FRESH_FROM)),
                   ("fresh", config.FRESH_FROM, "99991231")]
    return frozenset(name for name, lo, hi in bounds if f <= hi and t >= lo)


def check(from_date: str, to_date: str, *, purpose: str, context: str, reads_outcomes: bool = True,
          reproduces: str | None = None) -> dict:
    """研究の読み込みの前に呼ぶ。許されなければ ResearchWindowError。戻り値は成果物の来歴に残す記録。"""
    if purpose not in PURPOSES:
        raise ResearchWindowError(f"未知の purpose {purpose!r} (使えるのは {PURPOSES})")
    if not context:
        raise ResearchWindowError("context (どの読み込みか) を書く")
    periods = periods_spanned(from_date, to_date)
    if "reserved" in periods:
        raise ResearchWindowError(
            f"{context}: {from_date}〜{to_date} は RESERVED_UNTOUCHED ({config.RESERVED_FROM}〜) に重なる。どの目的でも読まない"
            + (" (FRESH_FROM が未確定の間は RESERVED_FROM 以降をすべて読まない)" if config.FRESH_FROM is None else ""))
    if purpose == "primary_after_unlock":
        raise ResearchWindowError(f"{context}: 開封の手順はまだ無い (最初の候補の事前登録と一緒に実装する)")
    if purpose == "reproduce_consumed" and not reproduces:
        raise ResearchWindowError(f"{context}: reproduce_consumed では reproduces (再現する成果物) を書く")
    if purpose == "lockbox_count_only" and reads_outcomes:
        raise ResearchWindowError(f"{context}: lockbox_count_only は結果を読まない (reads_outcomes=False)")
    bad = periods - ALLOWED_PERIODS[purpose]
    if bad:
        raise ResearchWindowError(f"{context}: purpose {purpose!r} では {sorted(bad)} の期間を読まない ({from_date}〜{to_date})")
    return {"purpose": purpose, "from": from_date, "to": to_date, "periods": sorted(periods), "context": context,
            "reads_outcomes": reads_outcomes, "reproduces": reproduces, "reserved_from": config.RESERVED_FROM,
            "fresh_from": config.FRESH_FROM, "governance": "docs/LOCKBOX_GOVERNANCE.md"}


def check_years(min_year: int, max_year: int, *, purpose: str, context: str, **kw) -> dict:
    return check(f"{min_year}0101", f"{max_year}1231", purpose=purpose, context=context, **kw)


# ------------------------------------------------------------------------------------------- 件数の点検 (lockbox_count_only)

COUNT_SELECT = (
    ("r.race_year", "race_year"), ("r.race_month_day", "race_month_day"), ("r.track_code", "track_code"),
    ("r.kaiji", "kaiji"), ("r.nichiji", "nichiji"), ("r.race_num", "race_num"), ("r.track_type_code", "track_type_code"),
)
COUNT_COLUMNS = tuple(alias for _, alias in COUNT_SELECT)
# races / horse_races の結果・払戻・確定のオッズに当たる列名の断片。件数の SQL に 1 つでも含めたら止める
FORBIDDEN_FRAGMENTS = ("confirmed_order", "finish", "time_diff", "corner", "final_3f", "same_finish", "odds", "payout",
                       "pay_", "popularity", "win_", "place_", "lap", "dividend", "horse_races", "payouts", "*")
OBSTACLE_FROM = 51


def count_sql() -> str:
    sql = (f"SELECT {', '.join(f'{expr} AS {alias}' for expr, alias in COUNT_SELECT)} FROM races r "
           "WHERE (r.race_year || r.race_month_day) BETWEEN ? AND ? "
           "AND CAST(r.track_code AS INTEGER) BETWEEN 1 AND 10 AND r.data_div <> '9' "
           "ORDER BY 1, 2, 3, 6")
    low = sql.lower()
    bad = [f for f in FORBIDDEN_FRAGMENTS if f in low]
    if bad:
        raise ResearchWindowError(f"件数の SQL に結果の列が入っている: {bad}")
    return sql


def count_fresh_races(db_path: Path | str, from_date: str, to_date: str, *, context: str) -> dict:
    """新しい窓の対象レース数 (JRA 01〜10・平地・中止 (data_div 9) を除く) を、結果の列を読まずに数える。"""
    record = check(from_date, to_date, purpose="lockbox_count_only", context=context, reads_outcomes=False)
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        cur = conn.execute(count_sql(), (from_date, to_date))
        names = tuple(d[0] for d in cur.description)
        if names != COUNT_COLUMNS:
            raise ResearchWindowError(f"件数の SQL の返る列が allow-list と違う: {names}")
        rows = cur.fetchall()
    finally:
        conn.close()
    flat = [r for r in rows if int(r[6] or 0) < OBSTACLE_FROM]
    by_day: dict[str, int] = {}
    for r in flat:
        by_day[f"{r[0]}{r[1]}"] = by_day.get(f"{r[0]}{r[1]}", 0) + 1
    return {"n_flat_races": len(flat), "by_day": by_day, "window": record}
