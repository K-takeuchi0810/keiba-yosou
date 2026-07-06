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


def test_line_facts_expansion_round2_2026_07_05():
    """辞書第 2 次拡充 (母父世代 + turnto 新設) の父系事実固定。"""
    facts = {
        "スペシャルウィーク": "sunday",       # SS 直仔
        "デュランダル": "sunday",            # SS 直仔
        "カネヒキリ": "sunday",              # 父フジキセキ
        "エルコンドルパサー": "kingmambo",    # 父キングマンボ
        "レモンポップ": "kingmambo",         # 父レモンドロップキッド (Kingmambo 直仔)
        "アイルハヴアナザー": "mrprospector", # Flower Alley → Distorted Humor → Forty Niner
        "エンパイアメーカー": "mrprospector", # 父アンブライドルド (Fappiano 系)
        "アグネスデジタル": "mrprospector",   # 父クラフティプロスペクター
        "エスケンデレヤ": "storm",           # 父ジャイアンツコーズウェイ
        "キングヘイロー": "northern",        # 父ダンシングブレーヴ (Lyphard 系)
        "メイショウサムソン": "northern",     # 父オペラハウス (Sadler's Wells 系)
        "デインヒルダンサー": "northern",     # 父デインヒル (Danzig 系)
        "マヤノトップガン": "roberto",       # 父ブライアンズタイム
        "タイキシャトル": "turnto",          # 父デヴィルズバッグ (Halo 非 SS 枝)
        "ニシケンモノノフ": "turnto",        # メイショウボーラー → タイキシャトル
        "トウショウボーイ": "nasrullah",     # 父テスコボーイ (プリンスリーギフト系)
        "タピット": "nasrullah",            # 父プルピット (A.P. Indy 系)
        "カコイーシーズ": "native",          # 父アリダー (Raise a Native 系)
        "トランセンド": "nearctic",          # ワイルドラッシュ → Wild Again → Icecapade
    }
    for name, expect in facts.items():
        assert sl.classify_sire(name) == expect, name


def test_turnto_founder_stop_is_not_roberto():
    """FOUNDERS のヘイルトゥリーズン/ヘイローは turnto (旧: roberto 便宜寄せの是正)。
    Roberto 系の遡上は「ロベルト」で先に停止するので roberto のまま。"""
    assert sl.FOUNDERS["ヘイルトゥリーズン"] == "turnto"
    assert sl.FOUNDERS["ヘイロー"] == "turnto"
    assert sl.FOUNDERS["ロベルト"] == "roberto"
    conn = _mem_db()
    # 新X → 父 クリスエス(N2) → 父 ロベルト → (ヘイルトゥリーズンまで行かず停止)
    conn.execute("INSERT INTO breeding_horses VALUES ('N1','新X','クリスエス','N2')")
    conn.execute("INSERT INTO breeding_horses VALUES ('N2','クリスエス','ロベルト','N3')")
    conn.commit()
    assert sl.classify_sire("新X", conn=conn, sire_breeding_num="N1") == "roberto"


def test_country_classification_defaults():
    """亀谷分類 (国別血統) の系統既定値。2022 改訂: 日本型=SS系のみ。

    注: 本 country 系テスト群は「実装した既定値の回帰固定」であり事実検証ではない
    (実装と同じ根拠から書いた写しなので循環)。亀谷公式リストとの突合は
    docs/OPERATION.md「亀谷公式リスト突合」節の手動手順で行う (JV-Link 内に独立
    ソースが無いため audit_sire_lines のような DB 突合では確定できない)。
    """
    # 日本型 = サンデーサイレンス系
    assert sl.classify_country("ディープインパクト", "sunday") == "jpn"
    assert sl.classify_country("キタサンブラック", "sunday") == "jpn"
    # 米国型 = ミスプロ/ストキャ/ネイティヴ/A.P.Indy 系
    assert sl.classify_country("ロードカナロア", "kingmambo") == "usa"
    assert sl.classify_country("ヘニーヒューズ", "storm") == "usa"
    assert sl.classify_country("エーピーインディ", "nasrullah") == "usa"
    # 欧州型 = ノーザンダンサー欧州系/ロベルト系
    assert sl.classify_country("ハービンジャー", "northern") == "eur"
    assert sl.classify_country("モーリス", "roberto") == "eur"


def test_country_override_nasrullah_european_branch():
    """ナスルーラ系でも欧州分枝 (Grey Sovereign/Blushing Groom) は override で欧州型。
    A.P.Indy 系 (米国型) と血の質が分かれる点を種牡馬単位で解決する。"""
    assert sl.classify_country("トニービン", "nasrullah") == "eur"
    assert sl.classify_country("ジャングルポケット", "nasrullah") == "eur"
    assert sl.classify_country("バゴ", "nasrullah") == "eur"
    # 同系統でも A.P.Indy 枝は既定の米国型のまま
    assert sl.classify_country("タピット", "nasrullah") == "usa"


def test_country_labels_colors_complete_and_unknown():
    assert set(sl.COUNTRY_LABEL) == set(sl.COUNTRY_COLOR)
    assert sl.country_label("jpn") == "日本型"
    assert sl.country_label("usa") == "米国型"
    assert sl.country_label("eur") == "欧州型"
    # 判別不能系統は unknown → ラベル「判別不能」(sire_line 軸の「その他」と区別)
    assert sl.classify_country("架空種牡馬", "unknown") == "unknown"
    assert sl.country_label("unknown") == "判別不能"


def test_country_by_line_parity_with_line_label():
    """COUNTRY_BY_LINE は LINE_LABEL の全系統キーを網羅する (系統追加時の割当漏れを
    fail-fast。漏れると .get(line_key, 'unknown') で黙ってバッジが消える)。"""
    assert set(sl.COUNTRY_BY_LINE) == set(sl.LINE_LABEL)


def test_country_override_keys_exist_in_sire_dict():
    """COUNTRY_OVERRIDE の種牡馬名は LINE_BY_SIRE に実在する (typo で無効な
    override が黙って line 既定値に落ちるのを防ぐ)。"""
    assert set(sl.COUNTRY_OVERRIDE) <= set(sl.LINE_BY_SIRE)


def test_country_confirmed_error_fixes_2026_07_05():
    """予想ロジック監査で確定誤りとされた分類の regression。
    ND 北米発展枝 (Deputy Minister/War Front) とロベルト系米国残留枝を米国型に固定。"""
    # クロフネ等 Deputy Minister 枝: northern 既定 eur → override で usa
    assert sl.classify_country("クロフネ", "northern") == "usa"
    assert sl.classify_country("フレンチデピュティ", "northern") == "usa"
    assert sl.classify_country("マインドユアビスケッツ", "northern") == "usa"
    # War Front 枝
    assert sl.classify_country("デクラレーションオブウォー", "northern") == "usa"
    # ナダル: roberto 既定 eur → override で usa (Kris S. 米国残留枝)
    assert sl.classify_country("ナダル", "roberto") == "usa"
    # モーリス/エピファネイアは roberto 既定 eur のまま (亀谷公表と整合)
    assert sl.classify_country("モーリス", "roberto") == "eur"


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


def test_audit_traversal_only_uses_founders_not_dict():
    """audit_sire_lines の独立遡上は LINE_BY_SIRE を使わず FOUNDERS のみで判定する
    (辞書との循環検証を避ける設計の regression)。"""
    from scripts.audit_sire_lines import traversal_only_classify

    conn = _mem_db()
    # N1(新A) → 父 ディープインパクト(N2) → 父 サンデーサイレンス (FOUNDERS)
    conn.execute("INSERT INTO breeding_horses VALUES ('N1','新A','ディープインパクト','N2')")
    conn.execute("INSERT INTO breeding_horses VALUES ('N2','ディープインパクト','サンデーサイレンス','N3')")
    conn.commit()
    # ディープインパクトは LINE_BY_SIRE に居るが、独立遡上は辞書を見ないため
    # FOUNDERS (サンデーサイレンス) まで遡って初めて sunday になる
    assert traversal_only_classify(conn, "N1") == "sunday"
    assert traversal_only_classify(conn, "ZZ") == "unknown"   # HN 欠損
    assert traversal_only_classify(conn, None) == "unknown"


def test_traversal_table_absent_graceful():
    # breeding_horses テーブル自体が無い古い DB (BLOD 未取込 + readonly で
    # migration も走らない) でも例外を出さず unknown に劣化する
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert sl.classify_sire("不明", conn=conn, sire_breeding_num="ZZ") == "unknown"
