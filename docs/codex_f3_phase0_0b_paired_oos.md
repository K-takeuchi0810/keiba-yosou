# Codex 作業指示: F3 Phase 0-0b — paired control/treatment OOS ROI(review #1 closer・測定のみ)

## 0. これは何か / なぜやるか

Phase 0-0 は **val AUC を paired で**出した(公開v6 0.79141 / M1=0埋め 0.78944 / M2-control 0.79132 /
M2-treatment 0.78878、control−treatment=+0.00254、top-1 差 0)。しかし **OOS ROI は
M2-treatment のみ**(62.09%、425 bets、65 hits、日block 95%CI [48.97%, 76.28%])で、旧 70.70% とは
母集団・rules SHA が違う**非paired**のため「3チャネルの ROI 寄与」を分離できていない。

**目的**: 同一 OOS 窓・同一ベット選択規則・**同一の日block bootstrap 標本**で M2-control と
M2-treatment の ROI を出し、**paired 差分 (control − treatment) の CI** を求めて、発走後リーク3チャネルの
**ROI 寄与を同一レース上で確定**する。これで correctness 章を完全に閉じる。**production は不変、封印は不可触。**

## 1. 事前登録ガードレール(0-0 と同一・最上位・逸脱禁止)

> **Phase 0-0/0-0b の結果で変更してよいのは「ベースライン数値の更新」と「遮断 allowlist の確定」のみ。
> 特徴の追加・削除・再選択、閾値、期間、判定基準、ベット選択規則は結果を理由に変更しない。
> 封印ホールドアウト(2026-10-01 以降)には一切触れない。**

- 遮断対象は 0-0 と同一の **3 チャネル固定**(`same_day_bias_score` / `leg_quality_available` /
  `same_day_bias_available`)。増減しない。
- OOS 窓は 0-0 と同一(`20260101`–`20260614`、封印前・消費済み)。動かさない。
- ベット選択規則・EV/Kelly 定義・鮮度条件は 0-0 の OOS ハーネスと**バイト等価**にする(下記 §3)。

## 2. 全体ルール(前サイクル踏襲)

- 着手前 `git status --short`。tracked 未コミットがあれば停止報告(untracked のみなら続行)。
  `git checkout -b codex/f3-phase0-0b main`。**push しない**。作業後 `git checkout main` へ戻す。
- **触らない**: `C:\Users\kizun\dev\傾向収集\` / `.claude/skills/html-ui-ux-review/` /
  branch `codex/output-defects`・`codex/scheduler-repair`・`codex/f3-phase0-0` / 封印(2026-10-01 以降)。
- **production artifact 読み取り専用**(`predictor/lgbm_model.txt` 他4点)。生成物は `data/f3_phase0_0/` 配下のみ。
- `.venv64`。Discord 送信禁止。DB read-only。重い再学習が要る場合のみ CLAUDE.md ルール 1-ter を満たしてから。

## 3. 方法(paired・同一ハーネス)

### 3-1. モデルの用意(0-0 と同一構成であることを先に証明)
- 0-0 で保存した M2-control / M2-treatment を **`data/f3_phase0_0/` から再利用**。無ければ
  `scripts/f3_phase0_0_eval.py` の学習経路で seed=20260720・同 split・同ハイパラで**再学習**。
- **決定性チェック(先に実施)**: 用意した control/treatment が 0-0 の val AUC
  **0.79132 / 0.78878 を ±1e-5 で再現**することを確認してから OOS へ進む。再現しなければ停止して報告
  (構成不一致のまま OOS を回さない)。

### 3-2. OOS 評価(既存ハーネスをバイト等価で流用)
- `scripts/f3_phase0_0_eval.py` の **OOS + bootstrap 関数を再利用**(新ハーネスを書き起こさない)。
  M2-treatment を通したのと**同一コードパス・同一窓・同一ベット選択規則**に M2-control を通す。
- 各モデルについて `n_bets / n_hits / roi(点推定)` を出す。treatment は 0-0 の 425/65/62.09% を
  **再現するはず**(しなければ停止報告)。

### 3-3. paired 差分 bootstrap(ここが本題)
- **同一の日block 標本を両モデルで共有**する paired bootstrap: 反復ごとに日(開催日)block を
  1 セット resample し、その**同じ標本上で** control_roi と treatment_roi を計算 → 差分
  `d = control_roi − treatment_roi` を記録。BOOTSTRAP_SEED=20260720、反復数は 0-0 と同一。
- 出力: `control_roi` / `treatment_roi` の各点推定と CI に加え、**差分 `d` の点推定と 95%CI**。
- ベット集合の basis を **2 通り**出す(選択規則は変えない):
  - **(a) 各モデル自己選択**: それぞれの投資確率でベット選択規則を適用した現実的比較。
  - **(b) 共通レース basis**: treatment がベットした同一レース上で control の払戻を評価(逆も)。
    選択差でなく**モデル差のみ**に起因する paired 差分を見る。

### 3-4. 事前コミット判定(数値を見る前にここで固定)
- **paired 差分 `d` の 95%CI が 0 を含むなら「3 POST-HIGH チャネルは ROI に有意寄与しない」と結論し、
  correctness 章を閉じる。** 含まないなら寄与量と符号を記録(ただし遮断対象は増減しない=ガードレール)。
- val で top-1 差 0・AUC 差 0.0025 のため、**`d`≈0 が予想**されるが、予想で判定を書き換えない。

## 4. 生成物

- `data/f3_phase0_0/paired_oos.json`: 両モデルの `{n_bets,n_hits,roi,ci}`、paired 差分 `d` の点推定+95%CI、
  basis (a)/(b) 別、bootstrap 設定(seed/block=day/反復数)、決定性チェック結果。
- `docs/F3_phase0_0b_result.md`: 数値 + §3-4 の結論。加えて **T-10 正本へ転記するための "確定ベースライン" ブロック案**
  を明記(control ROI / treatment ROI / 差分CI / de-leaked baseline = M2-treatment)。
  **`F3_MARKET_RESIDUAL_DESIGN.md` は編集しない**(Claude がレビュー後に転記する)。

## 5. やらないこと(再掲)

- production 挙動・artifact・calibrator を変えない。遮断対象・窓・選択規則・判定基準を結果で変えない。
- 封印に触れない。push しない。新しい OOS ハーネスを書き起こさない(既存流用で methodology 同一を担保)。
- `F3_MARKET_RESIDUAL_DESIGN.md` / 私の v1.0-draft を編集しない。

## 6. 最終報告(12 行以内)

1. 決定性チェック: control/treatment が val AUC 0.79132 / 0.78878 を再現したか
2. treatment OOS が 425/65/62.09% を再現したか
3. control OOS: n_bets / n_hits / roi
4. paired 差分 `d` の点推定 + 95%CI(basis (a)/(b) 両方)
5. §3-4 事前コミット判定の結論(CI が 0 を含むか → 章を閉じるか)
6. production 無変更 / 封印無アクセス / 傾向収集・skill・他branch 無変更 / checkout=main / push なし

---

## (Claude Code 側メモ — Codex には渡さない)

- 受領後の Claude 検証: (a) bootstrap が**真に paired**(反復ごとに同一 day-block 標本を両モデルで共有)か
  実コードで確認、(b) OOS 窓・選択規則が 0-0 とバイト等価か、(c) 決定性チェックの AUC 再現、(d) 封印非接触。
- その後 Claude が **`F3_MARKET_RESIDUAL_DESIGN.md`(T-10 正本)へ確定ベースラインを追記** +
  構造4点(フィールド分割 / log(q)係数1固定offset / CLV前段ゲート / fail-closed)と
  `expected_value_net` 凍結の追補差分を起こす。私の v1.0-draft は superseded 指定で畳む。
- expert-review は 0-0 + 0-0b の**完成パッケージに一度だけ**、validation-process-auditor 中心
  (+ data-pipeline / prediction-logic)で。Codex 自作 scorecard は D1 無効なので別途正規で回す。
- これで correctness 章クローズ。次は本命の **Phase 1(市場残差 offset モデルの構築と 7 モデル比較)**。
