# コード品質 / 保守性レビュー — F3 Phase 0-0

## 総合: 4.0 / 5（主要指摘対応後）

- 前回: 3.7 / 5（本 F3 Phase 0-0 初回レビュー）
- 今回: 4.0 / 5
- 差分: **+0.3**
- 参考 baseline: 3.9 / 5（`20260607_p20_kelly_display__code-quality-reviewer.md`）

固定 split/seed、3チャネル allowlist、readonly DB、環境変数と monkeypatch の
`finally` 復元、production artifact の前後 SHA-256 比較は、安全な実験スクリプトとして
良い構造である。初回指摘後、実行 evaluator 自体の SHA-256、cache 実 race key の境界検証、
project root 外パスの拒否が追加された。さらに historical calibrator の current への silent fallback
を廃止し、使用 calibrator の SHA-256 を保存した。metrics 記録値 `48b158...ae491` と evaluator、
`d6793b...d489` と calibrator の実測 SHA-256 はそれぞれ完全一致し、未追跡中でも実行コードと
主要入力の content identity を検証できる。残る主な保守性課題は、
実験仕様値の平行記述と、139行の `run()` に I/O・学習・評価・成果物生成が集中している点である。

## 項目別

- **DRY / 重複コード: 4.0 / 5** — `_classification_metrics`、`_train_model`、
  `_temporary_environment`、`_artifact_hashes` への分離は適切。3チャネル遮断も helper 経由。
  減点は `BLOCKED_FEATURES` と `LIVE_VALUES` のキー二重管理、experiment ID の2回記述、
  report の3特徴名・`70.7%` の直書き、artifact path の「実パス生成」と metrics 用文字列の
  平行記述。変更時に report/JSON/実処理がずれる余地がある。

- **dead code / 未使用シンボル: 4.0 / 5** — 対象スクリプトの21関数は全て module 内または
  `main`/tests から到達し、基本 AST 検査で未使用 import は0件。今回追加分に明白な dead code はない。
  必須 dead-feature 簡易検査は rules 非参照候補32件を出したが、29件は現行 production LGBM
  schema が消費する。残る3候補は `recent_4corner_avg_position/change/samples` で、今回未導入の
  repo-wide 整理候補として別タスクで利用先を再確認すべき。

- **マジックナンバー / 設定外出し: 3.5 / 5** — 期間、seed、bootstrap 回数、出力先、
  production artifact は module 定数化され、固定実験として追跡しやすい。一方、112特徴、
  100円 stake、95% CI の 2.5/97.5、200 race ごとの進捗、環境 override、historical calibrator の
  path に型付き spec や根拠コメントがない。ただし historical calibrator は `.bak` 必須で
  fail-closed となり、使用内容の SHA-256 も metrics に固定されたため、初回の silent fallback
  / identity 不明という重大懸念は解消した。

- **テスト容易性 / 副作用分離: 4.0 / 5** — metrics、AUC、top-1、bootstrap、チャネル遮断は
  pure helper に分かれ、7 unit tests は全て成功。入力配列非破壊、sealed 拒否、cache 実 race key、
  外部パス拒否、race 単位 top-1、bootstrap 決定性を検証している。ただし `run()` は
  cache/production metadata 読込、2モデル学習、
  OOS、model/report/JSON 書込を一体化しており、production 不変・例外時復元・固定 split の同一性を
  unit test できていない。`_write_report`、`_temporary_environment`、`_training_params`、
  `_pooled_auc`、不正 cache/schema、0件/0 samples の境界テストもない。

- **エラー処理 / ログ / 安全境界: 4.5 / 5** — `open_db_readonly()`、sealed guard、artifact
  hash、`try/finally` による loader/calibrator cache 復元は強い。実測 metrics でも production
  SHA-256 は前後一致。`_require_project_path()` は `resolve()` 後に project root への
  `relative_to()` を要求するため、`..` と symlink による外部 cache/output/report 逸脱を拒否する。
  `_guard_cache_race_keys()` は cache 実値の最小・最大日付を sealed guard と登録 train window の
  双方で検査する。F3 内の `print` は進捗と CLI 最終結果のみ。減点は `_git_sha()` が取得失敗を
  無言で `unknown` にすること、成功終了時しか post-hash を検査しないこと、暦日妥当性を見ないこと。

## 検証結果

- `git log --stat -3`: 直近3 commit は予想 HTML publish。今回の script/test/doc は未追跡。
- `pytest tests/test_f3_phase0_0_eval.py -q`: **7 passed in 0.22s**。
- `compileall`: 対象 script/test とも成功。
- evaluator SHA-256: metrics/report の `48b158bd...ae491` と現ファイル実測値が完全一致。
- historical calibrator: `.bak` 不在時は `FileNotFoundError` で fail-closed。metrics の
  `d6793b14...d489` と実ファイル SHA-256 が完全一致。
- 新規境界: cache 実 race key の sealed/窓外拒否、project root 外の
  cache/output/report path 拒否を実装。path は canonicalize 後に判定。
- Ruff は `.venv64` に未導入のため実行不能。代替の基本 AST 検査で未使用 import 0件、
  未呼出し top-level function 0件。
- 必須 repo scan: `predictor/rules.py` は def 20件、直書き `score +=/-=` 1件。
- 必須 print scan: gui/predictor/jvlink_client/web に9件。確認範囲では CLI/main の表示で、
  今回追加した debug print はない。
- `data/f3_phase0_0/metrics.json`: production artifact 前後4件が全一致、
  `production_artifacts_unchanged=true`。ただし `data/*` ignore 対象。

## 優先課題

1. **実験仕様を単一の immutable spec にまとめる。** `ExperimentSpec` 等に期間、seed、
   `blocked_channels: {name: live_value}`、reference/calibrator hash、stake、CI、env override、
   experiment ID を集約し、実処理・metrics・report を同一 spec から生成する。
2. **`run()` を orchestration と pure assembly に分離し境界テストを追加する。** split 構築、
   validation 比較、成果物 manifest を抽出し、production hash 不変、例外時の env/module 復元、
   不正暦日、空 OOS、`bootstrap_samples <= 0`、report/metrics 整合を tmp_path + mock で検証する。
3. **provenance の仕上げ。** script SHA により初回の重大懸念は解消した。commit 後は commit SHA
   と script SHA の双方を維持し、`_git_sha()` の `unknown` fallback は warning または fail-fast にする。

## 判定

**合格。** 本番不変、sealed/窓外 cache 拒否、外部パス拒否、実行コード content identity を確認した。
残課題は次回の保守性改善で扱える範囲であり、F3 Phase 0-0 結果の引き渡しを妨げない。
