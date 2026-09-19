# Codex 作業指示: F3 Phase 0 — fail-closed (§4.4) の実装 (完走型)

## 0. 目的と、なぜ今か

正本 `docs/F3_MARKET_RESIDUAL_DESIGN.md` §4.4 の実装。**現行は LightGBM 不在・特徴計算失敗時に
黙って rule-only へ縮退**し、backtest と別物の予想を無警告で出す (`predictor/rules.py:1395-1408` の
`except Exception → logger.warning → blended = raw_rule_prob`、`predictor/ml_model.py:45-65` の
`load_lgbm() → None`)。これは**本番で既に起こりうると分かっている失敗**であり、放置期間 = リスク期間。
drift 蓄積とは独立に着手できる。

**このセッションで潰してきた「静かな失敗」クラスの最後の大物**
(`fetch_full --since-last` / PowerShell ExitCode-null / coverage 混入誤検知 と同型)。

## 1. ガードレール (最上位・逸脱禁止)

- **凍結決定 (D1 T-10 / D2 封印 / §4.0-4.6) を変更しない**。封印 (2026-10-01 以降) に触れない。
- **★凍結ベースラインの再現性を壊さない (最重要)**: `scripts/f3_phase0_0_eval.py` が出す
  val AUC **0.7913195088860858 / 0.7887806982333265** と OOS **425 bets / 62.0941%** は §4.0 の凍結値。
  本改修後も**同一値を再現**すること (受入ゲート G4)。再現しない実装は差し戻し。
- **backtest / 分析スクリプトの挙動を変えない**: `scripts/backtest.py:815`、`f3_phase0_0_eval.py`、
  `analyze_*.py` 等は歴史データを意図的に評価する経路。ここで fail-closed を発火させない (§3-1 の層分離)。
- 着手前 `git status --short`。tracked 未コミットは停止報告 (untracked のみ続行)。
  `git checkout -b codex/phase0-fail-closed main`。**push しない**。作業後 `git checkout main` へ戻す。
- **触らない**: `C:\Users\kizun\dev\傾向収集\` / `.claude/skills/` / 他 codex/*・fix/* branch /
  `predictor/lgbm_model.txt`・`lgbm_features.json`・`lgbm_meta.json`・`calibrator.json` (artifact 不変) /
  `weights.json` / DB の中身。Discord 送信禁止。bat/ps1 は ASCII のみ。
- **予想ロジックを変えない**: スコア・ブレンド重み・calibrator・フィルタ条件は不変。本改修は
  **「異常時に何を出さないか」だけ**を足す。正常時の出力は bit 一致でなければならない (受入ゲート G3)。

## 2. 「closed」の定義 (実装前に固定する契約)

`prediction_mode` を 3 値で定義し、**消費者ごとの挙動を契約として実装**する。曖昧なままだと
「縮退の縮退」が生まれる。

| mode | 意味 | 予想の生成 | 買い候補 (bet_candidate) |
|---|---|---|---|
| `full` | 全必須条件を満たす | する | 通常どおり判定 |
| `observation` | 予想は出せるが投資判断に使えない (必須モデル欠損・PIT/stale odds 違反 等) | **する** | **強制ゼロ** |
| `blocked` | 予想自体が信頼できない (特徴計算が広範に失敗 等) | **しない** | — |

**消費者別の契約** (すべて実装 + テストで固定):

| 消費者 | `observation` の挙動 | `blocked` の挙動 |
|---|---|---|
| `web/generator.py` (HTML) | 予想表は出す / **買い候補ボードは空** / 既存の観察専用バナーに加え `error_reasons` を可視表示 | 当該レースを予想表に出さず、理由を明示した行を出す |
| `gui/app.py` | 同上 + コントロールパネルに mode を可視表示 | 同上 |
| `scripts/predict.py` (CLI) | stderr に mode/理由、exit 0 (出力は出るため) | stderr に理由、**exit 非 0** |
| `scripts/auto_predict.py` | Discord 通知に mode/理由を含める。exit bit は既存 2 (prediction failure) を流用せず**新 bit 8** | 同上 (bit 8) |
| `db.insert_prediction_log` (ledger) | **`prediction_mode` と `error_reasons` を列として記録** (後日の答え合わせで縮退 run を識別可能に) | 記録する (mode=blocked) |
| `scripts/monitor.py` | 集計から除外せず、**mode 別の内訳を出す** (除外判断はユーザに委ねる。ここで勝手に除外しない) | 同上 |
| `scripts/backtest.py` / `f3_phase0_0_eval.py` / `analyze_*.py` | **fail-closed を発火させない** (§3-1) | 同上 |

## 3. 実装

### 3-1. 層の分離 (この設計を守ること)
`predict_race` は 17 箇所から呼ばれ、うち backtest/分析が多数。**深部で raise しない**。

- `predictor/rules.py`: preflight で状態を**計算して返すだけ** (raise しない)。`Prediction` に
  `prediction_mode: str = "full"` と `error_reasons: list[str]` を追加 (既定は後方互換)。
  縮退が起きた事実 (LGBM 不在等) を **`logger.warning` でなく構造化フィールドで**返す。
- **強制 (closed) は production 経路で行う**: `web/generator.py` / `gui/app.py` /
  `scripts/predict.py` / `scripts/auto_predict.py` が mode を見て §2 の契約どおり振る舞う。
- backtest/分析は mode を**無視してよい** (現行どおり動く)。明示の opt-out フラグは不要 — 強制が
  production 側にしか無いため自動的に非発火。

### 3-2. `error_reasons` は列挙型で閉じる (自由文字列にしない)
モジュール定数で定義し、テスト・監視・集計が機械的に扱えるようにする。最低限:

```
E01_MODEL_MISSING      : LightGBM model/artifact が読めない (load_lgbm() が None)
E02_STALE_ODDS         : 使用オッズが鮮度条件を満たさない
E03_PIT_VIOLATION      : PIT ゲート (fetched_at NULL / T-10 超過) 違反
E04_FEATURES_INCOMPLETE: 必須特徴の計算失敗が閾値を超えた
```

- 閾値・条件は**既存の実装値を流用**し、新しい判定基準を発明しない (E02 は既存の
  `max_odds_age_min`、E03 は `predictor/pit_gate.py`、E04 は既存 `feature_warnings` の集計)。
- 自由文字列の追加禁止。新種が要るときは定数を足す。

### 3-3. PIT ゲートの production 接続 (E03)
`predictor/pit_gate.py` は存在するが live 予測経路から呼ばれていない
(`docs/F3_design_review_report.md` §3.3)。**live 予測が使うオッズが PIT 条件を満たすかを判定し、
違反なら E03 + `observation`** とする。**backtest の既存オッズ選択ロジックは変更しない**
(変えると凍結ベースラインが動く)。

## 4. テスト (この順序で書く)

1. **現行の silent 縮退を捕捉する characterization テストを先に書く**
   (LGBM 不在時に rule-only で `full` 相当の予想が返る現状を assert)。→ **是正後にこのテストが
   FAIL することを確認**し、fail-closed 版の assert に書き換える。**「失敗を隠す経路を塞いだ」ことの
   証明が本体**であり、実装自体は薄いはず。
2. mode 遷移テスト: E01〜E04 各々で `observation` / `blocked` になること。
3. **消費者契約テスト**: §2 の表の各行 (generator の買い候補ゼロ / CLI exit code / ledger 記録 等)。
4. **正常系 bit 一致テスト (受入ゲート G3)**: 異常が無い入力に対し、改修前後で `Prediction` の
   既存フィールド (score/rank/mark/win_probability/expected_value/kelly_fraction/
   raw_blended_probability) が**完全一致**すること。改修前の値は base commit から生成して固定値で持つ。

## 5. 受入ゲート (すべて満たすこと)

- **G1**: characterization テストの red→green (silent 縮退が検出されることの実証)。
- **G2**: `pytest tests/ -q` が **410 passed 以上**で green (現状 410 passed / 4 skipped)。
- **G3**: 正常系 bit 一致 (§4-4)。
- **G4**: **`scripts/f3_phase0_0_eval.py` が §1 の凍結値を再現** (val AUC 2 値 + OOS 425/62.0941%)。
  ※ 実行が重い場合は `--skip-oos` 相当で val のみでも可。その場合は報告に明記。
- **G5**: ASCII 制約 (bat/ps1 を触った場合) / production artifact の SHA 不変。

## 6. 生成物 / 7. 最終報告 (12 行以内)

- 生成物: 実装 + テスト + `docs/F3_phase0_fail_closed_result.md` (mode 契約の実装状況、G1-G5 の結果、
  ledger スキーマ変更の有無と migration 方針)。**`F3_MARKET_RESIDUAL_DESIGN.md` は編集しない**
  (§4.4 の実装完了マークは Claude が rev1.3 で入れる)。
- 報告: (1) G1 red→green、(2) G2 テスト数、(3) G3 bit 一致、(4) G4 凍結値再現、(5) 消費者契約の
  実装漏れの有無、(6) ledger スキーマ変更と既存行の扱い、(7) 凍結設計・artifact・封印・
  傾向収集・他branch 不変 / checkout=main / push なし。

---

## (Claude Code 側メモ — Codex には渡さない)

- 受領後の Claude 検証: (a) `predict_race` が raise していないか (backtest 非破壊)、(b) 強制が
  production 経路にあるか、(c) G4 の凍結値再現を自分でも 1 回確認、(d) error_reasons が列挙で閉じているか。
- 完了後 **expert-review は全ドメイン該当** (予想生成経路 + GUI + HTML + データ基盤 + 検証 + コード品質)。
  これまでで最も production に近い改修なので 7 名フル。Codex 自作 scorecard は D1 無効。
- その後 Claude が **rev1.3** で §4.4 に実装完了を追記 (tag `f3-design-rev1.3`)。
- **(B) §4.1 出力スキーマ分割は本改修の直後**が良い (`Prediction` に触る改修が連続するため。
  ただし 1 PR に混ぜない — fail-closed は「異常時の挙動」、スキーマ分割は「正常時の契約」で
  レビュー観点が別)。
- **(D) 運用債に追加済み**: fresh 稼働窓の single source of truth 化 (ps1 の DurationMinutes と
  healthcheck の window_end が独立ハードコード = 今回の相互作用の根治)。
