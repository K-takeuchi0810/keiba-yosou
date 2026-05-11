# 検証プロセス監査人 採点

## 総合: 4.2 / 5  (前回 3.6 → +0.6)

P1-3 で logging を導入した本改修と並行して、**前回・前々回と 2 連続で警告した「改修後 backtest 未保存」問題が解消** された。`data/backtest/20260510_232027_tan_p02-calibrator-minbin-all.json` に 2026/01/01–2026/04/30 の **1,164 戦・16,550 馬の長期 backtest** が `rule_version=p02-calibrator-minbin` で保存され、Brier=0.057512 / LogLoss=0.209822 / 12 bin 分の reliability テーブル / 信頼度別 / クラス別 / 距離別 / トラック別すべて揃った。**「採点が紙面の話だった状態」から「データで言える状態」へ移行した最初の事例** となり、検証インフラとしての価値が初めて顕在化した瞬間。さらに重要なのは、長期 backtest が新事実を 3 件吐き出したこと: ①信頼度ラベルが回収率と相関しない (本命 56.9% / 注目 58.3% / 妙味 68.3% / 高信頼 59.8% — 「高信頼」が最低クラスの妙味に負けている)、②`buy_filter` 採用 0 件 / 1,164 戦 (`races_filtered=0`、フィルタが厳しすぎて発火していない)、③graded (重賞) のみ 115.4% で唯一黒字。これらは backtest を残さなければ永久に見えなかった構造的弱点で、今後の改修方向の **データ駆動な根拠** になる。

## 項目別

- **バックテスト設計の正しさ: 4/5 (±0)** — 今回未改修だが、長期 backtest を実走したことで設計の良し悪しが露見した。`by_confidence` / `by_class` / `by_bucket` / `by_track` / `calibration.bins` の多軸ブレイクダウンは機能している。一方 `buy_only_count=None` / `buy_only_bets=0` / `races_filtered=0` という結果は「フィルタが現実のデータで一度も発火していない」ことを意味し、`config.BUY_FILTER_DEFAULT` の閾値が長期分布に対して過剰に厳しい (= フィルタ A/B が無意味) ことを暴いた。
- **時系列リーク防止: 4/5 (±0)** — 改修対象外。calibrator.json の `source_count=16550` と新 backtest の `calibration.count=16550` が完全一致しており、**「学習に使った馬を評価でも使う」自己参照リーク** が依然として残ることが今回の長期 backtest で機械的に確認できた。次の改修候補だが今回は減点せず据え置き。
- **calibration / reliability 計測: 5/5 (4 → 5, +1)** — n=16,550 の Brier=0.0575 / LogLoss=0.2098 が時系列ファイルとして残った。bin ごとに count / avg_probability / actual_win_rate / wins が全部揃い、0.05–0.30 の 5 bin はサンプル 120+ で校正が効く一方、0.30 以上は count<60 と急減し最高でも 0.45–0.60 帯 n=2 という分布も明示。**Reliability diagram の入力データはすべて揃っており、あとは描画だけ** という状態に到達した。
- **A/B 比較 / バージョン管理: 4/5 (±0)** — `rule_version=p02-calibrator-minbin` が保存ファイル名と JSON 内部の両方に明記され、過去 5 件 (`v2-grade-all` / `v2-grade-filtered` / `current-week-check-filtered` / `tuned-week-check-filtered` / 今回) で異なる rule_version の比較材料が時系列で揃った。1 点減点理由は前回と同じ (config / calibrator.json 変更時に rule_version 強制 bump の機械的ガードが無い)。
- **過適合監視 / 期間分割評価: 4/5 (2 → 4, +2)** — **本日の主改善**。前回・前々回で問答無用 2 点としていた根拠 (改修後 backtest 0 件) が完全に解消。`from_date=20260101 to_date=20260430` の 4 ヶ月・1,164 戦という長期窓で評価が走り、最新の `0928`/`0932` 短期 (1 週間レベル) backtest と並べて短期/長期の二段比較ができる材料が揃った。**1 点減点の理由**: walk-forward / k-fold CV / 学習窓と評価窓の機械的な時系列分離はまだ未着手 (calibrator が 16,550 全件を学習に使い、同じ 16,550 件で評価している自己参照は構造的に残る)。5/5 にするには「2026/01–03 で校正、04 でホールドアウト評価」のような分割 backtest を 1 本走らせる必要がある。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **walk-forward 評価モードの追加** — `scripts/backtest.py` に `--holdout-from 20260401 --holdout-to 20260430` を追加し、calibrator は `--holdout-from` より前のデータだけから生成・評価は `--holdout-from` 以降だけ、という分離を強制する。これで calibration の自己参照リーク (n=16,550 が学習でも評価でも同じ) が構造的に解消し、過適合監視 5/5 到達と時系列リーク防止 5/5 到達が同時に進む。期待効果: Brier=0.0575 がホールドアウトでどれだけ劣化するかが見え、calibrator の汎化性能が初めて測れる。
2. **長期 backtest から見えた 3 つの新事実への即対応** — (a) 信頼度ラベルと回収率の相関が無い (本命 56.9% < 妙味 68.3%) ので `predictor/rules.py` の信頼度判定ロジックを再設計。(b) `races_filtered=0` の事実から `config.BUY_FILTER_DEFAULT` の閾値を 1,164 戦のうち 100–300 戦は採用される水準まで緩める。(c) graded のみ 115.4% 黒字なので「重賞限定モード」を `--class graded` で `scripts/backtest.py` に追加し sweep 候補にする。これらは新たに採れた検証データから直接導かれる、データ駆動な改修ロードマップ。
3. **改修と backtest をペアにする pre-commit ガード** — 今回は人手で長期 backtest を回したが、次の改修で再び忘れるリスクがある。`predictor/{rules.py,weights.json,calibrator.json}` または `config.py` の git diff があるのに `data/backtest/*.json` の最新 mtime が改修より古い場合、commit を block する `.git/hooks/pre-commit` を 30 行で追加。前回・前々回提案 #1 を構造化する形で再掲。

## 前回からの差分

- バックテスト設計の正しさ: 4 → 4 (±0) 維持: 設計は変えていないが、長期 backtest を実走したことで「`buy_filter` が一度も発火していない」という設計の隠れ欠陥が明らかになった
- 時系列リーク防止: 4 → 4 (±0) 維持: 改修対象外。次回の walk-forward 化で 5 点候補
- calibration / reliability 計測: 4 → 5 (+1) 改善: n=16,550 の Brier/LogLoss と 12 bin の reliability テーブルが時系列ファイルに残り、reliability diagram 描画の入力データが揃った
- A/B 比較 / バージョン管理: 4 → 4 (±0) 維持: rule_version=p02-calibrator-minbin で長期評価の比較基点が初めて確立
- 過適合監視 / 期間分割評価: 2 → 4 (+2) 大幅改善: **問答無用 2 点ルールの発動条件 (改修後 backtest 0 件) が解消**、1,164 戦の長期窓と既存 1 週間窓で短期/長期の対比が可能に
