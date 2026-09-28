"""cross-date 修正版 builder で 10 日を scratch に再生成する (data/results には書かない)。

- builder は cross-date の worktree (固定 SHA) のコードで動かす
- 本番 DB は --db で渡す (builder は SELECT だけ。2026-09-28 CHAT: 案 A、非開催日に実行)
- DB / WAL の size と mtime を、開始前・各日の後・終了後に記録する。変化したら止めて結果を採用しない
- HTML は旧 manifest の source_html (旧成果物がある 6 日)、無い 4 日は builder の既定と同じ規則
  (predictions_source_*.html を名前で並べた最後) を明示して渡す
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROD = Path(r"C:\Users\kizun\dev\keiba-yosou")
WT = PROD / ".claude" / "worktrees" / "cross-date"
TRACKED = "--tracked" in sys.argv   # worktree の data/results へ (上書き。builder が supersedes を刻む)
OUT = (WT / "data" / "results") if TRACKED else Path(__file__).resolve().parent / "out"
LOG_NAME = "regen_tracked_log.json" if TRACKED else "regen_log.json"
PY = PROD / ".venv64" / "Scripts" / "python.exe"
DB = PROD / "data" / "keiba.db"
WAL = PROD / "data" / "keiba.db-wal"
DATES = ["2026-06-12", "2026-06-17", "2026-07-03", "2026-07-18", "2026-08-08", "2026-08-15",
         "2026-08-22", "2026-08-29", "2026-09-05", "2026-09-12"]


def db_stat():
    """変化の判定に使う値。DB は size と mtime、WAL は size だけ。

    WAL の mtime は、別のプロセスが DB を開いただけで変わる (書き込みではない)。
    mutation_sandbox と同じ基準にする (2026-09-26 の誤 ABORT の教訓)。
    """
    # WAL が無いことと 0 バイトは同じ (未反映の書き込みが無い)。最後の接続を閉じると SQLite が消す
    wal = WAL.stat().st_size if WAL.exists() else 0
    return {"keiba.db": [DB.stat().st_size, DB.stat().st_mtime], "keiba.db-wal_size": wal}


def wal_mtime():
    return WAL.stat().st_mtime if WAL.exists() else None


def pick_html(d: str) -> tuple[Path, str]:
    res = PROD / "data" / "results" / d
    m = res / "manifest.json"
    if m.exists():
        src = json.loads(m.read_text(encoding="utf-8"))["source_html"]
        return Path(src), "old_manifest_source_html"
    cands = sorted(res.glob("predictions_source_*.html"))
    return cands[-1], "builder_default_rule_last_by_name"


def git(*a):
    return subprocess.run(["git", "-C", str(WT), *a], capture_output=True, text=True).stdout.strip()


def main():
    head = git("rev-parse", "HEAD")
    porcelain = git("status", "--porcelain")
    log_tracked_before = porcelain
    if porcelain:
        sys.exit(f"worktree が clean でない: {porcelain}")
    OUT.mkdir(parents=True, exist_ok=True)
    before = db_stat()
    log = {"started": datetime.now().isoformat(timespec="seconds"), "builder_worktree": str(WT),
           "builder_head": head, "db_before": before, "runs": []}
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    for d in DATES:
        html, why = pick_html(d)
        out_dir = OUT / d
        if not TRACKED and out_dir.exists() and any(out_dir.iterdir()):
            sys.exit(f"出力先が空でない: {out_dir}")
        r = subprocess.run([str(PY), "-m", "scripts.build_daily_results", "--date", d.replace("-", ""),
                            "--html", str(html), "--db", str(DB), "--output-dir", str(out_dir)],
                           cwd=WT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        after = db_stat()
        run = {"date": d, "html": str(html), "html_choice": why, "rc": r.returncode,
               "stdout_tail": r.stdout[-1500:], "stderr_tail": r.stderr[-1500:], "db_after": after,
               "wal_mtime_info": wal_mtime()}
        log["runs"].append(run)
        print(d, "rc", r.returncode, why, html.name, flush=True)
        if after != before:
            log["aborted"] = f"{d} の後に DB / WAL が変化した: {before} -> {after}"
            break
    log["db_after_all"] = db_stat()
    log["finished"] = datetime.now().isoformat(timespec="seconds")
    log["worktree_porcelain_after"] = git("status", "--porcelain")
    (Path(__file__).resolve().parent / LOG_NAME).write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in log.items() if k != "runs"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
