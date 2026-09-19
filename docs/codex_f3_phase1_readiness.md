# Codex 作業指示: F3 Phase 1 readiness — dev 窓ドリフトデータ棚卸し(測定のみ・完走型)

## 0. これは何か / なぜやるか

F3 の残差特徴 x_i(§4.2 で凍結: ドリフト = log(q_early / q_T10)、rank divergence、overround 変化 等の
**市場マイクロ構造量。変化量・相対量のみ、T-10 水準の単調関数は禁止=条件A**)を計算するには、
1 レースにつき **時刻の異なる 2 点以上の PIT スナップ**(早い基準点 + T-10 直前点)が要る。

しかし正本 `docs/F3_MARKET_RESIDUAL_DESIGN.md` §0/§1-6 は「朝の基準オッズを収集していない」と記載、
朝アンカー収集タスク(`keiba-morning-odds`)は ⏳ 未実装(定期タスク監査でも該当タスク不在)。

**目的**: dev 窓(2026-07-04 〜 直近)で「ドリフトが計算可能なレースがどれだけあるか」を、PIT ゲート
実体(`predictor/pit_gate.py`)で測る。**Phase 1 のモデル構築に着手できる母集団があるか**、および
**朝アンカータスクが本当に必要か**(既存 09:00-16:40 cadence で午後レースは十分な早い点が貯まっている
可能性)を数値で判断する。**モデルは作らない。production 不変。封印非接触。**

## 1. ガードレール(最上位・逸脱禁止)

- **測定のみ**。モデル学習・特徴実装・production 変更を**しない**。既存の凍結決定(D1 T-10 / D2 /
  §4)を**変更しない**(これは readiness 測定であって設計変更ではない)。
- **封印非接触**: 対象は dev 窓 `20260704`–(直近営業日)。`to_date < 20261001` を**コードでガード**し、
  封印(2026-10-01 以降)には SQL でも触れない。
- 着手前 `git status --short`。tracked 未コミットがあれば停止報告(untracked のみ続行)。
  `git checkout -b codex/f3-phase1-readiness main`。**push しない**。作業後 `git checkout main` へ戻す。
- **触らない**: `C:\Users\kizun\dev\傾向収集\` / `.claude/skills/html-ui-ux-review/` /
  branch `codex/output-defects`・`codex/scheduler-repair`・`codex/f3-phase0-0`・`codex/f3-phase0-0b`・
  `codex/f3-t10-rev11`。DB(`data/keiba.db`)は **read-only**。Discord 送信禁止。ASCII スクリプトのみ。

## 2. 方法

### 2-1. PIT ゲート実体を流用(再実装しない)
- スナップの可用性判定は **`predictor/pit_gate.py` の `usable_snapshots` / `pit_cutoff`** を唯一の入口として
  使う(`config.PIT_GATE_MINUTES=10`=T-10、`fetched_at IS NOT NULL`、`fetched_at ≤ 発走−10分`)。
  独自 SQL でゲートを書き直さない(実運用ゲートと乖離させない)。

### 2-2. dev 窓の全レースを走査し、レース単位で以下を集計
各レース(dev 窓・出馬表あり)について `usable_snapshots` を取り、**発走時刻からの lead 分**
(= 発走 − fetched_at、分)に変換して:

- `n_usable`: T-10 ゲートを通る PIT スナップ枚数。
- `earliest_lead_min`: 最も早いスナップの lead(分)。無ければ null。
- `latest_lead_min`: 最も遅い(T-10 に最も近い)スナップの lead。
- `drift_computable`: `n_usable ≥ 2` かつ **異なる時刻**の 2 点がある(= 変化量が作れる)か。
- `wide_drift`: `earliest_lead_min ≥ 60` かつ T-10 近傍点あり(= 朝〜直前の広いドリフト窓)か。
- レース発走時刻帯(午前/午後)も記録(朝アンカーの要否が post time に依存するため)。

### 2-3. 集計(日別 + 全体)
- dev 窓の総レース数 / 出馬表あり数。
- `n_usable ≥ 1` 率、`drift_computable`(≥2点)率、`wide_drift` 率。
- `earliest_lead_min` の分布(中央値・分位)。**午前レース vs 午後レース**で層別
  (午後は既存 09:00 cadence で早い点が貯まりやすい仮説の検証)。
- **日別トレンド**: 2026-07-04 から直近まで、drift_computable 率が改善しているか(収集系の稼働で
  貯まっているか)。

## 3. 判断(数値を出すだけ・設計は変えない)

結果 doc に以下を**事実として**書く(閾値の新設や設計変更はしない):
- ドリフト計算可能な dev レース数と率。**Phase 1 の 7モデル比較に足る母集団があるか**の目安
  (例: drift_computable が数百レース規模あるか、二桁しかないか)。
- **朝アンカータスクの要否**: `wide_drift` 率が低い/午前レースで earliest_lead が短いなら
  `keiba-morning-odds`(§1-6 の広窓 09:30 タスク)が必要、という**材料**を提示(タスク登録自体はしない)。
- 収集開始日以降のトレンドから「今後 N 週でどれだけ貯まるか」の粗い外挿(参考値、判定には使わない)。

## 4. 生成物

- `data/f3_phase1_readiness/dev_odds_coverage.json`: レース単位テーブル(集計値)+ 日別 + 全体サマリ +
  使用した gate 設定(PIT_GATE_MINUTES, 窓, 生成時刻, git_sha)。
- `docs/F3_phase1_readiness.md`: 上記 §3 の判断材料。**設計文書 `F3_MARKET_RESIDUAL_DESIGN.md` は編集しない**
  (Claude がレビュー後に §4/§1-6 へ反映)。
- 監査スクリプト: `scripts/f3_phase1_readiness.py`(新規、ASCII、read-only、封印ガード付き)。

## 5. やらないこと(再掲)

- モデル学習・特徴実装・production/artifact/calibrator 変更をしない。
- 封印に触れない(`to_date < 20261001` ガード)。DB を書き換えない。push しない。
- 凍結決定(D1/D2/§4)・閾値・選択規則を変えない。設計文書を編集しない。
- 朝アンカータスクの登録(schtasks/Register-ScheduledTask)は**しない**(要否の材料提示まで)。

## 6. 最終報告(12 行以内)

1. dev 窓の総レース / 出馬表あり / drift_computable(≥2点)数と率
2. earliest_lead_min の中央値、午前 vs 午後 層別
3. wide_drift 率、日別トレンド(改善しているか)
4. 朝アンカータスク要否の材料(1-2 行、判断は保留)
5. Phase 1 の 7モデル比較に足る母集団があるかの所見(事実ベース)
6. 封印非接触 / DB read-only / production 無変更 / 傾向収集・skill・他branch 無変更 / checkout=main / push なし

---

## (Claude Code 側メモ — Codex には渡さない)

- 測定のみ・production 無変更なので、受領後の検証は Claude 自身で: (a) `usable_snapshots` を実際に
  経由しているか(独自ゲート再実装でないか)、(b) 封印ガード `to_date < 20261001` の実効、(c) lead 分計算が
  発走時刻(start_time)基準で正しいか、(d) drift_computable の定義が「異なる時刻の2点」になっているか。
- 数値次第の分岐:
  - drift_computable が十分 → 7モデル spec を §4.2 軸(市場オフセット ± ドリフト x_i、mining 除外 ablation)で
    凍結する Phase 1 kickoff 指示書へ。**私の旧7モデルスケッチ(G-OWN 軸)は §4.2 と矛盾するので破棄**。
  - 不十分/朝アンカー要 → 先に `keiba-morning-odds` 登録(register スクリプト、要ユーザ承認)+ 蓄積待ち。
- Codex 自作 scorecard は D1 無効。ただし本件は測定のみ・production 無変更のため、full expert-review は
  Phase 1(モデル構築=production 隣接)着手時に回す。本 readiness は Claude 検証で足りると判断。
- 結果を F3_MARKET_RESIDUAL_DESIGN.md §1-6(朝アンカー ⏳)/§4 へ反映するのは Claude(design-freeze の human-in-loop)。
