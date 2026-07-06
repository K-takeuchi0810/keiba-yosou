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
    "unknown": "その他",
}

# WCAG を意識した識別しやすい色 (light/dark 双方で判別可能な中彩度)。
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
    "フォーティナイナーズサン": "mrprospector",  # 父フォーティナイナー
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
    # 注: ダノンレジェンド (父 Macho Uno = In Reality 系) やパーソロン系
    # (メジロマックイーン等) のような 11 大系統外は辞書に載せず unknown (グレー)
    # に落とす。誤答よりも「その他」が誠実。
}

# 父系遡上の始祖 (breeding_horses を遡って当たったらこの系統)。
# LINE_BY_SIRE と重複する founder も含め、遡上時の停止点として使う。
FOUNDERS: dict[str, str] = {
    "サンデーサイレンス": "sunday",
    # Roberto 系は遡上中に「ロベルト」で先に停止するため、ここまで遡った
    # Hail to Reason 系は非 Roberto 枝 (Halo 非 SS 等) = turnto (2026-07-05 是正。
    # 旧: 便宜上 roberto 寄せ → タイキシャトル等が誤表示になるため独立させた)。
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
    "unknown": "unknown",
}

# 種牡馬個別のオーバーライド (所属 line の既定値と国別タイプが異なるもの)。
# 最も確度が高いのはナスルーラ系の欧州分枝 (Grey Sovereign/Blushing Groom 経由) で、
# A.P. Indy 系 (米国型) とは血の質が明確に分かれる。
COUNTRY_OVERRIDE: dict[str, str] = {
    # ナスルーラ系のうち欧州で発展した枝 → 欧州型
    "トニービン": "eur",          # Grey Sovereign 系、欧州中長距離
    "ジャングルポケット": "eur",   # 父トニービン
    "トーセンジョーダン": "eur",   # 父ジャングルポケット
    "バゴ": "eur",               # Blushing Groom 系、仏・凱旋門賞
    "レインボウクエスト": "eur",   # Blushing Groom 系、欧州スタミナ
    "サクラローレル": "eur",      # 父レインボウクエスト
    "ミルリーフ": "eur",          # Never Bend 系だが英ダービー/凱旋門賞・欧州発展
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
_KANA_SMALL_TO_LARGE = str.maketrans("ァィゥェォッャュョヮ", "アイウエオツヤユヨワ")


def _normalize(name: str | None) -> str:
    """種牡馬名を照合キーに正規化 (全角空白除去 + trim + 小書き仮名→大書き仮名)。

    注: 半角カナ・その他の異表記 (海外馬の音写ゆれ等) には対応しない。breeding_horses
    の表記が辞書キーとずれると遡上停止点を素通りし得る (2026-07-05 検証監査)。
    その検出は scripts/audit_sire_lines.py の実 DB 突合で行う。
    """
    if not name:
        return ""
    return name.replace("　", "").strip().translate(_KANA_SMALL_TO_LARGE)


# 辞書キー (小書き仮名の現代表記) を _normalize 済みの形に畳んだ照合表。
# 照合は必ずこれらを使う (生の LINE_BY_SIRE 等は可読性のための原本)。
_LINE_BY_SIRE_N = {_normalize(k): v for k, v in LINE_BY_SIRE.items()}
_FOUNDERS_N = {_normalize(k): v for k, v in FOUNDERS.items()}
_COUNTRY_OVERRIDE_N = {_normalize(k): v for k, v in COUNTRY_OVERRIDE.items()}


def classify_sire(sire_name: str | None, conn=None, sire_breeding_num: str | None = None,
                  max_depth: int = 12) -> str:
    """種牡馬名 (と任意で breeding_num) から大系統 line_key を返す。

    1. LINE_BY_SIRE の直接照合。
    2. conn と sire_breeding_num があれば breeding_horses を父系遡上し、
       各世代の父名を LINE_BY_SIRE / FOUNDERS に照合。
    3. いずれも当たらなければ "unknown"。
    """
    key = _normalize(sire_name)
    if key in _LINE_BY_SIRE_N:
        return _LINE_BY_SIRE_N[key]
    if key in _FOUNDERS_N:
        return _FOUNDERS_N[key]

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
        except sqlite3.OperationalError as e:
            # breeding_horses 未作成の古い DB (BLOD 未取込 + readonly 接続で
            # migration も走らない) では遡上せず辞書照合のみで劣化させる。
            # 静かな劣化は「全部その他」症状の原因切り分けを不能にするので
            # 1 回だけ警告を出す (2026-07-05 code-quality 監査指摘)。
            global _warned_no_breeding_table
            if not _warned_no_breeding_table:
                _warned_no_breeding_table = True
                logger.warning("血統遡上を無効化して辞書照合のみで継続します: %s", e)
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
            if k in _LINE_BY_SIRE_N:
                return _LINE_BY_SIRE_N[k]
            if k in _FOUNDERS_N:
                return _FOUNDERS_N[k]
        cur = parent_num
    return "unknown"


def line_label(line_key: str) -> str:
    return LINE_LABEL.get(line_key, LINE_LABEL["unknown"])


def line_label_short(line_key: str) -> str:
    return LINE_LABEL_SHORT.get(line_key, LINE_LABEL_SHORT["unknown"])


def line_color(line_key: str) -> str:
    return LINE_COLOR.get(line_key, LINE_COLOR["unknown"])
