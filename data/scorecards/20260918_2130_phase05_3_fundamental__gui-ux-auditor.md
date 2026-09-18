# GUI / UX 監査人 採点 — 2fb703a Phase 0.5-3 Fundamental Model

## 判定: HOLD (前回維持 — 本改修由来の減点・停止条件抵触なし)

**理由**: type-B (分析スクリプト/台帳新設)。`gui/` `web/` `predictor/rules.py` `predictor/features.py` に差分なし、GUI への間接影響も下記 6 点で不在を実測。判定は直近 GUI 採点 (20260914, 3.2 / HOLD) を維持。HOLD 事由 (成績カードの期間表示 / 凍結バナー) の是正コードは `gui/app.py:462-481` に存在を確認したが、実機ウォークスルーによる再採点は次回 type-D 改修時に行う (スコア 3.2 < 4 のため rubric 上 PASS は出せない)。
**根拠ファイル**: `predictor/feature_manifest.py:101-121,124-135` / `predictor/ml_model.py:25-27` / `predictor/rules.py:1020-1059` / `config.py:201-208` / `gui/app.py:871-879,2356`
**次アクション**: 依頼 2 の表示要件 (下記 R1-R8) を 0.5-4 の設計に取り込む。GUI 実装時は R3 (発火 provenance の単一出典) を契約テスト化してから着手。

**改修タイプ宣言**: type-B。`git show 2fb703a --stat` = 12 files / +18,362 / -0 (全て新規追加)。P25 固有ゲート (market_snapshot / CONTROL_HTML 表示) は N/A。JS パースは CONTROL_HTML 無変更のため必須外だが回帰確認として実行。

## 総合: 3.2 / 5 (前回 3.2 維持)

## 依頼 1: GUI への間接影響 — なし (6 点実測)

1. **逆依存なし**: `feature_manifest|fundamental` を `predictor/ gui/ web/ config.py` で grep → 自己参照 (`feature_manifest.py:134`) のみ。`rules.py` `features.py` `predictor/__init__.py` は新モジュールを import しない。依存は `scripts/fundamental_*.py → predictor.feature_manifest` の一方向。
2. **features.py への作用は read-only**: `feature_manifest.py:107-108` は `features.py` をテキストとして `ast.parse` するだけ。monkeypatch・グローバル状態変更なし。
3. **新モデルファイルの誤読込なし**: `predictor/fundamental_model.txt` / `.meta.json` が追加されたが、`ml_model.py:25-27` は固定名 `lgbm_model.txt` / `lgbm_meta.json` を読む。venv32 実測 `MODEL_PATH=lgbm_model.txt exists=True`。
4. **封印指紋に影響なし**: `config.SEALED_ARTIFACTS` (`config.py:201-208`) は固定 6 ファイルの dict。新規ファイル追加で drift 検出 → 生成中止 → Discord 通知は発火しない (auto_predict 経路の無人停止リスクなし)。
5. **互換テーブル失効トリガに影響なし**: `rules.py:1035` の glob は `*-filtered.json`。追加された `data/backtest/20260918_phase05_3_frontrun.json` / `_fundamental_vs_t10.json` は非該当。
6. **実行確認**: `.venv32` で `predictor.rules/features/ml_model` + `gui.app` import OK。CONTROL_HTML JS 22,428 文字 `node --check` PASS。`pytest tests/test_feature_manifest.py tests/test_fundamental_dataset.py tests/test_gui_js_contract.py` = 20 passed。`-k "sealed or artifact or gui"` = 40 passed / 1 skipped。

**反証の試み**: 「新設の `assert_no_market_features` が本番経路のどこかで呼ばれ、`track_recent_*_avg_winning_pop` を使う本番 112 特徴が例外で落ちる」→ 呼び出し元は `scripts/fundamental_model.py:46` `scripts/fundamental_eval.py:41` のみ (grep)。本番 `predict_race` 経路には未接続 → 不成立。

## 依頼 2: 市場確率 / AI 確率 / 差 の表示要件 (0.5-4 先回り)

前提事実: 憲法の式は `logit(P_true) = logit(P_market) + AI補正`。Fundamental 単体は較正が崩れている (`docs/PHASE05_RESULTS.md`: 0-5% 帯で強気、10-20% 帯で +2.26pt 弱気、CI が 0 をまたがない)。現 GUI は `Odds最新` を `MAX(odds_fetched_at)` と「現在時刻からの分数」で 1 個だけ出す (`gui/app.py:871-879,2356`)。過去に `◎ ≠ 最高 P` が 42% で発生 (MEMORY 2026-07-19)。

- **R1 三値を必ず同じ行に並べる**: `市場 12.0% | AI補正 +2.5pt | 最終 14.5%`。EV や倍率 (「市場の 2.3 倍」) は主表示にしない (低確率帯で比率が誇張される = 誤読)。符号規約は 1 箇所に凡例固定: 「+ = 市場が過小評価している馬」。色は補助のみ、テキストラベル必須 (WCAG 1.4.1)。
- **R2 Fundamental 単体確率を「AI 確率」として単独表示しない**: 帯別較正が崩れている間は、表示するなら「未較正 / 参考」の別スタイルで最終列から分離。0.5-4 完了後は較正済 offset のみを表示。
- **R3 「設定 ON」と「発火」の分離 — 馬ごと provenance バッジ**: 各馬に `補正あり (T−N分 / fresh)` / `補正なし: stale` / `補正なし: 市場 unknown` / `補正なし: 機能 OFF` の 4 状態を出す。**値の出典は P を計算した同じオブジェクト** (Prediction dataclass に `market_offset_applied: bool` `market_offset_reason: str` を追加) とし、`config` のフラグから JS 側で組み立てない。P25 期の混同は「設定値を表示 → 実発火はサイレント」が原因。契約テスト (`tests/test_gui_js_contract.py` 流) で「バッジ文言が dataclass 由来」を固定。
- **R4 鮮度はレース単位・発走基準**: 既に `rules.py:237-255 _market_snapshot_age_min` が「発走時刻 − fetched_at」を馬ごとに持つ。GUI ヘッダの `MAX / N分前 (現在基準)` を廃止し、レースカードに `発走 T−N 分のオッズ` を出す。加えて日次サマリに `fresh / stale / unknown 頭数` を必置 (現 GUI は 0 箇所、web は `stale_suppressed` のみ)。検証結果は T−10 基準なので、T−10 より早い/遅いスナップショットには「検証条件 (T−10) と異なる」注記。
- **R5 印と確率の一致保証**: ◎ は表示中の最終 P (市場+補正) から導出するか、そうでなければ「◎ = ルール順位 / P = 確率」と行単位で分離表示。42% の不一致を再発させない。
- **R6 3 層ラベルを視覚的に非同型に**: `観察 (封印中)` / `購入候補 (判定後のみ)` / `本番採用` を色・アイコン・配置すべて別にし、`購入候補` 以上は `config` 単一出典のゲート (F3 判定 PASS が記録済み、`buy_filter_suspended()==False`、`SEALED_ARTIFACTS` 一致) を全て満たすまで DOM に出さない (CSS 非表示ではなく生成しない)。
- **R7 モデル指紋の表示**: ヘッダに `生成 時刻 / モデル指紋 (SEALED_ARTIFACTS sha 先頭 8 桁) / offset モデル版`。封印中に「どのモデルの出力か」がユーザに見えないと、判定の正当性を目視確認できない。
- **R8 差の帯別信頼度**: `+2.5pt` の横に帯別の較正 CI (例 `10-20% 帯: 実測 +1.3〜+3.3pt`) を tooltip で出す。単点の差だけを出すと過信を招く (Nielsen 1: 状態の可視性は「確からしさ」を含む)。

## 項目別 (前回維持、本改修による変動なし)

- **タスクフロー / 発見性: 3/5** — 差分なし。0914 是正 (凍結バナー) の実機再確認は未実施。
- **エラーの人間化 / 回復支援: 3/5** — 差分なし。
- **システム状態の可視性: 3/5** — 差分なし。`gui/app.py:2356` の鮮度表示が現在時刻基準の単一値 (R4 の根拠)。
- **状態整合性 / 誤読防止: 3/5** — 差分なし。fresh/stale/unknown 頭数は GUI 未表示のまま (P25 固有 Hard Fail は type-B のため N/A、type-A/D 移行時に FAIL 条件へ昇格)。
- **レイアウト / 入力効率 / a11y: 4/5** — 差分なし。

## 停止条件チェック

- [x] GUI / HTML 差分なし (前回スコア維持)
- [x] 逆依存・誤読込・封印指紋・glob の 4 経路で間接影響なし (実測)
- [x] JS `node --check` PASS / gui.app import OK (venv32)
- [x] 対象テスト 20 + 40 passed
- P25 固有 (market_snapshot counts / paired baseline / CONTROL_HTML 表示): N/A (type-B)
- [x] 専門領域別 Hard Fail 不抵触

## 主な改善提案 (本改修範囲外、0.5-4 着手前)

1. **Prediction に `market_offset_applied / market_offset_reason / snapshot_age_min` を追加** — R3/R4 の単一出典。`predictor/rules.py:218-234` の dataclass。GUI 実装より先に型を固定する。
2. **`gui/app.py:871-879` の MAX 集約を race 単位に置換** — `_market_snapshot_age_min` を再利用し、サマリは `fresh/stale/unknown` 頭数に変える。
3. **0913 持ち越し (1 回目)**: 「同日 3 回の重複 Discord 通知」の差分化 (gui-ux 担当) は未消化を確認していない。次回追跡。

## 前回からの差分

- 全 5 項目: 変動なし (GUI 無変更)。総合 3.2 → 3.2。
- 前回判定 HOLD (20260914) → 今回 HOLD 維持。理由: 本改修は GUI 非影響だが、HOLD 解除には 0914 是正の実機再採点 (type-D 改修時) が必要。
