# GUI / UX 監査人 採点 — 99eec68 Phase 0.5-4B 基盤修復

## 判定: HOLD (前回維持 — 本改修由来の GUI 減点なし / 自己提案 3 回放置による降格 1 件)

**理由**: type-B (config 分割定義 + 分析スクリプト + 学習成果物)。`git show 99eec68 --stat` = 20 files、`gui/` `web/` `predictor/*.py` に差分ゼロ。config 変更の GUI / 予想生成経路への波及は下記 7 経路で不在を実測。
**根拠ファイル**: `config.py:118-130,170-183,223-230,247-270` / `gui/app.py:23-35` / `predictor/ml_model.py:25,67` / `scripts/auto_predict.py:198-207,259` / `tests/test_data_split.py:68-101`
**次アクション**: `scripts/auto_predict.py` の同日重複 Discord 通知の差分化 (3 回目の持ち越し)。

## 総合: 3.1 / 5 (前回 3.2、−0.1)

## 依頼: config 変更の GUI / 既存予想経路への影響 — なし (7 経路実測)

1. **gui/app.py は DATA_SPLIT / DATA_PERIODS / SPLIT_DIVERGENCE / data_split() を一切参照しない**: 取り込み名は 11 個のみ。venv32 で import 後にソース正規表現検査 → False。`web/generator.py` も 0 件。**DATA_PERIODS 経路と混ざる余地なし**
2. **DATA_PERIODS 利用側は無変更**: `filter_sweep / bias_scan / monitor` が参照する値を venv32 実測で確認。`SPLIT_DIVERGENCE` の宣言文言が「旧経路は動かさない・混ぜない」と明記し、`test_new_split_does_not_collide_with_legacy_periods` / `test_declared_divergences_are_real` が未宣言の食い違いと陳腐化した宣言の両方を落とす。17 passed
3. **分割の重なりなし**: `warmup` 追加後も `splits_are_disjoint()` → True
4. **誤ロードなし**: `ml_model.py:25` は固定名。`predictor/*.py` にディレクトリ走査ロードなし
5. **封印指紋に干渉なし**: `SEALED_ARTIFACTS` は固定 6 key で置き換わった 2 ファイルは非対象。`artifact_drift()` → `[]`。`auto_predict.py:198` の drift ゲートも発火しない
6. **import 実行 (venv32)**: config → gui.app → predictor.rules / features すべて OK
7. **予想生成経路**: `auto_predict.py` → `web.generator` の期間引数は当日のみで、DATA_SPLIT / DATA_PERIODS を参照しない

**反証の試み**: 「`warmup` が `splits_are_disjoint` の対象に入り、将来 train を 2021 に戻すと黙って重なる」→ 重なれば `test_splits_do_not_overlap` が落ちる。棄却。

## 項目別

- タスクフロー / 発見性: 3/5 (変動なし)
- エラーの人間化 / 回復支援: 3/5 (変動なし)
- **システム状態の可視性: 3 → 2.5/5** (過去提案 3 回放置による降格。本 commit 由来ではない)
- 状態整合性 / 誤読防止: 3/5 (変動なし)
- レイアウト / 入力効率 / a11y: 4/5 (変動なし)

## 参考所見

- `SPLIT_DIVERGENCE` は「同名で期間が違う 2 系統が共存する」ことをコードで宣言した良い実装 (Nielsen 5: エラー防止を UI ではなく定義層で行う)。ただし **GUI の成績カード / backtest 期間表示は依然 DATA_PERIODS 系**なので、将来 Fundamental 系を GUI に載せる場合は「学習 2022-2024 (0.5-4B)」と「TRAIN 2021-2023 (旧)」を同じ語 (train) で出さないこと。同じ語で異なる期間が並ぶと in-sample を OOS と誤読する
- 将来 GUI に「モデル版」を出すなら `fundamental_model.meta.json` の指紋と `SEALED_ARTIFACTS` の指紋は **別物**と明示表示する必要がある
- `predictor/` に実験モデル 2 本が本番 6 本と同居する構造は継続 (`predictor/experiments/` 分離は未消化、2 回目)

## 停止条件チェック

- [x] GUI / HTML 差分なし
- [x] 7 経路で間接影響なし (実測)
- [x] JS `node --check` PASS / gui.app import OK (venv32)
- [x] test_data_split 17 passed / test_sealed_holdout 21 passed 1 skipped
- [x] 専門領域別 Hard Fail 不抵触

## 過去提案の消化追跡

- **0913 持ち越し (3 回目) → 降格実施**: 同日 3 回の Task Scheduler 起動で完了通知が重複する件。`auto_predict.py:259` は依然 `_notify(_completion_message(...))` を無条件送信で、同日既送信の判定が無い。前回「次回放置なら 3 → 2.5」と宣言済みのため適用。**本 commit の責ではない**
- 0919 提案「`predictor/experiments/` 分離」: 未消化 (2 回目)

## 前回からの差分

- 総合 3.2 → 3.1 (−0.1)。変動は「システム状態の可視性」の 1 件のみで、config / モデル成果物の変更による GUI 回帰は 0 件。
- 判定 HOLD 維持。
