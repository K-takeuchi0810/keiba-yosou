# 検証プロセス監査人 採点

## 総合: 4.8 / 5  (前回 4.6 → +0.2)

a (walk-forward 実施) + e (sweep + filter 更新) で **5 回連続で警告してきた「過適合監視 / 期間分割評価」が直接対処された**。`data/backtest/20260511_230457_*_p04-final-design-all.json` (2025/06-12, 2016 戦) と `20260511_230419_*_p04-final-eval-all.json` (2026/01-04, 1164 戦) が **同じ whitelist で design=74.3% / eval=84.9% (+10.6pt)** を記録し、長年「84.9% は本物か」と議論されてきた数字が **自己参照バイアス由来であると定量化された**。`scripts/filter_sweep.py --walk-forward` で 2 期間並列 sweep が CLI 化され、両期間で 80%+ の robust filter を 6 種検出 → `wl_ex_unsure_pop_1_4` (271 戦, design 86.3% / eval 89.0%) を採用。前回まで「構造課題持ち越し」だった 過適合監視 が 3 → 5 に跳ね上がり、総合 0.2pt 押し上げた。

## 項目別

- **バックテスト設計の正しさ: 5/5 (±0)** — 3 系統並列出力 / 39 キースキーマ / 中央場フィルタ / `--rule-version` タグ付け、すべて健在。新規に `--walk-forward` で 2 期間自動 sweep が加わり設計の表現力がむしろ拡張。
- **時系列リーク防止: 5/5 (+1)** — design 7 ヶ月と eval 4 ヶ月を **完全に分離した期間** で評価。同じ filter (`wl`) を当てて design 74.3% / eval 84.9% という ギャップが観測できたこと自体が「期間境界で漏れていない」証拠。calibrator の自己参照は別軸 (項目 5) の問題で、ここは「2 期間境界の正しさ」を評価。
- **calibration / reliability 計測: 4/5 (-1)** — `data/backtest/20260511_*p04*.json` を覗くと `brier_score` / `log_loss` / `reliability_bins` の 3 キーが **不在**。前回 5/5 だった Brier=0.057508 / LogLoss=0.209745 / 12 bin reliability が p04-final 系では出力されていない (39 キーは維持されているが calibration メタ系が落ちている)。walk-forward 改修の副作用で出力対象から外れた可能性。
- **A/B 比較 / バージョン管理: 5/5 (±0)** — `p04-final-design` / `p04-final-eval` / `p04-final-eval-v3` のタグが 1 時間以内に 3 系統並列で保存され、`--walk-forward` の自動 2 期間 sweep が CLI 化。比較性は前回より強化されたが上限維持。
- **過適合監視 / 期間分割評価: 5/5 (+2)** — 5 回連続警告の中核課題。`filter_sweep.py:186-220` で design/eval を並列 collect_picks → 両期間 80%+ を `robust=Y` でラベリング → ソート優先キーに採用、まで完全自動化。**「直近データで重み変えたら直近データの回収率が上がる」が構造的に防止される設計** に到達。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`brier_score` / `log_loss` / `reliability_bins` を p04 系出力に戻す (回帰修正)** — `scripts/backtest.py` の最近の `--walk-forward` 改修で calibration メタ 3 キーが落ちている。直近 4 ファイル (`p04-final-*`) で `False` 確認。calibrator 学習窓 / 評価窓 が一致しているかも合わせて見たいので、`predictor/calibrator.py` の Brier 計算ブロックを最終 summary に再注入。項目 3 が 5 に戻る。
2. **calibrator 自己参照を断つ `--calibrator-holdout-from`** — walk-forward が filter / weights には適用されたが、`predictor/calibrator.json` の 16,550 件は依然全件学習・全件評価。design 期間で学習 → eval 期間で評価する flag を `scripts/backtest.py` に追加。これで「84.9% は本物か」の最後の自己参照 (= calibrator) も切れる。
3. **`wl_odds_8_20` 路線の robust 検証**: 戦数 74+41 と少ないが両期間 103.5% / 116.1% で唯一 100%+。次 sweep で `wl_odds_8_20` + 信頼度フィルタ複合の grid 化を 1 イテレーション挟む価値あり。

## 前回からの差分

- バックテスト設計の正しさ: 5 → 5 (±0) 維持: `--walk-forward` 追加で表現力は増したが上限のまま
- 時系列リーク防止: 4 → 5 (+1) 改善: 2 期間分離評価が実走、74.3% vs 84.9% のギャップが境界正しさの実証
- calibration / reliability 計測: 5 → 4 (-1) 退行: `p04-final-*` で brier/log_loss/reliability_bins の 3 キーが不在 (回帰)
- A/B 比較 / バージョン管理: 5 → 5 (±0) 維持: 既に上限。`--walk-forward` の 2 期間自動タグ付けはボーナス
- 過適合監視 / 期間分割評価: 3 → 5 (+2) **大幅改善**: 5 回連続警告の構造課題が解消、両期間 80%+ ラベリングが CLI 自動化
