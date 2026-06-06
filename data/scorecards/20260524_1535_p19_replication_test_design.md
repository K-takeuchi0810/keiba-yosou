# P19 replication test design v1 — Gate-2 再診断の事前固定

**日時**: 2026-05-24 15:35
**目的**: `data/scorecards/20260524_1510_p19_ops_v2_gate2_recalc.md` §4 の「replication test 設計」を、実装 / 実行前に固定する。
**対象**:
- Gate-2 (a): H3-2 同季節 Brier 悪化の power caveat を解く
- Gate-2 (c): H3-3 exploratory signal を confirmatory に昇格できるか検証する

---

## 0. ops v2 前提

本 design は `docs/scorecard_ops_v2.md` の invariants を継承する。

| invariant | 本 design での固定 |
|---|---|
| 1. power 必須公表 | Welch / permutation / z-test の各 verdict に power caveat または resolution limit を併記する。 |
| 2. family size 必須記録 | H3-3 replication は fixed family を使い、axis / bucket / min_n を実行後に変更しない。 |
| 3. fresh-substitute | critic SendMessage に依存せず、本 doc を self-contained な design とする。 |
| 4. 閾値超過時 meta doc | `docs/scorecard_ops_v2.md` と `20260524_1510_p19_ops_v2_gate2_recalc.md` を前提に、plan / B1-S1 着手前の再診断として実施する。 |

---

## 1. Test R1: H3-2 paired sign-flip permutation

**目的**: Jan-May 5 pairs の `mean(2026 Brier - 2025 Brier)` が偶然の符号配置で説明できるかを見る。

**Input**:
- `scripts/season_brier_test.py` の `MONTHLY_BRIER_2025/2026`
- months = Jan-May 5 pairs

**Statistic**:
- paired deltas: `d_m = brier_2026_m - brier_2025_m`
- test statistic: `T = mean(d_m)`

**Permutation**:
- exact sign-flip permutation: 2^5 = 32 patterns
- primary p: two-sided `P(|T_perm| >= |T_obs|)`
- secondary p: one-sided greater `P(T_perm >= T_obs)` because the directional hypothesis is 2026 worsening

**Resolution limit**:
- two-sided exact p の最小値は 2/32 = 0.0625。したがって R1 単独では Gate-2 (a) PASS (p<0.05 two-sided) に昇格できない。
- one-sided exact p の最小値は 1/32 = 0.03125。one-sided は directional 補助としてのみ扱い、Gate-2 (a) の主判定には使わない。

**Verdict rule**:
- two-sided p < 0.05: theoretically PASS だが n=5 では達成不能。設計上 R1 は **Gate promotion ではなく robustness / caveat documentation**。
- one-sided p < 0.05 かつ T_obs > 0: 「directional weak support」と記録。ただし B1-S1 着手条件にはしない。

---

## 2. Test R2: H3-2 Q-segment split

**目的**: Jan-Mar 改善 vs Apr-May 悪化の inversion を、Gate-2 (a) の failure reason として明示する。

**Input**:
- Jan-Mar = Q1 proxy
- Apr-May = partial Q2 proxy
- 同じ monthly Brier table

**Statistic**:
- Q1 delta = mean(2026 Jan-Mar) - mean(2025 Jan-Mar)
- partial Q2 delta = mean(2026 Apr-May) - mean(2025 Apr-May)

**Verdict rule**:
- Q1 delta < 0 かつ partial Q2 delta > 0: **Q-aware split supported descriptively**
- ただし partial Q2 は n=2 pairs なので、単独で Gate-2 (a) PASS / pivot を確定しない。

**Use in route decision**:
- Q-aware pivot の候補 evidence として使う。
- B1-S1 着手可否の positive gate には使わない。

---

## 3. Test R3: H3-3 Q2 replication with fixed family

**目的**: Q1 H3-3 exploratory rows が、Q2 でも同じ fixed family / bucket で再現するか検証する。

**Input**:
- `data/dump_picks_h2.csv`
- baseline: 2025 Apr-May (= partial Q2)
- cohort: 2026 Apr-May (= partial Q2)
- race meta join: `data/keiba.db`

**Fixed family**:
- axes: grade_code, popularity, track_code, odds bucket, distance bucket, starter_count, dm_rank, tm_rank
- bucket definitions: `scripts/q1_root_cause.py` の現行 bucket 関数をそのまま使う
- min_n: 30
- z-method: pooled two-proportion z-test under H0
- correction: Bonferroni + BH-FDR, α=0.05

**禁止事項**:
- Q2 結果を見て min_n を 20 / 50 へ変更しない
- Q2 結果を見て axis を追加 / 削除しない
- Q2 結果を見て bucket 境界を変更しない

**Verdict rule**:
- corrected survivor >= 1: H3-3 replicated candidateあり。B1-S1 limited scope 再検討。
- corrected survivor = 0 but Q1 exploratory row と同方向の |z|>=1.7 が複数: exploratory remains, Gate PASS なし。
- corrected survivor = 0 and no same-direction exploratory rows: H3-3 confirmatory support なし。

---

## 4. Route decision matrix after R1-R3

| R1/R2/R3 result | Route |
|---|---|
| R3 corrected survivor >= 1 and leak-audit PASS feature covers it | B1-S1 limited scope を再検討 |
| R3 survivor 0, R2 Q split descriptive only | B1-S1 保留継続、Q-aware pivot 設計へ |
| R1 one-sided directional support + R3 exploratory repeated, but no corrected survivor | 再診断継続。B1-S1 着手は不可 |
| R1/R2/R3 all weak | Phase B1 は Q-aware pivot or stop を優先 |

---

## 5. 工数見積もり

保守的見積もり:
- R1/R2 implementation: 1.0-1.5h
- R3 implementation: 1.5-2.0h
- log 再出力 + scorecard 更新: 0.5-1.0h

**合計**: 3.0-4.5h

本日 B1-S0 の訂正累計 14 件を踏まえ、30-60 分 task と見積もらない。

---

## 6. 自己評価

この design は「replication test をやる」と言うだけでなく、実行前に以下を固定した:
- test statistic
- family
- correction
- method
- route decision matrix
- 工数

残るリスク:
- Apr-May は partial Q2 であり、真の Q2 replication ではない。
- monthly Brier は集計済み 5 pairs で power が構造的に足りない。
- R3 は picks 単位で sample は増えるが、axis / bucket 探索の研究者自由度は完全には消えない。
