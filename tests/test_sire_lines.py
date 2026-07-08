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


def test_every_line_has_founder_stop_point():
    """LINE_BY_SIRE に現れる全 line_key は FOUNDERS の停止点にも存在する
    (2026-07-08 code-quality 監査の変更失敗モード対策)。新 line を追加したのに
    FOUNDERS へ遡上停止点を登録し忘れると、その系統の dict 未収載子孫が BLOD 遡上で
    親系統 (例 Nasrullah) の founder まで素通りし、例外も出さず親系統ラベルへ silent
    誤分類する。この構造ガードで停止点の網羅漏れを fail-fast にする。"""
    lines = set(sl.LINE_BY_SIRE.values()) - {"unknown"}
    founder_lines = set(sl.FOUNDERS.values())
    missing = lines - founder_lines
    assert not missing, f"FOUNDERS 停止点が無い line: {sorted(missing)}"


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


def test_country_branch_overrides_2026_07_06():
    """予想ロジック監査 (2026-07-06 バッチ) の country 軸是正 regression。
    父系 male-line の line_key は正しいが、国別が line 既定と割れる枝の個別補正。"""
    # High Top: nearctic 既定 usa → override eur (英 2000 ギニー馬・全英供用の Nearco 欧州枝)
    assert sl.classify_country("ハイトップ", "nearctic") == "eur"
    assert sl.classify_country("High Top", "nearctic") == "eur"
    # Hold Your Peace: stsimon 既定 eur → override usa (Prince John 枝・米国産米国供用)。
    # 同枝の Meadowlake=usa と対称。
    assert sl.classify_country("ホールドユアピース", "stsimon") == "usa"
    assert sl.classify_country("Hold Your Peace", "stsimon") == "usa"
    assert sl.classify_country("メドウレイク", "stsimon") == "usa"
    # Silver Shark: manowar 既定 usa → override eur (仏スプリンター・Relic 仏発展枝)
    assert sl.classify_country("シルバーシャーク", "manowar") == "eur"
    assert sl.classify_country("Silver Shark", "manowar") == "eur"


def test_no_duplicate_literal_dict_keys():
    """sire_lines.py の全 dict リテラルに重複キーが無いこと (2026-07-06 code-quality)。
    len parity は正規化衝突しか見ないが、リテラル完全重複は Python が評価前に畳むため
    後勝ちで無音上書きする。ast でソースを直接検査して fail-fast 化する。"""
    import ast
    from pathlib import Path
    tree = ast.parse(Path(sl.__file__).read_text(encoding="utf-8"))
    dups = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            dups += [k for k in set(keys) if keys.count(k) > 1]
    assert not dups, f"重複リテラルキー: {dups}"


def test_english_katakana_alias_consistency():
    """英語名とカタカナ名が併存する主要ペアで系統・国別が一致 (2026-07-06 code-quality
    /profitability: 片側だけ是正した際の静かな乖離を fail-fast)。"""
    pairs = [
        ("Northern Dancer", "ノーザンダンサー"), ("Storm Cat", "ストームキャット"),
        ("Mr. Prospector", "ミスタープロスペクター"), ("Kingmambo", "キングマンボ"),
        ("Seattle Slew", "シアトルスルー"), ("A.P. Indy", "エーピーインディ"),
        ("Roberto", "ロベルト"), ("Halo", "ヘイロー"), ("Mill Reef", "ミルリーフ"),
        ("Native Dancer", "ネイティヴダンサー"),
        # 2026-07-06 country 是正で英語名を対で追加した枝別 override。片側だけ将来
        # 是正したときに黙って line 既定へ落ちる silent-failure を汎用ガードで捕捉する
        # (code-quality 監査の推奨: 個別 regression だけに頼らない)。
        ("High Top", "ハイトップ"), ("Hold Your Peace", "ホールドユアピース"),
        ("Silver Shark", "シルバーシャーク"),
    ]
    for en, ja in pairs:
        assert sl.classify_sire(en) == sl.classify_sire(ja), f"{en} != {ja} (系統)"
        lk = sl.classify_sire(ja)
        assert sl.classify_country(en, lk) == sl.classify_country(ja, lk), f"{en} 国別不一致"


def test_normalize_punct_and_fullwidth_folding():
    """NFKC + 記号/空白畳み込みで綴り変種を吸収 (2026-07-06 data-pipeline P2 / R-4)。"""
    # ピリオド/スペース変種
    assert sl.classify_sire("Mr.Prospector") == sl.classify_sire("Mr. Prospector") == "mrprospector"
    assert sl.classify_sire("A.P.Indy") == sl.classify_sire("A.P. Indy") == "nasrullah"
    assert sl.classify_sire("Kris S") == sl.classify_sire("Kris S.") == "roberto"
    # 全角ローマ字・連続空白・アポストロフィ字種
    assert sl.classify_sire("Ａｌｚａｏ") == "northern"
    assert sl.classify_sire("Northern  Dancer") == "northern"
    assert sl.classify_sire("Sadler’s Wells") == sl.classify_sire("Sadler's Wells") == "northern"


def test_english_key_length_budget():
    """英語キーは 20 字以内 (出馬表 subrow の折返し予算。2026-07-06 mobile #3)。
    超長名を系統付きで出すと 320px で溢れる。"""
    long = [k for k in sl.LINE_BY_SIRE if k.isascii() and len(k) > 20]
    assert not long, f"20字超の英語キー: {long}"


def test_normalized_lookup_no_key_collision():
    """仮名正規化 (小書き→大書き) で辞書キーが衝突しないこと。衝突すると dict 内包の
    後勝ちで 1 エントリが無音で消える (2026-07-06 code-quality P2 / validation R-3)。
    将来「シャ」表記と「シヤ」表記を両方追加した等の事故を fail-fast 化する。"""
    assert len(sl._LINE_BY_SIRE_N) == len(sl.LINE_BY_SIRE)
    assert len(sl._FOUNDERS_N) == len(sl.FOUNDERS)
    assert len(sl._COUNTRY_OVERRIDE_N) == len(sl.COUNTRY_OVERRIDE)


def test_short_labels_complete():
    assert set(sl.LINE_LABEL_SHORT) == set(sl.LINE_LABEL)
    assert sl.line_label_short("sunday") == "サンデー系"
    assert sl.line_label_short("架空") == "その他"


def test_non_top11_lines_classify():
    """11 大系統外でも名の通った系統は「その他」でなく系統名で分類する
    (2026-07-06 ユーザ要望: 11大系統外も系統国表示)。"""
    # パーソロン系 (実 DB unknown 上位に居たトウカイテイオー/シンボリルドルフ/メジロマックイーン)
    assert sl.classify_sire("シンボリルドルフ") == "personon"
    assert sl.classify_sire("トウカイテイオー") == "personon"
    assert sl.classify_sire("メジロマックイーン") == "personon"
    # セントサイモン系 / ハイペリオン系
    assert sl.classify_sire("Ribot") == "stsimon"
    assert sl.classify_sire("Princequillo") == "stsimon"
    assert sl.classify_sire("Hyperion") == "hyperion"
    # マンノウォー系 (Man o'War → Fair Play。米国基礎系統)
    assert sl.classify_sire("マンノウォー") == "manowar"
    assert sl.classify_sire("タイテエム") == "manowar"      # → War Relic → Man o'War
    assert sl.classify_country("タイテエム", "manowar") == "usa"
    # 系統名は実系統名で出る (「その他」でない)
    assert sl.line_label("personon") == "パーソロン系"
    # 国系統も出る (判別不能でない)。classify_country は line_key から国を決める。
    assert sl.classify_country("メジロマックイーン", "personon") == "eur"
    # country_label は「国キー」を受ける (line_key を渡すと判別不能になる区別を固定)。
    assert sl.country_label("eur") == "欧州型"
    assert sl.country_label("personon") == "判別不能"
    # 注: personon の eur は founder 由来の「暫定」(亀谷公式リスト未突合、OPERATION.md §10-1)。
    # 公式突合で型が変われば本アサートも更新する。
    # 真に系統不明なものは依然 unknown (誤答よりその他が誠実)
    assert sl.classify_sire("架空種牡馬ZZ") == "unknown"


def test_historic_unknown_top_sires_classify():
    """実機 unknown 上位に居た歴史的な父を、DB の大書き仮名スペルのまま系統+国系統
    に解決できることを固定 (2026-07-06 実機突合)。誤答防止のため父系 founder まで
    確度の高いものだけ収載。国系統も判別不能でないことを確認する。"""
    cases = {
        "ミルジヨージ": ("neverbend", "eur"),        # 父ミルリーフ → Never Bend (亀谷=ネヴァーベンド系)
        "ブレイヴエストローマン": ("neverbend", "eur"),  # 父 Never Bend
        "キンググローリアス": ("nasrullah", "usa"),   # 父 Naskra → Nasram → Nasrullah
        "ロイヤルスキー": ("nasrullah", "usa"),       # 父 Raja Baba → Bold Ruler
        "アローエクスプレス": ("neverbend", "eur"),   # 父 Never Beat → Never Bend
        "イエローゴツド": ("nasrullah", "eur"),       # 父 Red God (欧州枝) → COUNTRY_OVERRIDE eur
        "モガミ": ("northern", "eur"),               # 父 Lyphard → Northern Dancer
        "ノーザンデイクテイター": ("northern", "eur"), # 父 Northern Dancer
        "ホリスキー": ("northern", "eur"),           # 父マルゼンスキー → Nijinsky
        "ヤマニンスキー": ("northern", "eur"),        # 父 Nijinsky
        "アサティス": ("northern", "eur"),           # 父 Topsider
        "スリルシヨー": ("northern", "eur"),          # 父 Northern Baby
        "ロドリゴデトリアーノ": ("northern", "eur"),   # 父 El Gran Senor
        "マツリダゴツホ": ("sunday", "jpn"),          # 父サンデーサイレンス
        "タヤスツヨシ": ("sunday", "jpn"),            # 父サンデーサイレンス
    }
    for name, (line, country) in cases.items():
        k = sl.classify_sire(name)
        assert k == line, f"{name}: {k} != {line}"
        assert sl.classify_country(name, k) == country, name
        assert sl.line_label_short(k) != "その他", name


def test_audit_top_unknown_sires_classify():
    """実機 audit (2026-07-06) の unknown 上位を、DB の大書き仮名 / 英語スペルのまま
    系統+国系統に解決できることを固定。父系 founder まで確度の高いもののみ収載。"""
    cases = {
        # 大書き仮名 (母父/父母父で頻出の古い父)
        "ネヴアービート": ("neverbend", "eur"),   # Never Beat → Never Bend (亀谷=ネヴァーベンド系)
        "ヴエンチア": ("manowar", "usa"),         # Venture VII → Relic → War Relic → Man o'War
        "チヤイナロツク": ("hyperion", "eur"),     # China Rock → Rockefella → Hyperion
        "フアバージ": ("stsimon", "eur"),         # Faberge II → Prince Bio → Prince Rose
        "シヤトーゲイ": ("hyperion", "eur"),       # Chateaugay → Swaps → Khaled → Hyperion
        "シンザン": ("stsimon", "eur"),           # 父ヒンドスタン (Bois Roussel = St. Simon)
        "フオルテイノ": ("nasrullah", "eur"),      # Fortino → Grey Sovereign (仏欧州枝→eur override)
        "ボールドリツク": ("nasrullah", "usa"),    # Bold Ruckus → Boldnesian → Bold Ruler
        # 英語スペル (UM 3代血統の海外祖先。小文字連結で格納)
        "lefabuleux": ("stsimon", "eur"),        # Le Fabuleux → Rabelais → St. Simon
        "lasttycoon": ("northern", "eur"),       # Last Tycoon → Try My Best → Northern Dancer
        "kris": ("native", "usa"),               # Kris → Sharpen Up → Atan → Native Dancer
        "wildagain": ("nearctic", "usa"),        # Wild Again → Icecapade → Nearctic
        "lawsociety": ("stsimon", "eur"),        # Law Society → Tom Rolfe → Ribot
        "chiefscrown": ("northern", "eur"),      # Chief's Crown → Danzig → Northern Dancer
        # audit 2 巡目の追加
        "alleged": ("stsimon", "eur"),           # Alleged → Hoist the Flag → Tom Rolfe → Ribot
        "ターゴワイス": ("stsimon", "eur"),        # Targowice → Round Table → Princequillo
        "worden": ("stsimon", "eur"),            # Worden → Wild Risk → Rabelais → St. Simon
        "meadowlake": ("stsimon", "usa"),        # 系統 stsimon だが米国産 → COUNTRY_OVERRIDE usa
        "vaguelynoble": ("hyperion", "eur"),     # Vaguely Noble → Vienna → Aureole → Hyperion
        "mining": ("mrprospector", "usa"),       # 父 Mr. Prospector
        "ステイールハート": ("turnto", "usa"),      # Steel Heart → Habitat → Sir Gaylord → Turn-to
        # audit 3 巡目 (pycache 一掃後の新 unknown 上位)
        "rahy": ("nasrullah", "usa"),            # Rahy → Blushing Groom → Red God → Nasrullah
        "yourhost": ("hyperion", "eur"),         # Your Host → Alibhai → Hyperion
        "hornbeam": ("hyperion", "eur"),         # Hornbeam → Hyperion
        "stardenaskra": ("nasrullah", "usa"),    # Star de Naskra → Naskra → Nasram → Nasrullah
        "ダイアトム": ("stsimon", "eur"),          # Diatome → Sicambre → Prince Bio → Prince Rose
    }
    for name, (line, country) in cases.items():
        k = sl.classify_sire(name)
        assert k == line, f"{name}: {k} != {line}"
        assert sl.classify_country(name, k) == country, name
        assert sl.line_label_short(k) != "その他", name
    # 誤って Alydar を stsimon にした placeholder 混入の回帰ガード (native が正)
    assert sl.classify_sire("アリダー") == "native"


def test_english_ancestor_names_classify():
    """UM 3 代血統は海外祖先を英語で格納する。英語名でも系統が引け、大小差を吸収
    することを固定 (2026-07-06 父母父/母母父が英語名で「その他」化していた対処)。"""
    # verify_pedigree で実際に観測された父母父/母母父
    assert sl.classify_sire("Alzao") == "northern"        # 父 Lyphard
    assert sl.classify_sire("Riverman") == "neverbend"    # 父 Never Bend (亀谷=ネヴァーベンド系)
    assert sl.classify_sire("Affirmed") == "native"       # Raise a Native 系
    assert sl.classify_sire("Silver Ghost") == "mrprospector"  # 父 Mr. Prospector
    assert sl.classify_sire("Seattle Slew") == "nasrullah"
    # 大小差の吸収 (小文字化)
    assert sl.classify_sire("ALZAO") == sl.classify_sire("alzao") == "northern"
    # 主要国際種牡馬
    assert sl.classify_sire("Sadler's Wells") == "northern"
    assert sl.classify_sire("Storm Cat") == "storm"
    assert sl.classify_sire("Halo") == "turnto"
    assert sl.classify_sire("Roberto") == "roberto"


def test_normalize_large_kana_jvdata_convention():
    """JV-Data は大書き仮名 (ヤ/ユ/ヨ/ツ) で馬名を格納する。小書き仮名の辞書キーと
    照合できることを固定 (2026-07-06 実 DB で多数の既知種牡馬が小書き差で「その他」
    落ちしていた構造バグの regression)。"""
    # 辞書キーは小書き (リアルシャダイ/アンバーシャダイ/トウショウボーイ) だが
    # DB は大書き (シヤ/シヨ) — どちらでも同じ系統に解決する
    assert sl.classify_sire("リアルシヤダイ") == sl.classify_sire("リアルシャダイ") == "roberto"
    assert sl.classify_sire("アンバーシヤダイ") == "northern"
    assert sl.classify_sire("トウシヨウボーイ") == "nasrullah"
    # 小書きッ→大書きツ
    assert sl._normalize("マツリダゴッホ") == sl._normalize("マツリダゴツホ")


def test_line_facts_unknown_reduction_2026_07_06():
    """実 DB の unknown 上位から追加した高頻度種牡馬の父系事実固定。"""
    facts = {
        "アフリート": "mrprospector",       # 父ミスタープロスペクター
        "ヘクタープロテクター": "mrprospector",  # 父ウッドマン
        "ケイムホーム": "mrprospector",      # 父ゴーンウェスト
        "フサイチコンコルド": "northern",     # 父カーリアン (Nijinsky 系)
        "アジュディケーティング": "northern", # 父ダンチヒ
        "ミスターシービー": "nasrullah",     # 父トウショウボーイ
        "パラダイスクリーク": "neverbend",    # 父アイリッシュリヴァー → Riverman → Never Bend
        "リンドシェーバー": "native",         # 父アリダー
        "ニホンピロウイナー": "turnto",       # 父スティールハート (Sir Gaylord 系)
    }
    for name, expect in facts.items():
        assert sl.classify_sire(name) == expect, name
    # パラダイスクリークは neverbend 移設で国別が usa→eur に変化 (父アイリッシュリヴァー=仏
    # Riverman 系)。silent flip を防ぐため country も明示固定 (2026-07-08 code-quality 監査)。
    assert sl.classify_country("パラダイスクリーク", "neverbend") == "eur"


def test_normalize_fullwidth_space():
    # 末尾全角空白パディングを除去して照合できる
    assert sl.classify_sire("ディープインパクト　　") == "sunday"
    assert sl.classify_sire("  キズナ ") == "sunday"


def test_normalize_strips_halfwidth_kana_bleed():
    """breeding_horses(HN) の馬名は parse 上、末尾に隣接フィールド(半角カナ名)の
    先頭が混入する (2026-07-06 実機: 'ディープインパクト　…　ﾃﾞ' 等)。末尾の半角カナ
    混入を剥がして、クリーンな UM 父名と正規化一致することを固定。"""
    # bleed 付き (全角名+全角空白+半角カナ) がクリーン名と同じキーに正規化される
    assert sl._normalize("ディープインパクト　　　ﾃﾞ") == sl._normalize("ディープインパクト")
    assert sl._normalize("サンデーサイレンス　　　ｻﾞ") == sl._normalize("サンデーサイレンス")
    assert sl._normalize("ラオンジヤツク　　　　　ﾌﾞ") == sl._normalize("ラオンジヤツク")
    # 正常名・英名・辞書キーは影響を受けない (末尾が半角カナでない)
    assert sl.classify_sire("ディープインパクト") == "sunday"
    assert sl.classify_sire("Storm Cat") == "storm"
    assert sl.classify_sire("Alzao") == "northern"


def test_name_based_traversal_when_breeding_num_mismatches():
    """UM 3代血統の sire_breeding_num が HN の breeding_num と採番系不一致な実 DB
    (2026-07-06 実機: breeding_num 一致率 0.6%) の救済。辞書に無い父でも、名前で
    breeding_horses を引いて HN の breeding_num を得てから内部ポインタで遡上し、
    祖先名が founder に届けば分類する。名前照合は _normalize で仮名/空白揺れを吸収。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE breeding_horses (breeding_num TEXT PRIMARY KEY, "
                 "horse_name TEXT, sire_name TEXT, sire_breeding_num TEXT)")
    # 辞書に無い架空父 → 中間馬 → ノーザンダンサー(founder)。HN 内部番号 H1/H2/H3。
    conn.executemany("INSERT INTO breeding_horses VALUES (?,?,?,?)", [
        ("H1", "マイナー種牡馬X", "", "H2"),
        ("H2", "マイナー中間馬Y", "", "H3"),
        ("H3", "ノーザンダンサー", "", "H4"),
        ("H9", "テスト　シヤダイ", "", "H1"),  # 全角空白+大書き仮名の揺れ
    ])
    conn.commit()
    assert sl.lookup_line("マイナー種牡馬X") is None  # 辞書には無い
    # UM 由来 breeding_num は HN と一致しない ('UMxxxx') が、名前入口で遡上できる
    assert sl.classify_sire("マイナー種牡馬X", conn=conn, sire_breeding_num="UMxxxx") == "northern"
    # 表記揺れ (全角空白/小書き→大書き) も _normalize で吸収して入口一致
    assert sl.classify_sire("テストシャダイ", conn=conn, sire_breeding_num="UMyyy") == "northern"
    # 名前も breeding_horses に無ければ unknown (誤答より unknown)
    assert sl.classify_sire("全く未知の父ZZ", conn=conn, sire_breeding_num="UMzzz") == "unknown"


def test_finetop_line_and_brians_time():
    """ファイントップ系 (仏 Fine Top→Sanctus→Dictus) の追加と、ロベルト系の
    Brian's Time 枝。ユーザ指摘 (デイクタス=ディクタス が「その他」) への対処 +
    ナリタブライアンを誤って finetop にした混入の回帰ガード (正: roberto)。"""
    assert sl.classify_sire("デイクタス") == "finetop"      # DB 大書き仮名
    assert sl.classify_sire("ディクタス") == "finetop"
    assert sl.classify_sire("サッカーボーイ") == "finetop"
    assert sl.classify_country("ディクタス", "finetop") == "eur"
    assert sl.line_label("finetop") == "ファイントップ系"
    # ナリタブライアン/マヤノトップガンは父ブライアンズタイム = Roberto (finetop でない)
    assert sl.classify_sire("ナリタブライアン") == "roberto"
    assert sl.classify_sire("ブライアンズタイム") == "roberto"


def test_batch_teddy_herbager_blandford_and_existing():
    """unknown 上位(産駒数順)の確度の高い追加。既存 line への収載 + 古典基礎系統
    (Teddy/Herbager/Blandford) の named line 化。DB 大書き仮名でも解決。"""
    cases = {
        # 既存 line
        "slewpy": ("nasrullah", "usa"),          # Slewpy → Seattle Slew → Bold Ruler
        # Hold Your Peace: 父系は stsimon だが Prince John 枝=米国産米国供用 → usa
        # (2026-07-06 監査で Meadowlake=usa との非対称を是正)
        "holdyourpeace": ("stsimon", "usa"),     # Hold Your Peace → … → Princequillo → St. Simon
        # High Top: nearctic だが英 2000 ギニー馬・全英供用 (Nearco 欧州枝) → eur
        "hightop": ("nearctic", "eur"),          # High Top → Derring-Do → Darius → Dante → Nearco
        # Silver Shark: manowar だが仏スプリンター (Relic 仏発展枝) → eur
        "シルバーシヤーク": ("manowar", "eur"),    # Silver Shark → Buisson Ardent → Relic → Man o'War
        # 新 named line
        "victoriapark": ("teddy", "eur"),        # → Chop Chop → … → Sir Gallahad III → Teddy
        "シーホーク": ("herbager", "eur"),         # Sea Hawk II、父 Herbager
        "リマンド": ("blandford", "eur"),          # Remand → Alcide → Alycidon → … → Blandford
    }
    for name, (line, country) in cases.items():
        k = sl.classify_sire(name)
        assert k == line, f"{name}: {k} != {line}"
        assert sl.classify_country(name, k) == country, name
        assert sl.line_label_short(k) != "その他", name
    assert sl.line_label("teddy") == "テディ系"
    assert sl.line_label("herbager") == "エルバジェ系"
    assert sl.line_label("blandford") == "ブランドフォード系"


def test_batch_live_webapp_broodmare_sires_2026_07_08():
    """実 webapp 出馬表を HTTP でレンダして「その他」化していた現代の主要母父/母母父の
    継続追加 regression。父系 male-line が founder まで確度が高いもののみ (低確度は unknown
    据置)。

    実 webapp の母父セル (views.py classify_sire(dam_sire, ...)) に流れる dam_sire_name は
    JVData master 由来で**カナが主経路**。英語名 (3 代血統=父母父/母母父) だけ検証すると、
    将来カナキーが typo/削除された際にこの test は緑のまま実機の母父セルだけ静かに「その他」
    へ回帰する (code-quality 監査 2026-07-08 指摘の変更失敗モード)。よって**カナ・英語の
    両側を必ず assert** する。"""
    cases = {
        # カナ (母父=実 webapp 主経路)                     英語 (3 代血統=父母父/母母父経路)
        "スマートストライク": ("mrprospector", "usa"),  "Smart Strike": ("mrprospector", "usa"),
        "ミスターグリーリー": ("mrprospector", "usa"),  "Mr. Greeley": ("mrprospector", "usa"),
        "モティベーター": ("northern", "eur"),          "Motivator": ("northern", "eur"),
        "バラシア": ("northern", "eur"),                "Barathea": ("northern", "eur"),
        "ゴーストザッパー": ("northern", "usa"),        "Ghostzapper": ("northern", "usa"),
        "シルヴァーデピュティ": ("northern", "usa"),    "Silver Deputy": ("northern", "usa"),
        "ヴィンディケーション": ("nasrullah", "usa"),   "Vindication": ("nasrullah", "usa"),
        "オールアメリカン": ("roberto", "usa"),         "All American": ("roberto", "usa"),
        "バスティーノ": ("blandford", "eur"),           "Bustino": ("blandford", "eur"),
        "ハイセイコー": ("hyperion", "eur"),             # 日本馬 (英名なし)。父チャイナロック→Rockefella→Hyperion
    }
    for name, (line, country) in cases.items():
        k = sl.classify_sire(name)
        assert k == line, f"{name}: {k} != {line}"
        assert sl.classify_country(name, k) == country, name
        assert sl.line_label_short(k) != "その他", name


def test_batch_real_db_intl_broodmare_sires_2026_07_08():
    """実 DB フィードバック (ユーザ指摘の Oasis Dream/Dubai Destination 等) で「その他」化
    していた国際的主要母父の継続追加。父系 male-line が founder まで確度が高いもののみ。
    母父=カナ主経路のため英名+カナ両側を必ず検証 (code-quality 監査の変更失敗モード対策)。"""
    cases = {
        # Danzig 系欧州スプリンター枝 → northern / eur
        "オアシスドリーム": ("northern", "eur"),      "Oasis Dream": ("northern", "eur"),
        "ケープクロス": ("northern", "eur"),          "Cape Cross": ("northern", "eur"),
        "インヴィンシブルスピリット": ("northern", "eur"), "Invincible Spirit": ("northern", "eur"),
        "デインヒルダンサー": ("northern", "eur"),    "Danehill Dancer": ("northern", "eur"),
        "ロックオブジブラルタル": ("northern", "eur"), "Rock of Gibraltar": ("northern", "eur"),
        "ピヴォタル": ("northern", "eur"),            "Pivotal": ("northern", "eur"),
        "ハイシャパラル": ("northern", "eur"),         "High Chaparral": ("northern", "eur"),
        "シングスピール": ("northern", "eur"),         "Singspiel": ("northern", "eur"),
        # Kingmambo / A.P. Indy / Machiavellian 米国枝 → usa
        # Dubai Destination は kingmambo 系だが Godolphin 欧州マイラー → 欧州型 (亀谷分類・ユーザ確認)
        "ドバイデスティネーション": ("kingmambo", "eur"), "Dubai Destination": ("kingmambo", "eur"),
        "バーナディーニ": ("nasrullah", "usa"),        "Bernardini": ("nasrullah", "usa"),
        "ストリートクライ": ("mrprospector", "usa"),   "Street Cry": ("mrprospector", "usa"),
    }
    for name, (line, country) in cases.items():
        k = sl.classify_sire(name)
        assert k == line, f"{name}: {k} != {line}"
        assert sl.classify_country(name, k) == country, name
        assert sl.line_label_short(k) != "その他", name


def test_batch_european_classic_broodmare_sires_2026_07_08():
    """実 DB フィードバック (ユーザ指摘の Dalakhani 等) で line 未収載=「その他」化していた
    欧州古典系 (凱旋門賞/欧州ダービー級) 母父の一括収載。父系 founder まで確度が高いもののみ。
    国別はいずれも欧州発展のため eur (line 既定が usa の nasrullah/mrprospector/native は
    COUNTRY_OVERRIDE で、northern は既定 eur)。母父=カナ主経路のため英名+カナ両側を検証。"""
    cases = {
        # Mill Reef 枝 → neverbend (亀谷=ネヴァーベンド系。ナスルーラ系と別枠) / eur
        "ダラカニ": ("neverbend", "eur"),          "Dalakhani": ("neverbend", "eur"),
        "ダーシャーン": ("neverbend", "eur"),        "Darshaan": ("neverbend", "eur"),
        "シャーリーハイツ": ("neverbend", "eur"),     "Shirley Heights": ("neverbend", "eur"),
        # Blushing Groom/Grey Sovereign 枝 → nasrullah / eur
        "レインボウクエスト": ("nasrullah", "eur"),   "Rainbow Quest": ("nasrullah", "eur"),
        "グルームダンサー": ("nasrullah", "eur"),     "Groom Dancer": ("nasrullah", "eur"),
        "ハイエストオナー": ("nasrullah", "eur"),     "Highest Honor": ("nasrullah", "eur"),
        "ケンドー": ("nasrullah", "eur"),           "Kendor": ("nasrullah", "eur"),
        "カルドゥン": ("nasrullah", "eur"),          "Kaldoun": ("nasrullah", "eur"),
        # Gone West 欧州チャンピオン枝 → mrprospector / eur
        "ザフォニック": ("mrprospector", "eur"),     "Zafonic": ("mrprospector", "eur"),
        "ザミンダー": ("mrprospector", "eur"),       "Zamindar": ("mrprospector", "eur"),
        # Northern Dancer 欧州枝 → northern / eur (既定)
        "ペイントルセレブル": ("northern", "eur"),    "Peintre Celebre": ("northern", "eur"),
        "グリーンダンサー": ("northern", "eur"),      "Green Dancer": ("northern", "eur"),
        "ファビュラスダンサー": ("northern", "eur"),   "Fabulous Dancer": ("northern", "eur"),
        "アナバー": ("northern", "eur"),            "Anabaa": ("northern", "eur"),
        "リナミクス": ("northern", "eur"),           "Linamix": ("northern", "eur"),
        "シンダー": ("northern", "eur"),            "Sinndar": ("northern", "eur"),
        "シーザスターズ": ("northern", "eur"),        "Sea The Stars": ("northern", "eur"),
        "エルナンド": ("northern", "eur"),           "Hernando": ("northern", "eur"),
        "ジェネラス": ("northern", "eur"),           "Generous": ("northern", "eur"),
        # Sharpen Up/Sea-Bird 経由 Native Dancer 欧州枝 → native / eur
        "シャープンアップ": ("native", "eur"),        "Sharpen Up": ("native", "eur"),
        "ダイエシス": ("native", "eur"),            "Diesis": ("native", "eur"),
        "セルカーク": ("native", "eur"),            "Selkirk": ("native", "eur"),
        "トランポリーノ": ("native", "eur"),         "Trempolino": ("native", "eur"),
        "アークティックターン": ("native", "eur"),    "Arctic Tern": ("native", "eur"),
    }
    for name, (line, country) in cases.items():
        k = sl.classify_sire(name)
        assert k == line, f"{name}: {k} != {line}"
        assert sl.classify_country(name, k) == country, name
        assert sl.line_label_short(k) != "その他", name


def test_unknown_without_conn():
    assert sl.classify_sire("架空種牡馬XYZ") == "unknown"
    assert sl.classify_sire(None) == "unknown"
    assert sl.classify_sire("") == "unknown"


def test_no_dup_keys_lost():
    # 主要系統キーが全て LINE_LABEL/LINE_COLOR に存在
    for key in set(sl.LINE_BY_SIRE.values()) | set(sl.FOUNDERS.values()):
        assert key in sl.LINE_LABEL, key
        assert key in sl.LINE_COLOR, key


def test_founders_and_line_by_sire_agree_on_overlap():
    """同一種牡馬が LINE_BY_SIRE と FOUNDERS の両方に載る場合、指す系統は一致すること。
    (code-quality 指摘: 2 経路で系統が食い違うと遡上結果が起点次第で変わる。
    正規化キーで突合し、辞書間の系統割当ズレを機械的に禁止する。)"""
    line_n = sl._LINE_BY_SIRE_N
    founders_n = sl._FOUNDERS_N
    overlap = set(line_n) & set(founders_n)
    mismatches = {k: (line_n[k], founders_n[k]) for k in overlap if line_n[k] != founders_n[k]}
    assert not mismatches, f"LINE_BY_SIRE と FOUNDERS で系統が不一致: {mismatches}"


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
