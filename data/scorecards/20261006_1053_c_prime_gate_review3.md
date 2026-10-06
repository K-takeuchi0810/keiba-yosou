# 2026-10-06 10:53 — C′ の前の最終ゲート (3 名レビュー、マージの前)

- 対象: worktree `c-prime-gate`、レビュー SHA 5d0fec5 (base main f3d4870)。**subagent CWD 限定運用での評価** (全員 `git -C <worktree>`)
- 内容: 市場の列の単一の出典 (`race_market.market_feature` = log、fail-closed)、C′ の尤度・Fisher・購入の件数・診断の部品 (`predictor/market_clogit.py`)、
  事前登録 §8-6b の追補 (外部の指示者の承認と最終ゲートの指示)
- 確率モデルの定義を変えるので prediction-logic を入れた 3 名。ai_builder_impact: none (db.py・jvlink_client・取り込み・schema は差分なし)

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| validation-process-auditor | PASS | 4.1 | main に載せた SHA を改訂 SHA として台帳の冒頭に書いてから最初の C′ のクエリを打つ |
| prediction-logic-analyst | CONDITIONAL | 4.2 | §8-8 の件数の数え方を ratio_buys_at に (「S ≥ 2」の目安の撤回) / C′ の S の標準化の単位を台帳の前に事前登録 |
| code-quality-reviewer | CONDITIONAL | 3.6 | 非有限の係数・不収束の当てはめが「購入 0 件」に化ける経路を止める |

平均 3.97。prediction-logic は Fisher 情報を数値 Hessian と突き合わせて一致 (最大相対差 3.3e-7)、恒等性の誤差 5.6e-17 を確認。

## 反映 (9476a26 → 1b0cd79 → 1e08eaf → af91f82)

- must-fix: 非有限の係数と不収束を MarketClogitError に / §8-8 の件数は `ratio_buys_at(rows, 1.0, β_target)`、「S ≥ 2」の目安を撤回 (Group A の 97 頭は記録として残す) /
  C′ の S の標準化の単位を **提案** として事前登録 (学習期でプールしたレース内の SD。外部の指示者の確認まで台帳を開かない) / 台帳の冒頭の SHA は C′ の台帳で書く
- should-fix: 馬番の重複・Group A の logit の列・空の行を拒否、特異な情報行列を MarketClogitError に、入力の行を変えない、numpy の実数を受ける、例外の文は ASCII、
  β_market = 1 に制約した β_S の当てはめ (診断の 4 組目)、テストの生成器を検査対象から独立、Jaccard 3 組・許容幅の境界・一部の行の勝ちの列・収束の印のテスト、
  §8-6b に log の列の不変性・P_market を丸めない・C′ の runner の前提条件 (金額は fit の組をそのまま、T−10 の β を受け取らない、group_a を import しない、錠は blob で照合)
- 変異 r8 (1e08eaf): 25 / 25 KILLED (途中で G16・G25 の生存をテストの強化で殺した。ABORT 4 回は本番の書き手の検出)。eval_refund 39 / 39
- 全テスト (worktree、改行の都合の 1 本を除く): 1370 passed

## 持ち越し

- validation should-fix: 不変性テスト (1) の代わりに、build_choice_set の控除率付きの implied の経路で β・SE の一致を見る形 (runner の配線の時)
- code-quality should-fix: C′ のスクリプトのソースに math.log / group_a の import が無いことの静的なテスト (runner を作った時、§8-6b に前提条件として記載済み)
- 前回 (eval_refund) の持ち越し 4 件は C′ の中で扱う
