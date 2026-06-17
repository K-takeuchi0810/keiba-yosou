"""発走直前のレースだけオッズを再取得し、fresh snapshot を確保する。

usage (32bit Python 必須):
    .venv32\\Scripts\\python.exe -m scripts.fetch_fresh_odds
    .venv32\\Scripts\\python.exe -m scripts.fetch_fresh_odds --window 20
    .venv32\\Scripts\\python.exe -m scripts.fetch_fresh_odds --dry-run

Windows Task Scheduler で 10 分おきに実行すると、各レースが発走前に
少なくとも 1 回は fresh odds を取得できる。

  schtasks /create /tn "keiba-fresh-odds" /tr ^
    "C:\\Users\\kizun\\dev\\keiba-yosou\\scripts\\fetch_fresh_odds.bat" ^
    /sc minute /mo 10 /st 09:00 /et 16:40 ^
    /sd 2026/06/20 /f
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from jvlink_client import JVLinkClient
from jvlink_client.ingest import ingest_all

ROOT_DIR = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT_DIR / "data" / "logs" / "fetch_fresh_odds.lock"


@contextmanager
def single_run_lock(max_age_sec: int = 30 * 60):
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - LOCK_PATH.stat().st_mtime
        except OSError:
            age = 0
        if age > max_age_sec:
            try:
                LOCK_PATH.unlink()
                fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except OSError:
                print(f"  another fetch_fresh_odds run is active: {LOCK_PATH}")
                yield False
                return
        else:
            print(f"  another fetch_fresh_odds run is active: {LOCK_PATH}")
            yield False
            return
    try:
        os.write(fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode("ascii"))
        os.close(fd)
        yield True
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def race_key(race: dict) -> str:
    return (
        race["race_year"]
        + race["race_month_day"]
        + race["track_code"]
        + race["kaiji"]
        + race["nichiji"]
        + race["race_num"]
    )


def _race_start(race: dict) -> datetime | None:
    y = str(race.get("race_year") or "")
    md = str(race.get("race_month_day") or "").zfill(4)
    st = str(race.get("start_time") or "").strip().zfill(4)
    if len(y) != 4 or len(md) != 4 or len(st) < 4:
        return None
    try:
        return datetime.strptime(y + md + st[:4], "%Y%m%d%H%M")
    except ValueError:
        return None


COVERAGE_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "logs" / "fresh_odds_coverage.jsonl"


def _write_coverage_log(payload: dict) -> None:
    """1 実行あたり 1 行 JSONL を data/logs/fresh_odds_coverage.jsonl に append。

    Plan Step 4 (2026-06-17 外部レビュー追記) の coverage 監査用。
    `scripts/fresh_odds_coverage.py` で後追い集計する想定。
    エラーで本筋を止めないよう例外は飲み込む。
    """
    try:
        COVERAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with COVERAGE_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False))
            f.write("\n")
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="発走直前レースの fresh odds 取得")
    ap.add_argument(
        "--window", type=int, default=25,
        help="発走何分前までを対象にするか (default: 25)",
    )
    ap.add_argument(
        "--min-lead", type=int, default=2,
        help="発走何分前を下限にするか。直前すぎると取得が間に合わない (default: 2)",
    )
    ap.add_argument("--dry-run", action="store_true", help="取得せず対象レースだけ表示")
    ap.add_argument("--date", help="YYYYMMDD (default: today)")
    args = ap.parse_args()

    run_started_at = time.time()
    now = datetime.now()
    target_date = args.date or now.strftime("%Y%m%d")

    with open_db() as conn:
        rows = conn.execute(
            """
            SELECT race_year, race_month_day, track_code, kaiji, nichiji,
                   race_num, start_time
            FROM races
            WHERE race_year || race_month_day BETWEEN ? AND ?
            ORDER BY race_year, race_month_day, track_code, race_num
            """,
            (target_date, target_date),
        ).fetchall()

    upcoming = []
    for r in rows:
        race = dict(r)
        start = _race_start(race)
        if start is None:
            continue
        minutes_until = (start - now).total_seconds() / 60
        if args.min_lead <= minutes_until <= args.window:
            upcoming.append((race, start, minutes_until))

    print(f"[{now.strftime('%H:%M:%S')}] date={target_date} "
          f"total_races={len(rows)} upcoming={len(upcoming)} "
          f"window={args.min_lead}-{args.window}min")

    # coverage 監査用 (Plan Step 4 / 2026-06-17 外部レビュー)。
    # 早期 return パスでも 1 行 JSONL を残し「スケジューラ起動した記録」を担保。
    coverage_payload: dict = {
        "run_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "target_date": target_date,
        "window": args.window,
        "min_lead": args.min_lead,
        "total_races_in_db": len(rows),
        "eligible_races": len(upcoming),
        "dry_run": bool(args.dry_run),
        "fetched_races": 0,
        "ok_races": 0,
        "error_races": 0,
        "no_data_races": 0,
        "timeout_races": 0,
        "empty_races": 0,
        "skipped_late_races": 0,
        "lock_skipped": False,
        "ingested_records": None,
        "total_records": 0,
        "total_files": 0,
        "failed_reason": {},
    }

    if not upcoming:
        print("  no races in window")
        _write_coverage_log(coverage_payload)
        return 0

    for race, start, mins in upcoming:
        tc = race["track_code"]
        rn = int(race["race_num"])
        print(f"  {tc} {rn:02d}R  start={start.strftime('%H:%M')}  "
              f"in {mins:.0f}min", end="")
        if args.dry_run:
            print("  [dry-run skip]")
        else:
            print()

    if args.dry_run:
        _write_coverage_log(coverage_payload)
        return 0

    with single_run_lock() as acquired:
        if not acquired:
            coverage_payload["lock_skipped"] = True
            _write_coverage_log(coverage_payload)
            return 0

        fetched = []
        fetch_errors = []
        status_counts: Counter[str] = Counter()
        failed_reason: Counter[str] = Counter()
        skipped_late = 0
        with JVLinkClient() as cli:
            for race, start, mins in upcoming:
                try:
                    LOCK_PATH.touch()
                except OSError:
                    pass
                mins_now = (start - datetime.now()).total_seconds() / 60
                if not (args.min_lead <= mins_now <= args.window):
                    tc = race["track_code"]
                    rn = int(race["race_num"])
                    print(f"  skip {tc} {rn:02d}R  now in {mins_now:.0f}min")
                    skipped_late += 1
                    continue
                key = race_key(race)
                tc = race["track_code"]
                rn = int(race["race_num"])
                print(f"  fetching {tc} {rn:02d}R ...", end=" ", flush=True)
                try:
                    result = cli.fetch_realtime("0B31", key)
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {str(exc)[:80]}"
                    print(f"error {reason}")
                    fetch_errors.append({"race_key": key, "error": reason})
                    failed_reason[type(exc).__name__] += 1
                    continue
                records = int(result.get("records_total") or 0)
                files = int(result.get("files_written") or 0)
                timed_out = bool(result.get("timed_out"))
                no_data = bool(result.get("no_data"))
                if records > 0:
                    status = "ok"
                elif timed_out:
                    status = "timeout"
                elif no_data:
                    status = "no_data"
                else:
                    status = "empty"
                status_counts[status] += 1
                print(f"{status} records={records} files={files}")
                fetched.append(result)

        total_records = sum(int(r.get("records_total") or 0) for r in fetched)
        total_files = sum(int(r.get("files_written") or 0) for r in fetched)
        fetched_files = {
            name
            for result in fetched
            for name in (result.get("filenames") or [])
            if name
        }
        ingest_summary: dict | None = None
        if fetched_files:
            ingest_summary = ingest_all(
                dataspecs=["0B31"],
                only_files=fetched_files,
            )
            print(f"  ingest: {ingest_summary}")
        elif total_records > 0:
            ingest_summary = ingest_all(
                dataspecs=["0B31"],
                modified_since=run_started_at - 1,
            )
            print(f"  ingest: {ingest_summary}")
        else:
            print("  ingest: skipped (no records)")

        print(
            f"  done: races={len(fetched)} errors={len(fetch_errors)} "
            f"records={total_records} files={total_files}"
        )

        coverage_payload.update({
            "fetched_races": len(fetched),
            "ok_races": status_counts.get("ok", 0),
            "error_races": len(fetch_errors),
            "no_data_races": status_counts.get("no_data", 0),
            "timeout_races": status_counts.get("timeout", 0),
            "empty_races": status_counts.get("empty", 0),
            "skipped_late_races": skipped_late,
            "ingested_records": _normalize_ingest_summary(ingest_summary),
            "total_records": total_records,
            "total_files": total_files,
            "failed_reason": dict(failed_reason),
        })
        _write_coverage_log(coverage_payload)
        if fetch_errors and not fetched:
            return 1
    return 0


def _normalize_ingest_summary(summary: dict | None) -> dict | None:
    """ingest_all の戻り (dict[str, dict] が想定だが実装変動の可能性) を
    JSON serializable な形に丸める。フィールド名は今後の運用で増えうるので
    型変換だけ行い、キー名は ingest 側に追従する。
    """
    if summary is None:
        return None
    out: dict = {}
    for k, v in summary.items():
        if isinstance(v, dict):
            out[k] = {sk: (sv if isinstance(sv, (int, float, str, bool, type(None))) else str(sv))
                      for sk, sv in v.items()}
        elif isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
