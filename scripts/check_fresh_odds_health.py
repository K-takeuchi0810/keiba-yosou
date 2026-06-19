"""fresh odds 取得運用の健全性チェック (Python core)。

scripts/check_fresh_odds_health.ps1 から呼ばれ、JSONL + DB を見て
PASS / FAIL / HOLD / NOT_EVALUABLE を判定する。
スケジューラ情報は Get-ScheduledTaskInfo が PowerShell cmdlet のため
PS1 側で取得して JSON 文字列として渡してもらう。

入力 (argparse):
  --scheduler-json '{"registered": true, "last_run_time": "...", "last_task_result": 0, "next_run_time": "..."}'
  --date YYYYMMDD                (省略時: today)
  --check-after-time HH:MM       (省略時: 09:00)
  --runtime-dir PATH             (省略時: data/runtime)
  --coverage-path PATH           (省略時: data/logs/fresh_odds_coverage.jsonl)
  --db-path PATH                 (省略時: data/keiba.db)
  --quiet                        (stdout への summary 出力抑制)

副作用:
  - data/runtime/fresh_odds_health_<YYYYMMDD_HHMMSS>.json を atomic 保存
  - PS1 側で _latest.json にコピーされる想定 (本スクリプトは latest を直接更新しない)

exit code:
  0: PASS
  1: FAIL
  2: HOLD
  3: NOT_EVALUABLE
  4: 想定外エラー (本スクリプト自身の bug)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_HOLD = 2
EXIT_NOT_EVALUABLE = 3
EXIT_INTERNAL_ERROR = 4

DECISION_BY_EXIT = {
    EXIT_PASS: "PASS",
    EXIT_FAIL: "FAIL",
    EXIT_HOLD: "HOLD",
    EXIT_NOT_EVALUABLE: "NOT_EVALUABLE",
}


def _parse_dt(value: str | None) -> datetime | None:
    """ISO 8601 / Windows schtasks 形式の datetime をパース。

    PowerShell Get-ScheduledTaskInfo は LastRunTime を未実行時に
    `1999/11/30 0:00:00` で返す。これは「未実行」を意味するため None 化する。
    """
    if value is None or not str(value).strip():
        return None
    s = str(value).strip()
    if s.startswith("1999") or s.startswith("1999/"):
        return None
    # ISO 8601 を試す
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        pass
    # Windows 表示形式 (例: "2026/06/20 9:00:00")
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def evaluate_scheduler(
    scheduler_info: dict,
    date_str: str,
    check_after: time,
) -> dict:
    """Get-ScheduledTaskInfo の出力を判定。

    scheduler_info の期待形:
      {"registered": bool, "last_run_time": str, "last_task_result": int, "next_run_time": str}
    """
    out: dict = {
        "task_name": "keiba-fresh-odds",
        "registered": bool(scheduler_info.get("registered", False)),
        "last_run_time": scheduler_info.get("last_run_time"),
        "last_task_result": scheduler_info.get("last_task_result"),
        "next_run_time": scheduler_info.get("next_run_time"),
        "ran_today_after_check_time": False,
        "ok": False,
        "reason": "",
    }
    if not out["registered"]:
        out["reason"] = "scheduler task not registered"
        return out
    last_run = _parse_dt(out["last_run_time"])
    if last_run is None:
        out["reason"] = "scheduler has never run (LastRunTime epoch placeholder)"
        return out
    target_date = datetime.strptime(date_str, "%Y%m%d").date()
    threshold = datetime.combine(target_date, check_after)
    if last_run < threshold:
        out["reason"] = (
            f"last run {last_run.isoformat()} is before today's check threshold "
            f"{threshold.isoformat()}"
        )
        return out
    out["ran_today_after_check_time"] = True
    result = out["last_task_result"]
    # Windows scheduler の正常終了は 0 または 267009 (running) のことがある
    if result not in (0, 267009):
        out["reason"] = f"last_task_result={result} (0 以外 = エラー)"
        return out
    out["ok"] = True
    out["reason"] = "scheduler ran today and exited cleanly"
    return out


def evaluate_coverage(
    coverage_path: Path,
    date_str: str,
    check_after: time,
) -> dict:
    """coverage JSONL の今日分エントリを集計。

    test 由来データ混入の検出: scheduler 稼働窓 (09:00-16:40 想定) 外の run_at は
    test 由来の疑いありとしてフラグ。
    """
    out: dict = {
        "path": str(coverage_path),
        "exists": coverage_path.exists(),
        "updated_today_after_check_time": False,
        "runs_today": 0,
        "ok_races_today": 0,
        "error_races_today": 0,
        "skipped_late_races_today": 0,
        "contamination_detected": False,
        "contamination_examples": [],
        "post_start_warning": False,
        "ok": False,
        "reason": "",
    }
    if not coverage_path.exists():
        out["reason"] = f"coverage JSONL not found: {coverage_path}"
        return out

    target_date = datetime.strptime(date_str, "%Y%m%d").date()
    threshold = datetime.combine(target_date, check_after)
    # 稼働窓 (scheduler の通常稼働時間帯)。±5 分のマージンで弾く。
    window_start = time(8, 55)
    window_end = time(16, 50)

    today_runs = []
    contamination_rows = []
    try:
        with coverage_path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                run_at = _parse_dt(rec.get("run_at"))
                if run_at is None or run_at.date() != target_date:
                    continue
                today_runs.append(rec)
                rt = run_at.time()
                if rt < window_start or rt > window_end:
                    contamination_rows.append({"lineno": lineno, "run_at": rec.get("run_at")})
        out["runs_today"] = len(today_runs)
    except OSError as e:
        out["reason"] = f"cannot read coverage JSONL: {e}"
        return out

    if contamination_rows:
        out["contamination_detected"] = True
        out["contamination_examples"] = contamination_rows[:5]

    # 今日分かつ check_after 以降のエントリのみ集計対象
    valid = [
        r for r in today_runs
        if (_parse_dt(r.get("run_at")) or datetime.min) >= threshold
    ]
    if valid:
        out["updated_today_after_check_time"] = True
        out["ok_races_today"] = sum(int(r.get("ok_races") or 0) for r in valid)
        out["error_races_today"] = sum(int(r.get("error_races") or 0) for r in valid)
        out["skipped_late_races_today"] = sum(int(r.get("skipped_late_races") or 0) for r in valid)

    # 判定
    if out["contamination_detected"]:
        out["reason"] = (
            f"contamination detected: {len(contamination_rows)} entries with "
            f"run_at outside scheduler window (08:55-16:50). 例: {out['contamination_examples'][:2]}"
        )
        return out
    if not out["updated_today_after_check_time"]:
        out["reason"] = (
            f"coverage JSONL has no entries today after {threshold.isoformat()}"
        )
        return out
    if out["ok_races_today"] == 0:
        out["reason"] = (
            f"scheduler fired but ok_races_today=0 "
            f"(errors={out['error_races_today']}, skipped_late={out['skipped_late_races_today']})"
        )
        return out
    out["ok"] = True
    out["reason"] = f"ok_races_today={out['ok_races_today']}"
    return out


def evaluate_db(
    db_path: Path,
    date_str: str,
    check_after: time,
) -> dict:
    """horse_races.odds_fetched_at の今日分鮮度カウント。"""
    out: dict = {
        "path": str(db_path),
        "reachable": False,
        "fresh_horse_rows_since_check_time": 0,
        "post_start_rows_today": 0,
        "ok": False,
        "reason": "",
    }
    if not db_path.exists():
        out["reason"] = f"DB not found: {db_path}"
        return out
    target_date = datetime.strptime(date_str, "%Y%m%d").date()
    threshold = datetime.combine(target_date, check_after)
    threshold_iso = threshold.isoformat()
    # 翌日 00:00 をシーリングに
    end_threshold = datetime.combine(target_date, time(23, 59, 59)).isoformat()
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM horse_races
            WHERE odds_fetched_at IS NOT NULL
              AND odds_fetched_at >= ?
              AND odds_fetched_at <= ?
            """,
            (threshold_iso, end_threshold),
        )
        out["fresh_horse_rows_since_check_time"] = int(cur.fetchone()[0])
        out["reachable"] = True
    except sqlite3.DatabaseError as e:
        out["reason"] = f"DB query failed: {e}"
        try:
            conn.close()
        except Exception:
            pass
        return out
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if out["fresh_horse_rows_since_check_time"] == 0:
        out["reason"] = (
            f"no horse_races rows with odds_fetched_at >= {threshold_iso}. "
            f"取得は成功したが ingest が未完 / 別系統データの可能性。"
        )
        return out
    out["ok"] = True
    out["reason"] = f"fresh_horse_rows={out['fresh_horse_rows_since_check_time']}"
    return out


def integrate_decision(
    scheduler: dict,
    coverage: dict,
    db: dict,
) -> tuple[str, str]:
    """3 セクションを統合して最終 decision を返す。

    優先順:
      1. NOT_EVALUABLE: scheduler 未登録、DB 不在、または scheduler 稼働後なのに
         coverage 不在 (= 監査路自体が壊れている)
      2. FAIL: scheduler last_task_result が 0/267009 以外、contamination_detected
      3. HOLD: scheduler 未稼働 (待つだけで PASS になりうる)、ok_races==0、DB 0 件、
         coverage 未生成だが scheduler も未稼働 (整合性ある待機状態)
      4. PASS: 全 ok=True
    """
    # NOT_EVALUABLE 系
    if not scheduler.get("registered"):
        return "NOT_EVALUABLE", f"scheduler not registered ({scheduler.get('reason')})"
    if not db.get("reachable"):
        return "NOT_EVALUABLE", f"DB unreachable ({db.get('reason')})"
    # coverage absent: scheduler が今日 fire 後なら data path 破綻 (NOT_EVALUABLE)、
    # 未 fire ならまだ生成されていないだけ (HOLD)
    scheduler_fired_today = bool(scheduler.get("ran_today_after_check_time"))
    if not coverage.get("exists"):
        if scheduler_fired_today:
            return (
                "NOT_EVALUABLE",
                f"coverage JSONL absent despite scheduler firing today "
                f"({coverage.get('reason')}) → data path broken",
            )
        # scheduler 未 fire のときは coverage 不在で当然
        return (
            "HOLD",
            f"scheduler not yet fired today and coverage JSONL not yet generated "
            f"({scheduler.get('reason') or 'awaiting first fire'})",
        )

    # FAIL 系
    if coverage.get("contamination_detected"):
        return "FAIL", coverage.get("reason", "coverage contamination")
    result = scheduler.get("last_task_result")
    if result is not None and result not in (0, 267009):
        # 完全初回 (LastRunTime epoch placeholder) は scheduler.ok=False で HOLD 行きにしたい
        last_run = _parse_dt(scheduler.get("last_run_time"))
        if last_run is not None:
            return "FAIL", f"scheduler last_task_result={result}"

    # HOLD 系
    if not scheduler_fired_today:
        return "HOLD", f"scheduler not yet fired today ({scheduler.get('reason')})"
    if not coverage.get("updated_today_after_check_time"):
        return "HOLD", f"coverage no fresh entries today ({coverage.get('reason')})"
    if coverage.get("ok_races_today", 0) == 0:
        return "HOLD", coverage.get("reason", "ok_races_today=0")
    if db.get("fresh_horse_rows_since_check_time", 0) == 0:
        return "HOLD", db.get("reason", "no fresh horse_races rows yet")

    # PASS
    if scheduler.get("ok") and coverage.get("ok") and db.get("ok"):
        return "PASS", "all checks passed"
    # ここに来ているのは想定外
    return "HOLD", "one or more sections not ok despite no explicit FAIL/NOT_EVALUABLE"


def atomic_write_json(path: Path, payload: dict) -> None:
    """tempfile → os.replace で atomic に JSON 保存。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(
        prefix=path.stem + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmpname, path)
    except Exception:
        try:
            os.unlink(tmpname)
        except OSError:
            pass
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--scheduler-json", default="{}",
        help="Get-ScheduledTaskInfo の dict を JSON 文字列で渡す",
    )
    ap.add_argument(
        "--scheduler-json-path", default=None,
        help="Get-ScheduledTaskInfo の dict を書いた JSON ファイルパス "
             "(--scheduler-json と排他、PowerShell からの quoting 回避のため推奨)",
    )
    ap.add_argument("--date", default=None, help="YYYYMMDD (default: today)")
    ap.add_argument("--check-after-time", default="09:00", help="HH:MM")
    ap.add_argument("--runtime-dir", default=str(ROOT / "data" / "runtime"))
    ap.add_argument("--coverage-path", default=str(ROOT / "data" / "logs" / "fresh_odds_coverage.jsonl"))
    ap.add_argument("--db-path", default=str(ROOT / "data" / "keiba.db"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    # --scheduler-json-path が優先 (PowerShell の quoting 問題回避)
    if args.scheduler_json_path:
        try:
            scheduler_info = json.loads(
                Path(args.scheduler_json_path).read_text(encoding="utf-8")
            )
        except (ValueError, OSError) as e:
            print(
                f"--scheduler-json-path 読込み失敗 ({args.scheduler_json_path}): {e}",
                file=sys.stderr,
            )
            return EXIT_INTERNAL_ERROR
    else:
        try:
            scheduler_info = json.loads(args.scheduler_json or "{}")
        except ValueError as e:
            print(f"--scheduler-json は JSON である必要があります: {e}", file=sys.stderr)
            return EXIT_INTERNAL_ERROR

    now = datetime.now()
    date_str = args.date or now.strftime("%Y%m%d")
    try:
        ch_hh, ch_mm = args.check_after_time.split(":")
        check_after = time(int(ch_hh), int(ch_mm))
    except (ValueError, AttributeError):
        print(f"--check-after-time のフォーマットが HH:MM ではない: {args.check_after_time}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    scheduler = evaluate_scheduler(scheduler_info, date_str, check_after)
    coverage = evaluate_coverage(Path(args.coverage_path), date_str, check_after)
    db = evaluate_db(Path(args.db_path), date_str, check_after)
    decision, reason = integrate_decision(scheduler, coverage, db)

    payload = {
        "checked_at": now.isoformat(timespec="seconds"),
        "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
        "check_after_time": args.check_after_time,
        "scheduler": scheduler,
        "coverage": coverage,
        "db": db,
        "decision": decision,
        "reason": reason,
        "next_action": _next_action_hint(decision),
    }

    runtime_dir = Path(args.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    ts = now.strftime("%Y%m%d_%H%M%S")
    history_path = runtime_dir / f"fresh_odds_health_{ts}.json"
    atomic_write_json(history_path, payload)
    # latest は PS1 側でコピーしてもよいが、Python 側でも書く (PS1 経由でない直接呼び出し対応)
    latest_path = runtime_dir / "fresh_odds_health_latest.json"
    atomic_write_json(latest_path, payload)

    if not args.quiet:
        print(f"decision: {decision}")
        print(f"reason: {reason}")
        print(f"saved: {history_path}")
        print(f"latest: {latest_path}")

    return {
        "PASS": EXIT_PASS,
        "FAIL": EXIT_FAIL,
        "HOLD": EXIT_HOLD,
        "NOT_EVALUABLE": EXIT_NOT_EVALUABLE,
    }.get(decision, EXIT_INTERNAL_ERROR)


def _next_action_hint(decision: str) -> str:
    return {
        "PASS": "scripts/run_oos_backtest_if_fresh_ok.ps1 が起動可。実行に進める",
        "FAIL": "contamination や scheduler エラーを解消するまで OOS backtest 起動不可",
        "HOLD": "scheduler の次の起動を待つ (HH:00, HH:10 の周期)。1〜2 開催日ぶん観察を継続",
        "NOT_EVALUABLE": "scheduler 登録 / DB 配置 / coverage JSONL 出力経路を確認し、不備を修正",
    }.get(decision, "")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"internal error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(EXIT_INTERNAL_ERROR)
