# 予想ロジック分析官 採点

## 総合: 3.4 / 5 (前回 3.4 → 3.4, ±0)

## 項目別

- **シグナル網羅性: 4/5** — `predictor/rules.py` 冒頭 docstring・`predictor/features.py` 冒頭・`predictor/weights.json` 全体ともに baseline (20260510_2249) からバイト一致。シグナルセット (直近着順 / 距離バケット / コース / 道悪 / 血統 / 騎手・調教師 / マイニング / 脚質 × 同日バイアス / 重賞 / 斤量 / 上がり 3F / 持ち時計) は前回どおり。今回 P0-1 改修は `gui/app.py` の `buy_filter` を `config.BUY_FILTER_DEFAULT` に一元化しただけで、シグナル層への影響なし。
- **重み妥当性 / 過適合リスク: 2/5** — `weights.json` は前回確認時から無変更。12 namespace のみ外出し、`rules.py` 内の magic number 50+ 箇所は **未着手**。`risk.graded_unproven_penalty` / `risk.long_unproven_penalty` の dead weight も **依然残置** (line 67-68)。今回の改修ではここに触れていない。
- **信頼度判定 / 確率推定: 4/5** — `confidence.min_score=110 / min_gap=25 / min_stability=12 / negative_gap=28` (weights.json L59-65) は前回どおり。`_apply_calibrator` の Bayesian shrinkage、`_score_probabilities` の温度 30 + 信頼度別 shrink も未変更。calibrator.json は M フラグついているが本採点軸 (構造的妥当性) では前回判定を維持。
- **デッドコード / 設計の整合性: 3/5** — 前回指摘した dead feature 4 件 (`weight_trend` / `recent_avg_starters` / `same_day_leg_bias` / `same_track_type_runs`) は **未着手**。`_value_score` のフォールバック (score-70 + odds bonus) と EV 経路の単位混在も未着手。ただし今回の改修 (`buy_filter` 一元化) は予想スコア計算の後段である買い目フィルタを config に集約したもので、ロジック層の整合性を **乱していない** 点は良好。
- **本番運用との乖離リスク: 3/5** — `leg_quality_code` 推定 fallback / `feature_warnings` 伝搬 / `same_day_bias_available` フラグは前回どおり機能。推定脚質利用時のシグナル割引 (前回優先提案 #3) は **未着手**。今回の改修は予想時刻依存性とは無関係。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **【繰越】`rules.py` のマジックナンバーを weights.json に移し、未参照 weight を削除** — 前回優先 #1 がそのまま残置。少なくとも `recent_top3.win_bonus`, `same_track_type.*`, `same_distance.top3_bonus`, `same_course.*`, `going.*`, `final3f_rank.*`, `best_time.*`, `bloodline.surface.*`, `class.*` を namespace 化。同時に `weights.json` L67-68 の `risk.graded_unproven_penalty` / `risk.long_unproven_penalty` を削除 or 参照。期待効果: A/B 実験と過適合検知が容易に。
2. **【繰越】dead feature 4 件 (`weight_trend` / `recent_avg_starters` / `same_day_leg_bias` / `same_track_type_runs`) を削除 or 利用** — 前回優先 #2 そのまま。features.py の計算コスト削減と読解負荷の低下。
3. **【繰越】推定脚質 (`estimated_leg_code`) 利用時のシグナル割引** — 前回優先 #3 そのまま。`leg_quality_available=False` のとき `pace.*` / `same_day_bias_score` / 長距離脚質ボーナスを 0.6 倍 or 無効化。

## 前回からの差分

- シグナル網羅性: 4 → 4 (±0) 維持 (改修対象外)
- 重み妥当性 / 過適合リスク: 2 → 2 (±0) 維持 (繰越課題そのまま)
- 信頼度判定 / 確率推定: 4 → 4 (±0) 維持
- デッドコード / 設計の整合性: 3 → 3 (±0) 維持 (繰越課題そのまま)
- 本番運用との乖離リスク: 3 → 3 (±0) 維持

## 補足

P0-1 は `gui/app.py` の買い目フィルタを `config.BUY_FILTER_DEFAULT` に集約する後段処理の整理であり、`predictor/rules.py` / `features.py` / `weights.json` への変更は **無し** (3 ファイルすべて baseline とバイト一致を確認)。よってロジック層スコアは不変。前回優先課題 (`_score_one` 491 行 + magic number 直書き 60 箇所、dead weight 削除、推定脚質割引) は **依然すべて未着手**。次回ロジック改修時に着手することを推奨。
