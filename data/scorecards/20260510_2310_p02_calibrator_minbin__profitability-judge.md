# 収益性 / 投資判断専門家 採点

## 総合: 2.4 / 5

P0-2 で前回最大の指摘 (bin 0.15-0.20 の `count=27, calibrated=0.3333` 過学習) に直接対応した。`_apply_calibrator` の min_count 恒等寄せ + Bayesian shrinkage の二段で「少数 bin が偽の高 EV を量産する経路」が断たれた。実測で 0.17 入力 → 該当 bin が **恒等寄せ発動** (raw のまま blend されるので `0.3333` の汚染が消える) を確認。控除率 80% 未達のため総合 3 未満ルールは継続適用、ただし項目 5 単独は 4 に到達。

## 項目別

- **回収率 (本丸): 1/5 (前回 1/5, ±0)** — `data/backtest/` の最新 3 件は全て P0-2 前 (`20260510_093223` が最新)。校正修正後の backtest は未取得。直近スナップショット 50.7-62.4% / buy_only 0-2 件は不変。控除率 (約 80%) 未達は維持で底値据え置き。**P0-2 後の backtest を取り直すまで動かしようがない**。
- **EV 計算の整合性: 3/5 (前回 2/5, +1)** — 三段がけ (calibrator → market blend → odds-band discount) の **第 1 段が信頼に足る出力** を出すようになったので、下流の `_investment_probability` に渡る数値の意味が「校正値 or raw」と **明示的に切り分く** ようになった。`min_count` / `shrinkage_alpha` は `PRED_CALIBRATOR_MIN_COUNT` / `PRED_CALIBRATOR_ALPHA` 環境変数で上書き可能 (rules.py:763,772) なので、backtest で `min_count=0` (旧挙動再現) と `min_count=50` を比較する A/B 実験の足場が出来た点が +1 の根拠。一方で第 2-3 段 (blend / discount) と `PRED_DISABLE_DISCOUNT=1` 比較 backtest は今回もスコープ外で 4 には届かない。
- **Kelly fraction / 投資割合: 2/5 (前回 2/5, ±0)** — `_bet_metrics` の `min(kelly, 0.05)` 上限は表示のみで未着手。今回スコープ外として維持。
- **買い目フィルタの実用性: 3/5 (前回 3/5, ±0)** — P0-1 で生成 / 検証 / GUI 三者一致は達成済み。今回は触っていない。`relaxation` チェーンと採用件数不足 (1-2/72 戦) の問題は不変。維持。
- **校正済み確率の信頼性: 4/5 (前回 2/5, +2)** — **本改修の主役**。`predictor/calibrator.json` に `min_count: 50` / `shrinkage_alpha: 30` / `_comment_min_count` が追加され、`_apply_calibrator` (rules.py:737-796) が二段構え (恒等寄せ + Bayesian shrinkage) で実装された。実測値:
  - bin 0.15-0.20 (count=27 < 50): 恒等寄せ発動。raw 0.17 が `calibrated=0.3333` で汚染されない (確認済み)
  - bin 0.0-0.05 (count=317): Bayesian shrinkage `(317*0.0252 + 30*0.025)/(317+30) ≈ 0.0252` で calibrated を強く信用
  - bin 0.05-0.10 (count=99): `(99*0.0707 + 30*0.07)/129 ≈ 0.0703` で calibrated 寄り
  - bin 0.10-0.15 (count=52, 閾値ギリギリ): shrinkage で raw に約 36% 寄る = 安全側
  - bin 0.20+ (count <= 11): 全て恒等寄せ
  
  +2 の根拠は (a) 過学習源の遮断が実測で効いている (b) `min_count` を環境変数で動かせるので backtest A/B が組める (c) `PRED_CALIBRATOR_ALPHA` で shrinkage 強度も触れる。**5 に届かない理由**: 0.45 以上 count=0 の高確率帯空白 (前回からの長年の問題) が **未解決** で、本命候補の校正は「raw 任せ」のまま。`source_count: 512` が小さすぎて、min_count=50 に上げると bin 0.15-0.20 以上が全て raw 寄せになる = **校正の効く帯域が事実上 0-0.15 の低確率帯のみ** という構造的課題が残る。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **P0-2 後 backtest を即取得し `min_count=0` 旧挙動と A/B 比較** — `PRED_CALIBRATOR_MIN_COUNT=0 .venv32/Scripts/python.exe scripts/backtest.py ...` と既定の二本を `data/backtest/20260510_*_calibrator_minbin_{on,off}-filtered.json` で並べる。期待効果: bin 0.15-0.20 過学習が偽 EV をどれだけ生んでいたかを **数値で確定** できる。今回の改修価値の定量化。2 ファイル取れれば項目 1 を 1 → 2 に、項目 2 を 3 → 4 に上げる根拠になる。
2. **`source_count: 512` を `>= 2000` に拡大して校正対象帯域を広げる** — `scripts/backtest.py --save-calibrator` の取り込みレース範囲を拡張 (現状おそらく半年分 → 2-3 年分)。`source_count` を 4 倍にすれば bin 0.15-0.20 が count >= 50 に乗り恒等寄せから Bayesian shrinkage に格上げされる可能性が高い。期待効果: 「校正の効く帯域が 0-0.15 のみ」問題が緩和され、本命 (確率 0.2+) 候補の EV 計算が初めて意味を持つ。項目 5 を 4 → 5 に押し上げる経路。
3. **`predictor/calibrator.json` に bin 別 `was_shrunk` / `was_identity` フラグをメタ情報として埋める** — 例: bin に `mode: "identity" | "shrinkage"` を書き出して GUI / scorecard が「いま校正は何 bin が効いていますか」を一目で判断できるようにする。`scripts/backtest.py --save-calibrator` 実行時に `b["mode"] = "identity" if count < min_count else "shrinkage"` を追加するだけ。期待効果: 校正の状態が JSON 単体で自己記述になり、改修ごとに「effective_bins=2」のような one-line サマリが取れる。レビュー効率改善。

## 前回からの差分 (2.0 → 2.4, +0.4)

- 回収率: 1 → 1 (±0) — backtest 未再取得 (P0-2 後の数値がまだない)
- EV 計算の整合性: 2 → 3 (+1) — 三段がけの第 1 段が信頼できる出力を出すようになり、`PRED_CALIBRATOR_MIN_COUNT` で A/B 可能になった
- Kelly fraction: 2 → 2 (±0) — 未着手、維持
- 買い目フィルタの実用性: 3 → 3 (±0) — 今回スコープ外、維持
- 校正済み確率の信頼性: **2 → 4 (+2)** — 前回最大の指摘 (count=27 で calibrated=0.3333 過学習) を min_count 恒等寄せ + Bayesian shrinkage で直接解消。実測で bin 0.15-0.20 の汚染が消えたことを確認。5 に届かなかった理由は `source_count: 512` 不足で 0.2 以上の本命帯域が全て恒等寄せになる構造課題が残るため
