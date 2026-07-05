"""独自出馬表 webapp のローカルサーバ (標準ライブラリ http.server + jinja2)。

FastAPI 等の重い依存を足さず、既存依存 (jinja2) だけで動く自己利用向けサーバ。
ルーティング/描画は webapp/views.py に分離済 (単体テスト可能)。

== 予想生成への非干渉保証 (2026-07-05) ==
本サーバは GUI/generator/ingest の予想生成ワークフローと完全に分離する:
  - プロセス分離: 予想生成側は webapp を import しない (逆も read-only 利用のみ)。
  - DB は open_db_readonly (URI mode=ro + PRAGMA query_only) で開く。
    init_db の migration 書込みを発行せず、書込みロック競合を起こさない
    (WAL リーダは writer をブロックしない)。書込みは構造的に不可能。
  - predictor/rules・weights・calibrator には一切書き込まない (読み取り描画のみ)。

起動:
    python -m webapp.server            # 既定 127.0.0.1:8760
    python -m webapp.server --port 9000 --host 0.0.0.0

iPhone から見る場合は同一 LAN で --host 0.0.0.0、または Tailscale 経由。
JV-Data 由来データの一般公開には JRA-VAN 契約が必要なため既定は 127.0.0.1 束縛。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_PERIODS
from db import open_db_readonly
from webapp import views
from webapp.aggregate import jra_track_clause

logger = logging.getLogger(__name__)


def _default_trend_window() -> tuple[str, str]:
    """傾向集計の既定期間 = 直近5年 (今日から遡る)。Date 依存を避けるため
    config の test 期間終端があればそれ、無ければ現在時刻から算出。"""
    to = DATA_PERIODS.get("test", {}).get("to")
    if to:
        end = datetime.strptime(to, "%Y%m%d")
    else:
        end = datetime.now()
    start = end - timedelta(days=365 * 5)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _latest_race_date(conn) -> str | None:
    row = conn.execute(
        f"SELECT race_year, race_month_day FROM races WHERE {jra_track_clause()} "
        "ORDER BY race_year DESC, race_month_day DESC LIMIT 1"
    ).fetchone()
    return f"{row[0]}{row[1]}" if row else None


class Handler(BaseHTTPRequestHandler):
    db_path = None  # class-level; set by run()

    def log_message(self, fmt, *args):  # noqa: A003 — quiet default logging
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _send(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            # 読み取り専用接続 (query_only)。予想生成側の DB 書込みと競合しない。
            with (open_db_readonly(self.db_path) if self.db_path else open_db_readonly()) as conn:
                html = self._route(conn, path, q)
            if html is None:
                self._send(views.render_error("404", "該当データがありません。"), 404)
            else:
                self._send(html)
        except BrokenPipeError:
            pass
        except FileNotFoundError:
            # パスは露出しない (LAN 端末への情報露出防止。--db 指定値の確認を促すのみ)
            self._send(views.render_error(
                "DB が見つかりません",
                "JV-Link で取得・取込後に再度開いてください。",
                "起動時の --db 指定値 (未指定なら data/keiba.db) を確認してください。"), 500)
        except Exception:  # noqa: BLE001 — サーバは落とさずエラーページを返す
            # traceback はログのみ。画面には人間向けメッセージ + 復帰導線。
            logger.exception("request failed: %s", self.path)
            self._send(views.render_error(
                "表示に失敗しました", "時刻や条件を変えて再試行してください。"), 500)

    def _route(self, conn, path: str, q: dict) -> str | None:
        if path == "/" or path == "":
            return views.render_index(conn)
        if path == "/race":
            required = ("date", "track", "kaiji", "nichiji", "num")
            if not all(k in q for k in required):
                return None
            return views.render_race(conn, q["date"], q["track"], q["kaiji"],
                                     q["nichiji"], q["num"])
        if path == "/trends":
            frm, to = _default_trend_window()
            return views.render_trends(conn, frm, to, q.get("course"),
                                       q.get("factor", "sire_line"))
        if path == "/today":
            date = q.get("date") or _latest_race_date(conn)
            if not date:
                return "<h1>当日速報</h1><p>開催データがありません。</p>"
            return views.render_today(conn, date, q.get("factor", "waku"))
        return None


def run(host: str = "127.0.0.1", port: int = 8760, db_path: str | None = None) -> None:
    Handler.db_path = db_path
    server = ThreadingHTTPServer((host, port), Handler)
    logger.info("独自出馬表 webapp: http://%s:%d/  (Ctrl-C で停止)", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("停止しました")
    finally:
        server.server_close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="独自出馬表 webapp (ローカル自己利用)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8760)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    run(args.host, args.port, args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
