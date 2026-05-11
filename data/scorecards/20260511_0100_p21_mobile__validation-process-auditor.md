# 検証プロセス監査人 採点

## 総合: 4.6 / 5  (前回 4.6 → ±0)

P2-1 はモバイル CSS 専用改修で、`scripts/backtest.py` / `data/backtest/` / `predictor/calibrator.json` / `weights.json` いずれも非接触。検証インフラは前回 P1-1 リファクタで結晶化した「rule_version 別 5 連続履歴 + 3 系統並列出力 (all / buy_only / whitelist_only) + 12 bin reliability + Brier/LogLoss」をそのまま引き継ぎ、構造・運用ともに変化なし。担当範囲外改修につき項目スコアは全て据え置き、構造課題 (walk-forward 不在 = 過適合監視 3/5) も次回持ち越し。

## 項目別

- **バックテスト設計の正しさ: 5/5 (±0)** — 改修対象外。3 系統並列出力 / 遷移カウンタ / 39 キースキーマすべて P1-1 から不変。
- **時系列リーク防止: 4/5 (±0)** — 改修対象外。calibrator は依然 16,550 件全件学習・全件評価の自己参照状態で walk-forward 待ち。
- **calibration / reliability 計測: 5/5 (±0)** — 改修対象外。Brier=0.057508 / LogLoss=0.209745 / 12 bin 維持。
- **A/B 比較 / バージョン管理: 5/5 (±0)** — 改修対象外。CSS 改修は `rule_version` 不要で正解 (数値非影響につき backtest 走らせる必要なし)。22 namespace / 137 leaf の sweep 探索空間も健在。
- **過適合監視 / 期間分割評価: 3/5 (±0)** — 改修対象外。`--holdout-from` 未着手、whitelist_only=84.9% のホールドアウト不在は P2-1 では塞げない構造課題として持ち越し。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **リファクタ動作不変 CI 化 (前回 #1 継続)** — `scripts/backtest.py` に `--assert-equal-to data/backtest/<prev>.json` フラグ。CSS 改修のように「数値に影響しないはず」の PR でも、`--skip-backtest` フラグで明示宣言する仕組みを作れば検証文化が抜け漏れなく回る。
2. **weights.json sweep 起動 (前回 #2 継続)** — 22 namespace / 137 leaf の sweep 起動が依然未着手。P2 系 (UI) で 1 件挟まったので、P3 以降で `scripts/sweep_weights.py` を新設。
3. **`--holdout-from` 導入** — calibrator/weights の自己参照を断つため、backtest に `--holdout-from YYYYMMDD` を入れて学習窓と評価窓を分離。過適合監視 3 → 4 への唯一の道。

## 前回からの差分

- バックテスト設計の正しさ: 5 → 5 (±0) 維持: 改修対象外
- 時系列リーク防止: 4 → 4 (±0) 維持: 改修対象外
- calibration / reliability 計測: 5 → 5 (±0) 維持: 改修対象外
- A/B 比較 / バージョン管理: 5 → 5 (±0) 維持: 改修対象外 (CSS 改修で rule_version を切らない判断は正しい)
- 過適合監視 / 期間分割評価: 3 → 3 (±0) 維持: 構造課題持ち越し
