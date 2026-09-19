# 収益性 / 投資判断専門家 採点 — F3 Phase 1 readiness

## 判定: HOLD

**理由**: 本改修は type-B（計測・診断のみ）で予測、買い目、賭金、production artifactを変更していない。一方、Phase 1の7モデル比較に使える `drift_computable` は225レース中19件（8.4%）、`wide_drift` は0件であり、収益性を識別できる母集団に達していないため着手を保留する。  
**根拠ファイル**: `data/f3_phase1_readiness/dev_odds_coverage.json`、`docs/F3_phase1_readiness.md:12-34`、`scripts/f3_phase1_readiness.py:137-145`  
**次アクション**: 人間が事前に必要標本数を固定したうえで、朝アンカーを含むPIT収集を継続する。母集団到達後、同一race/day splitの7モデルpaired比較とday-block CIを実施し、ROI 80%超を最低条件として投資判断する。

## 総合: 2.0 / 5（前回 2.0、差分 ±0.0）

計測コードの安全性は改善しているが、収益性そのものを示す新しい結果はない。したがって直前のF3 Phase 0-0b評価から収益性スコアは据え置く。

## 改修タイプとスコープ

- **type-B（検証・診断ツール）**: `git log --stat -3` では最終HEAD `cb56778` が `scripts/f3_phase1_readiness.py` とそのテストのみを変更している。
- **採点対象**: Phase 1用PIT母集団のreadiness、計測結果を投資判断へ誤用しないための停止判断。
- **対象外**: P25固有のA/B採用ゲート、EV/Kelly/filter/calibratorの変更評価。該当ファイルは本改修で変更されていない。

## 項目別

- **回収率: 1/5** — 新しいbacktest、払戻、ROIは生成していない。直近の有効なbacktest `20260703_104724_tan_p25-v5-baseline-repaired-db-filtered.json` は1,568 bets・全体ROI 68.9%、buy-only 194 bets・54.1%で、どちらも控除率目安80%未満。最新 `p26-lgbm-v6-calibfit-2025` はbuy 0件である。今回のreadiness結果はこの不合格状態を改善しない。
- **EV計算の整合性: 2/5** — `_investment_probability` / `_bet_metrics` / `_value_score` は未変更で、新モデルも作られていない。19件のdrift母集団では市場残差を追加した確率、EV、`PRED_DISABLE_DISCOUNT=1`差のいずれも測定不能（`scripts/f3_phase1_readiness.py:371-421`）。
- **Kelly fraction / 投資割合: 3/5** — 現行コードにはfull Kellyから推奨率へ変換する経路と日次capがある（`web/generator.py:429-434,515-524`）が、readiness監査は賭金、最大DD、同日相関を評価していない。Phase 1開始を許可する証拠にはならない。
- **買い目フィルタの実用性: 2/5** — 既存のbuy-only 194件という評価母数はあるがROI 54.1%で、最新p26は0件。今回の225レースはPIT被覆を数えただけでbuy候補数・信頼度別採用率・relaxationを出していないため、フィルタ改善の主張はできない。
- **校正済み確率の信頼性: 2/5** — production calibratorは変更されず、hashのbefore/after一致も確認できた。しかし将来のPhase 1残差モデルについては、計算可能19件、wide drift 0件のためbin安定性、shrinkage、reliabilityを評価できない。

## Phase 1母集団 readiness

| 指標 | 実測 | 投資判断 |
|---|---:|---|
| entriesあり | 225 / 225 | レース台帳の母数は確保 |
| usable timestampあり | 71 / 225（31.6%） | 単一点評価は可能 |
| drift computable | 19 / 225（8.4%） | 7モデル比較には不足 |
| wide drift | 0 / 225（0.0%） | 60分以上のドリフト特徴は識別不能 |
| 観測active day | 2日 | 4週外挿 `+76` は計画参考値に限定 |

単純に19件を7モデルへ割り当てる設計ではないとしても、同一19レースに対するモデル差を安定推定する情報量が不足している。さらにwide driftが0件なので、朝アンカー由来チャネルを含むモデルは効果ゼロとデータ欠損を区別できない。よってPhase 1モデル構築、採用、実弾投入はいずれもHOLDとする。

## 停止条件チェック

- [x] `git_sha` と評価期間あり: JSONのSHAは `cb56778119b3998510820116510d2fc87bad8f0d`、窓は `20260704-20260719`。現在HEADと一致。
- [x] DB read-only / sealed非接触 / production不変: JSON記録を確認し、production 4 artifactの現行hashを独立再計算して一致。
- [x] baseline paired比較: **N/A**。type-B計測で収益改善・モデル差を主張していない。
- [x] market snapshot / payout欠損: **P25 backtest採用ゲートはN/A**。本成果物はPIT timestamp coverageの診断であり、払戻やROIを算出しない。
- [x] 収益性停止条件: ROI 80%超の証拠なし。ただし採用を主張せず明示的にHOLDするため、誤った実弾投入には進めない。
- [x] 再現確認: `.venv64/Scripts/python.exe -m pytest tests/test_f3_phase1_readiness.py -q` は **5 passed**。

## 反証の試み

- 主張候補「daily drift coverageが改善しているのでPhase 1開始可能」に対し、日別データと外挿前提を確認した。改善判定は前半0.0%対後半10.6%だが、usable snapshotがあるactive dayは2日のみで、wide driftは0件。4週 `+76` もこの2日平均の線形外挿なので、開始可能という反証は成立しない。レポートが `Reference-only` と明示している点は誤読防止になる（`docs/F3_phase1_readiness.md:31-34`）。

## 主な改善提案

1. **母集団到達条件を事前固定** — 人間判断で最低race数・最低開催日数・wide-drift最低件数を決め、到達前はPhase 1学習をfail-closedにする。
2. **朝アンカーを収集設計へ追加** — 現状のearliest lead中央値は約20分、wide drift 0件なので、09:30前後の独立アンカー候補を承認後に収集し、60分以上とT-10近傍の2点を確保する。
3. **収益ゲートをPhase 1評価計画に予約** — 同一day-block splitのpaired ROI/CI、最大DD、採用件数、7モデル多重比較を事前登録し、最低80%超・最終目標100%超を満たすまでproductionへ接続しない。

## 前回からの差分

- 前回: F3 Phase 0-0b paired OOS、総合2.0、HOLD。control 63.1% / treatment 62.1%で実弾不可。
- 今回: 総合2.0、HOLD（±0.0）。計測安全性は確認できたが、新ROI・EV・校正結果はなく収益性は不変。
- Kelly表示・日次capは現行コードで確認できたため項目所見を更新したが、本readiness改修による改善としては数えない。
