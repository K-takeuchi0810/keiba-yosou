# Phase A1 / A2 / S5 / S6 / S7 累積評価サマリ (expert-review 全 7 名)

**評価範囲**: `bad4e9c..d5c76ce` (Phase A1 + A2 + S5 + S6 + S7 の 18 commits)
**評価日**: 2026-05-18
**評価軸**: 「LGBM v5 環境下での最善対応」 (絶対収益性ベースの判定は不要、利益化は Phase B1 後)

## 7 名総合スコア

| Subagent | 今回 | 前回 | Δ |
|---|---:|---:|---:|
| gui-ux-auditor | **3.8** | 3.6 (P06) | **+0.2** |
| mobile-html-reviewer | **4.6** | 4.4 | **+0.2** |
| prediction-logic-analyst | **4.35** | 4.0 (P16 A1) | **+0.35** |
| profitability-judge | **3.5** | 3.8 (P05) | -0.3 |
| data-pipeline-engineer | **4.4** | 4.0 | **+0.4** |
| code-quality-reviewer | **4.5** | 4.3 (P05) | **+0.2** |
| validation-process-auditor | **4.55** | 4.22 | **+0.33** |
| **平均** | **4.24** | **4.06** | **+0.18** |

## profitability-judge の -0.3 について

絶対収益性ベース (TEST 81.2% / Holdout 52.1%) で評価軸を固定するルーブリック準用で -0.3。ただし subagent 自身が「LGBM v5 構造楽観 + 2026 ドメインシフトであり改修群の責任ではない」「Phase B1 完了後の再採点で +0.5〜+1.0 戻り、総合 4.0〜4.5 到達を予期」と明示。実質的には **構造的限界の証明** として評価された。

## 主要な肯定的所見

### 1. S7-α の構造的勝利 (DRY 集約)
- 4 経路 (predict / backtest / gui / generator) で重複していた `is_buy_candidate` を `predictor/filter.py` の 1 関数に集約
- 各経路 5-15 行の delegate に短縮、約 160 行の重複を 107 行 + 薄い委譲層に置換
- code-quality-reviewer: 4.7/5 (DRY 軸)
- gui-ux-auditor: 5/5 (バグ予防構造軸)、validation-process-auditor: 構造的予防として高評価

### 2. Phase A2 校正系の数値改善
- bin (TRAIN 21-23 fit) → Isotonic (TEST 2025 fit) で Brier 0.0606 → 0.0377 (-42%)
- meta snapshot 制度で「どの calibrator + LGBM + git_sha で出した結果か」3 世代追跡可能
- data-pipeline-engineer: 5/5 (データ鮮度管理)、validation-process-auditor: 4.4/5 (calibration、+0.6)

### 3. S6 sweep の陰性証明としての価値
- 74 戦略 × 3 fold = 222 データポイントで robust 0/74 を実証
- 「filter 層では救えない、Phase B1 (LGBM v6) こそが唯一の経路」という意思決定根拠
- validation-process-auditor: 「Phase B1 移行根拠を 222 データポイントで支持」と高評価

### 4. CLAUDE.md ルール 1-bis / 1-ter の運用ルール化サイクル
- S1 P16 A1 で subagent CWD 誤評価 → ルール 1-bis 制定
- S3 で TEST 全期 backtest 漏れ事故 → ルール 1-ter 制定
- S4 で ルール 1-ter を 2 回違反 → S5-0 で checkbox 形式に書き換え → S6/S7 違反ゼロ
- validation-process-auditor: 「稀有なメタ品質改善サイクル」と評価、過適合監視 +0.6

### 5. HTML UX の質的向上 (S7-β/γ)
- mobile-html-reviewer: タップ領域 4→5、情報密度 4→5
- ★ 強い買いバッジ、Kelly 降順、filter-summary、version-snapshot、pick-reason 17→5 シグナル

## 主要な残課題と Phase B1 への引き継ぎ

### prediction-logic-analyst 指摘

**LGBM v5 高 p 帯構造楽観** (n=48,058 records から定量化):
| bin (raw_p) | n | raw_p_mean | actual | gap |
|---|---:|---:|---:|---:|
| [0.30, 0.40) | 1045 | 0.340 | 0.070 | -0.27 |
| [0.40, 0.50) | 300 | 0.442 | 0.077 | -0.37 |
| [0.50, 0.70) | 243 | 0.549 | 0.033 | -0.52 (逆転) |
| [0.70, 1.00) | 14 | 0.756 | **0.000** | 致命的 |

**Isotonic は構造楽観を正しく学習している** (x_knots=0.908 を y≈6.5% にダウンマップ) が、`predictor/rules.py:806-809` の race 内 Σ=1 再正規化で高 p 帯馬が再浮上する。

### profitability-judge 指摘

Phase B1 後の予期スコア: **+0.5〜+1.0 戻り、総合 4.0〜4.5 到達**。

## Phase B1 plan の動機 (本評価から)

1. **LGBM v6 再訓練** (TRAIN rolling forward 2021-2024、val 2025、test 2026)
2. **listwise/softmax loss** で race 内 Σ=1 制約と構造楽観の同時解消
3. **Tier 2/3 features 追加** (rolling 統計、ペース動態、4 角通過順位、馬体重 Δ、馬場バイアス等)
4. **採用判定基準**: filter_sweep --recent-3fold で robust 戦略 ≥ 1 件、Brier ≤ 0.055 (LGBM val)

## 期待される Phase B1 改善

- profitability-judge: 3.5 → 4.0〜4.5
- prediction-logic-analyst: 4.35 → 4.5〜4.7
- 全体平均: 4.24 → 4.5+

## scorecard 個別ファイル

- `20260518_phase_a1_to_s7__gui_ux_auditor.md`
- `20260518_phase_a1_to_s7__mobile_html_reviewer.md`
- `20260518_phase_a1_to_s7__prediction_logic_analyst.md`
- `20260518_phase_a1_to_s7__profitability_judge.md`
- `20260518_phase_a1_to_s7__data_pipeline_engineer.md`
- `20260518_phase_a1_to_s7__code_quality_reviewer.md`
- `20260518_phase_a1_to_s7__validation_process_auditor.md`

## CLAUDE.md ルール 4 (戦略採用後の月次 rolling 監視義務) の含意

S5-3 で採用した BUY_FILTER 設定 (`min_kelly=0.05`, `max_predicted_p=0.40`, 全場開放) は、本 expert-review で「フィルタ層の最善対応」と評価された一方、S6 sweep で **robust 0/74** = 利益化不能。

→ **本設定は採用するが、Phase B1 完了まで「実弾運用しない」** ことを memory `feedback_current_buy_candidates_warning.md` で継続。
