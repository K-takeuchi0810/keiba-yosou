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
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH, PROJECT_ROOT  # noqa: E402
import sqlite3  # noqa: E402

WEBHOOK_FILE = PROJECT_ROOT / "data" / "discord_webhook.txt"
MARKER = PROJECT_ROOT / "docs" / "predictions_latest.md"
# GitHub Pages 公開先 (docs/index.html を main /docs から配信)。スマホでレンダリング表示。
PAGES_HTML = PROJECT_ROOT / "docs" / "index.html"
GENERATED_HTML = PROJECT_ROOT / "web" / "dist" / "index.html"
PAGES_URL = "https://k-takeuchi0810.github.io/keiba-yosou/"
PY = str(PROJECT_ROOT / ".venv64" / "Scripts" / "python.exe")


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


def _notify(text: str) -> None:
    url = WEBHOOK_FILE.read_text(encoding="utf-8").strip()
    req = urllib.request.Request(
        url, data=json.dumps({"content": text}).encode("utf-8"),
        # User-Agent 無しの urllib 既定値は Cloudflare に 403 で弾かれる
        headers={"Content-Type": "application/json", "User-Agent": "keiba-yosou-bot/1.0"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15).read()


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

    r = subprocess.run([PY, "-m", "web.generator", "--from", d_from, "--to", d_to],
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
    subprocess.run(["git", "add", str(PAGES_HTML), str(PAGES_HTML.parent / ".nojekyll"),
                    str(MARKER)], cwd=PROJECT_ROOT, check=True)
    c = subprocess.run(["git", "commit", "-m",
                        f"predictions: {d_from}-{d_to} published to Pages ({ver})"],
                       cwd=PROJECT_ROOT, capture_output=True, text=True)
    if c.returncode == 0:
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=PROJECT_ROOT,
                       capture_output=True, text=True)

    _notify(
        f"🏇 **予想生成完了** {d_from[:4]}/{d_from[4:6]}/{d_from[6:]}〜{d_to[4:6]}/{d_to[6:]} "
        f"({n_races}R, {ver})\n"
        f"📱 今すぐ見る(確実): iPhone ファイルApp → iCloud Drive → 競馬予想 → index.html\n"
        f"🌐 Web版: {PAGES_URL} (GitHub のビルド反映に数分ラグあり)\n"
        f"⚠ 観察専用 (実弾根拠となるエッジは未証明)"
    )
    print("notified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
