"""種牡馬 → 大系統 (父系) の分類。

スマート出馬表 (SmartRC) 踏襲 webapp の血統色分け・傾向集計「父系統」軸で使う。
JRA の現役種牡馬の大半は少数の始祖にたどれるので、方針は 2 段:

  1. LINE_BY_SIRE: 現役〜近年の主要種牡馬を直接 line_key に引く辞書 (traversal 不要)。
     出走馬の父はこの辞書でほぼ引ける。
  2. breeding_horses を使った父系遡上フォールバック: 辞書に無い父は、父の父…と
     sire_breeding_num を遡って FOUNDERS または LINE_BY_SIRE に当たるまで探索。

いずれも当たらなければ "unknown" ("その他") にフォールバックする。系統辞書の
完全性は本質的に部分的なので、未知は色 = グレーで安全に劣化させる。データ層
(breeding_horses) が空でも 1 段目の辞書だけで機能する。

大系統キー (line_key) は ASCII 安定文字列 (JSON/CSS クラス兼用)。
"""

from __future__ import annotations

import sqlite3

# 大系統の表示ラベルと色 (webapp の系統色分け用。SmartRC の 10 色分けに倣う)。
LINE_LABEL: dict[str, str] = {
    "sunday": "サンデーサイレンス系",
    "kingmambo": "キングマンボ系",
    "mrprospector": "ミスプロ系",
    "storm": "ストームキャット系",
    "northern": "ノーザンダンサー系",
    "roberto": "ロベルト系",
    "nasrullah": "ナスルーラ系",
    "nearctic": "ネアルコ／ニアークティック系",
    "native": "ネイティヴダンサー系",
    "unknown": "その他",
}

# 出馬表の系統セル用の短縮ラベル (父系/母父系の 2 段表示で幅を取らないため)。
LINE_LABEL_SHORT: dict[str, str] = {
    "sunday": "サンデー系",
    "kingmambo": "キングマンボ系",
    "mrprospector": "ミスプロ系",
    "storm": "ストームC系",
    "northern": "ノーザンD系",
    "roberto": "ロベルト系",
    "nasrullah": "ナスルーラ系",
    "nearctic": "ネアルコ系",
    "native": "ネイティヴD系",
    "unknown": "その他",
}

# WCAG を意識した識別しやすい 10 色 (light/dark 双方で判別可能な中彩度)。
LINE_COLOR: dict[str, str] = {
    "sunday": "#8bc34a",       # 黄緑 (SmartRC 慣習に合わせる)
    "kingmambo": "#e57373",    # 赤
    "mrprospector": "#ff8a65", # 橙
    "storm": "#ba68c8",        # 紫
    "northern": "#4fc3f7",     # 水色 (SmartRC 慣習)
    "roberto": "#a1887f",      # 茶
    "nasrullah": "#ffd54f",    # 黄
    "nearctic": "#4db6ac",     # 青緑
    "native": "#f06292",       # 桃
    "unknown": "#bdbdbd",      # グレー
}

# 主要種牡馬 → line_key。分類は**父の系統** (父系遡上)。
# キー照合は _normalize で全角空白除去 + 前後 trim して行う。
# 2026-07-05 fable 監査で約 12 件の事実誤りを是正 (ドゥラメンテ=父キンカメ等)。
LINE_BY_SIRE: dict[str, str] = {
    # --- サンデーサイレンス系 (父が SS 直仔 or SS 系) ---
    "サンデーサイレンス": "sunday",
    "ディープインパクト": "sunday",
    "ハーツクライ": "sunday",
    "ステイゴールド": "sunday",
    "オルフェーヴル": "sunday",       # 父ステイゴールド
    "ゴールドシップ": "sunday",       # 父ステイゴールド
    "ダイワメジャー": "sunday",
    "アグネスタキオン": "sunday",
    "マンハッタンカフェ": "sunday",
    "ゴールドアリュール": "sunday",
    "キズナ": "sunday",              # 父ディープ
    "キタサンブラック": "sunday",     # 父ブラックタイド
    "サトノダイヤモンド": "sunday",   # 父ディープ
    "ワールドエース": "sunday",
    "ミッキーアイル": "sunday",
    "リアルインパクト": "sunday",
    "ネオユニヴァース": "sunday",
    "ヴィクトワールピサ": "sunday",   # 父ネオユニヴァース
    "ブラックタイド": "sunday",
    "フジキセキ": "sunday",
    "シルバーステート": "sunday",     # 父ディープ
    "スワーヴリチャード": "sunday",   # 父ハーツクライ
    "イスラボニータ": "sunday",      # 父フジキセキ
    "ジャスタウェイ": "sunday",      # 父ハーツクライ
    "グレーターロンドン": "sunday",   # 父ディープ
    "ディーマジェスティ": "sunday",   # 父ディープ
    "コントレイル": "sunday",        # 父ディープ
    "リアルスティール": "sunday",     # 父ディープ
    "サトノアラジン": "sunday",      # 父ディープ
    "ダノンプレミアム": "sunday",     # 父ディープ
    "アルアイン": "sunday",          # 父ディープ
    "フィエールマン": "sunday",      # 父ディープ
    "ロジャーバローズ": "sunday",     # 父ディープ
    "ディープブリランテ": "sunday",   # 父ディープ
    "トーセンラー": "sunday",        # 父ディープ
    "キンシャサノキセキ": "sunday",   # 父フジキセキ
    "インディチャンプ": "sunday",     # 父ステイゴールド
    "エスポワールシチー": "sunday",   # 父ゴールドアリュール
    "コパノリッキー": "sunday",      # 父ゴールドアリュール
    "ゴールドドリーム": "sunday",     # 父ゴールドアリュール
    "クリソベリル": "sunday",        # 父ゴールドアリュール
    "スマートファルコン": "sunday",   # 父ゴールドアリュール
    "アドマイヤマーズ": "sunday",     # 父ダイワメジャー
    "カレンブラックヒル": "sunday",   # 父ダイワメジャー
    # --- キングマンボ系 (Mr. Prospector → Kingmambo → キンカメ等) ---
    "キングマンボ": "kingmambo",
    "キングカメハメハ": "kingmambo",
    "ドゥラメンテ": "kingmambo",      # 父キングカメハメハ
    "リオンディーズ": "kingmambo",    # 父キングカメハメハ
    "ルーラーシップ": "kingmambo",    # 父キングカメハメハ
    "ロードカナロア": "kingmambo",    # 父キングカメハメハ
    "レイデオロ": "kingmambo",       # 父キングカメハメハ
    "ホッコータルマエ": "kingmambo",  # 父キングカメハメハ
    "サートゥルナーリア": "kingmambo",# 父ロードカナロア
    "ワークフォース": "kingmambo",    # 父キングズベスト (Kingmambo 直仔)
    "キングズベスト": "kingmambo",    # Kingmambo 直仔
    "エイシンフラッシュ": "kingmambo",# 父キングズベスト
    "ラブリーデイ": "kingmambo",     # 父キングカメハメハ
    "ベルシャザール": "kingmambo",    # 父キングカメハメハ
    "ミッキーロケット": "kingmambo",  # 父キングカメハメハ
    "トゥザワールド": "kingmambo",    # 父キングカメハメハ
    "キセキ": "kingmambo",           # 父ルーラーシップ
    "ダノンスマッシュ": "kingmambo",  # 父ロードカナロア
    "ステルヴィオ": "kingmambo",     # 父ロードカナロア
    # --- ミスタープロスペクター系 (Kingmambo 以外) ---
    "ミスタープロスペクター": "mrprospector",
    "フサイチペガサス": "mrprospector",
    "スウェプトオーヴァーボード": "mrprospector",  # 父エンドスウィープ (Forty Niner 系)
    "レッドファルクス": "mrprospector",  # 父スウェプトオーヴァーボード
    "アドマイヤムーン": "mrprospector",  # 父エンドスウィープ
    "ファインニードル": "mrprospector",  # 父アドマイヤムーン
    "マクフィ": "mrprospector",       # 父ドバウィ (Dubai Millennium → Seeking the Gold)
    "ニューイヤーズデイ": "mrprospector",  # 父ストリートクライ (Machiavellian 系)
    "ダンカーク": "mrprospector",     # 父アンブライドルズソング (Unbridled → Fappiano)
    "アメリカンファラオ": "mrprospector",  # 父パイオニアオブザナイル (Empire Maker → Unbridled)
    "タワーオブロンドン": "mrprospector",  # 父レイヴンズパス (Elusive Quality → Gone West)
    # --- ストームキャット系 (ND 傘下だが慣習上独立表示) ---
    "ストームキャット": "storm",
    "ヨハネスブルグ": "storm",        # Hennessy 系
    "ジャイアンツコーズウェイ": "storm",
    "ヘネシー": "storm",
    "ヘニーヒューズ": "storm",        # 父ヘネシー
    "アジアエクスプレス": "storm",    # 父ヘニーヒューズ
    "ドレフォン": "storm",           # Gio Ponti 系 (Storm Cat 系)
    "モーニン": "storm",             # 父ヘニーヒューズ
    "スキャットダディ": "storm",      # 父ヨハネスブルグ
    "ミスターメロディ": "storm",      # 父スキャットダディ
    "シャンハイボビー": "storm",      # 父ハーランズホリデー (Harlan → Storm Cat)
    "ディスクリートキャット": "storm", # 父フォレストリー (Storm Cat 直仔)
    "ブリックスアンドモルタル": "storm",  # 父ジャイアンツコーズウェイ
    # --- ノーザンダンサー系 (Storm Cat 系を除く) ---
    "ノーザンダンサー": "northern",
    "ノーザンテースト": "northern",
    "サドラーズウェルズ": "northern",
    "ダンチヒ": "northern",
    "ヌレイエフ": "northern",
    "ハービンジャー": "northern",     # Dansili (Danzig 系)
    "フレンチデピュティ": "northern",  # 父デピュティミニスター (Vice Regent → ND)
    "クロフネ": "northern",          # 父フレンチデピュティ
    "マインドユアビスケッツ": "northern",  # Posse → Silver Deputy → Deputy Minister
    "ガリレオ": "northern",          # 父サドラーズウェルズ
    "フランケル": "northern",        # 父ガリレオ
    "モズアスコット": "northern",     # 父フランケル
    "サトノクラウン": "northern",     # 父マージュ (Last Tycoon → Try My Best → ND)
    "ブラストワンピース": "northern", # 父ハービンジャー
    "ペルシアンナイト": "northern",   # 父ハービンジャー
    "ローエングリン": "northern",     # 父シングスピール (In the Wings → Sadler's Wells)
    "ロゴタイプ": "northern",        # 父ローエングリン
    "ウォーフロント": "northern",     # 父ダンチヒ
    "デクラレーションオブウォー": "northern",  # 父ウォーフロント
    "アメリカンペイトリオット": "northern",    # 父ウォーフロント
    "ザファクター": "northern",      # 父ウォーフロント
    "タリスマニック": "northern",     # 父メダグリアドーロ (El Prado → Sadler's Wells)
    "サンダースノー": "northern",     # 父ヘルメット (Exceed And Excel → Danehill → Danzig)
    # --- ロベルト系 (Hail to Reason → Roberto) ---
    "ロベルト": "roberto",
    "ブライアンズタイム": "roberto",
    "シンボリクリスエス": "roberto",  # Kris S. 系
    "タニノギムレット": "roberto",    # 父ブライアンズタイム
    "グラスワンダー": "roberto",      # Silver Hawk 系
    "スクリーンヒーロー": "roberto",  # 父グラスワンダー
    "モーリス": "roberto",           # 父スクリーンヒーロー
    "エピファネイア": "roberto",      # 父シンボリクリスエス
    "ルヴァンスレーヴ": "roberto",    # 父シンボリクリスエス
    "ナダル": "roberto",             # 父ブレイム (Arch → Kris S.)
    "フリオーソ": "roberto",         # 父ブライアンズタイム
    # --- ナスルーラ系 (Bold Ruler → Seattle Slew → A.P. Indy 含む) ---
    "ナスルーラ": "nasrullah",
    "ボールドルーラー": "nasrullah",
    "シアトルスルー": "nasrullah",
    "エーピーインディ": "nasrullah",
    "パイロ": "nasrullah",           # Pulpit → A.P. Indy
    "シニスターミニスター": "nasrullah",  # Old Trieste → A.P. Indy
    "マジェスティックウォリアー": "nasrullah",  # 父エーピーインディ
    "カジノドライヴ": "nasrullah",    # 父マインシャフト (A.P. Indy 直仔)
    "サクラバクシンオー": "nasrullah",# 父サクラユタカオー (テスコボーイ → プリンスリーギフト)
    "ビッグアーサー": "nasrullah",    # 父サクラバクシンオー
    "バゴ": "nasrullah",             # 父ナシュワン (Blushing Groom → Red God)
    "トニービン": "nasrullah",        # カンパラ → Kalamoun → Grey Sovereign
    "ジャングルポケット": "nasrullah",# 父トニービン
    # --- ネイティヴダンサー系 ---
    "ネイティヴダンサー": "native",
    # --- ネアルコ / ニアークティック ---
    "ニアークティック": "nearctic",
    "ネアルコ": "nearctic",
    # 注: ダノンレジェンド (父 Macho Uno = In Reality 系) のような 10 大系統外は
    # 辞書に載せず unknown (グレー) に落とす。誤答よりも「その他」が誠実。
}

# 父系遡上の始祖 (breeding_horses を遡って当たったらこの系統)。
# LINE_BY_SIRE と重複する founder も含め、遡上時の停止点として使う。
FOUNDERS: dict[str, str] = {
    "サンデーサイレンス": "sunday",
    "ヘイルトゥリーズン": "roberto",   # 便宜上 Roberto 側に寄せる (SS は上で捕捉)
    "ターントゥ": "roberto",
    "ロベルト": "roberto",
    "キングマンボ": "kingmambo",
    "ミスタープロスペクター": "mrprospector",
    "ストームキャット": "storm",
    "ストームバード": "storm",
    "ノーザンダンサー": "northern",
    "ナスルーラ": "nasrullah",
    "ボールドルーラー": "nasrullah",
    "ネイティヴダンサー": "native",
    "ニアークティック": "nearctic",
    "ネアルコ": "nearctic",
}


def _normalize(name: str | None) -> str:
    """種牡馬名を照合キーに正規化 (全角空白除去 + trim)。"""
    if not name:
        return ""
    return name.replace("　", "").strip()


def classify_sire(sire_name: str | None, conn=None, sire_breeding_num: str | None = None,
                  max_depth: int = 12) -> str:
    """種牡馬名 (と任意で breeding_num) から大系統 line_key を返す。

    1. LINE_BY_SIRE の直接照合。
    2. conn と sire_breeding_num があれば breeding_horses を父系遡上し、
       各世代の父名を LINE_BY_SIRE / FOUNDERS に照合。
    3. いずれも当たらなければ "unknown"。
    """
    key = _normalize(sire_name)
    if key in LINE_BY_SIRE:
        return LINE_BY_SIRE[key]
    if key in FOUNDERS:
        return FOUNDERS[key]

    if conn is None or not sire_breeding_num:
        return "unknown"

    # breeding_horses を sire_breeding_num で遡上する。
    seen: set[str] = set()
    cur = sire_breeding_num
    for _ in range(max_depth):
        if not cur or cur in seen:
            break
        seen.add(cur)
        try:
            row = conn.execute(
                "SELECT horse_name, sire_name, sire_breeding_num "
                "FROM breeding_horses WHERE breeding_num = ?",
                (cur,),
            ).fetchone()
        except sqlite3.OperationalError:
            # breeding_horses 未作成の古い DB (BLOD 未取込 + readonly 接続で
            # migration も走らない) では遡上せず辞書照合のみで劣化させる。
            break
        if row is None:
            break
        # row は sqlite3.Row 想定 (dict-like)。tuple の場合も許容。
        try:
            name = row["horse_name"]
            parent_name = row["sire_name"]
            parent_num = row["sire_breeding_num"]
        except (TypeError, IndexError, KeyError):
            name, parent_name, parent_num = row[0], row[1], row[2]
        for candidate in (name, parent_name):
            k = _normalize(candidate)
            if k in LINE_BY_SIRE:
                return LINE_BY_SIRE[k]
            if k in FOUNDERS:
                return FOUNDERS[k]
        cur = parent_num
    return "unknown"


def line_label(line_key: str) -> str:
    return LINE_LABEL.get(line_key, LINE_LABEL["unknown"])


def line_label_short(line_key: str) -> str:
    return LINE_LABEL_SHORT.get(line_key, LINE_LABEL_SHORT["unknown"])


def line_color(line_key: str) -> str:
    return LINE_COLOR.get(line_key, LINE_COLOR["unknown"])
