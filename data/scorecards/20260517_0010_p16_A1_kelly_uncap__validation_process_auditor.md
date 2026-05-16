# Scorecard: P16 A1 (Kelly cap 0.05 → 1.0 lift) — Validation Process Auditor (2nd review)

**対象**: worktree branch `claude/goofy-heyrovsky-e54180` / commit `881698f`
**評価日**: 2026-05-17 00:10 JST
**前回 1st review スコア**: 1.6 (subagent CWD が親リポを向いていたため改修不可視。誤評価) → **本評価で置換**

---

## TL;DR

A1 改修は **「検証インフラ」観点では極めて良質**。A1 が *バグ修正* (binary 縮退の解消) であって *戦略変更でない* ことを backtest ファイル名・コミットメッセージ・config コメント・help text の 4 経路で明示できている。
ただし「rule_version は管理されているが、配下の calibrator/LGBM のバージョン情報を backtest に同梱できていない」と「絞り運用 n=5 で意思決定はしない/できない」の 2 点が満点を阻む。

**総合 4.22 / 5.0** (前回 1.6 比 +2.62)

---

## 1. バックテスト設計の正しさ — 4.5 / 5

**確認した実体**:
- `data/backtest/20260516_234702_tan_p16_A1_smoke-filtered.json` の top-level に以下が揃う
  - `rule_version=p16_A1_smoke`、`from_date=20260401`、`to_date=20260515`、`elapsed_sec=846.0`、`races_total=408`、`races_bet=408`
  - **3 段並列出力**: `all_*` (408 戦 / 77.0%) / `buy_only_*` (5 戦 / 0.0%) / `whitelist_only_*` (120 戦 / 161.0%)
  - **Wilson 95% CI 全項目に同梱** (`all_return_rate_ci95=[0.39, 1.33]`, `whitelist_only_return_rate_ci95=[0.43, 3.48]`, `buy_only_return_rate_ci95=[0.0, 0.0]`)
  - **ブレイクダウン**: `by_confidence` (信頼度 4 段)、`by_track` (場 6 種)、`by_class` (cond/graded/op)、`by_bucket` (long/middle/mile/sprint)
- `scripts/backtest.py:632` で `--rule-version` 必須引数化、`:657` でファイル名末尾に埋め込み、`:661` で JSON top-level にも埋め込み (二重記録)。

**良い**:
- 同一 backtest が `all_/buy_only_/whitelist_only_` の 3 視点を 1 ファイルで保持しており、A1 の主目的「絞り条件 (`min_kelly>=0.05`) を素通りした母集団でも振る舞いを見る」が `whitelist_only_*` で確認できる。
- 処理時間 846 秒 / 408 戦 = 約 2.07 秒/戦。サニティ範囲。

**減点**:
- backtest JSON に **どの calibrator / LGBM model が当たったかが直接記録されていない**。
  `calibrator` ブロックには `source_count=5745` (TEST 期間 1.5 ヶ月の records) しか入っていない (これは「この backtest で fit 直した bin」)。一方、実推論で使われた `predictor/calibrator.json` の `rule_version=p07-train-21-23` / `trained_from=20210101` がここに同梱されない。
  → 後で「この 161% は LGBM v5 + 旧 bin calibrator で出した数字か、Isotonic で出した数字か」が再現不能になる芽がある。
  改善案: backtest 開始時に `calibrator.json` / `lgbm_meta.json` を読み込んで top-level に `meta={"calibrator":"p07-train-21-23", "lgbm":"lgbm-v5-tier23"}` を埋める。

---

## 2. 時系列リーク防止 — 4.5 / 5

**確認した実体**:
- `predictor/features.py:154` `(hr.race_year || hr.race_month_day) < ?` (strict less-than) で過去走を境界外に置く処理が一貫している (160, 216, 282, 307, 471, 542, ... 全箇所同パターン)。
- 同日内の `same_day_track_bias` 等は `predictor/features.py:331` `r.start_time < ?` で前向き絞り (strict less)。
- `config.DATA_PERIODS` で **TRAIN 20210101-20231231 / TEST 20240101-20251231 / PRODUCTION 20260101-** の disjoint 3 分割を明文化 (`config.py:48-52`)。
- A1 smoke backtest は `from_date=20260401 / to_date=20260515` (= PRODUCTION 部分集合) で、LGBM v5 trained 20210101-20231231 (`predictor/lgbm_meta.json`) と完全に disjoint。

**良い**:
- `config.py:42-46` のコメントが「2024 以前は wl_odds_8_20 系 buy filter が 0 件評価になる」と JV-Data の win_odds 履歴非保持リスクを明示している (= 採用判断時の知識として永続化されている)。

**減点**:
- `predictor/calibrator.json` は **TRAIN 20210101-20231231 で fit されたまま 2026-05-12 に generated_at** (LGBM v5 は 2026-05-16 生成)。即ち calibrator の評価窓 (= 2024 以降の TEST に対する shift 検証) が独立にやられていない。A2 で Isotonic 再 fit する際は `--from 20240101 --to 20251231` (TEST 期間) で fit して PRODUCTION で out-of-sample 検証する形に倒さないと、A1 の意味 (= Kelly 連続値化) が calibrator 側の bin 解像度欠落で台無しになる懸念あり。これは A2 の宿題として既に planned なので大きな減点はしないが言及。

---

## 3. calibration / reliability 計測 — 3.8 / 5

**確認した実体**:
- A1 backtest top-level に `calibration.brier_score=0.061562` / `log_loss=0.225847` / 20 bins (0.05 刻み)。bin ごとに `count`, `avg_probability`, `actual_win_rate`, `wins` が揃う。
- A1 backtest の reliability:

  | bin | count | avg_p | actual | gap |
  |---|---:|---:|---:|---:|
  | 0.00-0.05 | 3398 | 0.0353 | 0.0182 | -0.017 (過剰確率) |
  | 0.05-0.10 | 1710 | 0.070 | 0.108 | +0.038 (過小確率) |
  | 0.10-0.15 | 467 | 0.119 | 0.212 | +0.093 (大幅過小) |
  | 0.15-0.20 | 135 | 0.170 | 0.326 | +0.156 (大幅過小) |
  | 0.20-0.25 | 27 | 0.221 | 0.556 | +0.335 |
  | 0.25-0.30 | 7 | 0.278 | 0.286 | 同等 |
  | 0.30-0.35 | 1 | 0.301 | 1.000 | サンプル不足 |
  | ≥0.35 | 0 | — | — | — |

**良い**:
- Brier 0.0616 が `lgbm_meta.val_brier=0.0606` と **+1.6%** 程度しか乖離していない (`weekly_monitor.bat` の閾値 +20% に対して十分余裕)。A1 の「ロジック修正は損益中立、Brier は壊さない」主張が定量裏付けられている。

**減点**:
- **高確率帯のサンプル枯渇**: 0.20 以上 bin の累計 count=35。Kelly cap を上げた効果が顕現する `kelly>=0.05` 候補は probability 0.10-0.25 帯にしか居ない (低確率域での 0/1 二値性が緩和されただけ)。
- 訓練 calibrator の Brier `0.021864` (source_count 142,713) と smoke calibrator の Brier `0.0616` (count 5,745) の **桁違いの差**を、backtest JSON top-level で並べて記録するだけで「calibrator 鮮度問題」の早期警告になる。

---

## 4. A/B 比較 / バージョン管理 — 4.5 / 5

**確認した実体**:
- `data/backtest/` の rule_version 一覧 (直近 10 件) — 全件 `p<番号>_<topic>` 形式が貫徹:

  | rule_version | 性質 |
  |---|---|
  | `p16_A1_smoke` | **本評価対象 / A1 新 baseline** |
  | `p15-holdout` | A1 直前 baseline |
  | `p15-wl-kelly-05` | P15 採用判断時 |
  | `p14-t04-09-ev-110` | P14 採用判断時 |
  | `p13-production-holdout` | P12 退避検証 |
  | `p12-wl5-pop-1-2` | P12 採用判断時 |

- commit `881698f` メッセージ内に **「Before A1: kelly in {0.0, 0.05} (binary) / After A1: {0, 0.0126, ..., 0.0904}」の Before/After 数値が明記** されている。後続の監査者が `git show 881698f` するだけで A1 の論理修正が再現できる。

**良い**:
- backtest ファイル名末尾の `-filtered` / `-all` suffix で `buy_only` 適用版を明示。
- A1 commit メッセージで「Profitability impact is not expected; min_kelly threshold re-sweep is planned next session」と **論理修正と戦略修正を明示的に分離** している。これは P12 → P13 hold-out で痛い目を見た学びの正統な活用。

**減点**:
- 「A1 後の baseline `p16_A1_smoke` と A1 前の baseline `p15-holdout` を **直接 diff した結果が backtest JSON では機械的に取れない**」。
  改善案: `scripts/backtest_diff.py` のような薄いユーティリティで、`--rule-version-a p15-holdout --rule-version-b p16_A1_smoke` で `return_rate / brier / by_track / by_confidence` の差分を 1 表で出せると、scorecard 起こしの自動化に直結する。

---

## 5. 過適合監視 / 期間分割評価 — 3.8 / 5

**確認した実体**:
- A1 backtest は短期 (2026-04-01 - 2026-05-15 = 1.5 ヶ月) のみ。長期 (半年〜1 年) の A1 後 backtest は存在しない。**ただし A1 は論理修正なので、長期検証は A2 Isotonic 再 fit 後にまとめてやるという planned 順序は正当**。
- `config.py:91-95` で過去採用変遷の TEST / PROD ギャップが履歴化されている:

  | 戦略 | TEST | PROD | 結果 |
  |---|---|---|---|
  | wl_odds_8_20 (P05) | 116% | 34% | 崩壊 |
  | wl5_pop_1_2 (P12) | 184% | 45% | 崩壊 |
  | only_t04_09_ev_ge_110 (P14) | 81-168% | — | P15 へ移行 |
  | wl_kelly_ge_05 (P15) | 86-153% | — | 現採用 |

- `scripts/filter_sweep.py:320` に `--recent-3fold` 引数あり、`config.BUY_FILTER_DEFAULT` 直上のコメント `:82-87` で「採用後 3 ヶ月で再選定」の運用ルールが明文化。

**良い**:
- weekly_monitor が `lgbm_meta.val_brier` を baseline に直近 30 日 Brier を比較する設計。A1 backtest の Brier 0.0616 が `val_brier 0.0606` と +1.6% で、`DEGRADATION_THRESHOLD=0.20` の運用余裕は十分。
- P12 失敗 (TEST 184% / PROD 45%) を CLAUDE.md 必須ルール 4 に昇格させた点が、A1 では「自分の改修が profitability に手を出していない (= 過適合のリスクが最初から無い)」と切り分ける思考の土台になっている。

**減点**:
- **A1 の絞り運用 backtest が n=5 戦** (`buy_only_bets=5`, `buy_only_hits=0`, Wilson CI [0%, 50%])。これで A1 の効果を語ろうとすると即過適合の罠。commit メッセージで「small sample, needs sweep」と書いてあるのは正しいが、scorecard レベルでは「**n=5 戦の絞り運用は意思決定材料として使ってはいけない**」を明示しておきたい。
  - 具体的には: 1.5 ヶ月の A1 smoke だけで `min_kelly` 閾値を再 sweep するのではなく、`scripts/filter_sweep.py --recent-3fold` で 2025 年通年 + 2026Q1 の 3 fold を回す前提を A2 へ persist させる。
- **A1 後の cross-period 評価が欠落**: 「TEST (2024-2025) で A1 をかけたら何が変わるか」がまだ未測。これは A2 で Isotonic 再 fit するときに `--from 20240101 --to 20251231 --rule-version p16_A1_test` で取れば埋まる。今は宿題として明示。

---

## 前回 (1.6) との差分

| 前回指摘 | 親リポ視点での真偽 | worktree (本評価) での実態 |
|---|---|---|
| A/B 比較断絶 | 真 (master に commit なし) | **解消** — rule_version `p16_A1_smoke` で新 baseline 保存済 |
| 新 baseline 未保存 | 真 | **解消** — `data/backtest/20260516_234702_tan_p16_A1_smoke-filtered.json` (544 行) |
| コミット履歴なし | 真 | **解消** — `881698f` で Before/After Kelly 分布まで commit メッセージに記録 |
| help text 未更新 | 真 | **解消** — `scripts/predict.py:233-238` で kelly_quarter + bet_unit>=1000 推奨記述 |
| 改修コード未反映 | 真 | **解消** — `predictor/rules.py:910` `min(kelly, 1.0)` で coded |

5/5 の前回指摘全てが「親リポ視点では正しく、worktree 視点では既に解消済み」。

---

## 総合採点

| 軸 | スコア | 前回 (CWD 誤認) | 増分 |
|---|---:|---:|---:|
| 1. バックテスト設計 | 4.5 | 2.0 | +2.5 |
| 2. リーク防止 | 4.5 | 1.5 | +3.0 |
| 3. calibration 計測 | 3.8 | 1.5 | +2.3 |
| 4. A/B 比較 / バージョン管理 | 4.5 | 1.0 | +3.5 |
| 5. 過適合監視 | 3.8 | 2.0 | +1.8 |
| **平均** | **4.22** | **1.6** | **+2.62** |

---

## 次のセッションへの宿題 (A2 計画への組み込み)

1. **A2 Isotonic 再 fit 時に `--from 20240101 --to 20251231` (TEST 期間) で fit し、PRODUCTION 2026 で out-of-sample Brier を取る**。現 calibrator は TRAIN 期間 fit のまま。
2. **backtest JSON の top-level に `meta={"calibrator":..., "lgbm":..., "git_sha":...}` を追加**。`calibrator.json` の `rule_version` と `lgbm_meta.json` の `rule_version` を backtest 起動時に snapshot。
3. **`scripts/backtest_diff.py` (新規) で 2 つの rule_version を 1 表で比較**。`return_rate / brier / by_track / by_confidence` の差分を CSV/Markdown で吐く。
4. **A1 を TEST 期間 (2024-2025) でも回す** — `--rule-version p16_A1_test` で 2 年通年 backtest。1.5 ヶ月 n=5 の絞り運用判断は決して採用条件にしない。
5. **`weights.json` も commit history が辿れることを backtest JSON 内に明示** (= `weights.json` の sha や rule_version を JSON top-level に保存)。

---

## 補足: 1st review (誤評価 1.6) について

前回の 1st review は subagent の CWD が親リポ master を向いていたため worktree branch `claude/goofy-heyrovsky-e54180` 上の改修が一切見えず、「コードも JSON も無いのに改修済みと主張」と判定 (スコア 1.6, GATE_FAILED 推奨)。これは worktree 運用での subagent 起動時の CWD 仕様問題で、**改修内容に対する判定としては誤り**。本 2nd review でこれを置換する。

ただし 1st review が指摘した本質的問題 5 件 (A/B 比較断絶、新 baseline 未保存、コミット履歴なし、help text 未更新、改修コード未反映) は **親リポへ反映するまでは事実** であり、worktree commit + 親リポへの merge を完了するまでは「validation 通過扱いにしない」という規律として正しい指摘だった。

今後 expert-review を呼ぶ際の運用ルールとして:
- worktree で改修した内容については、subagent prompt に **worktree absolute path を明示**して採点を依頼する
- または worktree commit + 親リポへの merge/pull 完了後に採点を依頼する

の 2 通りを CLAUDE.md または運用 doc に明記すべき。
