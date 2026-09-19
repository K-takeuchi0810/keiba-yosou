# Codex 作業指示: F3 Phase 0-0 — 発走後リークの定量化(測定のみ・完走型)

## 0. これは何か / なぜ最優先か

2026-07-20 の整合レビュー(`docs/F3_design_review_report.md`)で、現行 LGBM v6 の一部特徴が
**当該レースの発走後にしか確定しない値(脚質 `leg_quality_code`)を参照している**ことが判明した
(Claude が `predictor/features.py:401,437` で独立確認済み)。過去 replay(train/val/backtest)では
この値が埋まって効くが、**live 予測時は NULL** で、v5 が live で AUC 0.579≒ランダムに崩れたのと
同一機構(リーク + train-serve skew)。

**目的**: この 3 チャネルを遮断したとき v6 の性能がどれだけ落ちるかを **train/val だけで定量化**し、
F3 が超えるべき「真のベースライン」を確定する。**production は一切変更しない**(観察専用のまま)。
封印ホールドアウト(2026-10-01 以降)には**触れない**。

## 1. 事前登録ガードレール(この指示の最上位ルール・逸脱禁止)

> **Phase 0-0 の結果で変更してよいのは「ベースライン数値の更新」と「遮断 allowlist の確定」のみ。
> 特徴の追加・削除・再選択、閾値、期間、判定基準は 0-0 の結果を理由に変更しない。
> 封印ホールドアウト(2026-10-01 以降)には一切触れない。**

- 遮断対象は**下記 §3 の 3 チャネルに固定**。0-0 の途中で「他にも怪しい特徴がある」と気づいても
  **遮断対象を増やさない**(気づきは最終報告に列挙するだけ。追加遮断は F3 設計側の決定事項)。
- mining(G-MIN 6件)や PIT-UNPROVEN(gate bias / draw / going 等)は **0-0 の対象外**。これらは
  「発走後確定」ではなく「取得時刻未証明」で別軸。触らない。

## 2. 全体ルール(前サイクル踏襲)

- 着手前に `git status --short`。**tracked に未コミット変更があれば停止して報告**(untracked のみなら続行可)。
  `git checkout -b codex/f3-phase0-0 main`。**push しない**。作業後 `git checkout main` へ戻す。
- **触ってはいけない**: `C:\Users\kizun\dev\傾向収集\` 配下 / `.claude/skills/html-ui-ux-review/` /
  branch `codex/output-defects`・`codex/scheduler-repair` / **封印ホールドアウト(2026-10-01 以降のデータ)**。
- **production artifact を上書きしない**: `predictor/lgbm_model.txt` / `predictor/lgbm_features.json` /
  `predictor/lgbm_meta.json` / `predictor/calibrator.json` は**読み取り専用**。0-0 が作る実験モデル・
  指標は**すべて `data/f3_phase0_0/` 配下の新規ファイル**に書く。production は v6 のまま。
- LGBM 学習・推論は `.venv64`(lightgbm 必須)。重い再学習(§4 の M2)は既定で 30 分未満想定だが、
  30 分超なら CLAUDE.md ルール 1-ter の pre-flight 3 項目を満たしてから bg 起動。
- Discord 実送信禁止。DB(`data/keiba.db`)の中身を書き換えない(読むだけ)。

## 3. 遮断対象 = 発走後リーク 3 チャネル(POST-HIGH、固定)

| # | feature_id | リーク根拠 |
|---:|---|---|
| 48 | `same_day_bias_score` | `same_day_track_bias_detail` が当該レースの `horse.leg_quality_code`(発走後確定)を照合キーに使う(`features.py:401,437`) |
| 102 | `leg_quality_available` | 当該レース `leg_quality_code` の有無そのもの = 「これは replay(発走後)行か」を識別する signal(`features.py:1031-1039`) |
| 103 | `same_day_bias_available` | 当該 leg の有無 + 先行レース結果可用性に依存 |

**live 相当値(= 0埋めに使う値)**: `same_day_bias_score=0`、`leg_quality_available=0(False)`、
`same_day_bias_available=0(False)`。これは live で leg が NULL のとき各関数が返す既定値と一致させること
(勝手に別の欠損値を使わない。`features.py` の該当関数の NULL 時 return を確認して合わせる)。

## 4. 測定(同一 train/val 分割・同一ハイパラ・同一 seed)

比較条件は **特徴集合以外すべて固定**: `scripts/train_lgbm.py` の既存 split ロジック・
`lgbm_meta.json` 記録のハイパラ(learning_rate 0.0160…, num_leaves 16, min_data_in_leaf 440, …,
best_iteration 781)・**固定 seed**(train_lgbm に seed 指定が無ければ全再学習で同一の固定値を明示注入)。
val は既存 v6 と同一スライス。

以下 4 モデルの val 指標を出す:

- **M0 = 公開 v6(現行 artifact そのまま・再学習なし)**: 参照値。
- **M1 = 0埋め再推論(再学習なし)**: M0 の model に、val 入力の 3 チャネルを §3 の live 相当値へ
  置換して再推論。→ **live の train-serve skew に対応**(公開v6 − M1 = skew の大きさ)。
- **M2-control = 全特徴・同 seed 再学習**: 交絡(seed/再学習ノイズ)分離用の control。
- **M2-treatment = 3チャネル遮断・同 seed 再学習**: feature 集合から 3 個を除いて再学習。
  → **F3 の真のベースライン**(M2-control − M2-treatment = 再学習後に残る純リーク寄与)。

指標は val の **AUC / Brier / LogLoss** を全モデルで。加えて **race 単位 top-1 的中率**(argmax が
1着か)も出す。差分表(公開v6−M1、M2-control−M2-treatment)を明示。

### 4-bis. 二次測定(必須・ただし封印には触れない)

M2-treatment を、**過去に "clean OOS 70.7%" を出したのと同一の pre-2026-07 OOS 窓**(封印前・消費済み)に
通し、buy_only 回収率と **CI(レース or 開催日単位の block bootstrap)** を出す。窓は**その既存窓に固定**し、
期間を動かさない(これは「ベースライン数値の更新」であって期間変更ではない)。**2026-10-01 以降の封印には
一切アクセスしない**。目的は「70.7% がリーク除去後に生き残るか」の一点。

## 5. 生成物

- `data/f3_phase0_0/metrics.json`: M0/M1/M2-control/M2-treatment の val 指標 + 差分 + §4-bis の ROI/CI。
- `data/f3_phase0_0/`: 実験モデル(`*.txt`)と使用 feature リスト。**production artifact とは別ファイル**。
- `data/f3_phase0_0/blocked_allowlist.json`: 遮断 3 チャネルの feature_id を**事前登録記録**として固定
  (「遮断 allowlist の確定」= ガードレールが唯一許す設計確定物)。root 直下や production には置かない。
- `docs/F3_phase0_0_result.md`: 結果と解釈(下記の分解を明記):
  - live skew = 公開v6 − M1(この分は live で実際に失われている見かけの性能)
  - 純リーク寄与 = M2-control − M2-treatment(F3 が超えるべき baseline は M2-treatment)
  - §4-bis の 70.7% が M2-treatment でどうなったか(CI 込み)
  - 一文の結論:「v6 の見かけ性能のうち発走後リーク由来は約 X。真のベースラインは AUC≈… / OOS≈…(CI…)」

## 6. やらないこと(再掲・重要)

- production の予想挙動・artifact・calibrator を変えない。
- 遮断対象を 3 個から増減しない。閾値・期間・判定基準・特徴選択を 0-0 結果で変えない。
- 封印ホールドアウトに触れない。Discord 送信しない。push しない。

## 7. 最終報告(15 行以内)

1. 4 モデルの val AUC/Brier/LogLoss/top1 と 2 つの差分
2. §4-bis の pre-2026-07 OOS 回収率 + block bootstrap CI(M2-treatment)
3. live skew と純リーク寄与の数値分解、一文結論
4. 使用した split/seed/hyperparams が v6 と同一である確認
5. production artifact 無変更 / 封印無アクセス / 傾向収集・skill 無変更 / checkout=main / push なしの確認
6. 気づいた追加リーク候補があれば「対象外・列挙のみ」として記載(遮断はしない)

---

## (Claude Code 側メモ — Codex には渡さない)

- 0-0 は測定主体。production predictor/scripts を変更しない設計なので、変更が `data/` + `docs/` +
  実験スクリプト(新規 `scripts/f3_phase0_0_eval.py` 等)に留まるなら expert-review は
  validation-process-auditor / data-pipeline-engineer / prediction-logic-analyst の**該当3名**に絞る
  (bat 変更時と同様、対象ドメイン外は N/A)。もし features.py / lgbm_features.json 本体に手が入っていたら
  scope 逸脱 → 差し戻し。
- 受領後の Claude 検証: (a) live 相当値が features.py の NULL 時 return と一致するか、(b) M2 の split/seed が
  本当に v6 と同一か(交絡除去の要)、(c) §4-bis が封印窓に触れていないか、を実コードで確認。
- 数値が出たら **既存 T-10 正本ドキュメント(`F3_MARKET_RESIDUAL_DESIGN.md`)へ「真のベースライン」を
  追記** + 構造4点(フィールド分割 / log(q)係数1固定offset / CLV前段ゲート / fail-closed)の追補差分を起こす。
  私の v1.0-draft の T-15/判定日は superseded 指定で畳む。
- `expected_value` は net(`p*odds-1`)へ、フィールド名 `expected_value_net` 込みで F3 追補に凍結。
