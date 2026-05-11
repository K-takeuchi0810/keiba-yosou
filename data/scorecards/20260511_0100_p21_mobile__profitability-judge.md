# 収益性 / 投資判断専門家 採点

## 総合: 3.0 / 5

P2-1 はモバイル HTML の **CSS 専用** 改修。`predictor/rules.py` / `web/generator.py` の BET_* 閾値 / `_investment_probability` / `_bet_metrics` / `calibrator.json` / `data/backtest/*.json` のいずれにも変更なし。本専門家の担当範囲 (実弾収益性) では数値が一切動いていないため、前回 3.0 を機械的に維持。whitelist_only 326 戦 / 84.9% / 控除率 +4.9pt の構造、buy_only=0/1164 の詰みも据え置き。控除率 80% 超えは保持されているのでルール上の 3 解禁は継続。本改修は表示層のみで、収益性に対しては中立。

## 項目別

- **回収率 (本丸): 4/5 (前回 4/5, ±0)** — backtest 数値は P0-3 / P1-1 と完全一致。CSS 改修は数値に影響しない。
- **EV 計算の整合性: 2/5 (前回 2/5, ±0)** — `_investment_probability` 未変更。Brier / LogLoss も同値。
- **Kelly fraction / 投資割合: 2/5 (前回 2/5, ±0)** — `min(kelly, 0.05)` 表示のみ据え置き。
- **買い目フィルタの実用性: 3/5 (前回 3/5, ±0)** — BET_MIN_EV / Odds 帯 / Value 閾値・`_is_buy_candidate` 全て不変。buy_only_bets=0 も同値。
- **校正済み確率の信頼性: 2/5 (前回 2/5, ±0)** — calibrator.json と by_confidence の高信頼<接戦の逆転は不変。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`weights.json` の sweep を即実施** — P1-1 で土台が整い P2-1 は数値に触っていないので、提案 1 は引き続き最優先。`scripts/filter_sweep.py` を whitelist_only 326 戦に走らせ、「採用件数 ≥ 50 / 回収率 ≥ 90%」の点を探索し buy_only=0 を解除。項目 4: 3 → 4、項目 1: 4 → 5 への最短経路。
2. **動作不変スナップショットテスト** — 主要 KPI (races_bet, return_rate, whitelist_only_*) を `tests/` に固定化。CSS 改修のように予想ロジック非関与の改修でも自動で「数値が動いていない」を保証でき、sweep 実施時の安全網になる。
3. **`weights.json` スキーマを README に明記** — JSON 化された各キー (EV 閾値 / Odds 下限上限 / Value 閾値 / 重み係数) の意味・既定値・許容範囲を残す。提案 1 の sweep を安全に回す前提条件。

## 前回からの差分 (3.0 → 3.0, ±0)

- 回収率: 4 → 4 (±0) — backtest 不変、CSS 改修は数値非関与
- EV 計算の整合性: 2 → 2 (±0) — 未着手
- Kelly fraction: 2 → 2 (±0) — 未着手
- 買い目フィルタの実用性: 3 → 3 (±0) — フィルタ閾値・`_is_buy_candidate` 不変
- 校正済み確率の信頼性: 2 → 2 (±0) — 未着手

**総括**: P2-1 は表示層のみの改修で、本専門家の担当範囲 (実弾収益性) には触れていない。スコアは想定通り 3.0 維持。次の数値改善は P1-1 で整った `weights.json` sweep が引き続き最短経路。
