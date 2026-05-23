# scorecard 運用 v2 — 限界と 4 invariants

**書いた日時**: 2026-05-24 14:30
**書いた理由**: 2026-05-23 〜 24 の Phase H1 → H2 → B1 plan v1/v2 → B1-S0 セッション群で露呈した「rule + 機械適用」運用の構造的限界を踏まえ、plan v3 (= tactical) を書く前に **scorecard 運用そのものの invariants** を 1 doc に固定。
**maintenance policy**: **2027-05-24 までこの doc は触らない**。例外条項は §5 を見よ。
**adopted by**: CLAUDE.md (= 関連スキル / メタルール section に reference)

---

## 1. 背景: 今日 (2026-05-23/24) 露呈した 4 つの限界

`data/scorecards/` 形式 + §0 rubric 機械適用 + メタ訂正履歴 警告機構は、2026-05-09 〜 2026-05-23 までは概ね機能した。Phase A1/A2/S5-S7 (= LGBM v5 採用) や P15 wl_kelly_ge_05 採用判定で「数値で見える事故予防」を提供できた実績がある。

しかし 2026-05-23/24 セッション群で **「rule + 機械適用」では fix できない 4 つの限界** が同時露呈した:

### 1.1 限界 (i): 訂正 14 回超過 (= scorecard 本質崩壊閾値 13 を超えた)

- H2 v4 で 2 件、Plan v1 で 8 件、Plan v2 で 10 件、B1-S0 で +2 件、累計 **14 件**。
- 「scorecard の本質的価値 = 規律維持の機構」が訂正回数の数値で「崩壊閾値」を超えたと宣言される段階に到達。
- ただし「閾値超過 → どう対応するか」は rule として存在せず、B1-S0 末で著者判断で「plan v3 起こし review trigger」と判定。**rule 不在ゾーン**。

### 1.2 限界 (ii): 内部 critic 機構の運用基盤崩壊

- B1 plan v1/v2 で内部 critic (validation-process-auditor agent への SendMessage で continuation) を確立、CONDITIONAL APPROVE 取得。
- B1-S0 末で critic SendMessage を実行しようとしたところ、本環境で **SendMessage tool が deferred として load 不可** と判明。
- Agent tool description に SendMessage は記載があるが、ToolSearch で発見できず、call 不可。
- 結果: 内部 critic 機構の継続が tool レベルで折れた、「v2 critic memory を活かした verdict」の取得経路が消えた。

### 1.3 限界 (iii): expert-review の品質後退

- B1-S0 expert-review で平均 3.87 / 5、ただし内訳で **code-quality (-1.1) + validation-process (-0.75)** の大幅後退。
- 後退の原因は本 B1-S0 で追加した診断 script 2 件の設計品質課題 (= MONTHLY_BRIER ハードコード / bucket 関数 6 種 DRY 違反 / power 計算欠落 / Bonferroni 未補正)。
- expert-review 自体は機能した (= 後退を検出)、しかし「7 名平均」の集計で表面的に「平均維持」と見えてしまい、**内訳の不健康さが集計平均で隠蔽される構造**。

### 1.4 限界 (iv): Bonferroni 未補正による判定根拠の構造的脆弱性

- B1-S0 H3-3 で 8 軸 × 平均 5 buckets ≈ 40 bucket の delta z-test を実施、|z|>=2.0 で 4 candidates 報告 → Gate-2 (c) PASS 強。
- validation-process-auditor が指摘: Bonferroni 補正 α/40 = 0.00125 (≈ |z|>=3.0) 適用すれば **0 candidates**。
- すなわち **Gate-2 (c) PASS は未補正 multi-comparison の上に立っており、補正適用後は FAIL の可能性**。
- 同様に H3-2 Welch p=0.81 も power 計算事前公開なしで判定、「FAIL = bias なし」と「FAIL = power 不足」が分離不能。

### 1.5 4 限界を貫く構造課題

4 限界は表面上独立だが、共通の構造課題を持つ:

> **「rule を増やすほど rule 自体の運用 / 監視 / 更新コストが増え、ある閾値を超えると rule 群が新規事故を生む source になる」**

具体的に:
- 限界 (i): 「訂正 13 件閾値」rule 自体は機能、ただし「閾値超過時の action」 rule 不在
- 限界 (ii): 「critic SendMessage」rule は tool 仕様に依存、tool 削除で rule 全体が無効化
- 限界 (iii): 「expert-review 平均監視」rule は集計優先、内訳の構造的後退を隠蔽
- 限界 (iv): 「§0.1 統計検定 rubric」rule は p 値閾値のみ、power と multi-comparison が rule の外

→ **rule の追加で fix する path はもう限界に近い**。invariants (= rule より高次の構造的不変条件) を 4 件絞り、それより下の rule は invariants の implementation として再評価する path に切替。

---

## 2. 4 invariants (= 1 年触らない普遍ルール)

### Invariant 1: 統計検定は power を必須公表

**原則**: どの統計検定 (= t-test / Welch / paired / chi-square / permutation 等) を実行する script でも、事前に検出力 β を計算し、log 末尾の verdict section に明記する。

**規範**:
1. 検定実行前に effect size の想定値 + sample size + α 水準から β を計算
2. log 末尾の verdict section に「power = X.XX (= effect size Y, n=Z)」を必ず 1 行記録
3. p 値 verdict のみで「FAIL = 効果なし」と書くことを禁止。「power < 0.80 なら FAIL の解釈に幅、replication test を必須付帯条件として記録」を verdict 文の中に書く

**implementation hint**: `statsmodels.stats.power.TTestIndPower / TTestPower` を helper 化 + scripts/_stats_helper.py に集約 (= 別 task)。

**違反例 (= 本日露呈、再発防止対象)**:
- `scripts/season_brier_test.py` (= bf9cb99 commit) で Welch t-test 実行、power 事前計算なしで「primary Gate-2 (a) FAIL」を確定。effect size delta=0.003 / n=5 vs 5 で β ≈ 0.20-0.40、「FAIL = bias なし」と「FAIL = power 不足」を区別不能のまま judgment 確定。

### Invariant 2: multi-comparison は family size を必須記録

**原則**: 複数の hypothesis / bucket / 軸を扱う script は、tested family の N (= 同時検定数) を記録し、補正済 verdict (Bonferroni および BH-FDR) を併載する。

**規範**:
1. 検定対象を「family」として定義 (= 軸ごとの bucket 集合、または独立な検定群)
2. family size N を log + scorecard に必ず記録
3. naive p / z 結果と併走で、Bonferroni 補正 (α/N) + BH-FDR 補正 (q-value) を計算
4. Gate / 採否判定は **補正済 verdict を採用**、naive は参考値扱い
5. family size を後付け変更する時は scorecard §訂正履歴に「multi-comparison family 拡張」として明記

**implementation hint**: scripts/_stats_helper.py の `apply_bonferroni(p_values, family_size) → corrected_p` + `apply_bh_fdr(p_values) → q_values` helper 化。

**違反例 (= 本日露呈、再発防止対象)**:
- `scripts/q1_root_cause.py` (= bf9cb99 commit) で 8 軸 × 平均 5 buckets ≈ 40 bucket の delta z-test を実施、|z|>=2.0 (= 片側 α=0.0228) で 4 candidates 報告 → Gate-2 (c) PASS 強。Bonferroni α/40=0.00125 (|z|>=3.0) 適用すれば 0 candidates、PASS が虚偽の可能性。

### Invariant 3: 外部 tool 不可時の fresh-substitute pattern

**原則**: 「外部 tool / specific agent ID / continuation」に依存する運用は、tool 削除 / API 変更 / 環境差 で破綻する前提で書く。代替手順 (= fresh substitute) を最初から明文化する。

**規範**:
1. tool 依存の運用 (= SendMessage / continuation / persistent agent state) は handoff doc に「依存」と明示
2. 依存 tool が unavailable の時の代替経路を **同 handoff doc 内に予め記述**
3. fresh substitute は memory 喪失するので、必要 context (= 過去 verdict / 議論内容 / 規律) を **scorecard / handoff doc 自体に self-contained に埋め込む**
4. critic / verdict / 承認系の運用は「memory 共有がなくても同等品質の判断ができる」ように doc 化を優先する

**implementation hint**:
- critic SendMessage の文面を pre-write、handoff doc §2 に常時 paste-ready で保存
- fresh agent spawn 時の self-contained prompt template を skill (`.claude/skills/critic-substitute/`) として明文化

**違反例 (= 本日露呈、再発防止対象)**:
- B1 plan v1/v2 で内部 critic (= specific agent ID a6ddb18d1d9f3d9d3) を用い CONDITIONAL APPROVE 取得、B1-S0 末で SendMessage tool 不可 → 内部 critic 機構の継続が tool レベルで折れた。「v2 critic memory を活かした verdict」の取得経路が消えた状態を予見していなかった。

### Invariant 4: 訂正閾値超過時は plan 着手前に meta doc 1 件挟む

**原則**: 1 セッション内訂正数が「scorecard 本質崩壊閾値」(= 各セッション末で算出される動的閾値、参考値 13 件) を超えたとき、即時 plan v(N+1) 起こしに走らず、**まず meta-level reflection doc を 1 件挟む**。

**規範**:
1. 訂正累計 (= 本日通算 + 当 phase 増分) を session notes に毎セッション末で記録
2. 累計が「閾値」を超えた時点で、次セッション最初の作業は **plan ではなく meta doc** とする
3. meta doc は **「過去 N セッションで露呈した限界の structural diagnose + 新 invariants 提案」** に絞る、tactical fix を含めない
4. meta doc 完了後に plan v(N+1) 起こしへ進む
5. meta doc 自体の訂正累計は別カウント (= 「メタ 訂正累計」)、訂正閾値が再発しないかを観察

**implementation hint**:
- 訂正累計の算出を session notes の constant section (= §訂正履歴) で自動化
- 「閾値超過 → meta doc 1 件挟む」を CLAUDE.md ルール 1-quater 候補として記録 (= 本 doc § 4 を見よ)

**違反予防 (= 本日 B1-S0 で適用、初回 success)**:
- B1-S0 末で訂正累計 14 件 (= 閾値 13 件超過) を自己診断、plan v3 急ぎ書きを回避し本 doc (= scorecard 運用 v2) を先に書く判断。**Invariant 4 の初回適用事例**。

---

## 3. 運用ルール: invariants の implementation 順位

invariants は「principle」、これを script / scorecard / process に reflect する concrete task は別 doc / commit で扱う。

### 3.1 invariants → tactical task の対応 (= plan v3 で扱う候補)

| invariant | tactical task (plan v3 候補) | 優先度 | 工数見積 |
|---|---|---|---|
| 1 (power) | scripts/_stats_helper.py の power helper 化 + 既存 script の retro-fit | 高 | 1-2h |
| 2 (multi-comparison) | scripts/_stats_helper.py の Bonferroni + BH-FDR helper 化 + q1_root_cause.py に適用 | 高 | 1-2h |
| 3 (fresh-substitute) | `.claude/skills/critic-substitute/SKILL.md` の作成 + handoff doc template 改修 | 中 | 1-2h |
| 4 (meta doc 必須) | CLAUDE.md ルール 1-quater 追記 + session notes template 更新 | 中 | 0.5h |

**合計工数**: 3.5-6.5h、plan v3 起こしの前提 task として並列実施可能。

### 3.2 invariants 違反時の対応 protocol

各 invariant 違反を session notes / scorecard で発見したときの handling:

1. **Invariant 1 違反** (= power 未公表で検定 verdict 確定): 該当 verdict を「保留」に降格、power 計算後の verdict 再評価まで Gate 通過とみなさない
2. **Invariant 2 違反** (= multi-comparison family size 未記録): 該当 PASS / FAIL を「未補正」と tag、補正後の verdict を別途算出
3. **Invariant 3 違反** (= 外部 tool 依存の単一経路運用): handoff doc に代替経路追記、現セッション中に substitute pattern を実行
4. **Invariant 4 違反** (= 閾値超過後に plan を起こしてしまった): plan 起こし作業を中断、meta doc を遡及的に書き、plan を re-evaluate

### 3.3 新 invariant 追加 protocol

1. 新 invariant 候補は **独立 doc** として書く (= 本 doc に直接追記しない)
2. 1 年後 (= 2027-05-24 以降) に 5 件以上の invariant 違反事例が記録されていれば、新 invariant を merge / refine する判定が起動
3. **新 invariant 即時追加は禁止**、ただし「本 doc に存在する 4 invariants に矛盾する新事象」が起きた場合は §5 例外条項を適用

---

## 4. CLAUDE.md / 既存 scorecard rubric との接続

### 4.1 CLAUDE.md へのリンク

本 doc は CLAUDE.md の **「関連スキル」 section** で reference:

```
- `docs/scorecard_ops_v2.md` ← scorecard / Gate / plan の運用 invariants (= 2026-05-24 制定、2027-05-24 まで maintain free)
```

CLAUDE.md 本体への変更は **invariant 4 に対応する「ルール 1-quater」追加** のみ:

```
### 1-quater. 訂正閾値超過時の meta doc 必須挿入

1 セッション内 + 当 phase 累計の訂正数が「scorecard 本質崩壊閾値」を超えた時、
次セッション最初の作業は plan v(N+1) 起こしではなく meta-level reflection doc とする。
詳細: `docs/scorecard_ops_v2.md` invariant 4。
```

### 4.2 既存 scorecard §0 rubric との関係

既存 scorecard の §0.0 dataset 上限ルール + §0.1 統計検定 rubric (p 値範囲表) は **継承**、本 doc は §0 の **上位 (= meta) layer** として位置付け:

- §0.0 / §0.1 は「個別 verdict の判定強度」を扱う
- 本 doc invariants は「verdict 算出方法そのものの妥当性」を扱う
- 矛盾しない、相補関係

### 4.3 plan v3 起こし時の chain

plan v3 を書くときは、§0 rubric の参照に加え、**本 doc invariants も §0 で参照**:

```
### 0.4 scorecard 運用 v2 invariants の継承

`docs/scorecard_ops_v2.md` の 4 invariants を本 plan の運用前提として継承。
... (本 plan で違反が発生したら §訂正履歴で tag、修正タスクを §採用判定基準に組込)
```

---

## 5. 例外条項: 「1 年触らない」の崩し条件

本 doc は 2027-05-24 まで原則 **maintain free zone** だが、以下のいずれかの事象が発生した時のみ更新を許可:

1. **5 件以上の invariant 違反事例**が `data/scorecards/` に記録された
2. **4 invariants と矛盾する structural 事象**が 2 件以上発生 (= 例: invariants 全部遵守したのに同等の事故が再発)
3. **CLAUDE.md ルール 1-quater 自体の運用が破綻**した (= meta doc 挟む rule が機能不全)
4. ユーザによる**明示的更新指示** (= 著者 1 名運用なので、ユーザ判断で例外発動可能)

更新する場合も「invariant 削除」は最低限、「新 invariant 追加」は新 doc (= scorecard 運用 v3) として独立させる方向で。

---

## Appendix: 今日 (2026-05-23/24) 露呈した 4 限界の事例詳細

詳細は以下の scorecard で確認可能 (= 本 doc の motivating evidence):
- `data/scorecards/20260524_0530_p18_h2_results_v4.md` (= H2 v4、§4 メタ事故 3 件 + 訂正 2 件 / scope creep 1)
- `data/scorecards/20260524_0700_p19_b1_plan_v1.md` (= plan v1、self-aware 列挙 8 件)
- `data/scorecards/20260524_0900_p19_b1_plan_v2.md` (= plan v2、critic 必須 2 + 推奨 2 反映、§8.5 self-aware 防御線批判)
- `data/scorecards/20260524_1315_p19_b1s0_results.md` (= B1-S0 結果、Gate-2 ALL FAIL、事故 4「Gate-2 (a) 予想外し = framing 過剰一般化」)
- `data/scorecards/20260524_1400_p19_b1s0__expert_review.md` (= 7 専門家平均 3.87、code-quality -1.1 + validation-process -0.75 の大幅後退)

各 scorecard の §訂正履歴 + §メタ事故 section を invariants 1-4 の動機として参照可能。

---

## 自己評価

本 doc を 1 年触らないことの賭けポイント:

- **賭け 1**: 4 invariants が「正しい principle」であり、12 ヶ月以上の事故予防に効く。Phase B1 のように 2-3 ヶ月単位の長期 phase で initial bias を上書きする evidence が複数積まれた時に、invariants が rigid すぎて妨げにならないこと
- **賭け 2**: 「1 年触らない」自体が **invariants の安定性 demonstration**。短期で更新が必要になった = invariants の選定ミス、と読み替える self-correction 機構
- **賭け 3**: 訂正累計 14 件超過の状態で書いた本 doc 自体に、structural な誤りが含まれていない (= 本日 framing 過剰一般化を起こした著者が、meta 層でも同じ過誤を犯している可能性は否定できない)

これらの賭けは Phase B2 / B3 セッション群 (= 2026 後半 〜 2027 春) で検証される。本 doc も次回再読時に「やはり何かが混入していた」と訂正される前提で書かれている。
