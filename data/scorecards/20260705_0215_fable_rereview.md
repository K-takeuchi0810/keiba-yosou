# 2026-07-05 02:15 — Fable 正規再採点 (bias_scan + webapp + Phase4 一括)

## 経緯

- 2026-06-29〜30 の bias_scan 採点は Fable 5 がシステム全体で利用不可だったため
  sonnet 暫定 → Opus/v4 代替で実施 (`20260629_2344` / `20260630_0502`)。
- 本セッションでセッションモデルが Fable 5 に切替わり、agent 定義 (`model: fable`)
  のままの正規起動が復旧したことを確認 → **定義どおり Fable で 7 名を並列再採点**。
- 対象: 本 branch (`claude/feature-bias-validation-yl5key`) の全成果物
  (scripts/bias_scan.py + tests / webapp 一式 / Phase4 corner+lap ingest / sire_lines)。
- rubric v4 改修タイプ別ゲート適用。分類 = type-B (bias_scan 診断) + type-C (Phase4
  データ層) + type-D (webapp 表示)。type-A (backtest 採用判断) は本改修に該当なし。

## 総合結果

| 専門家 | 判定 | スコア | 主要指摘 → 対処 |
|---|---|---|---|
| validation-process-auditor | PASS | 4.3 | 追加要修正なし (two-proportion TODO は既に docstring 化済) |
| data-pipeline-engineer | PASS | 4.3 | 追加要修正なし (upsert 両順序ガード・原子書込を評価) |
| gui-ux-auditor | PASS | 4.0 | 追加要修正なし |
| profitability-judge | PASS | 4.2 | bias_scan に payout 欠損開示がない → **対処済** (下記 1) |
| code-quality-reviewer | HOLD | 3.8 | backtest 後方互換 alias 残存 / corner ガード直接テスト欠如 → **対処済** (下記 2, 3) |
| prediction-logic-analyst | HOLD | 3.8 | in-sample 警告の文言が測定量 (calibrator 前 raw) と不整合 → **対処済** (下記 4) |
| mobile-html-reviewer | FAIL | 3.8 | light テーマ warn 4.39:1 AA 未達 / 44pt 未満リンク / iOS title 到達不能 → **対処済** (下記 5) |

FAIL/HOLD の根拠指摘は本セッション内で全件対処し、全 pytest 234 passed / 3 skipped。

## 指摘 → 対処の記録

1. **profitability**: `bias_scan.py` の pick 経路が `get_payout` (欠損不可視) を使用。
   → `get_payout_with_presence` へ置換。`Cell.payout_row_missing` (的中かつ払戻行
   欠損で return 系列に 0 が混入した件数、trusted のみ) を追加し、JSON セル出力と
   コンソール (`ret=..%(払戻欠N:下方歪)`) へ開示。webapp `payout_missing` と開示規律を
   対称化。テスト `test_payout_row_missing_counter` 追加。
2. **code-quality**: `scripts/backtest.py` の後方互換 alias (`_popularity_config` 等)
   を削除し、`tests/test_backtest_market_snapshot.py` を public 名 import へ移行
   (18 passed)。単一出典原則の回復。
3. **code-quality**: `upsert_horse_race` の corner 上書きガードに直接テストがなかった
   → `test_upsert_horse_race_corner_overwrite_guard` を追加 (結果→発走前で保持、
   逆順で更新、同一キーで行が増えない、の 3 点。`upsert_race` lap ガードテストと同型)。
4. **prediction-logic**: bias_scan の in-sample 警告 2 箇所 (`print_report` /
   `main`) が「Brier/gap は in-sample」と calibrator fit 窓を直接の原因のように
   記述していた → 「測定量は calibrator 前 raw のため、in-sample 性は LGBM TRAIN 窓
   重複に由来 (calibrator fit 窓を TRAIN 窓の代理として判定)」へ是正。
5. **mobile**: light テーマ `--warn` を #b71c1c (AA 達成) に変更、index の当日速報
   リンクに backlink クラス (44pt)、trends の払戻欠チップ説明を本文凡例へ追加
   (iOS は title 属性到達不能)、短縮表示 `abs(delta)`、apt `(n<10)` 表記、
   corner_env 無効時 `4角-`、error ページ導入 (パス非露出)。
6. **prediction-logic (別件)**: `predictor/sire_lines.py` の父系分類 約 12 件の
   事実誤り (ドゥラメンテ=kingmambo 系ほか) を是正、`test_line_facts_regression` で固定。
7. **validation (別件)**: `probe_corner_offsets --ra` が非 200m 倍数距離で false-red
   → スキップ + skipped_frac 表示。`features.py` の cache=None クラッシュ →
   `_cached` 経由へ。db fallback の TOCTOU 空 DB 生成 → `mode=rw` URI へ。

## 位置づけ

- `20260629_2344` (sonnet 暫定) / `20260630_0502` (Opus/v4 代替) を置き換える
  **正規 (定義モデル Fable) の採点記録**。時系列比較はこの scorecard を基準にする。
- 残作業 (ユーザ実機のみ可): probe --expect/--ra の実 .jvd 緑化 → backfill →
  実 DB での bias_scan 実行 → 先行力 ablation。hard gate はコード側で強制済み。
