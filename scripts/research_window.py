"""研究の経路だけに効く窓の関所 (docs/LOCKBOX_GOVERNANCE.md、外部の指示者の決定 2026-10-06)。

本番の封印 (`config.SEALED_FROM` / `config.guard_analysis_window`) とは別物。本番の予想・monitor・GUI・ai-builder はここを通らない。
研究の読み込み (`scripts.group_a.load_races` / `scripts.c_prime.load_races` と、これから作る候補の runner) は、読む期間と目的
(purpose) をここに通し、許されない組み合わせは例外で止める (黙って打ち切らない)。

期間 (日付 YYYYMMDD):
- development: `config.DATA_SPLIT["train"]["to"]` (20241231) まで。2021 の burn-in を含む
- consumed: validation の開始 (20250101) 〜 RESERVED_FROM の前日。既に結果を見た期間 (2025 の主検定 2 回・strategy_dev など)
- reserved: RESERVED_FROM 〜 FRESH_FROM の前日 (RESERVED_UNTOUCHED)。対象としてはどの目的でも読まない (fresh の対象の履歴としての読みは
  `check_history_for_fresh_targets`、開封の中だけ)。FRESH_FROM が未確定の間は RESERVED_FROM 以降をすべて reserved として扱う
- fresh: FRESH_FROM 以降
どの期間にも属さない日が出たら (定数の崩れ) 止める。

目的:
- development: development の期間だけ
- reproduce_consumed: development と consumed。凍結済みの runner の再現だけで、`reproduces` は REPRODUCIBLE_PURPOSES の完全一致に限る
  (新しい候補の 2025 の閲覧を自由記述で通さない)。通るたびに監査ログに 1 行追記し、書けなければ止める
- lockbox_count_only: fresh だけ、結果を読まない (`reads_outcomes=False`)。件数の点検だけ
- primary_after_unlock: 開封の手順 (候補の事前登録・錠・月末の点検) がまだ無いので、今は常に止める。最初の候補の事前登録と一緒に実装する

例外はすべて ResearchWindowError (日付の形式の誤りも包む)。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import config
from db import sql_evaluable_race

PURPOSES = ("development", "reproduce_consumed", "lockbox_count_only", "primary_after_unlock")
ALLOWED_PERIODS = {
    "development": frozenset({"development"}),
    "reproduce_consumed": frozenset({"development", "consumed"}),
    "lockbox_count_only": frozenset({"fresh"}),
}

# 主検定まで実行済みの runner (Group A / C′) が 2025 を読むときの目的の文字列 (完全一致、run_index 1 = 実行済みの 1 回だけ)。
# 新しい候補の 2025 の閲覧はここに足さない (足すなら config.CONSUMED_WINDOWS への記録と事前登録の開示が先、docs/LOCKBOX_GOVERNANCE.md §7)。
# Group D は主検定を実行せずに停止した (BLOCKED_BY_IDENTIFIABILITY) ので、D の runner の目的は入れない (D の runner は 2025 を読めない)
REPRODUCIBLE_PURPOSES = frozenset({
    "power: 2025 の過去走の時計を S の履歴として読む (対象レースの結果は対象の行に付けない)",
    "primary: Group A の主検定 (run_index 1)",
    "power: 2025 の対象日より前の走の脚質コードを履歴として読む (対象の行に結果を付けない)",
    "arm / primary の前の履歴の照合 (2025 の着順・オッズは SQL で NULL)",
    "primary: Group C′ の主検定 (run_index 1)",
})


class ResearchWindowError(RuntimeError):
    """研究の経路が、許されない期間・目的で読もうとした (または関所の前提が崩れている)。"""


def development_until() -> str:
    return config.data_split("train")[1]


def consumed_from() -> str:
    return config.data_split("validation")[0]


def _day(label: str, value) -> str:
    try:
        return config._require_daystamp(f"research_window: {label}", value)
    except ValueError as e:
        raise ResearchWindowError(str(e)) from None


def _shift(ymd: str, days: int) -> str:
    d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])) + timedelta(days=days)
    return d.strftime("%Y%m%d")


def consumed_until_before_reserved() -> str:
    """RESERVED_FROM より前に始まる消費済みの窓の最後の日。開封した fresh の窓を CONSUMED_WINDOWS に記録しても、関所の前提を崩さない。"""
    return max((w["to"] for w in config.CONSUMED_WINDOWS if w["from"] < config.RESERVED_FROM), default="00000000")


def check_constants() -> None:
    """定数の不変条件。崩れていたら研究の読み込みを一切通さない。"""
    dev_to = _day("development_until", development_until())
    cons_from = _day("consumed_from", consumed_from())
    reserved = _day("RESERVED_FROM", config.RESERVED_FROM)
    not_before = _day("FRESH_FROM_NOT_BEFORE", config.FRESH_FROM_NOT_BEFORE)
    if _shift(dev_to, 1) != cons_from:
        raise ResearchWindowError(f"development (〜{dev_to}) と consumed ({cons_from}〜) の間に隙間・重なりがある")
    if not cons_from < reserved < not_before:
        raise ResearchWindowError(f"期間の順序が崩れている: consumed {cons_from}〜 / reserved {reserved}〜 / fresh の下限 {not_before}")
    if reserved <= consumed_until_before_reserved():
        raise ResearchWindowError(f"RESERVED_FROM {reserved} が消費済みの最後の日 {consumed_until_before_reserved()} より後でない")
    if config.FRESH_FROM is not None and _day("FRESH_FROM", config.FRESH_FROM) < not_before:
        raise ResearchWindowError(f"FRESH_FROM {config.FRESH_FROM} が規則の下限 {not_before} より前")


def periods_spanned(from_date: str, to_date: str) -> frozenset[str]:
    """[from_date, to_date] が重なる期間の集合。"""
    f, t = _day("from_date", from_date), _day("to_date", to_date)
    if f > t:
        raise ResearchWindowError(f"from_date {f} > to_date {t}")
    check_constants()
    bounds = [("development", "00000101", development_until()),
              ("consumed", consumed_from(), _shift(config.RESERVED_FROM, -1))]
    if config.FRESH_FROM is None:
        bounds.append(("reserved", config.RESERVED_FROM, "99991231"))
    else:
        bounds += [("reserved", config.RESERVED_FROM, _shift(config.FRESH_FROM, -1)),
                   ("fresh", config.FRESH_FROM, "99991231")]
    periods = frozenset(name for name, lo, hi in bounds if f <= hi and t >= lo)
    if not periods:
        raise ResearchWindowError(f"{f}〜{t} がどの期間にも属さない (定数の崩れ)")
    return periods


def _log_access(record: dict) -> None:
    path = Path(config.RESEARCH_WINDOW_ACCESS_LOG)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({**record, "at": datetime.now().astimezone().isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
    except OSError as e:
        raise ResearchWindowError(f"監査ログに書けない ({path}): {e}。書けないなら読ませない") from None


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
            f"{context}: {from_date}〜{to_date} は RESERVED_UNTOUCHED ({config.RESERVED_FROM}〜) に重なる。対象としてはどの目的でも読まない"
            + (" (FRESH_FROM が未確定の間は RESERVED_FROM 以降をすべて読まない)" if config.FRESH_FROM is None else ""))
    if purpose == "primary_after_unlock":
        raise ResearchWindowError(f"{context}: 開封の手順はまだ無い (最初の候補の事前登録と一緒に実装する)")
    if purpose == "reproduce_consumed" and reproduces not in REPRODUCIBLE_PURPOSES:
        raise ResearchWindowError(f"{context}: reproduce_consumed の reproduces {reproduces!r} は凍結済みの runner の目的に無い "
                                  "(新しい候補の 2025 の閲覧はこの経路で通さない)")
    if purpose == "lockbox_count_only" and reads_outcomes:
        raise ResearchWindowError(f"{context}: lockbox_count_only は結果を読まない (reads_outcomes=False)")
    bad = periods - ALLOWED_PERIODS[purpose]
    if bad:
        raise ResearchWindowError(f"{context}: purpose {purpose!r} では {sorted(bad)} の期間を読まない ({from_date}〜{to_date})")
    record = {"purpose": purpose, "from": from_date, "to": to_date, "periods": sorted(periods), "context": context,
              "reads_outcomes": reads_outcomes, "reproduces": reproduces, "reserved_from": config.RESERVED_FROM,
              "fresh_from": config.FRESH_FROM, "governance": "docs/LOCKBOX_GOVERNANCE.md"}
    if purpose != "development":
        _log_access(record)
    return record


def check_years(min_year: int, max_year: int, *, purpose: str, context: str, **kw) -> dict:
    return check(f"{min_year}0101", f"{max_year}1231", purpose=purpose, context=context, **kw)


# ------------------------------------------------------------------------------------------- 履歴としてだけの読み (§9 の改訂)

HISTORY_LOOKBACK_DAYS = frozenset({365})          # 事前に固定した参照日数 (A″ は Group A と同じ 365 日、テストで group_a.WINDOW_DAYS と照合)
# 市場の情報 (オッズ・払戻・人気・票数) の列名の断片と、それだけを持つ表。件数の SQL と履歴の列の両方がここを使う (単一の出典)。
# data/schema.sql の全列に対する照合はテストで行う
MARKET_FRAGMENTS = ("odds", "payout", "_pop", "popularity", "vote")
MARKET_TABLES = frozenset({"payouts", "exotic_odds", "vote_counts", "odds_snapshots", "win5", "win5_payouts"})


def check_history_for_fresh_targets(target_from: str, target_to: str, *, lookback_days: int, history_columns: tuple[str, ...],
                                    context: str) -> dict:
    """fresh の対象の特徴を作るために、対象より前の履歴 (consumed・reserved・それ以前の fresh を含む) を読む許可 (§9 の改訂)。

    条件: 対象がすべて fresh / 履歴の窓は [最初の対象日 − 参照日数, 最後の対象日 − 1 日] (期間の粗い上界。**対象ごとの
    history_date < target_date は特徴の作り手の要件** で、開封の手順の実装のときに単体テストで強制する) / 参照日数は
    HISTORY_LOOKBACK_DAYS / 履歴の列は呼び出し側が「表.列」で渡し、市場の表とオッズ・払戻・人気・票数の列を含めない
    (候補の固定の allow-list は事前登録で定める)。監査ログは開封の手順の実装のときに結び付ける。**主検定の開封の中からだけ** 呼ぶ — 開封の手順 (primary_after_unlock) が
    まだ無いので、条件を確かめた後に常に止まる。開封の手順を実装するときに、ここを開封の記録 (錠・開始の印) と結び付ける。
    """
    if not context:
        raise ResearchWindowError("context (どの読み込みか) を書く")
    periods = periods_spanned(target_from, target_to)
    if periods != {"fresh"}:
        raise ResearchWindowError(f"{context}: 履歴としてだけの読みは、対象がすべて fresh のときだけ (対象 {target_from}〜{target_to}: {sorted(periods)})")
    if type(lookback_days) is not int or lookback_days not in HISTORY_LOOKBACK_DAYS:
        raise ResearchWindowError(f"{context}: 参照日数 {lookback_days!r} は事前に固定した値 {sorted(HISTORY_LOOKBACK_DAYS)} に無い")
    cols = tuple(history_columns)
    if not cols or not all(isinstance(c, str) and c for c in cols):
        raise ResearchWindowError(f"{context}: 履歴の列の allow-list (表.列) を渡す")
    malformed = [c for c in cols if len(c.split(".")) != 2 or not all(c.split(".")) or "*" in c]
    if malformed:
        raise ResearchWindowError(f"{context}: 履歴の列は「表.列」で渡す: {malformed}")
    bad = [c for c in cols if c.split(".")[0].lower() in MARKET_TABLES
           or any(f in c.split(".")[1].lower() for f in MARKET_FRAGMENTS)]
    if bad:
        raise ResearchWindowError(f"{context}: 履歴の列にオッズ・払戻・人気・票数を含めない: {bad}")
    history_from, history_to = _shift(target_from, -lookback_days), _shift(target_to, -1)
    raise ResearchWindowError(
        f"{context}: 履歴としてだけの読み ({history_from}〜{history_to}) は主検定の開封の中からだけ呼ぶ。開封の手順 (primary_after_unlock) は"
        "まだ無い (最初の候補の事前登録と一緒に実装する)")


# ------------------------------------------------------------------------------------------- 件数の点検 (lockbox_count_only)

# JV-Data の競馬場コード 01〜10 が JRA (11 以降は地方・海外)。track_type_code 51 以上が障害 (`scripts.group_a.OBSTACLE_FROM` と同じ)
JRA_TRACK_SQL = "CAST(r.track_code AS INTEGER) BETWEEN 1 AND 10"
OBSTACLE_FROM = 51
COUNT_SELECT = (
    ("r.race_year", "race_year"), ("r.race_month_day", "race_month_day"), ("r.track_code", "track_code"),
    ("r.kaiji", "kaiji"), ("r.nichiji", "nichiji"), ("r.race_num", "race_num"), ("r.track_type_code", "track_type_code"),
    ("r.data_div", "data_div"),
)
COUNT_COLUMNS = tuple(alias for _, alias in COUNT_SELECT)
# 結果・払戻・オッズ・発走後に決まる races の列 (前後半の時計・頭数・天候・馬場状態) に当たる列名の断片。件数の SQL に 1 つでも含めたら止める
OUTCOME_FRAGMENTS = ("confirmed_order", "finish", "time_diff", "corner", "final_3f", "3f_time", "4f_time", "same_finish",
                     "starter_count", "weather", "condition", "win_", "place_", "lap")
FORBIDDEN_FRAGMENTS = OUTCOME_FRAGMENTS + MARKET_FRAGMENTS + tuple(sorted(MARKET_TABLES)) + ("horse_races", "*")
CONFIRMED_DATA_DIV = "7"


def count_sql() -> str:
    sql = (f"SELECT {', '.join(f'{expr} AS {alias}' for expr, alias in COUNT_SELECT)} FROM races r "
           f"WHERE (r.race_year || r.race_month_day) BETWEEN ? AND ? AND {JRA_TRACK_SQL} AND {sql_evaluable_race('r.data_div')} "
           "ORDER BY 1, 2, 3, 6")
    low = sql.lower()
    bad = [f for f in FORBIDDEN_FRAGMENTS if f in low]
    if bad:
        raise ResearchWindowError(f"件数の SQL に結果の列が入っている: {bad}")
    return sql


def count_fresh_races(db_path: Path | str, from_date: str, to_date: str, *, context: str) -> dict:
    """新しい窓の対象レース数 (JRA 01〜10・平地・中止を除く) を、結果の列を読まずに数える。

    確定 (data_div 7) と未確定 (発走前の 1/2 など) を分けて返す。開封の点検の件数は確定だけ (docs/LOCKBOX_GOVERNANCE.md §4)。
    """
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
    unknown = [r for r in rows if not str(r[6] or "").strip().isdigit()]
    if unknown:
        raise ResearchWindowError(f"track_type_code が不明の行がある (平地か障害か判定できない): {[r[:6] for r in unknown[:5]]}")
    by_day: dict[str, dict[str, int]] = {}
    for r in rows:
        if int(r[6]) >= OBSTACLE_FROM:
            continue
        cell = by_day.setdefault(f"{r[0]}{r[1]}", {"confirmed": 0, "pending": 0})
        cell["confirmed" if r[7] == CONFIRMED_DATA_DIV else "pending"] += 1
    return {"n_confirmed": sum(c["confirmed"] for c in by_day.values()),
            "n_pending": sum(c["pending"] for c in by_day.values()), "by_day": by_day, "window": record}


# ------------------------------------------------------------------------------------------- FRESH_FROM の確定 (§2)

SCHEDULE_SELECT = "MIN(s.race_year || s.race_month_day)"
SCHEDULE_COLUMNS = ("first_day",)


def schedule_sql() -> str:
    """開催スケジュール (YS、`schedules`) だけを読む。結果の列は持たない表。"""
    sql = (f"SELECT {SCHEDULE_SELECT} AS first_day FROM schedules s "
           "WHERE (s.race_year || s.race_month_day) >= ? AND CAST(s.track_code AS INTEGER) BETWEEN 1 AND 10")
    low = sql.lower()
    bad = [f for f in FORBIDDEN_FRAGMENTS if f in low]
    if bad:
        raise ResearchWindowError(f"開催日の SQL に結果の列が入っている: {bad}")
    return sql


def determine_fresh_from(db_path: Path | str) -> dict:
    """規則 (§2) どおり FRESH_FROM を決める: FRESH_FROM_NOT_BEFORE 以降で最初の JRA の開催日 (年間の開催スケジュールで)。

    結果は読まない。中止・順延で実際の開催がずれても、ここで決まった日を境界として保つ (§2)。来歴として返す。
    """
    not_before = _day("FRESH_FROM_NOT_BEFORE", config.FRESH_FROM_NOT_BEFORE)
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        cur = conn.execute(schedule_sql(), (not_before,))
        names = tuple(d[0] for d in cur.description)
        if names != SCHEDULE_COLUMNS:
            raise ResearchWindowError(f"開催日の SQL の返る列が allow-list と違う: {names}")
        (first,) = cur.fetchone()
        rows = conn.execute("SELECT track_code, data_div, data_created FROM schedules WHERE (race_year || race_month_day) = ? "
                            "AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10 ORDER BY 1", (first,)).fetchall() if first else []
    finally:
        conn.close()
    if first is None:
        raise ResearchWindowError(f"{not_before} 以降の JRA の開催日が開催スケジュールに無い")
    first = _day("first_day", first)
    out = {"fresh_from": first, "not_before": not_before, "source": "schedules (YS)",
           "schedule_data_created": max(r[2] for r in rows), "schedule_rows": [list(r) for r in rows],
           "sql": schedule_sql(), "governance_commit": config.FRESH_GOVERNANCE_COMMIT}
    _log_access({"purpose": "determine_fresh_from", "context": "research_window.determine_fresh_from", **out})
    return out
