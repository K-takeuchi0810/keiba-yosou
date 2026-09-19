# 収益性 / 投資判断専門家 採点 — F3 Phase 0-0b paired OOS

## 総合: 2.0 / 5（前回 2.0、差分 ±0.0）

同一 OOS 窓・同一 rules/filter/calibrator・同一 day-block 標本で control/treatment を paired 評価できるようになり、前回の最大の測定課題は解消した。しかし実弾判断の本丸は変わらない。control は **424 bets / 65 hits / ROI 63.1132% / 95% CI [49.5444%, 77.3060%]**、treatment は **425 bets / 65 hits / ROI 62.0941% / 95% CI [48.9680%, 76.2769%]**。両者とも点推定だけでなく CI 上限も JRA 単勝控除率の目安 80%未満であり、「80%を超えない限り総合3以上不可」に該当する。今回の改善は損失原因の切り分け精度であり、収益性そのものの改善ではないため2.0据置とする。

## 項目別

- **回収率（本丸）: 1/5（前回 1、±0）** — treatment は前回の425件/62.09%を完全再現。controlも424件/63.11%に留まり、100円均等なら投資42,400円、払戻26,760円、損失15,640円。treatmentは投資42,500円、払戻26,390円、損失16,110円。どちらの個別95%CI上限も80%未満で、実弾投入不可の判定は強い。
- **EV計算の整合性: 2/5（前回 2、±0）** — 両モデルを同一 `is_buy_candidate`、同一旧p21 isotonic calibrator、同一linear blend/discountで通したため、control−treatmentの内部比較条件は揃った。一方、絶対的な投資確率は現行p26 rulesへ旧p21 calibratorを適用するversion mismatchを残し、`PRED_DISABLE_DISCOUNT=1` 対照もない。paired化は二重係数・確率歪みの監査を解消していない。
- **Kelly fraction / 投資割合: 2/5（前回 2、±0）** — Kellyは候補判定に使われるが、評価賭け金は全件100円均等。5% capの資金配分効果、flat対Kelly、日内・開催内の相関集中、最大ドローダウンは未評価。race top-1のみなのでrace内複数候補の分散問題はない。
- **買い目フィルタの実用性: 1/5（前回 1、±0）** — 採用424/425件で詰みパターンではないが、ROIは62〜63%で実用不合格。自己選択basisのunionは471 racesで、集合算術上 overlap 378、control-only 46、treatment-only 47。共通race basisでは差が完全に0なので、観測された+1.0191ptはbet集合差に由来するとの解釈に整合する。ただしrace ledger未保存のため、馬選択が全raceで同一とは直接監査できない。confidence別採用率・relaxation・EV/Kelly帯別ROIは今回もない。
- **校正済み確率の信頼性: 2/5（前回 2、±0）** — paired比較としてcalibrator固定は正しいが、旧p21 isotonic成果物にはbin別count / avg_probability / actual_win_rateがなく、高確率帯の標本数、shrinkage、reliability diagramを監査できない。両モデルの絶対ROI判断に使う校正としては不十分。

## paired basis・ROI/CI・符号の検査

| basis | control | treatment | d = control−treatment | 判定 |
|---|---:|---:|---:|---|
| 各モデル自己選択 | 424/65、63.1132% [49.5444%, 77.3060%] | 425/65、62.0941% [48.9680%, 76.2769%] | **+1.0191pt [-4.6737pt, +6.4106pt]** | 0を含む |
| treatment bet races | 425/65、62.0941% [48.9680%, 76.2769%] | 同左 | **0.0000pt [0, 0]** | 完全一致 |
| control bet races | 424/65、63.1132% [49.5444%, 77.3060%] | 同左 | **0.0000pt [0, 0]** | 完全一致 |

- 実装は各反復で同じ50日分のindexを両モデルの分子・分母へ適用しており、10,000標本すべて有効。day内相関を保った真のpaired bootstrapになっている。
- 差分の符号は正しい。controlは3 POST-HIGHチャネルを含むため、`control−treatment = +1.0191pt` は「当該チャネルを残した側が点推定で約1.02pt高い」を意味する。ただしCIは約-4.67〜+6.41ptで、正負どちらも許容する。
- §3-4の事前判定basisは自己選択で固定され、結果を見る前の条件「CIが0を含むなら有意寄与なし」に機械的に従って `CLOSED` とした。手続きと符号判定は正しい。
- ただし「ROIに有意寄与しない」は **有意差を検出できなかった** という意味に限定すべきで、実質同等性や寄与ゼロの証明ではない。CI幅は最大で数ptの損益影響を許すため、外部文書では「有意な寄与を検出せず」と表現するのが安全。
- 共通raceの0差は有用だが、保存JSONにはrace-level ledger、top馬一致数、集合overlapの明示がない。集計値から結論は再確認できても、第三者が「各raceで何が一致したか」を軽量監査できない。

## 直近 backtest 3件の確認

- `20260703_053033_tan_p26-lgbm-v6-calibfit-2025-filtered.json`: 3,455 races、buy 0件 / buy ROI 0%。フィルタ詰みパターン。
- `baseline_brier.json`: backtest集計schemaではなく、回収率・採用件数の評価対象外。
- `20260703_104724_tan_p25-v5-baseline-repaired-db-filtered.json`: 1,578 races、全体68.9%、buy 194件 / buy ROI 54.1%。

mtime上の次の有効成果物も p26 817件/62.0%、clean OOS 123件/56.3%で、今回の62〜63%と同じ不採算方向。直近数値には80%超の反証がない。

## 再現性・不変性

- control/treatment val AUCは0.7913195089 / 0.7887806982を期待値と完全一致で再現。モデルartifact SHAも保存済み。
- treatment OOSは凍結済み425/65/62.0941%を再現できない場合controlを走らせないfail-closed構成。
- evaluator SHA `ecabaa...09ad` は長時間評価を実行したcommit `af13474c0a523abaa83c851bcfb3d418ced593db` の `scripts/f3_phase0_0_eval.py` と一致。最終HEAD `fa1d491` はその後に出力先衝突ガード・原子的書込み・不正bootstrap件数のfail-fast・paired成果物のcanonical path固定を追加しており、ROI計算・買い候補選択・paired標本化には変更がない。production 4 artifactはbefore/after一致、封印アクセスなし。
- `.venv64/Scripts/python.exe -m pytest tests/test_f3_phase0_0_eval.py -q` は最終HEADで **11 passed**、全体は **377 passed**。出力先がproduction/input成果物や任意パスへ衝突しないこと、bootstrap件数0をOOS実行前に拒否することが追加固定された。ただしpaired数値testは同一ledgerの0差が中心で、非対称bet集合・common-race 2分岐・符号を直接固定するunit testはない。
- `docs/F3_phase0_0b_result.md` はレビュー時点でuntracked、`paired_oos.json` はgit管理外。JSON内SHAでコードは照合できるが、結果文書と成果物をcommit単位で固定できていない。

## 前回からの差分

- 総合 **2.0 → 2.0 (±0.0)**。ROI62.09%という収益性証拠は不変。
- 前回は旧70.7%との非paired比較しかなく、3チャネルのROI寄与を分離不能だった。今回は同一day-blockのcontrol/treatmentで、点推定差+1.0191pt、CI [-4.6737pt, +6.4106pt]まで確定した。
- 共通race basisでは両方向とも0差。自己選択差はbet集合の境界差で説明でき、3チャネルが馬のtop-1選択を改善した証拠はない。ただしrace単位の一致証明にはledger保存が必要。
- 測定品質は明確に改善したが、control/treatment双方が控除率以下なので投資判断は引き続き **HOLD / 実弾投入不可**。

## 優先課題

1. **収益性改善を先に要求** — Phase 1候補は同じOOS/day-block方式で最低でもROI 80%超、採用件数を保ち、最終的には100%超を目標にする。ROI差だけでなく損益・最大DDも同時に出す。
2. **確率と資金配分を分離監査** — M2-treatment専用calibratorをTRAIN内のみでfitし、旧p21流用版と比較する。`PRED_DISABLE_DISCOUNT=1`、flat 100円、fractional Kelly cap別を同じledgerで並べる。
3. **paired監査証跡を固定** — 匿名race ledgerまたは日別集計、bet集合のintersection/control-only/treatment-only、top馬一致数を保存し、非対称集合とcommon-race分岐のunit testを追加する。結果JSON/文書もcommitまたはmanifest SHAで固定する。
