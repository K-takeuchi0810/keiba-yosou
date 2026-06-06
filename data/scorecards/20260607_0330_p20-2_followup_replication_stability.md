# P20-2 follow-up: 2025 再現確認 + _stability_score 非対称性の検証

**日時**: 2026-06-07 03:30
**目的**: expert-review (20260607_0300) の優先課題 2 (1 窓 permanent delete の堅牢化) と 3 (_stability_score の recent_avg 非対称性) を backtest で決着。
**前提**: P20-2 (commit 5d30d44) = raw 平均着順を `_score_one` から削除、`_stability_score` には残置。

---

## 優先課題 2: 2025 同季節での再現確認

expert-review で「2026 Apr-May の +7.6pt は two-proportion z=1.10 で非有意、1 窓 1 dataset での permanent delete は scorecard_ops_v2 §0.0 dataset 上限違反」と指摘された。別季節 (2025 Apr-May, n=372 races) で削除の符号が再現するか確認。

| 指標 | 2026 with→without | 2025 with→without | 符号 |
|---|---|---|---|
| rank-1 回収率 | 77.0% → 84.6% (**+7.6pt**) | 79.9% → 85.4% (**+5.5pt**) | **両年 +** ✓ |
| rank-1 的中 | 42→52 / 408 | 25→29 / 372 | 両年 + |
| buy_only 回収率 | 50.6% → 47.6% (-3.0pt) | 82.4% → 93.1% (+10.6pt) | 不一致 (noisy) |
| Brier | 0.065533→0.065449 (中立) | 0.028131→0.028140 (中立) | 両年中立 ✓ |

**判定**: rank-1 べた買い (= 最も安定な n=372-408 指標) で **2 季節とも削除が +改善**、Brier は両年とも中立。各単年は非有意だが、**独立 2 dataset で符号一致** = scorecard_ops_v2 §0.0 の「観察範囲内」を超えた支持。**raw 平均着順削除は非有害と確認、permanent delete を正当化**。

buy_only は 2026 -3pt / 2025 +10.6pt と不一致だが、両年とも候補集合が変わる (n 92-160) + 的中 4-13 の小サンプルで決定材料にしない (検証監査人の「別集合比較」指摘どおり)。

evidence: `data/backtest/20260607_*baseline-2025val*` (with) vs `*p20-2-2025val*` (without)

---

## 優先課題 3: _stability_score の recent_avg 非対称性

expert-review (予測ロジック + コード品質) が「recent_avg を `_score_one` から消したのに `_stability_score` (hardcoded 8/5/2/-4) に残るのは非対称、ablation 対象に」と指摘。`_stability_score` からも削除した版を 2026 Apr-May で backtest。

| 2026 Apr-May | P20-2 (stability 残置) | stability も削除 | Δ |
|---|--:|--:|--:|
| rank-1 回収率 | 84.6% | **62.7%** | **-21.9pt** |
| rank-1 的中 | 52/408 | 53/408 | +1 |
| buy_only 回収率 | 47.6% | 49.8% | +2.2pt |
| Brier | 0.065449 | 0.065446 | -0.000003 |

**判定**: stability 側も削除すると rank-1 回収率が **-21.9pt 大幅悪化** (的中は +1 だが回収率崩壊 = ◎ が低オッズ寄りにシフトし価値を取れない)。→ **revert、stability の recent_avg は残す**。

**非対称性は「バグ」ではなく data 上正しい配置**:
- `_score_one` の recent_avg: スコア直加算 → 薄経験馬の 1走2着を過大評価 → **有害** (削除 +7.6pt)
- `_stability_score` の recent_avg: 接戦時の secondary tie-break / 高信頼ゲート → 安定した中オッズ馬へ誘導 → **有益** (削除 -21.9pt)

同じ feature でも「直接スコア化」と「接戦時のみ効く tie-break」で符号が逆転する非自明な発見。コード comment (rules.py:111-118) にこの根拠を記録。

evidence: `data/backtest/20260607_*p20-2b-stability-removed*` vs `*abl-b-no-recentavg*`

---

## 結論

| 課題 | 判定 | アクション |
|---|---|---|
| 優先 2 (再現) | 2 季節で削除 +改善・Brier 中立 | permanent delete 確定 (堅牢化済) |
| 優先 3 (非対称) | stability 削除は -21.9pt 有害 | stability recent_avg 残置 (data 正当) |

expert-review の収益性 -0.9 / 検証 -0.55 の主因 (「1 窓 permanent delete + 過剰主張」) のうち、**1 窓問題は 2025 再現で解消**。残る「+7.6pt 過剰主張」は scorecard (20260607_0300) で「非有害 + 構造的冗長」へ訂正済。改修 (P20-2) は維持で確定。

## 残る宿題 (別タスク)
- training_times 0 行 (新馬戦・調教データ取込、jvdata-record skill 領域)
- mobile: portfolio-note の flex-wrap 化 (8 日窓で折り返し過密)
- kelly_weighted_return_rate を backtest に追加 (収益性 judge 積み残し)
