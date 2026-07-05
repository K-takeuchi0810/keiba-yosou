"""predictor/sire_lines.py の系統分類テスト。"""

from __future__ import annotations

import sqlite3

import predictor.sire_lines as sl


def test_direct_lookup():
    assert sl.classify_sire("ディープインパクト") == "sunday"
    assert sl.classify_sire("キングカメハメハ") == "kingmambo"
    assert sl.classify_sire("ロードカナロア") == "kingmambo"
    assert sl.classify_sire("ハービンジャー") == "northern"
    assert sl.classify_sire("モーリス") == "roberto"


def test_line_facts_regression():
    """2026-07-05 fable 監査で是正した誤分類 12 件の regression。父系事実に固定する。"""
    facts = {
        "ドゥラメンテ": "kingmambo",       # 父キングカメハメハ
        "リオンディーズ": "kingmambo",     # 父キングカメハメハ
        "ワークフォース": "kingmambo",     # 父キングズベスト
        "エピファネイア": "roberto",       # 父シンボリクリスエス
        "ヘニーヒューズ": "storm",         # 父ヘネシー
        "アジアエクスプレス": "storm",     # 父ヘニーヒューズ
        "パイロ": "nasrullah",            # A.P. Indy 系
        "シニスターミニスター": "nasrullah",
        "クロフネ": "northern",           # デピュティミニスター系
        "フレンチデピュティ": "northern",
        "マインドユアビスケッツ": "northern",
    }
    for name, expect in facts.items():
        assert sl.classify_sire(name) == expect, name
    # 10 大系統外は誤答せず unknown に落とす
    assert sl.classify_sire("ダノンレジェンド") == "unknown"


def test_line_facts_expansion_2026_07_05():
    """辞書拡充 (実機で非サンデー系が「その他」だらけになった対処) の父系事実固定。"""
    facts = {
        "コントレイル": "sunday",            # 父ディープインパクト
        "キンシャサノキセキ": "sunday",       # 父フジキセキ
        "ゴールドドリーム": "sunday",         # 父ゴールドアリュール
        "エイシンフラッシュ": "kingmambo",    # 父キングズベスト
        "キセキ": "kingmambo",               # 父ルーラーシップ
        "レッドファルクス": "mrprospector",   # 父スウェプトオーヴァーボード (Forty Niner 系)
        "アメリカンファラオ": "mrprospector", # Empire Maker → Unbridled → Fappiano
        "タワーオブロンドン": "mrprospector", # 父レイヴンズパス (Gone West 系)
        "ブリックスアンドモルタル": "storm",  # 父ジャイアンツコーズウェイ
        "ミスターメロディ": "storm",         # 父スキャットダディ (Johannesburg 系)
        "モズアスコット": "northern",        # 父フランケル (Galileo → Sadler's Wells)
        "サトノクラウン": "northern",        # 父マージュ (Last Tycoon 系)
        "サンダースノー": "northern",        # Exceed And Excel → Danehill → Danzig
        "ルヴァンスレーヴ": "roberto",       # 父シンボリクリスエス
        "ナダル": "roberto",                # 父ブレイム (Arch → Kris S.)
        "ビッグアーサー": "nasrullah",       # 父サクラバクシンオー (プリンスリーギフト系)
        "バゴ": "nasrullah",                # 父ナシュワン (Blushing Groom → Red God)
        "ジャングルポケット": "nasrullah",    # 父トニービン (Grey Sovereign 系)
        "マジェスティックウォリアー": "nasrullah",  # 父エーピーインディ
    }
    for name, expect in facts.items():
        assert sl.classify_sire(name) == expect, name


def test_short_labels_complete():
    assert set(sl.LINE_LABEL_SHORT) == set(sl.LINE_LABEL)
    assert sl.line_label_short("sunday") == "サンデー系"
    assert sl.line_label_short("架空") == "その他"


def test_normalize_fullwidth_space():
    # 末尾全角空白パディングを除去して照合できる
    assert sl.classify_sire("ディープインパクト　　") == "sunday"
    assert sl.classify_sire("  キズナ ") == "sunday"


def test_unknown_without_conn():
    assert sl.classify_sire("架空種牡馬XYZ") == "unknown"
    assert sl.classify_sire(None) == "unknown"
    assert sl.classify_sire("") == "unknown"


def test_no_dup_keys_lost():
    # 主要系統キーが全て LINE_LABEL/LINE_COLOR に存在
    for key in set(sl.LINE_BY_SIRE.values()) | set(sl.FOUNDERS.values()):
        assert key in sl.LINE_LABEL, key
        assert key in sl.LINE_COLOR, key


def test_labels_and_colors_complete():
    assert set(sl.LINE_LABEL) == set(sl.LINE_COLOR)
    assert sl.line_label("sunday") == "サンデーサイレンス系"
    assert sl.line_color("unknown") == "#bdbdbd"
    assert sl.line_label("架空") == "その他"


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE breeding_horses (breeding_num TEXT PRIMARY KEY, horse_name TEXT, "
        "sire_name TEXT, sire_breeding_num TEXT)"
    )
    return conn


def test_traversal_fallback():
    conn = _mem_db()
    # 未知の父 "新種牡馬A" (num=N1) の父が "ディープインパクト" (直接辞書ヒット)
    conn.execute("INSERT INTO breeding_horses VALUES ('N1','新種牡馬A','ディープインパクト','N2')")
    conn.commit()
    # 名前は辞書に無いが breeding_num 遡上で父=ディープ→sunday
    assert sl.classify_sire("新種牡馬A", conn=conn, sire_breeding_num="N1") == "sunday"


def test_traversal_multi_generation_to_founder():
    conn = _mem_db()
    # N1(新A) → 父 新B(N2) → 父 サンデーサイレンス (FOUNDERS)
    conn.execute("INSERT INTO breeding_horses VALUES ('N1','新A','新B','N2')")
    conn.execute("INSERT INTO breeding_horses VALUES ('N2','新B','サンデーサイレンス','N3')")
    conn.commit()
    assert sl.classify_sire("新A", conn=conn, sire_breeding_num="N1") == "sunday"


def test_traversal_cycle_guard():
    conn = _mem_db()
    # 自己ループでも無限ループしない
    conn.execute("INSERT INTO breeding_horses VALUES ('N1','ループ馬','ループ馬','N1')")
    conn.commit()
    assert sl.classify_sire("ループ馬X", conn=conn, sire_breeding_num="N1") == "unknown"


def test_traversal_missing_row():
    conn = _mem_db()
    # breeding_horses に該当なし → unknown (落ちない)
    assert sl.classify_sire("不明", conn=conn, sire_breeding_num="ZZ") == "unknown"


def test_traversal_table_absent_graceful():
    # breeding_horses テーブル自体が無い古い DB (BLOD 未取込 + readonly で
    # migration も走らない) でも例外を出さず unknown に劣化する
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert sl.classify_sire("不明", conn=conn, sire_breeding_num="ZZ") == "unknown"
