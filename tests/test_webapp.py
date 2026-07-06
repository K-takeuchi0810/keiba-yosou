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
          sire_breeding_num TEXT, dam_sire_name TEXT, dam_sire_breeding_num TEXT,
          sire_dam_sire_name TEXT, sire_dam_sire_breeding_num TEXT,
          dam_dam_sire_name TEXT, dam_dam_sire_breeding_num TEXT);
        CREATE TABLE payouts (race_year TEXT, race_month_day TEXT, track_code TEXT,
          kaiji TEXT, nichiji TEXT, race_num TEXT,
          tan_horse_num1 TEXT, tan_payout1 INTEGER, tan_horse_num2 TEXT, tan_payout2 INTEGER,
          tan_horse_num3 TEXT, tan_payout3 INTEGER);
        CREATE TABLE breeding_horses (breeding_num TEXT PRIMARY KEY, horse_name TEXT,
          sire_name TEXT, sire_breeding_num TEXT, birthplace TEXT);
        """
    )
    # B1: 父ディープ(産地=安平)、母父キンカメ、父母父ノーザンテースト(産地=米)、母母父トニービン
    conn.execute("INSERT INTO horse_masters VALUES ('B1','ディープインパクト','S1','キングカメハメハ','D1',"
                 "'ノーザンテースト','SD1','トニービン','DD1')")
    conn.execute("INSERT INTO horse_masters VALUES ('B2','キングカメハメハ','S2','母父Y','D2',"
                 "'','','','')")
    conn.execute("INSERT INTO breeding_horses VALUES ('S1','ディープインパクト','サンデーサイレンス','S9','安平')")
    conn.execute("INSERT INTO breeding_horses VALUES ('SD1','ノーザンテースト','ノーザンダンサー','S8','米')")
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
    assert "サンデー系" in html              # 父系統 (短縮ラベル)
    assert "#8bc34a" in html                 # sunday の色
    assert "キングマンボ系" in html           # 母父系統 (B1 の母父=キングカメハメハ)
    assert "#e57373" in html                 # kingmambo の色 (母父段の dot)
    assert "系統(父/母父)" in html            # 2 段表示ヘッダ
    assert "買い推奨ではありません" in html    # 誤読防止バナー
    assert "近3走" in html                    # SmartRC 相当のサブ行 (補助指標)
    assert "父×馬場" in html


def test_render_race_gen3_pedigree_and_origin():
    """父母父/母母父の系統表示と、繁殖馬マスタ由来の産地表示 (SmartRC パリティ)。"""
    conn = _db()
    html = views.render_race(conn, "20250518", "05", "01", "01", "01")
    assert html is not None
    # 補助行の 3 代血統: 名前(系統短/産地)
    assert "父母父 ノーザンテースト(ノーザンD系/米)" in html
    assert "母母父 トニービン(ナスルーラ系)" in html          # 産地未取込 → 系統のみ
    # 父列の産地サフィックス (S1=安平)
    assert "(安平)" in html
    # 国系統バッジ (亀谷分類): B1 の父ディープ=日本型 / B2 の父キンカメ=米国型。
    # 塗り潰しでなく枠線+テーマ色チップ (ctag-jpn/ctag-usa)、country_key 駆動。
    assert 'class="ctag ctag-jpn"' in html
    assert 'class="ctag ctag-usa"' in html
    assert "日本型" in html
    assert "米国型" in html
    # 凡例に国系統の暫定注記と軸一覧 (凡例ドリフト防止の固定 assert)
    assert "亀谷分類の日本型/米国型/欧州型・暫定" in html
    assert "父/母父国系統の各軸に対応" in html
    # 凡例は実表示と一致させる (「凡例と実表示の不一致」の 2 連続再発防止 —
    # gui-ux 監査。文言を変えたらこの assert も実表示と突合して更新する)
    assert "父/母父の丸括弧=産地" in html
    assert "丸括弧は 系統/産地（産地未取込時は系統のみ）" in html


def test_render_race_breeding_horses_without_birthplace():
    """breeding_horses に birthplace 列が無い旧スキーマでも 500 にならず産地なしで縮退。"""
    conn = _db()
    conn.executescript(
        """
        CREATE TABLE bh_old AS SELECT breeding_num, horse_name, sire_name,
          sire_breeding_num FROM breeding_horses;
        DROP TABLE breeding_horses;
        ALTER TABLE bh_old RENAME TO breeding_horses;
        """
    )
    html = views.render_race(conn, "20250518", "05", "01", "01", "01")
    assert html is not None
    assert "(安平)" not in html                              # 産地サフィックス消滅
    assert "父母父 ノーザンテースト(ノーザンD系)" in html      # 系統のみで継続


def test_render_race_old_schema_without_dam_sire_bn():
    """dam_sire_breeding_num 列が無い古い DB でも 500 にならず縮退表示できる。

    views.build_race の PRAGMA probe が欠如列を NULL に差し替える縮退経路を
    実際に通す regression (2026-07-05 監査の共通指摘)。
    """
    conn = _db()
    conn.executescript(
        """
        CREATE TABLE hm_old AS SELECT blood_register_num, sire_name,
          sire_breeding_num, dam_sire_name FROM horse_masters;
        DROP TABLE horse_masters;
        ALTER TABLE hm_old RENAME TO horse_masters;
        """
    )
    html = views.render_race(conn, "20250518", "05", "01", "01", "01")
    assert html is not None
    assert "サンデー系" in html       # 父系統は維持
    assert "キングマンボ系" in html    # 母父系統も名前照合のみで分類継続 (遡上なし縮退)


def test_race_rows_pair_and_alt_integrity():
    """mainrow と subrow は常に 1:1 ペアで、alt 縞も両行同数 (縞ズレ誤帰属の防止)。"""
    conn = _db()
    html = views.render_race(conn, "20250518", "05", "01", "01", "01")
    n_main = html.count('class="mainrow')
    n_sub = html.count('class="subrow')
    assert n_main == n_sub == 4                    # 4 頭 = 2 行 × 4 ペア
    assert html.count('"mainrow alt"') == html.count('"subrow alt"') == 2


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
