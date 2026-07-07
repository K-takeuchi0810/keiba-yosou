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

import logging
import sqlite3
import unicodedata

logger = logging.getLogger(__name__)

# breeding_horses 欠如の警告は 1 回だけ出す (1 ページ ~36 回呼ばれるため)
_warned_no_breeding_table = False

# 大系統の表示ラベルと色 (webapp の系統色分け用。SmartRC の色分け慣習に倣う)。
# turnto はヘイロー系の非サンデー枝 (タイキシャトル等) の受け皿 (2026-07-05 追加。
# 従来はロベルト系への便宜寄せ or その他落ちで不正確だった)。
LINE_LABEL: dict[str, str] = {
    "sunday": "サンデーサイレンス系",
    "kingmambo": "キングマンボ系",
    "mrprospector": "ミスプロ系",
    "storm": "ストームキャット系",
    "northern": "ノーザンダンサー系",
    "roberto": "ロベルト系",
    "turnto": "ターントゥ系(ヘイロー等)",
    "nasrullah": "ナスルーラ系",
    "nearctic": "ネアルコ／ニアークティック系",
    "native": "ネイティヴダンサー系",
    # 11 大系統外だが JRA で名の通った系統 (2026-07-06 追加。「その他」を実系統名にする)。
    "personon": "パーソロン系",
    "stsimon": "セントサイモン系",
    "hyperion": "ハイペリオン系",
    "manowar": "マンノウォー系",
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
    "turnto": "ターントゥ系",
    "nasrullah": "ナスルーラ系",
    "nearctic": "ネアルコ系",
    "native": "ネイティヴD系",
    "personon": "パーソロン系",
    "stsimon": "セントサイモン系",
    "hyperion": "ハイペリオン系",
    "manowar": "マンノウォー系",
    "unknown": "その他",
}

# 系統 dot の色。15 系統でパレットは飽和しており、色単独では判別できない近接ペアが
# ある (personon≈turnto/storm、stsimon≈roberto、hyperion≈northern、manowar≈stsimon(距離62)
# — 2026-07-06 mobile 監査で sRGB 距離実測)。したがって色は「雰囲気付けの補助」であり、
# 識別の唯一の担保はテキストラベル併記 (base.html.j2 の line-dot 不変条件参照)。dot 単独出力は禁止。
LINE_COLOR: dict[str, str] = {
    "sunday": "#8bc34a",       # 黄緑 (SmartRC 慣習に合わせる)
    "kingmambo": "#e57373",    # 赤
    "mrprospector": "#ff8a65", # 橙
    "storm": "#ba68c8",        # 紫
    "northern": "#4fc3f7",     # 水色 (SmartRC 慣習)
    "roberto": "#a1887f",      # 茶
    "turnto": "#7986cb",       # 藍
    "nasrullah": "#ffd54f",    # 黄
    "nearctic": "#4db6ac",     # 青緑
    "native": "#f06292",       # 桃
    "personon": "#9575cd",     # 藤
    "stsimon": "#8d6e63",      # 焦茶
    "hyperion": "#26c6da",     # シアン (#4dd0e1 は light 地で 1.84:1 と淡すぎ濃度上げ — 2026-07-06 mobile)
    "manowar": "#607d8b",      # 青灰 (Man o'War 系)
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
    # 母父世代の SS 直仔・SS 系 (2026-07-05 拡充: 実機で母父が「その他」だらけの対処)
    "スペシャルウィーク": "sunday",   # SS 直仔
    "アドマイヤベガ": "sunday",      # SS 直仔
    "ダンスインザダーク": "sunday",   # SS 直仔
    "ゼンノロブロイ": "sunday",      # SS 直仔
    "デュランダル": "sunday",        # SS 直仔
    "マーベラスサンデー": "sunday",   # SS 直仔
    "バブルガムフェロー": "sunday",   # SS 直仔
    "スズカマンボ": "sunday",        # SS 直仔
    "ハットトリック": "sunday",      # SS 直仔
    "ディープスカイ": "sunday",      # 父アグネスタキオン
    "ダノンシャンティ": "sunday",     # 父フジキセキ
    "カネヒキリ": "sunday",          # 父フジキセキ
    "ドリームジャーニー": "sunday",   # 父ステイゴールド
    "ナカヤマフェスタ": "sunday",     # 父ステイゴールド
    "フェノーメノ": "sunday",        # 父ステイゴールド
    "レインボーライン": "sunday",     # 父ステイゴールド
    "エイシンヒカリ": "sunday",      # 父ディープ
    "ダノンバラード": "sunday",      # 父ディープ
    "ダノンキングリー": "sunday",     # 父ディープ
    "トーセンホマレボシ": "sunday",   # 父ディープ
    "ジョーカプチーノ": "sunday",     # 父マンハッタンカフェ
    "ヒルノダムール": "sunday",      # 父マンハッタンカフェ
    "サリオス": "sunday",            # 父ハーツクライ
    "ドウデュース": "sunday",        # 父ハーツクライ
    "イクイノックス": "sunday",      # 父キタサンブラック
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
    "エルコンドルパサー": "kingmambo",# 父キングマンボ
    "ヴァーミリアン": "kingmambo",    # 父エルコンドルパサー
    "ローズキングダム": "kingmambo",  # 父キングカメハメハ
    "チュウワウィザード": "kingmambo",# 父キングカメハメハ
    "レモンドロップキッド": "kingmambo",  # 父キングマンボ
    "レモンポップ": "kingmambo",     # 父レモンドロップキッド
    "ビーチパトロール": "kingmambo",  # 父レモンドロップキッド
    "パンサラッサ": "kingmambo",     # 父ロードカナロア
    "タイトルホルダー": "kingmambo",  # 父ドゥラメンテ
    # --- ミスタープロスペクター系 (Kingmambo 以外) ---
    "ミスタープロスペクター": "mrprospector",
    "フサイチペガサス": "mrprospector",
    "スウェプトオーヴァーボード": "mrprospector",  # 父エンドスウィープ (Forty Niner 系)
    "レッドファルクス": "mrprospector",  # 父スウェプトオーヴァーボード
    "アドマイヤムーン": "mrprospector",  # 父エンドスウィープ
    "ファインニードル": "mrprospector",  # 父アドマイヤムーン
    "マクフィ": "mrprospector",       # 父ドバウィ (Dubai Millennium → Seeking the Gold)
    "サウスヴィグラス": "mrprospector",  # 父エンドスウィープ (Forty Niner 系)
    "ニューイヤーズデイ": "mrprospector",  # 父ストリートクライ (Machiavellian 系)
    "ダンカーク": "mrprospector",     # 父アンブライドルズソング (Unbridled → Fappiano)
    "アメリカンファラオ": "mrprospector",  # 父パイオニアオブザナイル (Empire Maker → Unbridled)
    "タワーオブロンドン": "mrprospector",  # 父レイヴンズパス (Elusive Quality → Gone West)
    "カフェファラオ": "mrprospector", # 父アメリカンファラオ
    "フォーティナイナー": "mrprospector",  # 父ミスタープロスペクター
    "エンドスウィープ": "mrprospector",    # 父フォーティナイナー
    "プリサイスエンド": "mrprospector",    # 父エンドスウィープ
    "オメガパフューム": "mrprospector",    # 父スウェプトオーヴァーボード
    "シーキングザゴールド": "mrprospector",# 父ミスタープロスペクター
    "マイネルラヴ": "mrprospector",   # 父シーキングザゴールド
    "クラフティプロスペクター": "mrprospector",  # 父ミスタープロスペクター
    "アグネスデジタル": "mrprospector",    # 父クラフティプロスペクター
    "ウッドマン": "mrprospector",     # 父ミスタープロスペクター
    "ティンバーカントリー": "mrprospector",# 父ウッドマン
    "ジェイドロバリー": "mrprospector",    # 父ミスタープロスペクター
    "ウォーエンブレム": "mrprospector",    # 父アワエンブレム (Mr. Prospector 直仔)
    "エンパイアメーカー": "mrprospector",  # 父アンブライドルド (Fappiano 系)
    "バトルプラン": "mrprospector",   # 父エンパイアメーカー
    "アイルハヴアナザー": "mrprospector",  # 父フラワーアレー (Distorted Humor → Forty Niner)
    "ゴーンウェスト": "mrprospector", # 父ミスタープロスペクター
    "スパイツタウン": "mrprospector", # 父ゴーンウェスト
    "マテラスカイ": "mrprospector",   # 父スパイツタウン
    "ケイムホーム": "mrprospector",   # 父ゴーンウェスト
    "アフリート": "mrprospector",     # 父ミスタープロスペクター
    "ヘクタープロテクター": "mrprospector",  # 父ウッドマン (Mr. Prospector 系)
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
    "エスケンデレヤ": "storm",        # 父ジャイアンツコーズウェイ
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
    "ニジンスキー": "northern",       # 父ノーザンダンサー
    "マルゼンスキー": "northern",     # 父ニジンスキー
    "カーリアン": "northern",        # 父ニジンスキー
    "ラムタラ": "northern",          # 父ニジンスキー
    "リファール": "northern",        # 父ノーザンダンサー
    "ダンシングブレーヴ": "northern", # 父リファール
    "ホワイトマズル": "northern",     # 父ダンシングブレーヴ
    "コマンダーインチーフ": "northern",  # 父ダンシングブレーヴ
    "キングヘイロー": "northern",     # 父ダンシングブレーヴ
    "ローレルゲレイロ": "northern",   # 父キングヘイロー
    "フェアリーキング": "northern",   # 父ノーザンダンサー (Sadler's Wells 全弟)
    "エリシオ": "northern",          # 父フェアリーキング
    "ファルブラヴ": "northern",      # 父フェアリーキング
    "オペラハウス": "northern",      # 父サドラーズウェルズ
    "メイショウサムソン": "northern", # 父オペラハウス
    "デインヒル": "northern",        # 父ダンチヒ
    "デインヒルダンサー": "northern", # 父デインヒル
    "ロックオブジブラルタル": "northern",  # 父デインヒル
    "グリーンデザート": "northern",   # 父ダンチヒ
    "ケープクロス": "northern",      # 父グリーンデザート
    "ベーカバド": "northern",        # 父ケープクロス
    "チーフベアハート": "northern",   # 父チーフズクラウン (Danzig 系)
    "アンバーシャダイ": "northern",   # 父ノーザンテースト
    "メジロライアン": "northern",     # 父アンバーシャダイ
    "フサイチコンコルド": "northern", # 父カーリアン (Nijinsky → Northern Dancer)
    "アジュディケーティング": "northern",  # 父ダンチヒ (Danzig)
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
    "リアルシャダイ": "roberto",      # 父ロベルト
    "マヤノトップガン": "roberto",    # 父ブライアンズタイム
    "シルヴァーホーク": "roberto",    # 父ロベルト
    "ストロングリターン": "roberto",  # 父シンボリクリスエス
    "エフフォーリア": "roberto",      # 父エピファネイア
    "ジャックドール": "roberto",      # 父モーリス
    # --- ターントゥ系 (Hail to Reason → Halo の非サンデー枝など。Roberto 系は別掲) ---
    "ヘイロー": "turnto",            # 父ヘイルトゥリーズン (SS の父。SS 系は上で捕捉)
    "サザンヘイロー": "turnto",       # 父ヘイロー
    "モアザンレディ": "turnto",       # 父サザンヘイロー
    "デヴィルズバッグ": "turnto",     # 父ヘイロー
    "タイキシャトル": "turnto",       # 父デヴィルズバッグ
    "メイショウボーラー": "turnto",   # 父タイキシャトル
    "ニシケンモノノフ": "turnto",     # 父メイショウボーラー
    "デヴィルヒズデュー": "turnto",   # 父デヴィルズバッグ
    "ロージズインメイ": "turnto",     # 父デヴィルヒズデュー
    "ニホンピロウイナー": "turnto",   # 父スティールハート (Habitat → Sir Gaylord → Turn-to)
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
    "トニービン": "nasrullah",        # カンパラ → Kalamoun → Zeddaan → Grey Sovereign
    "ジャングルポケット": "nasrullah",# 父トニービン
    "トーセンジョーダン": "nasrullah",# 父ジャングルポケット
    "プリンスリーギフト": "nasrullah",# 父ナスルーラ
    "テスコボーイ": "nasrullah",      # 父プリンスリーギフト
    "トウショウボーイ": "nasrullah",  # 父テスコボーイ
    "サクラユタカオー": "nasrullah",  # 父テスコボーイ
    "グランプリボス": "nasrullah",    # 父サクラバクシンオー
    "ショウナンカンプ": "nasrullah",  # 父サクラバクシンオー
    "グレイソヴリン": "nasrullah",    # 父ナスルーラ
    "コジーン": "nasrullah",         # 父カロ (Fortino → Grey Sovereign)
    "アドマイヤコジーン": "nasrullah",# 父コジーン
    "タマモクロス": "nasrullah",      # 父シービークロス (Fortino → Grey Sovereign)
    "ブラッシンググルーム": "nasrullah",  # 父レッドゴッド (Nasrullah 直仔)
    "レインボウクエスト": "nasrullah",# 父ブラッシンググルーム
    "サクラローレル": "nasrullah",    # 父レインボウクエスト
    "ミルリーフ": "nasrullah",        # 父ネヴァーベンド (Nasrullah 直仔)
    "ボストンハーバー": "nasrullah",  # 父カポーティ (Seattle Slew 系)
    "タピット": "nasrullah",         # 父プルピット (A.P. Indy 系)
    "ラニ": "nasrullah",             # 父タピット
    "カリフォルニアクローム": "nasrullah",  # 父ラッキーパルピット (Pulpit 系)
    "ベストウォーリア": "nasrullah",  # 父マジェスティックウォリアー
    "ミスターシービー": "nasrullah",  # 父トウショウボーイ (テスコボーイ系)
    "パラダイスクリーク": "nasrullah",  # 父アイリッシュリヴァー (Riverman → Never Bend)
    # --- ネイティヴダンサー系 ---
    "ネイティヴダンサー": "native",
    "レイズアネイティヴ": "native",   # 父ネイティヴダンサー
    "アファームド": "native",        # 父エクスクルーシヴネイティヴ (Raise a Native 系)
    "カコイーシーズ": "native",      # 父アリダー (Raise a Native 系)
    "アリダー": "native",            # 父レイズアネイティヴ
    "リンドシェーバー": "native",     # 父アリダー (Raise a Native 系)
    # --- ネアルコ / ニアークティック ---
    "ニアークティック": "nearctic",
    "ネアルコ": "nearctic",
    "アイスカペイド": "nearctic",     # 父ニアークティック
    "ワイルドアゲイン": "nearctic",   # 父アイスカペイド
    "ワイルドラッシュ": "nearctic",   # 父ワイルドアゲイン
    "トランセンド": "nearctic",      # 父ワイルドラッシュ
    # --- 海外種牡馬 (英語名)。UM の 3 代血統は海外祖先を英語で格納するため
    #     (例: 父母父 Alzao / 母母父 Riverman)、英語名でも引けるよう併記する。
    #     _normalize が NFKC + 小文字化 + 記号/空白除去するので綴り変種 (Mr.Prospector /
    #     A.P.Indy / Sadler's Wells の ' 字種 / 全角ローマ字) を吸収する。
    #     2026-07-06 実 DB で父母父/母母父が英語名により「その他」化していた対処。
    #     **実 DB で綴り観測済みは Alzao/Riverman/Affirmed/Seattle Slew/Silver Ghost の
    #     数件のみ、残りは周知血統からの暫定** (不一致でも安全側=その他に劣化)。網羅
    #     確認は scripts/audit_sire_lines.py (gen3 列対応済) の実機実行で行う。---
    # northern (Northern Dancer 系、Storm Cat 系を除く)
    "Northern Dancer": "northern", "Nijinsky": "northern", "Sadler's Wells": "northern",
    "Danzig": "northern", "Nureyev": "northern", "Lyphard": "northern",
    "Alzao": "northern",              # 父 Lyphard (父母父アンカーで観測)
    "Caerleon": "northern",           # 父 Nijinsky
    "Danehill": "northern", "Galileo": "northern", "Montjeu": "northern",
    "El Prado": "northern", "Fairy King": "northern", "Green Desert": "northern",
    "Vice Regent": "northern", "Deputy Minister": "northern",  # 系統は northern (国別 override は別)
    "Be My Guest": "northern", "Try My Best": "northern", "Dansili": "northern",
    # storm (Storm Cat 系)
    "Storm Cat": "storm", "Storm Bird": "storm", "Giant's Causeway": "storm",
    "Hennessy": "storm", "Johannesburg": "storm", "Forestry": "storm",
    "Harlan": "storm", "Harlan's Holiday": "storm", "Scat Daddy": "storm",
    # mrprospector (Mr. Prospector 系、Kingmambo を除く)
    "Mr. Prospector": "mrprospector", "Gone West": "mrprospector",
    "Forty Niner": "mrprospector", "Fappiano": "mrprospector",
    "Seeking the Gold": "mrprospector", "Machiavellian": "mrprospector",
    "Woodman": "mrprospector", "Miswaki": "mrprospector", "Gulch": "mrprospector",
    "Silver Ghost": "mrprospector",   # 父 Mr. Prospector (母母父アンカーで観測)
    "Distorted Humor": "mrprospector", "Unbridled": "mrprospector",
    "Unbridled's Song": "mrprospector", "Empire Maker": "mrprospector",
    "Smart Strike": "mrprospector", "Elusive Quality": "mrprospector",
    "Carson City": "mrprospector", "Crafty Prospector": "mrprospector",
    # kingmambo
    "Kingmambo": "kingmambo", "King's Best": "kingmambo", "Lemon Drop Kid": "kingmambo",
    # nasrullah (Bold Ruler/Seattle Slew/A.P. Indy/Grey Sovereign/Blushing Groom 各枝)
    "Nasrullah": "nasrullah", "Bold Ruler": "nasrullah", "Secretariat": "nasrullah",
    "Seattle Slew": "nasrullah",      # 母母父アンカーで観測
    "A.P. Indy": "nasrullah", "Pulpit": "nasrullah", "Tapit": "nasrullah",
    "Never Bend": "nasrullah", "Mill Reef": "nasrullah",
    "Riverman": "nasrullah",          # 父 Never Bend (母母父アンカーで観測)
    "Red God": "nasrullah", "Blushing Groom": "nasrullah", "Nashwan": "nasrullah",
    "Grey Sovereign": "nasrullah", "Caro": "nasrullah", "Cozzene": "nasrullah",
    "Capote": "nasrullah",
    # native (Native Dancer / Raise a Native 系)
    "Native Dancer": "native", "Raise a Native": "native",
    "Affirmed": "native",             # 父 Exclusive Native (母母父アンカーで観測)
    "Alydar": "native", "Exclusive Native": "native",
    # roberto (Hail to Reason → Roberto)
    "Roberto": "roberto", "Kris S.": "roberto", "Silver Hawk": "roberto",
    "Brian's Time": "roberto", "Dynaformer": "roberto", "Arch": "roberto", "Blame": "roberto",
    # turnto (Turn-to → Hail to Reason/Halo/Sir Gaylord 各枝、SS を除く)
    "Turn-to": "turnto", "Hail to Reason": "turnto", "Halo": "turnto",
    "Sir Gaylord": "turnto", "Sir Ivor": "turnto", "Devil's Bag": "turnto",
    "Southern Halo": "turnto", "More Than Ready": "turnto", "Habitat": "turnto",
    # nearctic / nearco
    "Nearco": "nearctic", "Nearctic": "nearctic", "Icecapade": "nearctic",
    # --- 11 大系統外だが JRA で名の通った系統 (2026-07-06)。従来「その他」だったが
    #     実系統名で表示する。父系事実で確度の高いものだけ収載。---
    # パーソロン系 (Partholon。JRA 独自呼称の一系統)
    "パーソロン": "personon",
    "シンボリルドルフ": "personon",   # 父パーソロン
    "トウカイテイオー": "personon",   # 父シンボリルドルフ
    "メジロティターン": "personon",   # 父メジロアサマ (父パーソロン)
    "メジロアサマ": "personon",       # 父パーソロン
    "メジロマックイーン": "personon", # 父メジロティターン
    "メジロデュレン": "personon",     # 父メジロティターン
    # セントサイモン系 (St. Simon: Ribot / Princequillo / Prince Rose 各枝)
    "セントサイモン": "stsimon", "St. Simon": "stsimon",
    "Ribot": "stsimon", "リボー": "stsimon",
    "His Majesty": "stsimon", "Graustark": "stsimon", "Tom Rolfe": "stsimon",
    "Pleasant Colony": "stsimon",
    "Princequillo": "stsimon", "Round Table": "stsimon", "Prince John": "stsimon",
    "Prince Rose": "stsimon", "Prince Chevalier": "stsimon",
    # ハイペリオン系 (Hyperion)
    "ハイペリオン": "hyperion", "Hyperion": "hyperion",
    "Aureole": "hyperion", "Khaled": "hyperion", "Swaps": "hyperion",
    "Star Kingdom": "hyperion",
    # --- 歴史的な内国産・輸入種牡馬 (実 DB の unknown 上位に居た古い父)。父系を founder
    #     まで辿って確度の高いものだけ収載 (2026-07-06 実機 unknown 突合)。breeding_horses
    #     の遡上でも拾えるが、古いレコードは血統木が疎で遡上が届かない場合があるため
    #     名前で直接固定する。---
    # ナスルーラ系
    "ミルジョージ": "nasrullah",         # 父ミルリーフ → Never Bend → Nasrullah
    "ブレイヴエストローマン": "nasrullah", # 父 Never Bend → Nasrullah
    "キンググローリアス": "nasrullah",    # 父 Naskra → Nasram → Nasrullah
    "ロイヤルスキー": "nasrullah",        # 父 Raja Baba → Bold Ruler → Nasrullah
    "アローエクスプレス": "nasrullah",    # 父 Never Beat → Never Bend → Nasrullah
    "イエローゴッド": "nasrullah",        # 父 Red God → Nasrullah
    # ノーザンダンサー系
    "モガミ": "northern",                # 父 Lyphard → Northern Dancer
    "ノーザンディクテイター": "northern", # 父 Northern Dancer
    "ホリスキー": "northern",            # 父マルゼンスキー → Nijinsky → Northern Dancer
    "ヤマニンスキー": "northern",         # 父 Nijinsky → Northern Dancer
    "アサティス": "northern",            # 父 Topsider → Northern Dancer
    "スリルショー": "northern",          # 父 Northern Baby → Northern Dancer
    "ロドリゴデトリアーノ": "northern",   # 父 El Gran Senor → Northern Dancer
    # サンデーサイレンス系
    "マツリダゴッホ": "sunday",          # 父サンデーサイレンス
    "タヤスツヨシ": "sunday",            # 父サンデーサイレンス
    # --- ナスルーラ系の追加枝 ---
    "カンパラ": "nasrullah",             # Kalamoun → Zeddaan → Grey Sovereign → Nasrullah
    # --- ノーザンダンサー系の追加枝 ---
    "パントレセレブル": "northern",       # 父 Nureyev → Northern Dancer
    # --- マンノウォー系 (Man o'War → Fair Play。11 大系統外の米国基礎系統) ---
    "マンノウォー": "manowar",
    "タイテエム": "manowar",             # 父ヴェンチア → Relic → War Relic → Man o'War
    "ヴェンチア": "manowar",             # Venture VII → Relic → War Relic → Man o'War
    "インリアリティ": "manowar",          # → Intent → War Relic → Man o'War
    "リローンチ": "manowar",             # 父 In Reality
    # --- 実機 audit (2026-07-06) の unknown 上位 (産駒数順) で父系 founder まで確度が
    #     高いもの。多くは古い母父/父母父で英語 or 大書き仮名で格納される。BLOD 遡上が
    #     効かない環境でも名前で直接引けるよう収載する。---
    # ナスルーラ系
    "ネヴァービート": "nasrullah",        # Never Beat → Never Bend → Nasrullah
    "ダイハード": "nasrullah",           # Die Hard → Never Say Die → Nasrullah
    "クリスタルパレス": "nasrullah",      # Crystal Palace → Caro → Fortino → Grey Sovereign → Nasrullah
    "フォルティノ": "nasrullah",          # Fortino → Grey Sovereign → Nasrullah
    "ボールドリック": "nasrullah",        # Bold Ruckus 想定 → Boldnesian → Bold Ruler (原名は BLOD で要確認。Bold Ruler 系なら line は安全)
    "ライジングフレーム": "nasrullah",     # Rising Flame → Nasrullah
    "ゴールドメリディアン": "nasrullah", "Gold Meridian": "nasrullah",  # → Seattle Slew → Bold Ruler
    # ノーザンダンサー系
    "ナイスダンサー": "northern",         # Nice Dancer → Northern Dancer
    "カーネギー": "northern",            # Carnegie → Sadler's Wells → Northern Dancer
    "ラストタイクーン": "northern", "Last Tycoon": "northern",  # → Try My Best → Northern Dancer
    "チーフズクラウン": "northern", "Chief's Crown": "northern", # → Danzig → Northern Dancer
    # ネイティヴダンサー系
    "クリス": "native", "Kris": "native",         # Kris → Sharpen Up → Atan → Native Dancer
    "ダンサーズイメージ": "native",       # Dancer's Image → Native Dancer
    "ベーリング": "native", "Bering": "native",   # Arctic Tern → Sea-Bird → Dan Cupid → Native Dancer
    # ニアークティック系
    "Wild Again": "nearctic",  # → Icecapade → Nearctic (カナ ワイルドアゲイン は上で定義済)
    # ハイペリオン系
    "チャイナロック": "hyperion",         # China Rock → Rockefella → Hyperion
    "シャトーゲイ": "hyperion",          # Chateaugay → Swaps → Khaled → Hyperion
    # セントサイモン系 (Prince Rose / Rabelais / Ribot / Bois Roussel は St. Simon 系)
    "ファバージ": "stsimon",             # Faberge II → Prince Bio → Prince Rose → … St. Simon
    "ルファビュルー": "stsimon", "Le Fabuleux": "stsimon",  # → Wild Risk → Rialto → Rabelais → St. Simon
    "ローソサエティ": "stsimon", "Law Society": "stsimon",   # → Alleged → Hoist the Flag → Tom Rolfe → Ribot
    "ヒンドスタン": "stsimon",           # Hindostan → Bois Roussel → Vatout → Prince Chimay → Chaucer → St. Simon
    "シンザン": "stsimon",              # 父ヒンドスタン (Bois Roussel 系 = St. Simon)
    # --- 実機 audit 2 巡目 (2026-07-06) の unknown 上位で父系 founder まで確度が高いもの ---
    "アレツジド": "stsimon", "Alleged": "stsimon",        # → Hoist the Flag → Tom Rolfe → Ribot → St. Simon
    "ターゴワイス": "stsimon", "Targowice": "stsimon",     # → Round Table → Princequillo → St. Simon
    "ウォーデン": "stsimon", "Worden": "stsimon",         # → Wild Risk → Rialto → Rabelais → St. Simon
    "ヴイミー": "stsimon", "Vimy": "stsimon",             # → Wild Risk → Rabelais → St. Simon
    "メドウレイク": "stsimon", "Meadowlake": "stsimon",   # → Hold Your Peace → Speak John → Prince John → Princequillo → St. Simon
    "ヴェイグリーノーブル": "hyperion", "Vaguely Noble": "hyperion",  # → Vienna → Aureole → Hyperion
    "ユアホスト": "hyperion", "Your Host": "hyperion",     # → Alibhai → Hyperion
    "ホーンビーム": "hyperion", "Hornbeam": "hyperion",    # 父 Hyperion
    "マイニング": "mrprospector", "Mining": "mrprospector",  # 父 Mr. Prospector
    "スティールハート": "turnto", "Steel Heart": "turnto",  # → Habitat → Sir Gaylord → Turn-to
    "ラーイ": "nasrullah", "Rahy": "nasrullah",           # → Blushing Groom → Red God → Nasrullah
    "スターデナスクラ": "nasrullah", "Star de Naskra": "nasrullah",  # → Naskra → Nasram → Nasrullah
    "ダイアトム": "stsimon", "Diatome": "stsimon",         # → Sicambre → Prince Bio → Prince Rose → St. Simon
    # マンノウォー系は上で定義済 (ヴェンチア 等)
    # 注: なお確度の低い/真に不明な系統は依然 unknown (グレー)。誤答よりも
    # 「その他」が誠実。ダノンレジェンド (父 Macho Uno → Holy Bull → Great Above 系)
    # 等は上記いずれにも該当しないため unknown のまま。
}

# 父系遡上の始祖 (breeding_horses を遡って当たったらこの系統)。
# LINE_BY_SIRE と重複する founder も含め、遡上時の停止点として使う。
FOUNDERS: dict[str, str] = {
    "サンデーサイレンス": "sunday",
    # Roberto 系は遡上中に「ロベルト」で先に停止するため、ここまで遡った
    # Hail to Reason 系は非 Roberto 枝 (Halo 非 SS 等) = turnto (2026-07-05 是正。
    # 旧: 便宜上 roberto 寄せ → タイキシャトル等が誤表示になるため独立させた)。
    # 「ターントゥ系」ラベルは Turn-to 直下の Hail to Reason 枝 (Halo 等) に加え、
    # Sir Gaylord 枝 (ニホンピロウイナー等、Hail to Reason を経由しない Turn-to 直系)
    # も内包する広義の呼称 (2026-07-06 予想ロジック監査の注記反映)。
    "ヘイルトゥリーズン": "turnto",
    "ターントゥ": "turnto",
    "ヘイロー": "turnto",
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
    # 11 大系統外の始祖 (遡上停止点)。より特異的な founder (ND/Nasrullah 等) が
    # 先に当たるため、これらは末端の稀な枝でのみ発火する。
    "パーソロン": "personon",
    "セントサイモン": "stsimon", "St. Simon": "stsimon",
    "ハイペリオン": "hyperion", "Hyperion": "hyperion",
    # マンノウォー系の停止点 (Man o'War / War Relic / Relic / In Reality 枝。ND や
    # Nasrullah を経由しない米国基礎系統なので、これらに達したら manowar)。
    "マンノウォー": "manowar", "Man o'War": "manowar",
    "War Relic": "manowar", "Relic": "manowar",
    "In Reality": "manowar", "Intentionally": "manowar",
}


# ===========================================================================
# 国別血統タイプ (亀谷敬正の分類、SmartRC「国系統」)。系統 (父系大系統) とは別軸で、
# 「その血が米国競馬で発展したか欧州競馬で発展したか」= 適性の質を表す。
#   - jpn 日本型: サンデーサイレンス系。瞬発力・トップスピード・平均ペース。
#   - usa 米国型: スピード・持続力・速いペース・短めの距離。ミスプロ/ストキャ等。
#   - eur 欧州型: スタミナ・パワー・遅いペース・長い距離。ND 欧州系/ロベルト等。
#
# **暫定分類 (2026-07-05)**: 2022 年 8 月改訂の公表ルール「日本型 = SS 系のみ、
# 非 SS 系は米国型/欧州型へ」に準拠し、非 SS 系は founder 由来 (Mr.Prospector/
# Storm Cat/Bold Ruler 米国分枝=米国型、Sadler's Wells/Danzig/Roberto=欧州型) で
# 既定値を置いた。亀谷氏の分類は本来**種牡馬個別**で会員サイトの公式リストが一次
# 出典。同系統でも米欧が割れる枝は COUNTRY_OVERRIDE で吸収する (ND の北米発展枝
# =Deputy Minister/War Front、ロベルト系米国残留枝=ナダル、ナスルーラ系欧州枝
# =トニービン/バゴ 等を 2026-07-05 予想ロジック監査で補正済み)。
# **なお公式リスト未突合の暫定が残る**: キングマンボ系の米/日 split、マクフィ
# (ドバウィ系=欧州?)、チーフベアハート/タリスマニック (北米発展?)、プリンスリー
# ギフト枝 (テスコボーイ/サクラバクシンオー)、ノーザンテースト。確定は
# docs/OPERATION.md「亀谷公式リスト突合」節の手順で会員サイトと突合後。
COUNTRY_LABEL: dict[str, str] = {
    "jpn": "日本型", "usa": "米国型", "eur": "欧州型", "unknown": "判別不能",
}
# 傾向集計の国系統セル dot 用の色 (label 文字を必ず併記するので色単独識別ではない)。
# 出馬表バッジは色相衝突 (系統 dot と重複) 回避のため塗りでなく枠線+テーマ色チップ
# (base.html.j2 .ctag-*) を使い、この hex は使わない。値は白/淡地上で判読できる
# 中彩度 (2026-07-05 mobile 監査: 旧 #e53935/#1e88e5/#43a047 は白文字 AA 未達だった)。
COUNTRY_COLOR: dict[str, str] = {
    "jpn": "#d32f2f",   # 赤 (日本)
    "usa": "#1976d2",   # 青 (米)
    "eur": "#2e7d32",   # 緑 (欧)
    "unknown": "#bdbdbd",
}

# 大系統 line_key → 国別タイプの既定値 (種牡馬個別の例外は COUNTRY_OVERRIDE)。
COUNTRY_BY_LINE: dict[str, str] = {
    "sunday": "jpn",          # 改訂ルールの定義: 日本型 = SS 系
    "kingmambo": "usa",       # Mr. Prospector 基盤 (キンカメ系は公式突合で要確認)
    "mrprospector": "usa",
    "storm": "usa",           # Storm Cat = 米国ダート/スピード
    "native": "usa",          # Native Dancer/Raise a Native = 米国
    "nasrullah": "usa",       # A.P. Indy/Bold Ruler 米国分枝を既定。欧州枝は override
    "northern": "eur",        # Sadler's Wells/Danzig/Galileo/ハービンジャー = 欧州
    "roberto": "eur",         # 日本の Roberto 系 (モーリス/エピファネイア) = 持続/パワー
    "turnto": "usa",          # Halo/Hail to Reason 米国。タイキシャトル系のスピード寄り
    "nearctic": "usa",        # Icecapade/Wild Again 米国ダート (トランセンド等)
    "manowar": "usa",         # マンノウォー系 (米国基礎種牡馬 Fair Play/Hastings 系)
    # 11 大系統外の旧欧州スタミナ系 → 欧州型 (非 SS + 長距離/持続の質。亀谷公式
    # 未突合の暫定)。
    "personon": "eur",        # パーソロン系 (メジロマックイーン=長距離スタミナ)
    "stsimon": "eur",         # セントサイモン系
    "hyperion": "eur",        # ハイペリオン系
    "unknown": "unknown",
}

# 種牡馬個別のオーバーライド (所属 line の既定値と国別タイプが異なるもの)。
# 最も確度が高いのはナスルーラ系の欧州分枝 (Grey Sovereign/Blushing Groom 経由) で、
# A.P. Indy 系 (米国型) とは血の質が明確に分かれる。
COUNTRY_OVERRIDE: dict[str, str] = {
    # ナスルーラ系のうち欧州で発展した枝 → 欧州型
    "トニービン": "eur",          # Grey Sovereign 系、欧州中長距離
    "カンパラ": "eur",            # 父 (Kalamoun→Zeddaan→Grey Sovereign)。トニービンと同枝=欧州
    "フォルティノ": "eur",         # Grey Sovereign 直仔 (仏)。欧州スプリンター/マイラー
    "クリスタルパレス": "eur",     # 父 Caro → Fortino → Grey Sovereign (仏)。欧州
    "ジャングルポケット": "eur",   # 父トニービン
    "トーセンジョーダン": "eur",   # 父ジャングルポケット
    "バゴ": "eur",               # Blushing Groom 系、仏・凱旋門賞
    "レインボウクエスト": "eur",   # Blushing Groom 系、欧州スタミナ
    "サクラローレル": "eur",      # 父レインボウクエスト
    "ミルリーフ": "eur",          # Never Bend 系だが英ダービー/凱旋門賞・欧州発展
    "メドウレイク": "usa", "Meadowlake": "usa",  # stsimon 系だが米国産・米国供用 (Prince John 枝)
    "ミルジョージ": "eur",         # 父ミルリーフ (欧州枝の子孫。nasrullah 既定 usa の例外)
    "イエローゴッド": "eur",       # 父 Red God (英仏で発展した欧州枝。Blushing Groom と同枝)
    "タマモクロス": "eur",         # 同 Grey Sovereign 枝 (トニービンと同質、天皇賞春=スタミナ)
    # ノーザンダンサー系のうち北米で発展した枝 → 米国型 (northern 既定=欧州の例外)。
    # Deputy Minister/Vice Regent 枝は ND の北米発展枝で亀谷氏の代表例
    # (クロフネ=米国型)。2026-07-05 予想ロジック監査の確定誤り指摘を反映。
    "クロフネ": "usa",            # 父フレンチデピュティ (Deputy Minister 枝、米国産ダート)
    "フレンチデピュティ": "usa",   # Deputy Minister → Vice Regent (北米)
    "マインドユアビスケッツ": "usa",  # Posse → Silver Deputy → Deputy Minister
    "デクラレーションオブウォー": "usa",  # War Front (Danzig 米国残留枝、米国供用)
    "アメリカンペイトリオット": "usa",    # 父ウォーフロント
    "ザファクター": "usa",        # 父ウォーフロント
    # ロベルト系のうち米国残留枝 → 米国型 (roberto 既定=欧州の例外)。
    "ナダル": "usa",             # Blame←Arch←Kris S. 米国残留枝、米国ダート G1 のみ
    # 英語名の併記 (3 代血統は海外祖先を英語で格納。カナ側 override と国別を一致させ、
    # 表記で日/米/欧が割れないようにする — 2026-07-06 profitability/prediction-logic)。
    "Mill Reef": "eur",          # =ミルリーフ (欧州名馬・スタミナ)
    "Deputy Minister": "usa",    # ND 北米発展枝 (カナ子孫 クロフネ/フレンチデピュティ=usa と一致)
    "Vice Regent": "usa",        # Deputy Minister の父 (北米)
}


def classify_country(sire_name: str | None, line_key: str) -> str:
    """種牡馬名 + その大系統 line_key から国別タイプ (jpn/usa/eur/unknown) を返す。

    種牡馬個別の COUNTRY_OVERRIDE を最優先し、無ければ line_key の既定値
    (COUNTRY_BY_LINE) を使う。line_key は classify_sire の戻り値を渡す想定。
    """
    key = _normalize(sire_name)
    if key in _COUNTRY_OVERRIDE_N:
        return _COUNTRY_OVERRIDE_N[key]
    return COUNTRY_BY_LINE.get(line_key, "unknown")


def country_label(country_key: str) -> str:
    return COUNTRY_LABEL.get(country_key, COUNTRY_LABEL["unknown"])


def country_color(country_key: str) -> str:
    return COUNTRY_COLOR.get(country_key, COUNTRY_COLOR["unknown"])


# JV-Data の馬名は旧 JRA 表記の**大書き仮名** (ヤ/ユ/ヨ/ツ/ア…) で格納される
# (例: リアルシヤダイ, トウシヨウボーイ, マツリダゴツホ)。辞書キーは現代表記の
# 小書き仮名 (シャ/ショ/ッ) なので、両者を大書きへ畳んで照合する (2026-07-06 実 DB
# で小書き差により多数の既知種牡馬が「その他」落ちしていた構造バグの対処)。
_KANA_SMALL_TO_LARGE = str.maketrans("ァィゥェォッャュョヮヵヶ", "アイウエオツヤユヨワカケ")
# 照合時に除去する記号・空白 (英語名の綴り変種を吸収)。半角/全角スペース、ピリオド、
# アポストロフィ 2 種 (' U+0027 / ’ U+2019)、バッククォート、ハイフン、中黒。
_PUNCT_STRIP = str.maketrans("", "", " 　.'’`-・")


def _normalize(name: str | None) -> str:
    """種牡馬名を照合キーに正規化。

    処理順: NFKC 正規化 (全角英字→半角・半角カナ→全角) + 小書き仮名→大書き仮名 +
    英字小文字化 + 記号/空白除去。JV-Data は UM 3 代血統で海外祖先を英語 (Title Case)
    で格納し (Alzao / Seattle Slew 等)、綴りに Mr. Prospector↔Mr.Prospector、
    A.P. Indy↔A.P.Indy、Sadler's Wells (' vs ’)、全角ローマ字等の揺れがある。
    これらを畳んでカタカナ主体の辞書と大小・記号差を無視して照合する
    (2026-07-06 実 DB で父母父/母母父の英語名が「その他」化 → 綴り変種で取りこぼす
    リスクを検証監査が指摘 → NFKC+記号 fold で頑健化)。カタカナ/漢字は不変。
    衝突は test_normalized_lookup_no_key_collision (len parity) が fail-fast で守る。
    """
    if not name:
        return ""
    # 繁殖馬マスタ(HN)の馬名フィールドは parse 上、全角名+パディングの末尾に
    # 隣接フィールド(半角カナ名)の先頭数文字が混入する (2026-07-06 実機判明:
    # 'ラオンジヤツク　…　ﾌﾞ' 等)。NFKC 前に**末尾の半角カナ(U+FF61-FF9F)+空白**を
    # 剥がす。全角馬名は末尾が半角カナにならず、英字/カタカナ辞書キーも影響を受けない
    # ので安全。これで breeding_horses の馬名が UM の父名と正規化一致する。
    s = name
    while s and (s[-1] in "　 \t\r\n\x00" or 0xFF61 <= ord(s[-1]) <= 0xFF9F):
        s = s[:-1]
    s = unicodedata.normalize("NFKC", s)
    return s.translate(_KANA_SMALL_TO_LARGE).lower().translate(_PUNCT_STRIP).strip()


# 辞書キー (小書き仮名の現代表記) を _normalize 済みの形に畳んだ照合表。
# 照合は必ずこれらを使う (生の LINE_BY_SIRE 等は可読性のための原本)。
_LINE_BY_SIRE_N = {_normalize(k): v for k, v in LINE_BY_SIRE.items()}
_FOUNDERS_N = {_normalize(k): v for k, v in FOUNDERS.items()}
_COUNTRY_OVERRIDE_N = {_normalize(k): v for k, v in COUNTRY_OVERRIDE.items()}


# breeding_horses の「正規化馬名 → breeding_num」索引のキャッシュ (接続ごと)。
# UM 3 代血統の sire_breeding_num は HN の breeding_num と採番系が食い違う実 DB がある
# (2026-07-06 実機: breeding_num 一致率 0.6%)。そこで遡上の入口を「名前一致」にし、
# breeding_horses 内部で自己整合な breeding_num ポインタで上に辿る。名前は _normalize
# (仮名 fold + 記号/空白畳み込み) で照合するため、exact SQL 一致が 0% でも拾える。
_bh_name_index_cache: dict[int, tuple[int, dict[str, str]]] = {}


def _breeding_name_to_num(conn) -> dict[str, str]:
    """breeding_horses を「正規化馬名 → breeding_num」に索引化してキャッシュ。
    行数が変われば再構築 (再取込への追随)。テーブルが無ければ空 dict。"""
    try:
        count = conn.execute("SELECT COUNT(*) FROM breeding_horses").fetchone()[0]
    except sqlite3.OperationalError:
        return {}
    cached = _bh_name_index_cache.get(id(conn))
    if cached is not None and cached[0] == count:
        return cached[1]
    idx: dict[str, str] = {}
    try:
        for row in conn.execute("SELECT horse_name, breeding_num FROM breeding_horses"):
            try:
                nm, bn = row["horse_name"], row["breeding_num"]
            except (TypeError, IndexError, KeyError):
                nm, bn = row[0], row[1]
            k = _normalize(nm)
            if k and bn:
                idx.setdefault(k, bn)  # 同名は先勝ち (重複スナップショット対策)
    except sqlite3.OperationalError:
        return {}
    _bh_name_index_cache[id(conn)] = (count, idx)
    return idx


def _traverse_from_num(conn, start_num: str | None, max_depth: int) -> str | None:
    """breeding_horses を breeding_num で父系遡上し、各世代の馬名を辞書照合。
    当たれば line_key、当たらなければ None。テーブル欠如は 1 回警告して None。"""
    seen: set[str] = set()
    cur = start_num
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
        except sqlite3.OperationalError as e:
            global _warned_no_breeding_table
            if not _warned_no_breeding_table:
                _warned_no_breeding_table = True
                logger.warning("血統遡上を無効化して辞書照合のみで継続します: %s", e)
            return None
        if row is None:
            break
        try:
            name, parent_name, parent_num = (
                row["horse_name"], row["sire_name"], row["sire_breeding_num"])
        except (TypeError, IndexError, KeyError):
            name, parent_name, parent_num = row[0], row[1], row[2]
        for candidate in (name, parent_name):  # sire_name は空の DB もある
            k = _normalize(candidate)
            if k in _LINE_BY_SIRE_N:
                return _LINE_BY_SIRE_N[k]
            if k in _FOUNDERS_N:
                return _FOUNDERS_N[k]
        cur = parent_num
    return None


def classify_sire(sire_name: str | None, conn=None, sire_breeding_num: str | None = None,
                  max_depth: int = 12) -> str:
    """種牡馬名 (と任意で breeding_num) から大系統 line_key を返す。

    1. LINE_BY_SIRE / FOUNDERS の直接照合。
    2. conn があれば breeding_horses を父系遡上:
       (a) UM 由来 sire_breeding_num で遡上 (採番系が一致する DB 用)。
       (b) 失敗したら**種牡馬名で breeding_horses を引き HN の breeding_num を得てから**遡上
           (UM と HN で breeding_num 採番系が食い違う実 DB の救済)。
    3. いずれも当たらなければ "unknown"。
    """
    key = _normalize(sire_name)
    if key in _LINE_BY_SIRE_N:
        return _LINE_BY_SIRE_N[key]
    if key in _FOUNDERS_N:
        return _FOUNDERS_N[key]
    if conn is None:
        return "unknown"

    # (a) UM 由来 breeding_num で遡上
    if sire_breeding_num:
        r = _traverse_from_num(conn, sire_breeding_num, max_depth)
        if r:
            return r
    # (b) 名前照合で HN の breeding_num を得てから遡上 (採番系不一致の救済)
    hn_num = _breeding_name_to_num(conn).get(key)
    if hn_num and hn_num != sire_breeding_num:
        r = _traverse_from_num(conn, hn_num, max_depth)
        if r:
            return r
    return "unknown"


def lookup_line(name: str | None) -> str | None:
    """種牡馬名 → line_key を正規化照合で直接引く (遡上なし)。無ければ None。

    LINE_BY_SIRE → FOUNDERS の順で _normalize 済みキーで照合する。モジュール外
    (scripts/audit_sire_lines.py 等) が生の LINE_BY_SIRE/FOUNDERS を直接引くと
    _normalize の仮名大書き化と食い違い小書きキーに当たらないため、照合は必ず
    この公開関数を通す (2026-07-06 code-quality 監査 P1)。
    """
    k = _normalize(name)
    if k in _LINE_BY_SIRE_N:
        return _LINE_BY_SIRE_N[k]
    return _FOUNDERS_N.get(k)


def line_label(line_key: str) -> str:
    return LINE_LABEL.get(line_key, LINE_LABEL["unknown"])


def line_label_short(line_key: str) -> str:
    return LINE_LABEL_SHORT.get(line_key, LINE_LABEL_SHORT["unknown"])


def line_color(line_key: str) -> str:
    return LINE_COLOR.get(line_key, LINE_COLOR["unknown"])
