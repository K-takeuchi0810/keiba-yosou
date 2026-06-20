# 証跡固定 (Day1 evidence lock) — 2026-06-20 12:25

**目的**: P25 Plan Step 4 初日 PASS の状態を「勝利宣言」せず「証跡固定」する。
ユーザ指摘の 5 項目を read-only で確認し、誤読しようのない一次データに固定する。

**Day1 判定 (data-pipeline 観点)**: PASS。ただし Plan Step 4 **正式完了は 2026-06-21 (日) 同等稼働観測後** に保留。本セッションで OOS auto を enable しない。

## 1. coverage.runs_today の定義 (明文化)

| 確認項目 | 結果 |
|---|---|
| JSONL への書き込み source | **`scripts/fetch_fresh_odds.py` のみ** (4 箇所の exit path から `_write_coverage_log`) |
| `scripts/check_fresh_odds_health.py` は書き込むか | **No** — `--coverage-path` 引数で **読むだけ** |
| `scripts/fresh_odds_coverage.py` は書き込むか | **No** — 集計用、読むだけ |
| 重複集計 | **0 件** (本日 21 件すべて unique run_at) |
| 隣接 run_at 間隔 | **全て 10.0 分ぴったり** (`schtasks /sc minute /mo 10` 仕様通り) |
| 手動実行混入 | **No** — 全 timestamp が `HH:MM:01` (scheduler 起動の 1 秒遅延) で整合 |
| autouse fixture によるテスト汚染 | **No** — `tests/test_fetch_fresh_odds.py` の autouse `_isolate_coverage_log` が tmp_path にリダイレクト |

**結論**: `coverage.runs_today` = **`keiba-fresh-odds` 本体 scheduler が 10 分おきに走らせた起動回数**。healthcheck の起動回数でも、手動実行でも、重複集計でもない。

11:45 時点の 17 = 09:00〜11:40 の 17 fire (定義整合)。12:20 時点で 21 fire。

## 2. 本日 12:20 時点の summary (本日終業前段階)

| 指標 | 値 |
|---|---|
| 期間 | 09:00:00 〜 12:20:01 (現在進行中、最終 16:40 まで) |
| scheduler `keiba-fresh-odds` 起動回数 | 21 (`LastRun=2026/06/20 12:20:01`、`LastResult=0`、`MissedRuns=0`) |
| `keiba-fresh-odds-healthcheck` 起動回数 | (推定 13 回、15 分おき 09:15-12:15) |
| eligible_races (累計) | 33 |
| fetched_races (累計) | 33 (= 100%) |
| ok_races (累計) | **33** (= 100%) |
| error_races (累計) | **0** |
| no_data / timeout / empty | 0 / 0 / 0 |
| lock_skipped | **0** |
| failed_reason 分類 | 空 |
| db.fresh_horse_rows (前回 11:45 測定) | 505 行 |
| contamination_detected | **False** |
| OOS auto (`keiba-oos-backtest-auto`) State | **Disabled** (LastRun=1999/11/30 = 一度も発火していない) |
| Plan 期待値比 (eligible 36 vs 累計 33) | **0.92** (12:20 時点、最終 16:40 までさらに増加見込み) |

## 3. NOT_EVALUABLE=1 の素性 (明記)

`data/logs/fresh_odds_health_20260620.log` 内の唯一の NOT_EVALUABLE は:

```
[2026-06-20 08:16:09] decision=NOT_EVALUABLE reason=coverage JSONL absent
```

- **timestamp 08:16:09** — scheduler 初発火 (09:00) より **44 分前**
- **修正前ロジック** での run — このセッション中で `integrate_decision` を修正する **前** の試行運転で、「scheduler 未稼働 + coverage 未生成 = NOT_EVALUABLE」と判定していた
- 同セッション内で **08:17 以降の修正後ロジック** では同じ状況を HOLD と判定 (`scheduler not yet fired today and coverage JSONL not yet generated`)
- **09:00 以降の本番 run には 1 件も NOT_EVALUABLE は存在しない**

09:00 以降の run 集計 (本セッション 12:21 時点):

| 区分 | 件数 |
|---|---:|
| PASS | **12** |
| HOLD | 1 (scheduler 1 回目発火直後の transient) |
| FAIL | **0** |
| NOT_EVALUABLE | **0** |

→ **09:00 以降の本番稼働では FAIL も NOT_EVALUABLE もゼロ**。1 件残っている NOT_EVALUABLE は 09:00 前の修正前ロジックの試行運転で、本番運用とは無関係。

## 4. OOS auto Disabled 維持確認

| 確認 | 結果 |
|---|---|
| `keiba-oos-backtest-auto` State | **Disabled** |
| LastRunTime | 1999/11/30 0:00:00 (= 一度も発火していない) |
| NextRunTime | 2026/06/20 17:30:00 (登録は維持、ただし Disabled で発火しない) |
| 本セッションで Enable した? | **No** |

**OOS backtest は本セッションでは絶対に起動しない**。day2 PASS + PRED_DISABLE_BLEND 実装後まで保留。

## 5. 次の作業分解 (実装はしない、設計のみ固定)

### 5-A. HTML サイズ削減 (mobile HOLD 解消) — 優先 1

現状: `web/dist/index.html` = **1.79MB** (1.5MB 警戒線を 0.29MB 超過)。192 `<details>` / 2369 `<tr>` / 37,570 行。

#### Step A1: 各日 section 別 HTML 化 (推奨先頭)

| 項目 | 内容 |
|---|---|
| 改修対象 | `web/generator.py` の `render()` |
| 入力 | `days = list(days.values())` のループ |
| 出力 | 各日ごとに `web/dist/days/YYYYMMDD.html` を生成 + 親 `index.html` は日リストと「直近 1 開催日のみ inline」のハイブリッド |
| URL 構造 | `index.html` → 過去日は `<a href="days/20260613.html">` でナビ |
| サイズ目安 | 1 日あたり ~80 KB (= 192 日 × 80 KB ÷ 全体) なので、親 ~200KB、各日 ~80KB に収まる見込み |
| `publish_to_icloud` 対応 | `WEB_DIST/days/*.html` をコピー対象に追加 (`shutil.copytree`) |
| 互換性 | アンカー `#day-N` から `days/<date>.html` への変換 (旧ブックマーク対策で fallback `<a>` を残す) |
| テスト | `test_template_render` を「親 + 直近日 inline + 別 HTML へのリンク存在」に拡張 |

#### Step A2: 過去日の `<details>` 内 lazy unmount (副案)

A1 で十分なら不要。実装は HTMLAtttr ベースの `loading="lazy"` ではなく、Jinja で過去日は inner 部を空にしておき、open イベントで `<iframe>` を差し込む案。複雑度高、A1 で問題が残ったときに検討。

#### Step A3: 不要列・重複 DOM 削減 (副案)

各 race の `<tr>` 列を確認し、画面で表示していない冗長列を削除。地味だが効果小。A1 で 1.5MB 以下を確実に下回るならスキップ。

#### 受入条件

- `wc -l web/dist/index.html` < 10,000 行
- `ls -l web/dist/index.html` < 1,500,000 bytes
- mobile-html-reviewer が PASS に戻る
- `publish_to_icloud` でフォルダ全体 (index.html + days/*.html) を atomic 配信

### 5-B. PRED_DISABLE_BLEND 実装 (factorial C3/C6 の前提) — 優先 2

現状: `_investment_probability` (層 B) を OFF にする env が **未実装**。`PRED_W_model_blend_*=1.0` を全 confidence に手動設定する代替経路はあるが、それは「blend を市場 100% にする」であって「blend 自体を無効化」とは違う (model 確率も計算には残る)。

#### Step B1: env 実装

| 項目 | 内容 |
|---|---|
| 改修対象 | `predictor/rules.py:_investment_probability` |
| 仕様 | 関数冒頭で `if os.environ.get("PRED_DISABLE_BLEND") == "1": return model_probability` を追加 |
| 副作用 | discount は適用しない (B 層完全 OFF を意味するため)、または `PRED_DISABLE_DISCOUNT=1` と組合せ可能にする |
| docstring | 3 層 (A/B/C) ablation の正規 OFF 経路として明示 |
| backtest meta 記録 | `meta.env_overrides` に自動記録される (既存の `_snapshot_meta` 経路で対応済み) |

#### Step B2: テスト追加

| テスト | 検証 |
|---|---|
| `test_investment_probability_blend_disabled_by_env` | `monkeypatch.setenv("PRED_DISABLE_BLEND", "1")` で呼出すと market_probability に依存せず model_probability を直接返す |
| `test_pred_disable_blend_records_in_meta` | `scripts.backtest` 経由で env を設定すると JSON の `meta.env_overrides` に記録される |

#### Step B3: scorecard 記録

- 既存の `PRED_W_*` ablation との **意味の違いを明記**: `PRED_W_model_blend_*=1.0` は「blend で market を 100% にする」、`PRED_DISABLE_BLEND=1` は「blend 自体を無効化して model のみ」
- C1/C2/C3/C5 の実行コマンドを記載 (env override の具体的な羅列)

#### Step B4: expert-review

予想ロジックの意味が変わるため `prediction-logic-analyst` と `validation-process-auditor` を必ず通す。CLAUDE.md ルール 1 (D1 mode auto-trigger)。

### 5-C. 工程順序 (絶対遵守)

```
[今日] Day1 PASS の証跡固定 (本 scorecard)
   ↓
[明日 2026-06-21] Day2 観察 (PASS 継続を確認)
   ↓
[次セッション] PRED_DISABLE_BLEND 実装 + expert-review
   ↓
[Plan Step 5] C1 / C2 / C3 / C5 paired backtest 実行
   ↓
[Plan Step 6] out-of-sample backtest (from=20260101) で paired CI 再導出
   ↓
[Plan Step 7] calibrator refit 検証 (発火帯 subset Brier に基づく)
   ↓
[Plan Step 8] scorecard + expert-review + Plan 完了判定
   ↓
[最後] **ユーザが明示的に OOS auto を Enable** (Enable-ScheduledTask)
```

OOS backtest を **PRED_DISABLE_BLEND 実装より先に走らせない**。サンプル不足の run を量産する誘惑に屈さない (前 OOS bg の死体コレクションを繰り返さない)。

### 5-D. 並行作業の可否

- 5-A (HTML サイズ削減) は予想ロジック / backtest に影響しないため、5-B (PRED_DISABLE_BLEND) と **並行実装可**
- ただし両者を同一 commit にまとめると expert-review の責任範囲が交錯するため、**別 commit で連投** を推奨

## 6. このセッションの結論

- Day1 fresh odds 取得運用は **機構面で全項目 PASS** (scheduler / coverage / DB / contamination / OOS auto Disabled)
- ただし **Plan Step 4 正式完了は 2026-06-21 (日) day2 観察後** に保留 (1 開催日だけで完了宣言しない厳格姿勢)
- 「runs_today=17 (12:20 時点 21)」の定義は **fresh_odds 本体の 10 分おき起動回数** で確定、重複なし、手動混入なし
- NOT_EVALUABLE 1 件は **09:00 前の修正前ロジックの試行運転**、09:00 以降の本番 run には FAIL / NOT_EVALUABLE 共にゼロ
- OOS auto は **Disabled 維持**、本セッションでは絶対 Enable しない
- 次セッションの工程順序: Day2 観察 → PRED_DISABLE_BLEND → C1/C2/C3/C5 → OOS paired CI → calibrator refit → OOS auto Enable

**比喩**: 水道は通った。料理の腕前 (= P25 の利益エッジ) はこれから測る。今日の仕事は「水道工事の検収」であって「料理の試食」ではない。
