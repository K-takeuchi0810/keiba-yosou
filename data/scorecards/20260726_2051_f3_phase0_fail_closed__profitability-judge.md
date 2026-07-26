# 収益性 / 投資判断専門家 採点 — F3 Phase 0 fail-closed（post-fix）

## 判定: HOLD

**理由**: fail-closed 実装としての重大指摘は解消した。mode/reason severityを単一関数から導出し、Prediction・Batch・ledger・auto process boundaryで矛盾を拒否、production専用buy wrapperは non-full またはreason有りを強制ゼロにする。正常系G4もexact。ただし固定OOSは425 bets / ROI 62.0941%のままで、収益戦略は実弾候補ではない。  
**根拠ファイル**: `predictor/rules.py:55-77,282-305,1529-1564`、`predictor/filter.py:141-163`、`db.py:758-760`、`scripts/auto_predict.py:35-51,127-132`、`scripts/auto_predict_daily.bat:31-42`、`docs/F3_phase0_0b_result.md:18-28`  
**次アクション**: fail-closedを利益改善と混同せず、次の確率・戦略変更を同じ凍結OOS/day-block basisでpaired評価する。最低ROI 80%超、実弾候補にはCI下限100%超を要求する。

## 総合: 2.2 / 5（参考スコア、前回post-fix前 2.2、差分 ±0.0）

改修タイプは **type-C/Dを含むproduction運用安全性改修**。`BUY_FILTER_DEFAULT`、EV/Kelly式、calibrator、weights、backtest/evaluatorを変更せず、収益改善や新戦略採用を主張していないためP25固有の採用A/BゲートはN/A。安全実装は承認可能だが、収益戦略は引き続き観察用で、紙運用・実弾候補への昇格は認めない。

## 項目別

- **回収率（本丸）: 1/5（前回 1、±0）** — OOSは指示どおり再走していない。凍結済みpaired OOSのtreatmentは425 bets / 65 hits / 62.0941%、日block 95% CI [48.9680%, 76.2769%]、100円均等で損失16,110円。CI上限も控除率目安80%未満で実弾不可（`docs/F3_phase0_0b_result.md:18-28`）。mtime直近3件にも80%超の反証はない。
- **EV計算の整合性: 2/5（前回 2、±0）** — `_investment_probability` / `_bet_metrics` / `_value_score` は未変更。最新diffに対するG4 `--skip-oos` の独立再計算でcontrol AUC `0.7913195088860858`、treatment AUC `0.7887806982333265`を完全再現し、production artifactも不変。ただし従来どおりcalibrator・market blend・discount合成の絶対EVと実回収の乖離、`PRED_DISABLE_DISCOUNT=1`対照不足は未解決（`predictor/rules.py:1336-1418`）。
- **Kelly / 資金管理: 3/5（前回 3、±0）** — quarter Kelly、1点5% cap、日次portfolio cap・予算縮小は不変（`predictor/risk.py:64-116`、`predictor/portfolio.py:23-104,120-167`）。非full-quality予測はKellyが正でもproduction buy wrapperでゼロになる。ただしflat対Kelly、最大DD、日内相関、破産確率の新しい実測はない。
- **買い目フィルタの実用性: 3/5（前回 3、±0）** — Web/GUI/CLIは通常filterを直接呼ばず `is_production_buy_candidate` を使用し、modeがfull以外、またはreasonが1件でもあれば通常条件より前にFalse（`predictor/filter.py:141-163`、`web/generator.py:484-495`、`gui/app.py:424-436`、`scripts/predict.py:75-82`）。通常 `is_buy_candidate` は不変なのでbacktest/分析とfull-quality productionの条件も不変。安全性はプロ水準に近づいたが、実際のfilter ROIが62.09%級なので実用収益性の観点では3を超えない。
- **校正済み確率の信頼性 / 不確実性開示: 2/5（前回 2、±0）** — production calibratorは変更なし。2025年47,884件・118 knotsのisotonic、expected rules versionはp26。一方、bin別count / avg probability / actual win rateがなく、高確率帯のreliability監査は今回もできない。常設観察専用表示とmode/reasonの日本語復旧案内は誤読防止になるが、確率品質自体は改善していない。

## post-fix production実弾停止の監査

| 境界 | post-fix確認 | 判定 |
|---|---|---|
| severity導出 | E04を含めばblocked、E01/E02/E03のみならobservation、理由なしはfull | PASS |
| Prediction | full+reason、non-full+空reason、severity不一致を共通validatorで拒否 | PASS |
| PredictionBatch | 構築時に全memberのmode/reasons不一致を拒否し、append/extend/insert/setitem/iadd後の不一致も拒否 | PASS |
| mixed severity | E04+E01はblockedを優先し、両reasonを保持 | PASS |
| production buy | mode!=full **または** reason有りを通常filter前に拒否 | PASS |
| ledger | 共通validator通過前は書込せず、observation+E04等を拒否 | PASS |
| auto boundary | invalid JSON・mode/reason矛盾をRuntimeError、正常full+[]は保持して受理 | PASS |
| daily batch | auto exit 8を既存failure bit 2へ潰さずbit 8で伝播 | PASS |
| Web / GUI / CLI | observationは表示のみ・候補0、blockedは予想抑止・候補0 | PASS |
| monitor | mode/reason内訳を保持し、縮退runを不可視化しない | PASS |
| backtest / 分析 | production wrapper非使用で凍結数値経路を維持 | PASS |

## 停止条件チェック

- [x] **正常系再現性**: G3固定golden通過。G4 validation 2値を最新diffで独立再計算し完全一致。production artifact不変。
- [x] **OOS基準**: 今回はskipを明示し、既存425/65/62.0941%のみ参照。新しい収益改善とは表現していない。
- [x] **baseline paired比較**: N/A。戦略・確率・filter閾値を変えない安全改修。
- [x] **market snapshot / payout欠損**: N/A。新しいbacktest採用判断ではない。
- [x] **production non-full候補ゼロ**: core、container、ledger、process、consumerの各境界で確認。
- [x] **mode/reason意味整合**: severity一元導出と共通validator、Batch/member一致検査で前回指摘を解消。

## 重大指摘

**なし。**

前回指摘した `full + E04` のfail-openは、共通validatorとproduction wrapperの二重防御で解消した。再監査中に検出したauto正常 `full + []` の誤拒否も、emptyとmissingの区別に修正され、直接実測で `("full", [])` を確認。さらにBatchヘッダがobservationなのにmemberがfullという交差不一致は、構築時だけでなくappend/extend/insert/setitem/iaddによる構築後mutationでも `ValueError` になることを実測した。

## 反証の試み

- `PredictionBatch(full, [E04])`、`PredictionBatch(observation, [])`、`PredictionBatch(observation, [E04])`、ledger `observation+[E04]`、auto JSON `full+[E04]` はすべて拒否された。
- `PredictionBatch([member full], batch observation+[E01])` も `prediction batch status conflicts with member status` で拒否された。
- 構築済みobservation Batchへfull memberをappend / extend / insert / `+=` / scalar setitem / slice setitemする全経路も同じ `ValueError` で拒否された。
- production wrapperへ `mode=full, reasons=[E04]` のテスト用objectを渡すとFalse。modeだけでなくreason側からも停止する。
- E04 post-race warningとE01 model missingを同時発火させるテストは `blocked / [E04, E01]` を再現。
- 正常auto JSON `full+[]` は修正後に `("full", [])`、exit 0経路として受理された。

## 検証

- `.venv64/Scripts/python.exe -m pytest tests/ -q` → **441 passed / 4 skipped**。
- fail-closed focused 5ファイル → **42 passed**。
- G4 validation exact: control `0.7913195088860858` / treatment `0.7887806982333265`。
- OOSは再走せず、既存 `425 bets / 65 hits / 62.0941%` を参照。
- 一時G4成果物は検査後に削除し、指定scorecard以外のレビュー生成物は残していない。

## 残る非ブロッキング留保

1. auto process boundaryはparser/bit/helperのpositive/negative testが揃ったが、Task Scheduler相当のbat→Python→通知→exit全結合testはない。今回のbit 8伝播はbatを静的確認済み。

## 前回からの差分

- 総合: **2.2 → 2.2（±0.0）**。安全実装の重大穴は解消したが、回収率・EV・Kelly・校正という収益性数値は不変。
- 判定: **HOLD → HOLD**。fail-closed実装は承認可能。固定OOS 62.0941%のため実弾戦略は引き続き不承認。
- 段階: **観察用**。紙運用・実弾候補ではない。
