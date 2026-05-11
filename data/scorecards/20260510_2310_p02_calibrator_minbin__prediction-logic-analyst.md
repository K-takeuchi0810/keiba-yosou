# 予想ロジック分析官 採点

## 総合: 3.6 / 5 (前回 3.4 → 3.6, +0.2)

## 項目別

- **シグナル網羅性: 4/5** — `features.py` / `weights.json` のシグナル外出しは前回どおり。今回の P0-2 はシグナル層に触れていないため評価不変。
- **重み妥当性 / 過適合リスク: 3/5 (前回 2)** — calibrator.json L4 で `min_count=50` を導入し、これまで Bayesian shrinkage 経由で `bin[0.15,0.20]` (count=27, calibrated **0.3333**, raw avg 0.1725) が `(27*0.3333 + 30*p)/(27+30) ≒ 0.158+...`  と raw の **約 2 倍** に膨らんでいた経路を遮断 (恒等寄せで `q=p`)。少サンプル bin の `calibrated_probability` 暴走による偽高 EV 量産を構造的に止めた点が、過適合リスク軸の改善として大きい。`weights.json` の magic number 直書き繰越は依然 -1。
- **信頼度判定 / 確率推定: 4.5/5 (前回 4)** — **今回の主役**。`_apply_calibrator` (rules.py L737-796) に **2 段ガード** が入った: ①`count < min_count → q = p` (強い恒等寄せ)、②それ以外は従来の Bayesian shrinkage `(count*cal + alpha*p)/(count+alpha)`。docstring (L738-753) も「なぜ 2 段必要か」「`bin[0.15,0.20]` count=27 が calibrated 0.33 を出す具体例」まで書かれており、保守性が高い。`min_count` は `calibrator.json` 既定 + `PRED_CALIBRATOR_MIN_COUNT` env で上書き可 (L767-775) で、`shrinkage_alpha` と同じ流儀に揃っている。実測でも bin[0.15,0.20] (count=27) は raw 0.17 が貫通、bin[0,0.05] (count=317) は依然 shrinkage 適用 (0.0252 と 0.025 の中間) で **狙いどおりの分岐**。<br>満点でない理由: (a) `min_count` の根拠 (なぜ 50 か。30 や 100 でない理由) は backtest 由来のはずだが scorecard / 改修ノートに数値根拠が残っていない、(b) `calibrated_probability=0.0` の空 bin (count=0, lower>=0.3) も恒等寄せで埋まるため安全だが、本来は **空 bin を bins から除外** したほうが意図が明確。
- **デッドコード / 設計の整合性: 3/5** — 前回指摘の dead feature 4 件 (`weight_trend` / `recent_avg_starters` / `same_day_leg_bias` / `same_track_type_runs`) と dead weight 2 件は **未着手**。今回の改修は `_apply_calibrator` 内部に閉じており、整合性を乱してはいない。`min_count_default` のフォールバック (`50.0`) と `calibrator.json` の値 (`50`) が **二重定義** になっている点は微妙 (片方変更時の食い違いリスク) だが、`alpha` も同じ二重定義パターンなので一貫性は取れている。
- **本番運用との乖離リスク: 3/5** — calibrator は本番予想時刻 (朝〜午前) でも常に同じ JSON を読むため新たなリスクは増えていない。`min_count` を高く設定しすぎると **全 bin が恒等寄せになり calibrator 無効化** という静かな失敗モードがあり得るため、有効 bin 数を起動時にログ出力する仕組みがあると尚良い (現状なし)。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`min_count` 決定根拠の記録と、空 bin の除外** — `calibrator.json` の `_comment_min_count` に「20 では bin[0.15,0.20] count=27 が calibrated 0.33 を出して暴走、50 で確実に除外、80 だと bin[0.1,0.15] count=52 も切れて raw 比信頼が下がる」のような根拠コメントを追加。同時に `count == 0` の bin を `bins` から `scripts/backtest.py --save-calibrator` で出力しないようにする (現在 0 埋め空 bin が 13 個ある)。期待効果: 設定理由が後任に伝わる + JSON サイズ縮減。
2. **calibrator 適用統計のログ出力** — `_apply_calibrator` 初回呼び出し時に「min_count=50 / 有効 bin=3 / 恒等寄せ bin=4 / 空 bin=13」を logger.info で 1 行出す。`min_count` 過大設定で calibrator 無効化に気づかない事故を予防。
3. **【繰越】`rules.py` magic number 50+ 箇所の `weights.json` 移管 + dead weight / dead feature 削除** — 前回優先 #1, #2 そのまま。今回の改修対象外。

## 前回からの差分

- シグナル網羅性: 4 → 4 (±0) 維持 (改修対象外)
- 重み妥当性 / 過適合リスク: 2 → 3 (+1) **改善**: calibrator の少数 bin 過学習という最大の過適合経路を構造的に遮断
- 信頼度判定 / 確率推定: 4 → 4.5 (+0.5) **改善**: 2 段ガード (恒等寄せ + Bayesian shrinkage) で「count による信用度の連続的低下 → 閾値以下では完全切り捨て」という理論的にも実装的にもクリーンな設計に到達。docstring も具体例つきで充実
- デッドコード / 設計の整合性: 3 → 3 (±0) 維持 (繰越課題そのまま)
- 本番運用との乖離リスク: 3 → 3 (±0) 維持

## 補足

P0-2 は `_apply_calibrator` の **理論的な弱点を狙い撃ちした最小改修**。bin[0.15,0.20] の計算 `(27*0.3333 + 30*0.17)/(27+30) = 0.247` (raw 0.17 の **1.45 倍**) という偽の高 EV 押し上げが、`min_count=50` で完全に消える。前回までの Bayesian shrinkage が「count が 0 でも alpha=30 で raw に寄せるから安全」という前提だったが、count=27 のような「中途半端に多い」少数 bin は shrinkage を抜けて calibrated を半分以上反映してしまう、という穴を本改修が塞いだ。これは profitability-judge 軸でも EV フィルタの偽陽性が減るはずで、回収率改善も期待できる構造変更。総合 +0.2 の昇格は妥当。
