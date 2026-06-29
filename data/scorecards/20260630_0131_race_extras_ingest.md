# 採点 2026-06-30 01:31

**改修内容**: RACE dataspec の全レコード取り込み完備。式別オッズ O2-O6 (馬連/ワイド/馬単/三連複/三連単)・票数 H1/H6・競走馬除外 JG・WIN5 WF の parser/schema/db/ingest を追加 (commit ad696d0/7c21493/47a6f1f)。指摘是正 (cc5a82b)。実 ingest バックフィルは bg 進行中。production 予想/GUI/backtest 不変。
**対象ファイル**: jvlink_client/parser.py, jvlink_client/ingest.py, db.py, data/schema.sql, scripts/backfill_race_extras.py, tests/test_exotic_odds_votes.py, tests/test_scratches_win5.py

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 | 判定 |
|---|---|---|---|---|
| GUI / UX 監査人 | 3.6 | 3.6 | ±0 | PASS (スコープ外) |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 | PASS (スコープ外) |
| 予想ロジック分析官 | 4.0 | 4.0 | ±0 | PASS |
| 収益性ジャッジ | 4.0 | 3.5 | **+0.5** | PASS |
| データ基盤エンジニア | 4.4 | 4.2 | +0.2 | PASS |
| コード品質レビュアー | 4.2 | 4.2 | ±0 | PASS |
| 検証プロセス監査人 (最終ゲート) | 4.1 | 4.0 | +0.1 | **GATE PASS** |

平均 **約 4.13**。**全員 PASS / 最終ゲート PASS**。後退 (前回比 -0.3 以上) なし。
純データ層追加・production 非接続 (新テーブル参照ゼロ) を全員が grep で実証。

## 各専門家の所見 (要約)

### データ基盤エンジニア (4.4, PASS ⬆+0.2)
冪等性 4→5: 配列系を (race複合キー, bet_type, combo) 単位 PK + executemany 行展開、再 upsert で行数不変を実 DB roundtrip で検証。backfill は COMMIT_EVERY=50 + finally close でクラッシュ一貫性。**実 raw 反証**: 全 O2 ファイルの data_div は確定'5':22376/削除'9':64 のみ (provisional 不在) → 現コーパスで odds 汚染クラスは発生しない。観測性: extras 行数計上で byte drift→0 行検出可。減点: PK に data_div 無し (将来 in-running 混入時の防御コード無し)、backfill の um 計上不整合、致命例外の種別集計欠如。

### コード品質レビュアー (4.2, PASS)
テスト容易性 4→5: DB往復テストで dataclass↔schema drift を即 OperationalError 検出 (前回宿題クリア)。観測性 3→4: _bump(rt,n) 行数計上 + warning 化。DRY: _EXOTIC_SPECS/_H*_BLOCKS テーブル駆動良。dead code 4→3 後退: parse_jg_file/parse_wf_file が _split_fixed トラップを再生産。**変更失敗モード**: _fit のサイレント正規化が、巨大 O6/H6 の CRLF 断片化時に配列後半をゼロ埋め→件数サイレント欠損 (痕跡なし)。

### 検証プロセス監査人 (4.1, GATE PASS) ★最終ゲート
production 全パスから新テーブル参照ゼロを grep 実証 (数値/リーク/skew 新規リスクなし)。byte 位置は実 raw 回帰テストが PASS (skip でない=synthetic 依存脱却)、第三者再現可。前回宿題: 件数サイレント→解消、実 raw 回帰→解消。**降格宣言 (次回 FAIL 材料)**: (1) _split_fixed トラップ未解消で新コードに踏襲 (2 セッション連続)、(2) 特徴量化前に PIT ゲート必須 (確定=発走後を発走前特徴に使用禁止)。

### 予想ロジック分析官 (4.0, PASS)
features.py 未参照=土台整備。F3 (市場マイクロストラクチャ) の素材として妥当・死蔵でない (着手条件明記)。重要区別: 水準スナップショットは市場既織り込み (alpha≈0)、価値は票数シェアのドリフトや式別オッズの相関構造 vs モデル。**train-serve skew/リーク** (3/5): 確定オッズ/票数を発走前特徴に使えばターゲットリーク。GUI(朝)とbacktest(確定込み)で鮮度ゲート不一致だと skew。

### 収益性ジャッジ (4.0, PASS ⬆+0.5)
predictor/config/gui/web diff ゼロ実測=回収率/EV/Kelly/フィルタ回帰なし。alpha 寄与分析: O2-O6 は market implied prob の cross-validation 素材だが複系控除率 20-25% で抽出困難、H1/H6 票数は最終オッズと大部分重複 (純寄与小)、JG は損失防止側。現状 OOS ROI 67% (CI 上限 99.8%<100%=エッジなし) の根因は calibration/model blend であり外部オッズ追加で直接解決しない。本改修は「将来への仕込み」。

### GUI/UX (3.6) / モバイルHTML (4.6) — ともに PASS (スコープ外)
gui/app.py・web/ 無変更を git diff で実測。JS パース PASS、HTML 399KB 維持。回帰なし。

## 是正済み (cc5a82b)

1. **_split_fixed CRLF 対応化** (validation 降格宣言 + code-quality 後退要因) — len%length トラップを CRLF 分割フォールバックで一掃。全 parse_*_file が実 raw で動作。回帰テスト追加。
2. **_fit 断片化ガード** (code-quality 変更失敗モード) — ±16 byte 超の乖離で warning。件数サイレント欠損に痕跡。
3. **PIT/leak-safe 明記** (data-pipeline + 予想ロジック + 検証 合意) — schema に「確定スナップショット・発走前特徴に使用禁止・速報混入時は PK に data_div 追加」を明記。
4. **backfill um 計上** (data-pipeline) — core_total に集計。

## 横断的に見た優先課題 (是正後に残るもの・優先順)

1. **特徴量化前の PIT ゲート設計** (検証 降格 #2 + 予想ロジック + data-pipeline) — F3 を実装する際、発走前 速報 odds/票数 (別 data_div) を取り込み、PK に data_div を加えて「発走前スナップショットのみ」を特徴入力にする。確定 (data_div=5) は学習・推論どちらにも入れない。現状はドキュメントで凍結済。
2. **致命例外の種別集計** (data-pipeline #3、master 期からの継続) — ingest_all の errors[] を failed_reason 分類粒度に。
3. **upsert の方式統一** (code-quality) — O/H 系は手書きタプル、JG は asdict の 2 方式併存。
