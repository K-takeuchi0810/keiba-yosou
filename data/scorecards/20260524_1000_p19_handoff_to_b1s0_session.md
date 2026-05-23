# P19 → B1-S0 セッション 引き継ぎメモ

**書いた日時**: 2026-05-24 10:00
**書いた理由**: plan v1 + critic + plan v2 + critic 再確認の 4 サイクルを 1 セッション内で完了したが、B1-S0 pre-flight 自体 (4-5h、実態 5-7h かも) は次セッションに送る。critic verdict **CONDITIONAL APPROVE** + 5 OP を「次の最初の作業」として handoff。

**critic 最終 verdict**: CONDITIONAL APPROVE (= B1-S0 着手 OK、ただし 5 OP を B1-S0 内で完遂が前提)
**critic agent ID** (継続会話用): `a6ddb18d1d9f3d9d3`

**参照すべき先行 doc**:
- `data/scorecards/20260524_0900_p19_b1_plan_v2.md` (= B1-S0 が従う master plan)
- `data/scorecards/20260524_0700_p19_b1_plan_v1.md` (= v2 直前版、参考用)
- `data/scorecards/20260524_0530_p18_h2_results_v4.md` (= 上流 evidence、§0 rubric 出典)
- `data/scorecards/20260523_2230_p18_handoff_to_next_session.md` (= 前々セッション handoff)
- `data/p19_b1_session_notes.txt` (= 事前予想 + 訂正履歴 + 対立仮説、本セッション中の規律記録)
- `docs/PHASE6_TIER23_DESIGN.md` (= Tier 2/3 features 既存設計)

---

## 次セッション開始時の最初の作業

### 1. `git status` 確認 (CLAUDE.md ルール 0)

本セッション末で master HEAD は `e8ea17e` (= H2 commit) のまま。本セッション中 commit はなし。以下が untracked:
- `data/scorecards/20260524_0700_p19_b1_plan_v1.md` (P19 plan v1)
- `data/scorecards/20260524_0900_p19_b1_plan_v2.md` (P19 plan v2)
- `data/scorecards/20260524_1000_p19_handoff_to_b1s0_session.md` (本 doc)
- `data/p19_b1_session_notes.txt` (規律 notes)
- `data/scorecards/20260524_0600_p18_h2_n1n8n2__expert_review.md` (前セッション末から既存)
- `docs/prediction_usage.md` (前セッション末から既存)

**判断**: B1-S0 着手前に上記 4 件を 1 commit にまとめて commit 推奨。理由: B1-S0 で `docs/phase_b1_leak_audit.md` 新規作成、`scripts/season_brier_test.py` 等の新規 script を追加する可能性高、その前に plan family の clean state を作っておく。

### 2. plan v2 § 0.2 Gate 構造を頭に入れる

3 段 gate を再確認:
- **Gate-1 (OPEN)**: plan 執筆 + B1-S0 pre-flight (= 本セッションで通過済、CONDITIONAL APPROVE)
- **Gate-2**: B1-S2 (LGBM v6 retrain 本体) 着手 gate
  - (a) H3-2 で N3 season selection bias 「弱く棄却」以上 (= Welch t-test p < 0.05)
  - (b) §5.2 シナリオ判定 table に multi-fold 採否 row 追加済 (= OP-1)
  - (c) H3-3 で 2026Q1 LGBM 崩壊 causal candidate >= 1 個特定
- **Gate-3**: 採否 (シナリオ A/A-partial/B/C/D)

### 3. critic 5 OP を着手順に確認 (CONDITIONAL の前提条件)

---

## B1-S0 着手手順 (= critic 5 OP を組み込んだ順序)

### Step 0 (= B1-S0 着手 1 日目 最初 30 分): **OP-1 実施**

**plan v2 §5.2 シナリオ判定 table に multi-fold 評価 row を 1 行追加** (P9 対処):

新規 row 案 (v2 §5.2 table の最後に追加):
```
| **multi-fold** | quarterly fold (Q1-Q4) + rolling 12m + 季節別 の 3 scheme 中 >= 2 scheme で robust=Y or min_lo >= 75% | Gate-2 (b) 通過 → シナリオ A 必須 |
```

実装: plan v2 file を直接 Edit。multi-fold scheme は filter_sweep.py の既存機能の組合せ (`--walk-forward-3fold`, `--by-track-3fold` 等) で実現。

### Step 1: H3-1 (MING dynamics changelog 検証, 0.5h)

- `git log --oneline --all -- jvlink_client/ingest.py predictor/features.py | head -30` で 2025-2026 間の変更 list
- MING (dm_rank_1_3) が picking する horse の odds median 40.4 → 7.7 fold shift が:
  - (a) ingest 層変更 (raw → SQLite で MING fields の column mapping 変わった)
  - (b) features 層変更 (MING signal の derivation logic 変わった)
  - (c) 両方とも変更なし (= データ自身の shift)
- いずれかを git log + diff で特定、`data/h3_1_ming_changelog.log` に記録

### Step 2: H3-2 (同季節 Brier 悪化 Welch t-test, 0.5h) + **OP-5 (Gate-2 (a) precommit)**

- v4 §1.1 N1 月次 Brier 表 から 2025-01 〜 05 と 2026-01 〜 05 の 5 ペアを抽出
- Welch t-test (`scipy.stats.ttest_ind(..., equal_var=False)`) で p 値計算
- monthly bootstrap CI (n_resample=10000) も併走
- 出力: `data/h3_2_season_brier_test.log` に p, CI, n_per_group
- **完了直後**: `data/p19_b1_session_notes.txt §8` に Gate-2 (a) 判定を 1 行記録 (= "p=X.XX, (a) verdict: <pass/fail>")

### Step 3: H3-3 (2026Q1 LGBM 崩壊 root cause 探索, 2-3h)

- 2026Q1 picks 276 件 (v4 §1.1 N1 表より) を以下軸で分解:
  - 馬場状態 going (1-4) × hit_rate
  - 出走頭数 head_count × hit_rate
  - 新馬比率 × hit_rate
  - グレード × hit_rate
  - 距離帯 × hit_rate
- 2025Q1 baseline と比較、anomaly >= 2σ なら causal candidate
- 出力: `data/h3_3_q1_root_cause.log` + causal candidate list
- **causal candidate がいずれか Tier 2/3 features (T2.1b expected_pace_index 等) に対応するかチェック**
- 完了後 `data/p19_b1_session_notes.txt §8` に causal candidate 数を 1 行記録 (= "causal candidates: <n>, (c) verdict: <pass/fail>")

### Step 4: **OP-3 + OP-2 sanity check** (個別 SQL leak audit, 1h → 実態 2-3h)

- `docs/phase_b1_leak_audit.md` を新規作成、9 sections (= T2.1a / T2.1b / T2.2a / T2.2b / T2.3a / T3.1a / T3.1b / T3.2a / T3.3a) で構成
- 各 section に:
  - 命題: feature の説明 (1 行)
  - 提案 SQL: `features.py:720-755` の jockey_track_stats パターンを literal 適用
  - audit 項目 4 つ (= plan v2 §4.2 step4 の audit 項目 1〜4) を Y/N 判定 + 根拠 1 行
- **OP-2 sanity check**: step4 着手 30 分時点で 1 feature 完了確認、未完了なら step4 所要を 2-3h に上方修正

### Step 5 (= B1-S0 終了直前): **OP-5 precommit 完成 + Gate-2 三条件 evaluate**

- `data/p19_b1_session_notes.txt §8` に Gate-2 (a)(b)(c) 三条件の現時点判定を最終記録:
  - (a) Welch t-test p < 0.05? Y/N
  - (b) plan v2 §5.2 multi-fold row 追加済? Y/N
  - (c) causal candidate >= 1 個? Y/N
- **3 条件 AND が Y → B1-S1 着手 OK**
- **1 つでも N → B1-S1 保留、§7.4 (= シナリオ B1-S0 stop) へ進む or plan v3 書き直し**

### Step 6 (= B1-S0 末): expert-review 通過確認

- B1-S0 で本体ロジック (`gui/` `predictor/` `jvlink_client/` `web/` `scripts/`) を編集していれば → CLAUDE.md ルール 1 で expert-review 必須
- 編集なしで `data/` `docs/` のみ → expert-review skip OK
- 注意: H3-2 で `scripts/season_brier_test.py` 等の新規 script を追加した場合は **expert-review 必須**

---

## 着手前の事前固定 (= B1-S0 セッション開始時に session notes へ書き写し)

### 事前予想 (= B1-S0 結果を見る前の予想)

**Gate-2 (a)(b)(c) 三条件 ALL pass 確率**:
- (a) Welch p < 0.05: 予想 0.50-0.65 (= +3.3σ observed だが n=5 ペアで power 不足)
- (b) multi-fold row 追加: 著者操作のため 0.95+ (technical only)
- (c) causal candidate >= 1: 予想 0.55-0.70 (= 276 picks に何らかの軸で anomaly 出る可能性高)
- **AND**: 0.30-0.42 (中央 0.36)

**Gate-2 通過 → B1-S1 進む確率**: 0.36

**Gate-2 未通過 → B1-S0 stop シナリオ確率**: 0.40
  (= plan v2 §7.4 で予想した 0.05-0.15 より大幅高、新発見)

**残り (Gate-2 通過 but B1-S1 で予想外発見)**: 0.24

### 30 秒ポーズ + 対立仮説 3 つ

(B1-S0 開始時に session notes §6 で実施、本 handoff には書かない)

---

## 解釈バイアスへの注意 (本日 P19 セッションの教訓)

1. **「self-aware は防御線ではない」** (= critic verdict §3 採用): plan §8.4 残置 list に列挙しただけで安心しない。critic 必須 verdict は本文 §1.2 / §0.2 等に直接 line-edit する
2. **両方向校正が plausible な場合 range 拡大** (= P1 修正の教訓): 機械的に下方校正しない、controlled 反証の強さで方向を決める
3. **訂正起源 tag 化** (= OP-4): 訂正を「critic 起源 / 著者自発 / data evidence 起源」で tag、著者自発訂正 >= 1 件で v3 起こし review
4. **handoff brief 外のタスクを思いついたら override 欄に書く** (= v4 §4 事故 1 予防): B1-S0 で causal candidate 探索中に「ついでに別 fold scheme も試す」等の scope creep が起きやすい

---

## このメモの自己評価

本 handoff は **次セッションの規律的 entrance** として書かれた。CLAUDE.md ルール 0 (git status)、ルール 1 (expert-review)、ルール 1-ter (重い計算前 checklist) との接続を明示。critic 5 OP を着手順に並べ替えて step 0-6 に整理した。

**残るリスク**:
- (R1) Step 1〜5 を 4-5h で完了する見積もりは critic verdict P10 で「2-3h かも」と楽観性が指摘済。実態 5-7h を許容
- (R2) Gate-2 未通過時の「B1-S1 保留 → §7.4 シナリオ」は plan v2 で「Q-aware operational hedge」と書いたが、handoff §B1-S0 終了時の判断ポイントとして明示的に書いたのは本 handoff が初。次セッションが Gate-2 未通過判定を素早く受け入れて pivot するかは不確実
- (R3) B1-S0 期間中に著者自発訂正が発生したら即時 v3 起こし review (= OP-4)。**この trigger が hot な状態であることを忘れない**
