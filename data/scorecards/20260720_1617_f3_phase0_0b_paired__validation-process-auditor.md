# 検証プロセス監査人 採点 — F3 Phase 0-0b paired OOS（最終）

**最終コード commit**: `fa1d491`（前段 `d4a4dcc` / `5b4d43d` / `655d5d0`、paired evaluator導入 `af13474`）  
**長時間実行 provenance**: `evaluator_commit=af13474c0a523abaa83c851bcfb3d418ced593db` / evaluator SHA-256 `ecabaa23...40ad`  
**対象**: `scripts/f3_phase0_0_eval.py`, `tests/test_f3_phase0_0_eval.py`, `data/f3_phase0_0/paired_oos.json`, `docs/F3_phase0_0b_result.md`

## 総合: 4.8 / 5 — **PASS**

- 直前レビュー: 4.6 → **+0.2**
- F3 Phase 0-0 初回レビュー: 4.4 → **+0.4**
- HOLD条件: なし。paired OOS correctness契約、sealed保護、production不変、provenance、安全な出力契約を確認した。

前回の最優先課題だった同一 OOS runner / race universe による control-treatment paired ROI 比較は成立している。主判定 `self_selected` は control 424 bets / 63.1132%、treatment 425 bets / 62.0941%、差 +1.0191pt、共通day resampleのpaired 95% CI [-4.6737pt, +6.4106pt] で0を含む。よって「事前登録3チャネルの除去によるROI有意差なし」という限定結論はデータと整合する。

最終差分では、paired JSON/reportのatomic replace、相互衝突・production/cache/Phase成果物/OOS reference/historical calibratorへの上書き拒否、`bootstrap_samples<=0` の長時間OOS前fail-fast、`evaluator_commit` と evaluator content SHAの保存を追加。`fa1d491` では任意 `output_dir` も閉じ、JSONを厳密に `data/f3_phase0_0/paired_oos.json`、reportを規定docsパスへ限定した。DB/source/configや `data/other` を含む任意プロジェクトファイルへの誤上書きを構造的に禁止している。

## 項目別

| 採点軸 | 最終 | 直前 | 差分 | 根拠 |
|---|---:|---:|---:|---|
| バックテスト設計の正しさ | 5/5 | 5/5 | ±0 | `_evaluate_oos` を両モデルで再利用し、期間・JRA限定・確定race・filter・calibrator・rulesを固定。race ledger集合一致を必須化し、同じday index/resampleで各ROIと差を計算。425/65/62.09%のfrozen treatment再現に失敗すればcontrol実行前に停止する。 |
| 時系列リーク防止 | 5/5 | 5/5 | ±0 | train/validation、2026-01-01〜06-14 OOS、2026-10-01以降sealedを分離。cache実race-key guard、`< before_date`、同日 `start_time < ?`、readonly DB、rules SHA固定、production SHA前後一致を確認。sealed accessはfalse。 |
| calibration / reliability計測 | 4/5 | 4/5 | ±0 | frozen validation AUCを完全再現し、Phase 0-0のBrier/LogLoss、固定historical calibrator SHAを維持。残課題はcontrol-treatmentのreliability bins、およびclustered ΔBrier/ΔLogLoss/ΔAUC CI。 |
| A/B比較 / バージョン管理 | 5/5 | 4/5 | +1 | experiment/rules/evaluator commit、evaluator blob SHA、model/features SHA、固定seed/B、production before/after SHAを機械可読保存。保存JSONのSHAは `git show af13474:scripts/f3_phase0_0_eval.py` と完全一致し、後続安全修正も `655d5d0` / `5b4d43d` / `d4a4dcc` / `fa1d491` で追跡可能。 |
| 過適合監視 / 期間分割評価 | 5/5 | 5/5 | ±0 | 学習/validationとは別の固定2026 OOSをpaired評価し、将来sealedを未使用のまま温存。判定は事前commitしたbasis (a) のpaired CIだけに限定し、旧70.70%との非paired比較を寄与推定に使っていない。 |

## paired correctness確認

### 同一day resample

`_paired_roi_bootstrap` は50日の共通 universeからbootstrap index行列を一度生成し、その同じ各行でcontrol/treatmentのbet・returnを再集計して `ROI_control - ROI_treatment` を算出する。独立CIの差ではなく真のpaired day-block bootstrapである。B=10,000、seed=20260720、valid samples=10,000。

`self_selected` の `n_races=471` は両policyのbet race union。intersection=378、control-only=46、treatment-only=47で、選択policy差を保持したdeployment比較になっている。basis (b-1)/(b-2) はrace集合を片側policyで固定した馬選択診断であり、差0を「全確率・全判定が同一」とは解釈しない。

### 再現性 / provenance

- paired artifact: `evaluator_commit=af13474...`。
- 保存 evaluator SHA `ecabaa23...40ad` は当該commitのscript blob SHAと完全一致。現HEADの後続安全修正と混同していない。
- frozen validation AUC: control 0.7913195088860858 / treatment 0.7887806982333265、期待値と再計算値が一致。
- treatment OOS: 425 bets / 65 hits / ROI 0.6209411764705882 をfrozen Phase 0-0から完全再現。
- production 4成果物のbefore/after SHAは一致し、sealed holdout accessはfalse。
- paired contract独立照合: **OK**。

### 出力安全性

- paired JSON/reportは一時ファイルから同一filesystem上でatomic replace。
- JSONとreportの同一pathを拒否。
- production artifacts、training cache、Phase metrics/models/features/allowlist、旧Phase report、OOS reference、historical calibratorとの衝突を実行前拒否。
- project外pathを拒否し、project内でもJSONは `data/f3_phase0_0/paired_oos.json`、reportは `docs/F3_phase0_0b_result.md` 以外を拒否。任意 `output_dir`、DB/source/config、`data/other` 等への誤上書き余地を閉じた。
- `bootstrap_samples<=0` はOOS処理開始前に即時拒否。内部paired関数にも防御を維持。

## テスト / サニティ

- focused: `.venv64/Scripts/python.exe -m pytest -q tests/test_f3_phase0_0_eval.py` → **11 passed**。
- 全体: `.venv64/Scripts/python.exe -m pytest -q` → **377 passed, 4 skipped**。
- 回帰テストは3件allowlist、zero-fill限定、sealed/cache日付/project path、共通resample、invalid B、出力衝突、OOS前fail-fast、saved AUC再現を含む。
- `git log --stat` で `af13474` → `655d5d0` → `5b4d43d` → `d4a4dcc` → `fa1d491` の実装・安全修正履歴を確認。

## 残課題（非HOLD）

1. validation/OOSの probability bin別 `count / avg_probability / actual_win_rate` をcontrol/treatment並列で保存する。
2. race/day clusterによる ΔBrier / ΔLogLoss / ΔAUC CIを追加し、「ROI差なし」と「確率品質差なし」を分離する。
3. policy overlapのintersection/control-only/treatment-only、top horse一致数、実bet day数をJSONへ直接保存し、現在の導出値を機械可読化する。

## 最終判定

**PASS**。F3 Phase 0-0b は、固定OOS上のpaired ROI検証として再現可能で、3チャネル差に限定した結論を支持する。CIは0を含むため、有意なROI寄与は確認されない。将来sealedは温存され、本番成果物も不変。reliability/確率差CIは次段の改善事項だが、correctness章を閉じることを妨げるHOLD要因ではない。
