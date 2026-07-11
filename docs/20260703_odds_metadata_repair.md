# odds 信頼メタデータ修復ログ (2026-07-03)

data-pipeline 監査指摘「修復で RACE タグを NULL に落としたため backfill 由来行が
DB から不可視」への監査証跡。DB 本体に追跡子を残す代わりに本ログで恒久記録する。

## 事故 (2026-06-30 に混入、2026-07-03 に検出)

- `scripts/backfill_race_extras.py` (RACE 全ファイル再 dispatch) が O1 (確定オッズ,
  data_div=5) を `update_win_odds(fetched_at=ファイルmtime)` で再取込し、
  `odds_fetched_at=NULL` (歴史的確定=信頼) だった行に発走後タイムスタンプを刻印。
- 影響: **261,163 行** (race_year 2021:47,660 / 2022:47,054 / 2023:47,493 /
  2024:46,994 / 2025:47,715 / 2026:24,247)。`odds_dataspec='RACE'` が刻印の識別子。
- 症状: Step1 odds ゲートが全レースを post-start 扱いで除外
  (20260703_053033 backtest: races_odds_untrusted=3455/3455, records n=0)。

## 修復 (2026-07-03, commit 17fd8ab と同時)

```sql
UPDATE horse_races SET odds_fetched_at=NULL, odds_dataspec=NULL
 WHERE odds_dataspec='RACE';  -- 261,163 rows
```

- 修復後検証: `odds_dataspec='RACE'` 残存 0 行 / 2025 の fetched_at 非NULL 残存 0 行 /
  修復後 backtest (20260703_082145) で races_odds_untrusted=0 (2025窓)。
- 意図的残置: `odds_dataspec='0B31'` の 17 行 (真正のリアルタイム PIT snapshot)。

## 副作用 (未クローズ、F3 着手時に対処)

- 2026年5-6月の旧 fresh-odds mining スナップショット (~9,027 行、97% が post-start/stale
  汚染と判定済だったもの) は、バックフィルが値を確定オッズで上書きした後に本修復で
  NULL 化された。**値はクリーンな確定オッズだが、当時の PIT タイムスタンプは復元不能**。
- 規律: NULL 行 (全 559k) はすべて「確定=発走後オッズ」であり、**発走前特徴の入力には
  使用禁止** (schema.sql の PIT 注記と同一規律)。F3 で発走前オッズ特徴を作る際は
  odds_fetched_at 非NULL の真正 PIT snapshot のみを使い、コードレベルのゲートを実装する
  (validation 降格宣言(2): 実装なしで参照したら即 FAIL)。

## 再発防止

- `db.py update_win_odds(historical=True)`: 確定オッズは NULL 維持・既存 PIT snapshot
  (非NULL) を上書きしない。`jvlink_client/ingest.py` の O1 dispatch は dataspec=RACE で
  historical=True。回帰テスト: tests/test_data_quality_gates.py (2 件)。
- レビュー観点の追加 (data-pipeline 自己監査): 再取込の冪等性は「行数不変」でなく
  「**信頼メタ列の write-path** と **Step1 ゲート通過レース数の不変**」で検証する。
