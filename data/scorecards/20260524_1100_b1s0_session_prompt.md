# B1-S0 セッション開始時の Claude 指示 prompt

**用途**: 次セッション開始時にユーザがこのまま Claude に貼り付ける。本セッション (P19) の handoff の中核を、prompt 形式に圧縮した版。
**書いた日時**: 2026-05-24 11:00
**handoff 本体**: `data/scorecards/20260524_1000_p19_handoff_to_b1s0_session.md`

---

## 貼り付け用 prompt (以下を次セッションへ)

```
Phase B1-S0 pre-flight を開始します。前セッションの plan v2 + critic
CONDITIONAL APPROVE を起点に、5 OP を組み込んだ step 0-6 の手順で進めて
ください。

【着手前の必読 (= 順に読む)】
1. data/scorecards/20260524_1000_p19_handoff_to_b1s0_session.md (handoff 本体)
2. data/scorecards/20260524_0900_p19_b1_plan_v2.md (= master plan, §0.2 Gate
   構造と §5.2 シナリオ判定 table を頭に入れる)
3. data/p19_b1_session_notes.txt (前セッション規律 notes、訂正履歴 + 対立仮説)
4. data/scorecards/20260524_0530_p18_h2_results_v4.md (上流 evidence、§0 rubric
   出典、§1.1 月次 Brier 表は H3-2 で使用)
5. docs/PHASE6_TIER23_DESIGN.md (Tier 2/3 features 既存設計、step 4 SQL
   audit で参照)

【セッション開始時の最初の作業 (= 順守)】
(a) git status 確認 (CLAUDE.md ルール 0)
(b) plan family 4 件を 1 commit にまとめる (= 本日着手前の clean state)
    - data/scorecards/20260524_0700_p19_b1_plan_v1.md
    - data/scorecards/20260524_0900_p19_b1_plan_v2.md
    - data/scorecards/20260524_1000_p19_handoff_to_b1s0_session.md
    - data/scorecards/20260524_1100_b1s0_session_prompt.md (本 file)
    - data/p19_b1_session_notes.txt
(c) p19_b1_session_notes.txt §6 (= B1-S0 用) に事前予想 + 30 秒ポーズ +
    対立仮説 3 つを書く。Gate-2 三条件 ALL pass 確率の predict 中央値は
    handoff 「事前予想」section から流用 = 0.36

【最初に問い直す論点 (B1-S0 着手の起点)】
plan v2 §0.2 で定義した 3 段 gate のうち Gate-2 (a)(b)(c) AND を、
B1-S0 完了時に評価する。以下を順に問い直してください:

(i) Gate-2 (a) 「H3-2 同季節 Welch t-test で N3 season selection bias 「弱く
    棄却」以上」: v4 §1.1 N1 5 ペアで本当に p < 0.05 出るか。事前予想 0.50-0.65
(ii) Gate-2 (b) 「§5.2 シナリオ判定 table に multi-fold 採否 row 追加」: OP-1
     で 1 行追加、これが「組込み完成」と evaluate されるか
(iii) Gate-2 (c) 「H3-3 で 2026Q1 LGBM 崩壊の causal candidate >= 1 個特定」:
      276 picks 分解で anomaly が >= 2σ 出る軸があるか

【B1-S0 着手手順 (= handoff doc step 0-6 に critic 5 OP を組込済)】
Step 0 (30 分): OP-1 = plan v2 §5.2 table に multi-fold 評価 row を 1 行 Edit。
Step 1 (0.5h): H3-1 MING dynamics changelog 検証 (git log + diff)。
Step 2 (0.5h): H3-2 同季節 Brier Welch t-test + OP-5 = Gate-2 (a) precommit。
Step 3 (2-3h): H3-3 2026Q1 LGBM 崩壊 root cause 探索 (5 軸分解)。
Step 4 (1h, 実態 2-3h): OP-3 個別 SQL audit (9 features) + OP-2 sanity check
       = 30 分時点で 1 feature 完了確認、未完了なら 2-3h に上方修正。
Step 5 (B1-S0 終了直前): OP-5 完成 = Gate-2 (a)(b)(c) ALL evaluate、
       AND が Y なら B1-S1 着手 OK、N があれば §7.4 (C) Q-aware pivot or
       plan v3 起こし。
Step 6 (本体ロジック編集の有無で分岐): scripts/ に新規 .py を作ったら
       expert-review 必須 (CLAUDE.md ルール 1)、data/ docs/ のみなら skip OK。

【plan v2 から引き継ぐ未解決論点 (= v2 §8.4 残置 list + v2 critic 新規 P9/P10)】
- P9 (必須): Gate-2 (b) multi-fold 組込みは v2 plan §5.2 で「同一」と書いて
  しまった = OP-1 で 1 行追加して完成させる (= step 0 で先に解消)
- P10 (必須): step4 1h は楽観値、OP-2 で着手 30 分時点で sanity check
- P1' (推奨): P(robust) 0.15-0.30 + P(holdout) 0.15-0.25 下方校正の妥当性、
  critic 「strong evidence、下方維持は正当」だが、B1-S0 結果で再々確認
- P8 (推奨): 訂正累計 12 回 (v4→v1→v2 で 2→8→2 増分)、v3 起こし trigger は
  「著者自発訂正 >= 1 件」(= OP-4 で監視)
- B1-S0 シナリオ確率の事前固定 (handoff より): Gate-2 通過確率 0.36、
  B1-S0 stop (= Gate-2 未通過) 0.40、B1-S1 進行中の予想外発見 0.24

【規律 (= P19 セッション末で固定済)】
- 「self-aware は防御線ではない」(= v2 critic §3 採用): plan 訂正は本文に
  直接 line-edit、残置 list だけで安心しない
- 両方向校正が plausible な場合 range 拡大 (= P1 修正の教訓): 機械的下方
  禁止、controlled 反証の強さで方向を決める
- 訂正起源 tag 化 (= OP-4): 訂正を「critic 起源 / 著者自発 / data evidence
  起源」で tag、著者自発訂正 >= 1 件で即時 v3 起こし review
- handoff brief 外のタスクを思いついたら override 欄に書く (= v4 §4 事故 1
  予防): B1-S0 で causal candidate 探索中の scope creep に注意
- 事前予想 → 30 秒ポーズ → 事後判定の二重構造 (= v4 §4 事故 1 予防):
  step 2 / step 3 開始前に予想を session notes に書く、log 開いてから
  30 秒は別行動を挟む
- 平均訂正回数 (本日 12 回累計) を超える著者自発訂正があった時点で
  クロージング (= v3 起こし review に切替)

【完了条件】
B1-S0 セッション末で以下を全て満たす:
- [ ] OP-1〜OP-5 すべて実施済
- [ ] Gate-2 (a)(b)(c) 三条件の現時点判定が session notes §8 に明文化
- [ ] data/h3_1_ming_changelog.log / data/h3_2_season_brier_test.log /
       data/h3_3_q1_root_cause.log / docs/phase_b1_leak_audit.md の 4 ファイル
       が新規作成 + 内容充足
- [ ] 「B1-S1 着手 OK」or「§7.4 (C) Q-aware pivot」or「plan v3 起こし」の
       いずれを取るか明示的に決定
- [ ] B1-S0 結果を data/scorecards/{date}_p19_b1s0_results.md に集約
       (= H1 v3 / H2 v4 形式踏襲)
- [ ] CLAUDE.md ルール 1: scripts/ 新規 .py を追加した場合は expert-review
       を実行 + scorecard 保存
- [ ] 次セッション (= B1-S1 or pivot session) への handoff doc を
       data/scorecards/{date}_p19_b1s0_handoff_to_next.md として書く

完了したら critic (a6ddb18d1d9f3d9d3 = v2 critic 継続) に B1-S0 結果と
Gate-2 (a)(b)(c) evaluate を SendMessage で送り、B1-S1 着手の最終許可を
得てください。
```

---

## 補足: prompt 設計の判断記録

### 本 prompt が圧縮した handoff 本体の要素

handoff doc (= `20260524_1000`) の長さは ~280 行。本 prompt は ~100 行に圧縮。圧縮で削った内容:
- 個別 SQL audit の templates 例 (= step 4 着手時に handoff から読み込ませる)
- 「このメモの自己評価」section (= 内部記録、prompt には不要)
- 残るリスク R1-R3 (= step 4 着手時の sanity check + OP-4 で吸収)

### 本 prompt が **強化** した要素 (handoff 本体より明確化)

- **完了条件 7 項目**: handoff §B1-S0 着手手順は step 順だが、完了条件 list は明示してなかった
- **critic SendMessage 指示**: handoff §「次セッションへ送るタスク」では「critic に再依頼」とだけ書いたが、prompt では agent ID a6ddb18d1d9f3d9d3 を明示
- **訂正累計 12 回 + クロージング条件**: handoff §「解釈バイアスへの注意」では明示してなかった

### prompt 形式が本セッション冒頭 prompt と異なる点

本セッション冒頭 prompt (= ユーザがくれた P19 plan v1 着手 prompt) との対照:

| 項目 | P19 plan v1 prompt (本セッション冒頭) | B1-S0 prompt (次セッション用) |
|---|---|---|
| 着手前の必読 | 3 件 | 5 件 (+ plan v2、PHASE6_TIER23_DESIGN) |
| 最初に問い直す論点 | (i)(ii)(iii) plan 全体の起点 | Gate-2 (a)(b)(c) 三条件 |
| 規律 | rubric 継承 + 訂正規律 | + 「self-aware は防御線ではない」+ OP-4 訂正起源 tag |
| 完了条件 | plan v1 作成 + critic 依頼 | OP-1〜5 + Gate-2 evaluate + 4 ファイル新規 + handoff doc + critic SendMessage |

形式の連続性を維持しつつ、B1-S0 固有の operational task (step 0-6) を埋め込んでいる。
