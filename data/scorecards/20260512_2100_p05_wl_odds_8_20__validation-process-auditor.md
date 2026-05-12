# 検証プロセス監査人 採点

## 総合: 4.6 / 5  (前回 4.8 → -0.2)

walk-forward 運用 (DESIGN 2025/06-12 / EVAL 2026/01-04) は前回確立した枠組みをそのまま継続し、30 種 sweep → 両期間 +100% の robust ラベル 3 種 (`wl_odds_8_20` / `wl_odds_8_20_ex_tentative` / `wl_odds_8_20_pop_4_8`) を抽出 → `wl_odds_8_20` を `config.BUY_FILTER_DEFAULT` に反映、まで一直線にトレース可能 (`data/backtest/20260512_walk_forward_v2.csv` + `20260512_205837_*_p05-wl-odds-8-20-filtered.json` + `config.py:38-67` のコメント)。前回課題の **calibration 出力 (brier_score / log_loss / reliability bins) が p05 backtest で完全復活** (count=16,550 / Brier 0.057508 / LogLoss 0.209745 を JSON 内 `calibration` キーで確認) で項目 3 が 4 → 5 に回復。一方、**EVAL 期間 = 採用判断材料** の自己参照が新規構造問題として浮上 (項目 5 で -1)。EVAL n=41 / 4 hits の Wilson 95% CI は **hit_rate [3.9%, 22.6%]** / **return_rate [8.0%, 224.2%]** と幅が広く、点推定 116.1% を本番投入の確信材料にするには不足。総合は +0.5(calib 復活) -0.5(EVAL 自己参照 + サンプル過少) -0.2(改善余地) で -0.2pt。

## 項目別

- **バックテスト設計の正しさ: 5/5 (±0)** — 39 キースキーマ + 3 系統並列 (all / buy_only / whitelist_only) + `--rule-version` タグ + by_bucket/by_class/by_confidence/by_track のブレイクダウン健在。`data/backtest/20260512_walk_forward_v2.csv` で 30 filter × (d_bets, d_hit_rate, d_return_rate, e_*, robust) の 7 列スキーマも整い、sweep アーティファクトの再現性も担保。
- **時系列リーク防止: 5/5 (±0)** — DESIGN/EVAL 完全分離は前回どおり。新規 `wl_odds_8_20` は両期間とも +100% を要求した上で採用しているため、EVAL 単独 cherry-pick よりは健全。`predict_race` の `before_date` 境界・同日 bias の前向き絞り込み・calibrator 16,550 件 (全期間) の取扱は前回と同一構造。
- **calibration / reliability 計測: 5/5 (+1)** — 前回回帰した brier_score / log_loss / reliability_bins の 3 キーが p05 出力で **完全復活**。`calibration.count=16,550 / brier=0.057508 / log_loss=0.209745` が JSON 内に直接書き出され、12 bin の actual_win_rate vs avg_probability も保存。`predictor/calibrator.json` も brier 0.058346 / log_loss 0.210631 / source_count=512 / shrinkage_alpha=30 / min_count=50 / bins=20 と運用パラメタが揃う。
- **A/B 比較 / バージョン管理: 5/5 (±0)** — `p04-final-eval-v3` (旧採用 wl_ex_unsure_pop_1_4: 105戦/89.0%) → `p05-wl-odds-8-20` (新採用: 41戦/116.1%) の rule_version タグ付き JSON が並存し直接比較可能。`config.py:38-67` のコメントブロックに sweep 結果の trade-off 比較 (`wl_odds_8_20_pop_4_8` は EVAL 上振れ大だが DESIGN +1.2% でギリ → 見送り) まで明文化されており、採用判断の audit trail として模範的。
- **過適合監視 / 期間分割評価: 4/5 (-1)** — walk-forward の DESIGN/EVAL 分離は機能しているが、**「両期間 +100%」を採用基準にした時点で EVAL は完全に in-sample 化**。本来は (DESIGN, EVAL) でフィルタを絞り、**第三の untouched hold-out (例: 2026/05 以降の前向きデータ)** で最終検証してから本番投入すべき。さらに EVAL n=41 は Wilson 95% CI が return_rate [8%, 224%] と広く、点推定 116.1% を信頼区間として運用する仕組みも未実装。前回 5 → 今回 4 へ -1。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **第三の hold-out 期間 (`HOLDOUT`) を `filter_sweep.py` に追加** — DESIGN (2025/06-12) と EVAL (2026/01-04) で +100% を要求して filter を確定したあと、**filter 固定** のまま 2026/05/01 以降の前向きデータで `scripts/backtest.py --rule-version p05-holdout` を 1 回だけ走らせ、それを本番昇格の唯一の判断材料にする運用フローを README/docstring に明記。今は採用判断と評価が同一期間で循環している。期待効果: 「両期間 +100% を要求しても、その両期間自体に over-fit している」という残存リスクを切る。
2. **`buy_only_races` / Wilson 95% CI を backtest JSON に追加** — 現状 `buy_only_bets=41` は出るが `buy_only_races=None` / `buy_only_wins=None` / Wilson CI 未出力。`scripts/backtest.py` の summary 直後に `n, k, p, lo, hi` を計算して `buy_only_hit_rate_ci95: [0.039, 0.226]` / `buy_only_return_rate_ci95: [0.080, 2.242]` を出力。今回 `wl_odds_8_20` を採用するなら、点推定 116.1% ではなく **下限 8% (= ほぼ 0 円) ／ 上限 224% の幅** で意思決定すべき。期待効果: 「+660 円 = 期待値」と誤読する事故を防ぐ。
3. **calibrator の DESIGN-only 学習 flag `--calibrator-train-until 20251231`** — 前回も提案 (`predictor/calibrator.json` の 16,550 件は依然全期間学習)。filter は walk-forward 済みだが calibrator の学習窓 ≠ 評価窓は未着手。p05 で予想ロジック (calibrator) と filter が両方変わったとき、Brier 改善 (0.210288 → 0.209745) が真の改善か自己参照か区別できない。期待効果: 予想ロジック改修の効果判定が calibrator 自己参照と分離される。

## 前回からの差分

- バックテスト設計の正しさ: 5 → 5 (±0) 維持: sweep CSV 7 列スキーマ追加で表現力は微増、上限維持
- 時系列リーク防止: 5 → 5 (±0) 維持: DESIGN/EVAL 期間境界は健在
- calibration / reliability 計測: 4 → 5 (+1) **改善**: 前回回帰した brier_score / log_loss / reliability_bins の 3 キーが p05 出力で完全復活
- A/B 比較 / バージョン管理: 5 → 5 (±0) 維持: `p04-final-eval-v3` vs `p05-wl-odds-8-20` の直接比較 + config コメントに trade-off 明文化
- 過適合監視 / 期間分割評価: 5 → 4 (-1) **退行**: walk-forward は機能継続だが「両期間 +100% を採用基準」にした時点で EVAL が in-sample 化。第三 hold-out 未実装 + EVAL n=41 の Wilson CI [8%, 224%] が広い
