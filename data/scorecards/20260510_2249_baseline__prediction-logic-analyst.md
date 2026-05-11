# 予想ロジック分析官 採点

## 総合: 3.4 / 5

## 項目別

- **シグナル網羅性: 4/5** — 直近着順 / 距離バケット / コース / 道悪 / 父・母父 × 馬場・距離・道悪 / 騎手・調教師 / マイニング / 脚質 × 同日バイアス / 重賞接戦敗 / 斤量・馬体減 / 上がり 3F・相対時計まで広く押さえている。短距離 (sprint) と長距離 (long) はバケット別ロジックを分岐。漏れは「ペース予想 (raw 数値)・テン乗り (騎手×馬の組合せ)・枠 × 距離の交互作用」あたり。
- **重み妥当性 / 過適合リスク: 2/5** — `weights.json` に外出しされているのは 12 名前空間のみで、`rules.py` 内に `score += 4 / 5 / 8 / -3 / -6` 等のマジックナンバーが 50 箇所以上残る (例: `recent_best_win` 以外の `recent_top3_count`、`days_since_last`、`same_track_type_wins` 重み、`scd_top3` ボーナス、上がり順位・持ち時計・血統 surface ボーナス幅など)。`weights.json` の `risk.graded_unproven_penalty` / `risk.long_unproven_penalty` は **どこからも参照されていない (dead weight)**。コメントに「5/2-3 の backtest を受けて〜」が複数あり、直近 2 日の結果に重みを寄せた形跡 → 過適合リスク高。
- **信頼度判定 / 確率推定: 4/5** — `_apply_calibrator` の Bayesian shrinkage (count·calibrated + α·p) / (count+α) はノイジー bin (0.15–0.20 で calibrated 0.33) をしっかり丸める良い設計。`_score_probabilities` の温度 30 + 信頼度別 shrink は二重に見えるが、shrink が信頼度ラベルに合わせて動くので役割は分離している。閾値は `weights.json` で `min_score=110 / min_gap=25 / min_stability=12` と充分厳しく、`_has_negative_signal` のガードも併用している。calibrator が 0.30+ で count≤2 の bin を残しているのは shrinkage で吸収されるので実害なし。
- **デッドコード / 設計の整合性: 3/5** — 実害のあるデッドフィーチャーが複数残る: `weight_trend` (計算するが未使用)、`same_track_type_runs` (top3/wins だけ使用)、`same_day_leg_bias` / `same_day_leg_samples` (新スコア化版に置換されたが旧 bool が残置)、`recent_avg_starters` (avg だけ使う)。`_value_score` の `expected_value==0` フォールバック (`score - 70` + odds bonus) と EV 経路で単位 (スコア vs EV%) が混在。V2_GRADE / V2_DIST フラグは一貫運用。
- **本番運用との乖離リスク: 3/5** — `leg_quality_code` は post-race だが `estimate_leg_code` (過去 5 走から最頻) のフォールバックがあり、`leg_quality_available` / `estimated_leg_code` も `feature_warnings` 経由で呼び出し元に伝わるので朝予想でも機能。`same_day_*_bias` は当日 1R 目では必ず欠落するが `same_day_bias_available=False` を出して警告化済み。`needs_post_race_data` リストも propagate。設計は良いが、`leg_quality_code` 由来のシグナルがスコアに与える影響度 (長距離脚質+3、当日バイアス±5、ペース±5) が合計でかなり大きく、推定値依存時のディスクラウントが入っていないのが残念。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`rules.py` のマジックナンバーを weights.json に移し、未参照 weight を削除** — 少なくとも `recent_top3.win_bonus`, `same_track_type.win_bonus / top3_bonus`, `same_distance.top3_bonus`, `same_course.*`, `going.*`, `final3f_rank.*`, `best_time.*`, `bloodline.surface.*`, `class.*` を namespace 化。同時に `weights.json` の `risk.graded_unproven_penalty` / `risk.long_unproven_penalty` を削除 (dead) または `rules.py` で参照する。期待効果: A/B 実験と過適合検知が容易に。
2. **dead feature 4 件 (`weight_trend` / `recent_avg_starters` / `same_day_leg_bias` / `same_track_type_runs`) を削除 or 利用** — 計算コストの無駄と読解負荷を減らす。`weight_trend` は `_score_one` で +1〜2 の補助シグナルとして拾うか、`features.py` の計算を消す。
3. **推定脚質 (`estimated_leg_code`) 利用時のシグナル割引** — 現状は raw と推定で扱いが同じ。`leg_quality_available=False` のとき `pace.*` / `same_day_bias_score` / 長距離脚質ボーナス (+3) を 0.6 倍に弱めるか、`estimated_leg_samples < 3` なら無効化。本番予想 (朝) での過信を防ぎ、当日 1R で `same_day_bias` が無い件と整合する。

## 前回からの差分

- 初回採点 (前回スコアなし)
