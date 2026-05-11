# データパイプライン技術者 採点

## 総合: 3.8 / 5 (前回 3.8 → 3.8, ±0)

**担当範囲 (jvlink_client / db.py / data/schema.sql / data/raw) には変更なし**。本改修 P0-2 は `predictor/calibrator.json` の再学習成果物差し替えと `predictor/rules.py` の min_bin 適用ロジック (P0-1 延長) で、データパイプライン層は完全に不変のためスコア維持。

## 項目別

- **JV-Link エラー回復: 4/5** — `client.py` 不変。`TRANSIENT_OPEN_RCS` リトライ・rc=-1 正常扱い・rc=-3 (DL中) タイムアウト・finally JVClose は健在。`JVStatus` ループに上限/cancel が無い既知の弱点も未対処。
- **ingest idempotency / 二重取込防止: 4/5** — `ingest.py` 不変。`is_file_ingested` + `only_files` / `modified_since` と `INSERT OR REPLACE` の冪等性は維持。`ingested_files` に mtime/hash を持たず、同名ファイル更新を取りこぼし得る弱点も据え置き。
- **データ鮮度管理: 3/5** — `db.py` の `odds_fetched_at` 書き込み・`_ensure_column` マイグレ不変。SQL レベル freshness フィルタは依然欠落。calibrator は予測時の確率変換であり、鮮度パイプラインには無関係。
- **スキーマ整合性 / マイグレーション: 4/5** — `data/schema.sql` 不変、`init_db` の `_ensure_column` 経路も変更なし。`schema_version` 体系化が無い弱点も継続。
- **リトライ・タイムアウト・パフォーマンス: 3/5** — `JVLINK_OPEN_RETRIES` 系 env、WAL/FK 有効化はそのまま。`PRAGMA synchronous=NORMAL` / `temp_store=MEMORY` / `cache_size` チューニング欠如、3000+ 規模ベンチ未確認も未対処。

## 主な改善提案 (前回から不変・未着手)

1. **`ingested_files` に mtime/size を保存し ingest 時に自動再取込** — 未着手。`data/schema.sql` の `ingested_files` に `mtime REAL, size INTEGER` 追加 + `_ensure_column` migration、`is_file_ingested` を「名前一致 かつ mtime 同一」判定に変更し、週次 RACE 同名上書きの取りこぼしを恒久ガード。
2. **`JVStatus` ダウンロード待機ループに timeout / cancel** — 未着手。`client.py` の `while True` に `JVLINK_DOWNLOAD_TIMEOUT_SEC` (デフォルト 600) と `on_progress` コールバック戻り値による cancel を追加。GUI ハング回避。
3. **DB チューニング PRAGMA** — 未着手。`db.py:open_db` に `PRAGMA synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-65536` を追加。週次バルク ingest が 2-3 倍速見込み。

## 前回からの差分

- JV-Link エラー回復: 4 → 4 (±0) `client.py` 無変更
- ingest idempotency: 4 → 4 (±0) `ingest.py` 無変更
- データ鮮度管理: 3 → 3 (±0) `db.py` 無変更、SQL 層 freshness 未追加
- スキーマ整合性: 4 → 4 (±0) `schema.sql` 無変更
- リトライ/タイムアウト/パフォーマンス: 3 → 3 (±0) PRAGMA 追加なし

**前回優先課題 3 件 (mtime 保存 / JVStatus timeout / DB PRAGMA) はいずれも未着手のまま 2 連続持ち越し**。次回改修で 1 件でも着手しないと、データ層スコアは 3.8 で頭打ちが続く見込み。
