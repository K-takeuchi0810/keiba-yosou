"""fresh odds 取得 coverage の後追い集計。

scripts/fetch_fresh_odds.py が 10 分おきに append している JSONL
(data/logs/fresh_odds_coverage.jsonl) を読み、開催日別の取得成功率と
失敗理由を一覧表示する。

P25 Plan Step 4 (2026-06-17 外部レビュー追記) の「fresh odds 取得の安定稼働確認」
完了条件を満たしているかを検証するための監視用スクリプト。

usage:
    python -m scripts.fresh_odds_coverage              # 全期間
    python -m scripts.fresh_odds_coverage --last 14    # 直近 14 日
    python -m scripts.fresh_odds_coverage --date 20260620

出力:
    対象日: 2026-06-20
      起動回数:        45
      eligible races:  142 (中央値 4 / 起動、p90 8)
      fetched races:   138 (97.2%)
      ingested rate:   97.2%
      ok rate:         96.5%
      失敗理由:        TimeoutError=2, ComError=3
      鮮度 (p50/p90):  8min / 22min
      compute_total_records: 1,820
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from db import open_db_readonly


COVERAGE_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "logs" / "fresh_odds_coverage.jsonl"
GAP_WINDOW_START = (9, 0)
GAP_WINDOW_END = (16, 40)
GAP_THRESHOLD_MINUTES = 15


def _notify_warnings(warnings: list[str]) -> None:
    """Send detailed gap warnings without changing the monitor exit code."""
    try:
        from scripts.notify_discord import notify_discord

        for warning in warnings:
            notify_discord(warning)
    except Exception as exc:  # noqa: BLE001 - monitoring must remain best effort
        print(f"WARN: fresh odds notification failed: {exc}", file=sys.stderr)


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _filter_records(records: list[dict], *, last_days: int | None, target_date: str | None) -> list[dict]:
    if target_date:
        return [r for r in records if r.get("target_date") == target_date]
    if last_days is not None:
        cutoff = (datetime.now() - timedelta(days=last_days)).strftime("%Y%m%d")
        return [r for r in records if (r.get("target_date") or "") >= cutoff]
    return list(records)


def _group_by_date(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        grouped[r.get("target_date") or "?"].append(r)
    return dict(sorted(grouped.items()))


def _find_run_gaps(
    date_records: list[dict], threshold_minutes: int = GAP_THRESHOLD_MINUTES,
    *, target_date: str | None = None, now: datetime | None = None,
) -> list[tuple[datetime, datetime, int]]:
    run_times: list[datetime] = []
    for record in date_records:
        raw = record.get("run_at")
        if not raw:
            continue
        try:
            run_at = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        hhmm = (run_at.hour, run_at.minute)
        if GAP_WINDOW_START <= hhmm <= GAP_WINDOW_END:
            run_times.append(run_at)
    run_times.sort()

    date_key = target_date
    if not date_key and date_records:
        date_key = date_records[0].get("target_date")
    if not date_key and run_times:
        date_key = run_times[0].strftime("%Y%m%d")
    if not date_key:
        return []

    day = datetime.strptime(date_key, "%Y%m%d")
    tzinfo = run_times[0].tzinfo if run_times else None
    window_start = day.replace(
        hour=GAP_WINDOW_START[0], minute=GAP_WINDOW_START[1], tzinfo=tzinfo
    )
    window_end = day.replace(
        hour=GAP_WINDOW_END[0], minute=GAP_WINDOW_END[1], tzinfo=tzinfo
    )
    current = now or datetime.now(tz=tzinfo)
    if current.date() == day.date():
        window_end = min(window_end, current.replace(second=0, microsecond=0))
    elif current.date() < day.date():
        return []

    # Window boundaries are virtual runs so missing first/last fetches are visible.
    run_times = [window_start, *run_times, window_end]

    gaps: list[tuple[datetime, datetime, int]] = []
    threshold_seconds = threshold_minutes * 60
    for previous, current in zip(run_times, run_times[1:]):
        seconds = (current - previous).total_seconds()
        if seconds > threshold_seconds:
            gaps.append((previous, current, int(seconds // 60)))
    return gaps


def _requested_date_range(
    records: list[dict], *, last_days: int | None, target_date: str | None
) -> tuple[str, str] | None:
    if target_date:
        return target_date, target_date
    if last_days is not None:
        return (
            (datetime.now() - timedelta(days=last_days)).strftime("%Y%m%d"),
            datetime.now().strftime("%Y%m%d"),
        )
    dates = sorted(r.get("target_date") for r in records if r.get("target_date"))
    return (dates[0], dates[-1]) if dates else None


def _load_open_dates(
    start_date: str, end_date: str, coverage_records: list[dict] | None = None
) -> set[str]:
    """Return JRA race dates so a fetcher that emitted zero logs is still detected."""
    with open_db_readonly() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT race_year || race_month_day AS race_date
              FROM races
             WHERE track_code BETWEEN '01' AND '10'
               AND (race_year || race_month_day) BETWEEN ? AND ?
            """,
            (start_date, end_date),
        ).fetchall()
    dates = {str(row[0]) for row in rows}
    # If morning race ingestion failed, races may be empty even though an earlier
    # coverage heartbeat had eligible races. Treat that as an open-day signal.
    for record in coverage_records or []:
        date = str(record.get("target_date") or "")
        if start_date <= date <= end_date and int(record.get("eligible_races") or 0) > 0:
            dates.add(date)
    return dates


def _aggregate(date_records: list[dict]) -> dict:
    """1 開催日分の起動ログを集計し、coverage 指標 dict を返す。"""
    runs = len(date_records)
    eligible_per_run = [int(r.get("eligible_races") or 0) for r in date_records]
    fetched_per_run = [int(r.get("fetched_races") or 0) for r in date_records]
    ok_per_run = [int(r.get("ok_races") or 0) for r in date_records]
    error_per_run = [int(r.get("error_races") or 0) for r in date_records]
    total_records = sum(int(r.get("total_records") or 0) for r in date_records)
    failed_reasons: Counter[str] = Counter()
    for r in date_records:
        for k, v in (r.get("failed_reason") or {}).items():
            failed_reasons[k] += int(v)
    lock_skipped = sum(1 for r in date_records if r.get("lock_skipped"))

    def pct(num: int, den: int) -> float:
        return (num / den * 100) if den > 0 else 0.0

    total_eligible = sum(eligible_per_run)
    total_fetched = sum(fetched_per_run)
    total_ok = sum(ok_per_run)
    return {
        "runs": runs,
        "lock_skipped": lock_skipped,
        "eligible_total": total_eligible,
        "eligible_p50": int(statistics.median(eligible_per_run)) if eligible_per_run else 0,
        "eligible_p90": int(_p90(eligible_per_run)) if eligible_per_run else 0,
        "fetched_total": total_fetched,
        "fetched_rate_pct": round(pct(total_fetched, total_eligible), 1),
        "ok_total": total_ok,
        "ok_rate_pct": round(pct(total_ok, total_eligible), 1),
        "error_total": sum(error_per_run),
        "total_records": total_records,
        "failed_reasons": dict(failed_reasons),
    }


def _p90(values: list[int]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, int(round(0.9 * (len(sorted_vals) - 1))))
    return float(sorted_vals[idx])


def _print_report(grouped: dict[str, list[dict]]) -> None:
    if not grouped:
        print("(no coverage records)")
        return
    print(f"date          runs  eligible  fetched  ok%   total_records  failed_reasons")
    print(f"-" * 90)
    for date, recs in grouped.items():
        agg = _aggregate(recs)
        reasons = ",".join(f"{k}={v}" for k, v in agg["failed_reasons"].items()) or "-"
        print(
            f"{date:<10}  {agg['runs']:>5}  {agg['eligible_total']:>8}  "
            f"{agg['fetched_total']:>7}  {agg['ok_rate_pct']:>5.1f}  "
            f"{agg['total_records']:>13,}  {reasons}"
        )

    # 全体サマリ + Plan 完了条件チェック (popularity_bonus_candidate_horses ≥ 500 馬
    # or races ≥ 150 は本スクリプトでは観測できない。ここでは「実取得 race 数」までを
    # 出し、補正候補数は backtest 側の market_snapshot で検証する仕様。)
    all_recs = [r for recs in grouped.values() for r in recs]
    total_agg = _aggregate(all_recs)
    print()
    print(f"合計起動: {total_agg['runs']} 回 (lock_skipped={total_agg['lock_skipped']})")
    print(f"  eligible races (累計): {total_agg['eligible_total']}")
    print(f"  fetched races (累計):  {total_agg['fetched_total']}  ({total_agg['fetched_rate_pct']}%)")
    print(f"  ok races (累計):       {total_agg['ok_total']}  ({total_agg['ok_rate_pct']}%)")
    print(f"  total records (累計):  {total_agg['total_records']:,}")
    if total_agg['failed_reasons']:
        print(f"  failed reasons:        {total_agg['failed_reasons']}")
    # Plan 完了条件の参考表示 (実 race 数で間接的に評価)
    expected_per_day = 36  # 1 開催日あたり最大 race 数 (Plan の期待値計算より)
    open_days = len(grouped)
    expected_eligible = expected_per_day * open_days
    if expected_eligible:
        ratio = total_agg['eligible_total'] / expected_eligible
        print(f"\nPlan Step 4 参考: eligible races / 期待値 ({expected_per_day}×{open_days}={expected_eligible}) "
              f"= {ratio:.2f}")
        if total_agg['ok_rate_pct'] < 80.0:
            print("  WARN: ok_rate が 80% 未満。スケジューラ稼働 / JV-Link 認証 / "
                  "コンテキスト manager 漏れ等を確認してください。")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--last", type=int, default=None, help="直近 N 日分のみ集計")
    ap.add_argument("--date", default=None, help="特定の target_date (YYYYMMDD) のみ")
    ap.add_argument("--path", default=None, help="coverage JSONL のパス (デフォルト data/logs/fresh_odds_coverage.jsonl)")
    ap.add_argument(
        "--check-gaps", action="store_true",
        help="開催日の9:00〜16:40でrun間隔が15分超なら警告してexit 1",
    )
    ap.add_argument(
        "--notify", action="store_true",
        help="gap警告の詳細をDiscordへbest-effort送信",
    )
    args = ap.parse_args()
    path = Path(args.path) if args.path else COVERAGE_LOG_PATH
    records = _load_records(path)
    if not records and not args.check_gaps:
        print(f"(no coverage records at {path})")
        return 0
    filtered = _filter_records(records, last_days=args.last, target_date=args.date)
    grouped = _group_by_date(filtered)
    gap_grouped = grouped
    if args.check_gaps:
        requested = _requested_date_range(
            records, last_days=args.last, target_date=args.date
        )
        if requested:
            open_dates = _load_open_dates(*requested, records)
            # Coverage logs also contain non-race-day scheduler heartbeats. They
            # must stay in the normal report but are outside the gap canary.
            gap_grouped = {
                open_date: grouped.get(open_date, [])
                for open_date in sorted(open_dates)
            }
    _print_report(grouped)
    if args.check_gaps:
        found_gap = False
        warnings = []
        for date, date_records in gap_grouped.items():
            gaps = _find_run_gaps(date_records, target_date=date)
            for previous, current, minutes in gaps:
                found_gap = True
                if not any(record.get("run_at") for record in date_records):
                    warning = (
                        f"WARNING: all runs missing {date[:4]}-{date[4:6]}-{date[6:]} "
                        f"({previous:%H:%M}->{current:%H:%M}, {minutes}m)"
                    )
                else:
                    warning = (
                        f"WARNING: gap {date[:4]}-{date[4:6]}-{date[6:]} "
                        f"{previous:%H:%M}->{current:%H:%M} ({minutes}m)"
                    )
                print(warning)
                warnings.append(warning)
        if found_gap:
            if args.notify:
                _notify_warnings(warnings)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
