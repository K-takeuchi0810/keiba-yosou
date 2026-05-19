# コード品質 / 保守性レビュアー 採点 — Phase A1+A2+S5+S6+S7

**改修対象**: `bad4e9c..d5c76ce`
**評価日**: 2026-05-18

## 総合: 4.5 / 5 (前回 P05 4.3 → +0.2)

## 項目別

| 軸 | P05 | 今回 | 差分 |
|---|---|---|---|
| DRY / 重複コード | 4.3 | **4.7** | +0.4 |
| dead code / 未使用シンボル | 3.7 | **3.5** | -0.2 |
| マジックナンバー / 設定外出し | 4.7 | **4.6** | -0.1 |
| テスト容易性 / 副作用分離 | 2.5 | **2.7** | +0.2 |
| エラー処理 / ログ / 観測可能性 | 4.5 | **4.4** | -0.1 |

## 主な所見

### S7-α-2 は構造的勝利

`predictor/filter.py:22-107` の `is_buy_candidate` 単一関数に 4 経路 (`scripts/predict.py:65-72`、`scripts/backtest.py:256-282`、`gui/app.py:271-295`、`web/generator.py:199-230`) を集約。各経路の判定ロジックが 5-15 行の delegate に短縮、**~160 行の重複ロジックが 107 行 + 薄い委譲層に置換**された。

`config.py:55-138` の `BUY_FILTER_DEFAULT` 巨大 docstring が「唯一の出典」を docstring 内で再宣言する設計は同種 OSS でも上位水準。

### 減点要因 3 つ

1. `predictor/rules.py:93-601` の `_score_one` 508 行は **P05 から完全未着手** で feature 群ごとの責務分離なし。
2. `tests/` ディレクトリ依然不在。`is_buy_candidate` は `filter_spec` 引数 override 可能な pure 関数として testable に設計されているのに、テスト書かれていない。
3. S7-α-3 二重防御ガード `web/generator.py:259` の `kelly_fraction >= 0.0001` と S7-γ の `_RATIONALE_EXCLUDE_PREFIXES` 9 個 + `max_signals=4` が新規ハードコードで config 化されていない。

## 改善提案 (優先順)

1. **`tests/test_buy_filter.py` 即新設** — `predictor/filter.py:is_buy_candidate` の `filter_spec` 引数で全フィルタキー組合せを 30-50 行でテスト可能。S5-3 / S7-α 級「フィルタ漏れ」事故を CI で永続的に防止。期待効果: 総合 4.5 → 4.7。
2. **`_score_one` 分割** — feature 群ごとに `_score_record` / `_score_form` / `_score_pace` / `_score_pedigree` / `_score_track_affinity` 等へ責務分割。
3. **`web/generator.py:259` の `0.0001` を config 化** — `config.BUY_FILTER_DEFAULT["min_kelly_display_floor"]` として外出し + 根拠コメント明記。

## 関連ファイル
- 集約モジュール (S7-α 成果): `predictor/filter.py`
- BUY_FILTER 唯一の出典: `config.py:55-138`
- delegate 4 経路: `scripts/predict.py:65-72`, `scripts/backtest.py:256-282`, `gui/app.py:271-295`, `web/generator.py:199-230`
- 未着手の最大負債: `predictor/rules.py:93-601` (`_score_one` 508 行)
