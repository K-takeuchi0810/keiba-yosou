"""中止 → 抑止 → 最終確認 heartbeat を、実際の HTTP POST まで通す E2E (2026-09-20)。

## なぜ別ファイルなのか

`test_notify_dedup.py` / `test_auto_predict_artifacts.py` は `_notify` を差し替えて
いるので、**送信そのものは 1 度も動いていない**。9/20 の本番実証では 08:00 時点で
出走馬が 24/24 そろっており、中止経路が 1 度も走らなかったため、

  - coverage_abort の通知と抑止
  - 最終確認 heartbeat
  - POST が失敗したときに記録しないこと

の 3 つが本番でも単体でも未検証のまま残った。自然発生する中止日 (月 1-2 回) を
待つ代わりに、ここで隔離して確かめる。

## 隔離の方法

  DB      : 一時 sqlite (本番 keiba.db は開かない)
  状態     : conftest の autouse fixture + NOTIFY_STATE_PATH で一時ファイル
  Discord : 127.0.0.1 のテスト Webhook。**実際に HTTP POST する**ので送信成否は
            本物 (`notify_discord` をスタブしていない)
  時刻     : 08:00 / 09:00 / 11:00 を模擬 (実行時刻に依らず同じ結果になるように)

中止経路は generator も git push も呼ばずに exit 2 で戻るので、publish 系には
一切触れない。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scripts import auto_predict
from scripts.notify_discord import notify_discord


@pytest.fixture()
def webhook(tmp_path):
    """POST を受け取って本文を貯めるテスト用 Webhook。

    `status` を変えると Discord 側の失敗を再現できる。
    """
    posts: list[str] = []
    status = [204]

    class Hook(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            posts.append(json.loads(body.decode("utf-8"))["content"])
            self.send_response(status[0])
            self.end_headers()

        def log_message(self, *a):  # アクセスログを黙らせる
            pass

    srv = HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    path = tmp_path / "webhook.txt"
    path.write_text(f"http://127.0.0.1:{srv.server_port}/hook", encoding="utf-8")
    try:
        yield {"posts": posts, "status": status, "file": path}
    finally:
        srv.shutdown()


@pytest.fixture()
def abort_day(tmp_path, monkeypatch, webhook):
    """出走馬が 1 頭も入っていない開催日を仕立て、実送信につなぐ。"""
    today = date.today().strftime("%Y%m%d")
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT)")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " horse_num TEXT)")
    for rn in ("01", "02", "03"):
        conn.execute("INSERT INTO races VALUES (?,?,'05','01','01',?)",
                     (today[:4], today[4:], rn))
    conn.commit()
    conn.close()

    monkeypatch.setattr(auto_predict, "DB_PATH", str(db))
    # 本番 Webhook ファイルの代わりにテスト Webhook を使う。
    # notify_discord 自体はそのままなので **POST は本物**。
    monkeypatch.setattr(auto_predict, "_notify",
                        lambda text: notify_discord(text, webhook_file=webhook["file"]))
    return today


def _run(monkeypatch, final: bool):
    """1 起動ぶん。`final` は 11:00 の最終起動かどうか (時刻の模擬)。"""
    monkeypatch.setattr(auto_predict, "_is_final_attempt", lambda: final)
    monkeypatch.setattr("sys.argv",
                        ["auto_predict"] + (["--final-attempt"] if final else []))
    return auto_predict.main()


def test_abort_day_sends_the_notice_once_then_a_heartbeat(
        abort_day, webhook, monkeypatch, capsys):
    """08:00 中止通知 → 09:00 抑止 → 11:00 最終確認、で計 2 通。

    本番で確認できなかった系列そのもの。実際に HTTP POST が飛ぶところまで見る。
    """
    posts = webhook["posts"]

    assert _run(monkeypatch, final=False) == 2
    assert len(posts) == 1, "初回の中止通知が飛んでいない"
    assert "出走馬が未取り込み" in posts[0]

    assert _run(monkeypatch, final=False) == 2
    assert len(posts) == 1, "2 回目が抑止されていない"

    assert _run(monkeypatch, final=True) == 2
    assert len(posts) == 2, f"最終確認が飛んでいない: {posts}"
    assert "最終確認" in posts[1]
    assert "正常に実行されました" in posts[1], "起動したこと自体が伝わらない"
    assert "観察専用" in posts[1]

    audit = [l for l in capsys.readouterr().out.splitlines()
             if l.startswith("notify-audit ")]
    assert "type=coverage_abort" in audit[0] and "decision=first_time" in audit[0]
    assert "delivered=ok recorded=ok" in audit[0]
    assert "decision=duplicate attempted=no" in audit[1]
    assert "type=final_confirmation" in audit[-1]


def test_the_heartbeat_does_not_break_the_abort_suppression(
        abort_day, webhook, monkeypatch):
    """heartbeat を送った後も、同じ中止通知は抑止されたままであること。

    heartbeat の記録が中止通知の記録を消すと、次の起動で中止通知がもう 1 通
    飛ぶ。`supersedes=False` で記録しているのはこのため。
    """
    posts = webhook["posts"]
    _run(monkeypatch, final=False)
    _run(monkeypatch, final=True)
    assert len(posts) == 2

    _run(monkeypatch, final=True)

    assert len(posts) == 2, f"heartbeat 後に中止通知が再送されている: {posts}"


def test_state_keeps_both_the_abort_and_the_heartbeat(
        abort_day, webhook, monkeypatch):
    """状態に中止と最終確認の両方が残ること。"""
    from scripts import notify_dedup

    _run(monkeypatch, final=False)
    _run(monkeypatch, final=True)

    state = json.loads(notify_dedup.state_path().read_text(encoding="utf-8"))
    assert sorted(state) == [f"coverage_abort:{abort_day}",
                            f"final_confirmation:{abort_day}"]


def test_a_rejected_post_is_retried_on_the_next_run(
        abort_day, webhook, monkeypatch):
    """Discord が 500 を返したら記録せず、次の起動で送り直すこと。

    ここだけは実際に HTTP の失敗を起こして確かめる。`notify_discord` は
    `urlopen` が例外を投げると False を返すので、`record` に到達しない。
    """
    posts = webhook["posts"]
    webhook["status"][0] = 500

    assert _run(monkeypatch, final=False) == 2
    assert len(posts) == 1, "送信自体は試みること"

    webhook["status"][0] = 204
    assert _run(monkeypatch, final=False) == 2

    assert len(posts) == 2, "届かなかった通知が再送されていない"
    assert posts[0] == posts[1]
