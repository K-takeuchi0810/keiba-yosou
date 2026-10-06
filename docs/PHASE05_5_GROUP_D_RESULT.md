# Phase 0.5-5 Group D — 主検定を実行しない (構造的な非識別) (2026-10-06)

**状態: `BLOCKED_BY_IDENTIFIABILITY` / `PRIMARY_NOT_RUN`**。FAIL でも INCONCLUSIVE でもない (主検定を実行していない)。2025 の結果は読んでいない。
外部の指示者の決定 (2026-10-06)。

## 1. 停止の理由 (構造の量だけ。係数の値・符号は使わない)

Group D の主検定は、2025 の結果を読む前に、事前登録 §8-4d の主検定の量 (β_S) が §2 D で意図した仕組みを識別しないと分かったので実行しなかった。

> The Group D primary was not run because, before any 2025 outcome access, the registered §8-4d primary estimand was found not to identify the
> intended §2 D mechanism. Within races, the registered S was highly correlated with the previous-performance rating (r = 0.939) and 92.9% of its
> within-race linear variation was explained by the previous-performance rating plus `class_move`. Therefore the registered β_S primarily tests
> residual previous-performance information after conditioning on `class_move`, rather than whether performance interacts with class movement
> as intended by §2 D.

- レース内では `class_move = level(今回) − level(前走)` ≡ `−level(前走) + レースの定数`。要求水準は大部分が前走のクラスの関数なので、その部分は
  局外の `class_move` の列に吸収される (§8-4d が「今回のクラスの要求水準を引く案」を退けたのと同種の代数的な吸収が、前走のクラスの案にも大部分起きる)
- 構造の量 (学習期 2022-2024、`data/backtest/group_d_20261006/structural/`):
  - レース内の相関 S_std ↔ 前走の評価値 = **0.939**
  - S_std を [前走の評価値, `class_move`] でレース内に線形回帰したときの決定係数 = **0.929** (レース内の線形な変動の 92.9% が説明される。
    前走の評価値だけでは 0.882)
  - `class_move = 0` の行 **89%** (停止の理由そのものではないが、昇降の効果や交互作用を識別する実効の標本が小さいことの構造の診断)
- 前走の評価値は Group A の `last` 成分と同じ関数 (Group A の 1 走の評価値、対象日の 365 日前から前日までの最新の 1 走)。登録した S は、
  **Group A の last 成分が使う前走の評価値を、おおむね線形に表し直した量** である
- 「D に効果が無い」とは書かない。検定していない

## 2. 交互作用 (登録していない。診断だけ)

> Interaction formulations that more directly represent the §2 D mechanism were not preregistered. Their estimated power is
> specification-dependent: S × 1[upgrade] gives an approximate MDE of 0.29, while S × class_move gives approximately 0.11.
> These figures are diagnostic only and neither formulation will be promoted to a primary test within the current family.

- S × 1[昇級] (昇級の行 約 9.5%): 学習期 pooled の SE 0.049 → 主検定の年のレース数 (2024 の 3,019 で代用) に換算 0.086 → MDE ≈ 0.29
- S × `class_move` (整数 −4〜+4): SE 0.018 → 換算 0.031 → MDE ≈ 0.107 (大きな昇降の行が SE を下げる)
- 係数の値は計算の記録にも残していない (停止の理由に使わないため)。「§2 D の仮説は検出不能」とは結論しない (取り方で検出力が大きく変わる)
- 当初の報告で「交互作用は MDE ≈ 0.3 で検出不能」と書いたのは 0/1 の取り方だけの値で、撤回する

## 3. E1 / E2 (停止の判定から分離)

E1 / E2 の係数は **observed before the structural stop decision but not used as a stopping criterion**。成果物はそのまま残す
(登録した構成が意図した概念を識別していないことを見つけた開発の証拠)。

| 段 | β_S (z) |
|---|---|
| E1 2022 → 2023 | +0.0181 (+0.66) |
| E1 2023 → 2022 | −0.0549 (−1.93) |
| E2 2022-2023 → 2024 | −0.0212 (−0.76) |

この判断は E1 / E2 を見た後に行った (開示する)。停止の理由には E1 / E2 の β・z・符号・予想される区分を使っていない。

## 4. 族と 2025

- 2025 は Group A と C′ の 2 回の消費のまま (D で 3 回目を消費しない)。`config.CONSUMED_WINDOWS` は変えない
- 族の現状: A `PRIMARY_INCONCLUSIVE` / B `BLOCKED` / C′ `PRIMARY_FAIL` / **D `BLOCKED_BY_IDENTIFIABILITY` / `PRIMARY_NOT_RUN`** /
  E `BLOCKED_BY_PIT_AVAILABILITY` / PASS 0
- 将来の D′: 今回分かった構造を踏まえ、最初から `市場 + class_move + 前走の評価値の主効果 + class_move × 評価値` のように、「同じ昇級の幅で
  内容の差が効く」交互作用を主検定の量として登録する必要がある。十分な新しい標本を確保できる将来の候補として扱う (2025 では試さない)

## 5. 記録の場所

- PIT の確認: `data/backtest/group_d_pit_20261006/` (`626084c`)
- 仕様: `docs/PHASE05_5_PREREG.md` §8-4d (`31a7dfc`)
- 台帳: `docs/PHASE05_5_EXPLORATION.md` の Group D の節 (D-0〜D-3、E1、E2、構造的な停止)
- 実装・テスト・変異: `scripts/group_d.py` / `group_d_explore.py` / `group_d_run.py` / `prereg_runner.py`、`tests/test_group_d*.py`、
  `data/backtest/group_d_20261006/mutation/` (36 / 36)。凍結・検出力・錠・主検定は実行していない
- 構造の確認: `data/backtest/group_d_20261006/structural/` (`structural_check.py` → `structural_check.json`、学習期だけ)
