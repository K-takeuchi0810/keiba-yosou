"""webapp/views.py と server.py のレンダリング/ルーティングテスト。

DB は build_agg 相当の in-memory 合成データ。予想 (predict_race) 経路は
horse_masters/breeding のみで動く範囲を検証し、失敗時も出馬表が出ることを確認。
"""

from __future__ import annotations

import sqlite3

from webapp import views


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT,
          kaiji TEXT, nichiji TEXT, race_num TEXT, distance INTEGER, track_type_code TEXT,
          race_name TEXT, weather_code TEXT, turf_condition TEXT, dirt_condition TEXT,
          starter_count INTEGER);
        CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT,
          kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT, waku_num TEXT,
          blood_register_num TEXT, horse_name TEXT, jockey_short_name TEXT, jockey_code TEXT,
          trainer_short_name TEXT, trainer_code TEXT, confirmed_order INTEGER,
          win_popularity INTEGER, win_odds INTEGER, leg_quality_code TEXT);
        CREATE TABLE horse_masters (blood_register_num TEXT PRIMARY KEY, sire_name TEXT,
          sire_breeding_num TEXT, dam_sire_name TEXT);
        CREATE TABLE payouts (race_year TEXT, race_month_day TEXT, track_code TEXT,
          kaiji TEXT, nichiji TEXT, race_num TEXT,
          tan_horse_num1 TEXT, tan_payout1 INTEGER, tan_horse_num2 TEXT, tan_payout2 INTEGER,
          tan_horse_num3 TEXT, tan_payout3 INTEGER);
        CREATE TABLE breeding_horses (breeding_num TEXT PRIMARY KEY, horse_name TEXT,
          sire_name TEXT, sire_breeding_num TEXT);
        """
    )
    conn.execute("INSERT INTO horse_masters VALUES ('B1','ディープインパクト','S1','母父X')")
    conn.execute("INSERT INTO horse_masters VALUES ('B2','キングカメハメハ','S2','母父Y')")
    for i in range(30):
        key = ("2025", "0518", "05", "01", "01", f"{i + 1:02d}")
        conn.execute("INSERT INTO races VALUES (?,?,?,?,?,?,1600,'11','テストS','1','1','0',4)", key)
        for hn in range(1, 5):
            brn = "B1" if hn % 2 else "B2"
            order = 1 if hn == 1 else hn
            conn.execute(
                "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*key, f"{hn:02d}", str(hn), brn, f"馬{i}_{hn}", "ルメール", "J1",
                 "厩舎A", "T1", order, hn, 100 * hn, str((hn % 4) + 1)),
            )
        conn.execute(
            "INSERT INTO payouts (race_year,race_month_day,track_code,kaiji,nichiji,race_num,"
            "tan_horse_num1,tan_payout1) VALUES (?,?,?,?,?,?, '01', 250)", key)
    conn.commit()
    return conn


def test_render_index():
    html = views.render_index(_db())
    assert "開催日一覧" in html
    assert "東京" in html          # track_name(05)
    assert "2025/05/18" in html
    assert "/today?date=20250518" in html


def test_render_race_has_line_color_and_masters():
    conn = _db()
    html = views.render_race(conn, "20250518", "05", "01", "01", "01")
    assert html is not None
    assert "出馬表" in html
    assert "ディープインパクト" in html      # 父名表示
    assert "サンデーサイレンス系" in html     # 系統分類
    assert "#8bc34a" in html                 # sunday の色
    assert "買い推奨ではありません" in html    # 誤読防止バナー
    assert "近3走" in html                    # SmartRC 相当のサブ行 (補助指標)
    assert "父×馬場" in html


def test_render_race_missing_returns_none():
    conn = _db()
    assert views.render_race(conn, "20250518", "05", "01", "01", "99") is None


def test_render_trends_default_course():
    conn = _db()
    html = views.render_trends(conn, "20250101", "20251231", None, "sire_line", min_n=10)
    assert "傾向集計" in html
    assert "サンデーサイレンス系" in html
    assert "%" in html
    assert "95%CI" in html or "CI" in html


def test_build_trends_structure():
    conn = _db()
    ctx = views.build_trends(conn, "20250101", "20251231", "05|turf|1600", "sire", min_n=10)
    assert ctx["result"] is not None
    assert ctx["result"]["track_name"] == "東京"
    labels = [c["label"] for c in ctx["result"]["cells"]]
    assert "ディープインパクト" in labels


def test_render_today_waku_and_line():
    conn = _db()
    html_waku = views.render_today(conn, "20250518", "waku")
    assert "当日傾向速報" in html_waku
    assert "枠番別" in html_waku
    html_line = views.render_today(conn, "20250518", "sire_line")
    assert "父系統別" in html_line
    assert "サンデーサイレンス系" in html_line


def test_server_routing_smoke():
    # サーバのルーティング関数を直接叩く (ソケット無し)
    import types
    from webapp import server

    conn = _db()
    # _route は self を使わないメソッドなので、ダミーインスタンス経由で呼ぶ
    handler = types.SimpleNamespace(_route=server.Handler._route.__get__(object()))
    assert "開催日一覧" in handler._route(conn, "/", {})
    assert handler._route(conn, "/unknown", {}) is None
    today = handler._route(conn, "/today", {"date": "20250518", "factor": "waku"})
    assert "当日傾向速報" in today
    trends = handler._route(conn, "/trends", {"factor": "sire_line"})
    assert "傾向集計" in trends
