"""予想の自動生成 + Discord 通知 (F4, 2026-07-03 ユーザ要件・案A)。

条件判定 → web.generator 生成 → docs/predictions/latest.md を commit+push →
Discord webhook に「commit URL + 閲覧は iCloud」を通知。

生成条件 (自己判断): 今日〜明日に出馬表 (races) が存在すること。無ければ生成せず終了
(開催前々日以前や平日は静かに skip)。Task Scheduler から毎朝実行される前提。

使い方: .venv64/Scripts/python.exe -m scripts.auto_predict [--dry-run] [--force-notify]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH, ICLOUD_PUBLISH_DIR, PROJECT_ROOT  # noqa: E402
from scripts.notify_discord import notify_discord  # noqa: E402
import sqlite3  # noqa: E402

MARKER = PROJECT_ROOT / "docs" / "predictions_latest.md"
# GitHub Pages 公開先 (docs/index.html を main /docs から配信)。スマホでレンダリング表示。
PAGES_HTML = PROJECT_ROOT / "docs" / "index.html"
GENERATED_HTML = PROJECT_ROOT / "web" / "dist" / "index.html"
PAGES_URL = "https://k-takeuchi0810.github.io/keiba-yosou/"
PY = str(PROJECT_ROOT / ".venv64" / "Scripts" / "python.exe")


def _stage_publish_artifacts(
    target_date: str, sync_status_path: Path | None = None
) -> list[Path]:
    archive_dir = (
        PROJECT_ROOT / "data" / "results" /
        f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"
    )
    paths = [PAGES_HTML, PAGES_HTML.parent / ".nojekyll", MARKER]
    status_path = sync_status_path or ICLOUD_PUBLISH_DIR / "_sync_status.json"
    archive = None
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        raw_archive = status.get("repository_archive")
        if raw_archive:
            candidate = Path(raw_archive)
            if candidate.is_file():
                archive = candidate
    except (OSError, TypeError, ValueError):
        pass
    if archive is not None:
        paths.append(archive)
    else:
        paths.extend(sorted(archive_dir.glob("predictions_source_*.html")))
    subprocess.run(
        ["git", "add", *(str(path) for path in paths)],
        cwd=PROJECT_ROOT,
        check=True,
    )
    return paths


def _race_days(conn, days: list[str]) -> list[tuple[str, int]]:
    out = []
    for d in days:
        n = conn.execute(
            "SELECT COUNT(*) FROM races WHERE race_year=? AND race_month_day=?",
            (d[:4], d[4:]),
        ).fetchone()[0]
        if n > 0:
            out.append((d, n))
    return out


def _notify(text: str) -> bool:
    """Compatibility wrapper around the shared best-effort notifier."""
    return notify_discord(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="生成せず対象日のみ表示")
    args = ap.parse_args()

    today = date.today()
    cand = [(today + timedelta(days=i)).strftime("%Y%m%d") for i in (0, 1)]
    conn = sqlite3.connect(DB_PATH)
    targets = _race_days(conn, cand)
    conn.close()
    if not targets:
        print(f"skip: {cand} に出馬表なし (開催日でない)")
        return 0
    d_from, d_to = targets[0][0], targets[-1][0]
    n_races = sum(n for _, n in targets)
    print(f"generate: {d_from}-{d_to} ({n_races} races)")
    if args.dry_run:
        return 0

    r = subprocess.run([PY, "-m", "web.generator", "--from", d_from, "--to", d_to,
                        "--log-predictions"],
                       capture_output=True, text=True, cwd=PROJECT_ROOT)
    if r.returncode != 0:
        _notify(f"⚠ 予想生成に失敗 ({d_from}-{d_to})。ログ確認要。")
        print(r.stdout[-500:], r.stderr[-500:])
        return 1

    # 版情報
    meta = json.loads((PROJECT_ROOT / "predictor" / "lgbm_meta.json").read_text(encoding="utf-8"))
    ver = meta.get("rule_version", "?")

    # GitHub Pages へ公開: 生成 HTML を docs/index.html にコピーして commit+push。
    # commit URL はレンダリングされないので通知には Pages URL を載せる (案A 改)。
    from datetime import datetime
    PAGES_HTML.parent.mkdir(parents=True, exist_ok=True)
    PAGES_HTML.write_bytes(GENERATED_HTML.read_bytes())
    (PAGES_HTML.parent / ".nojekyll").touch()
    MARKER.write_text(
        f"# 最新予想生成\n\n- 対象: {d_from}〜{d_to} ({n_races} レース)\n"
        f"- 生成時刻: {datetime.now().isoformat(timespec='seconds')}\n"
        f"- モデル: {ver}\n- 閲覧: {PAGES_URL} (GitHub Pages) / iCloud Drive index.html\n",
        encoding="utf-8")
    _stage_publish_artifacts(d_from)
    c = subprocess.run(["git", "commit", "-m",
                        f"predictions: {d_from}-{d_to} published to Pages ({ver})"],
                       cwd=PROJECT_ROOT, capture_output=True, text=True)
    # Pages は main (デフォルトブランチ) からデプロイされるので main へ push する。
    # 非 fast-forward なら git が安全に reject → 通知して手動判断 (force はしない)。
    push_ok = True
    if c.returncode == 0:
        # ブランチガード: 共有 checkout が feature ブランチに居るとき、スケジュール実行が
        # HEAD:main へ push すると未レビュー commit が main へ流入する。main 上でのみ push。
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=PROJECT_ROOT,
            capture_output=True, text=True).stdout.strip()
        if branch != "main":
            push_ok = False
            print(f"WARN: HEAD が main でない ({branch}) ため main への push を中止しました。")
        else:
            subprocess.run(["git", "fetch", "origin", "main", "-q"], cwd=PROJECT_ROOT,
                           capture_output=True, text=True)
            p = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True)
            push_ok = p.returncode == 0
            if not push_ok:
                print("WARN: push to main failed:\n", p.stderr[-400:])

    web_line = (f"🌐 Web版: {PAGES_URL} (数分で更新)" if push_ok
                else f"🌐 Web版: main push 失敗のため未更新 (手動確認要)")
    _notify(
        f"🏇 **予想生成完了** {d_from[:4]}/{d_from[4:6]}/{d_from[6:]}〜{d_to[4:6]}/{d_to[6:]} "
        f"({n_races}R, {ver})\n"
        f"📱 今すぐ見る(確実): iPhone ファイルApp → iCloud Drive → 競馬予想 → index.html\n"
        f"{web_line}\n"
        f"⚠ 観察専用 (実弾根拠となるエッジは未証明)"
    )
    print("notified. push_ok=", push_ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
