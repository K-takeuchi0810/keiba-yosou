# データパイプライン技術者 採点

## 総合: 3.8 / 5 (前回 3.8 → 3.8, ±0)

**担当範囲 (jvlink_client / db / schema / data/raw) には変更なし**。本改修 P0-1 は `buy_filter` の config 一元化 (gui/app.py, predictor/rules.py 中心) で、データパイプライン層は不変のためスコア維持。

## 項目別

- **JV-Link エラー回復: 4/5** — `client.py` 不変。`TRANSIENT_OPEN_RCS` リトライ・rc=-1 正常扱い・rc=-3 タイムアウト・finally JVClose は前回どおり健在。減点理由 (`JVStatus` ループに上限/cancel 無し) も未対処。
- **ingest idempotency / 二重取込防止: 4/5** — `ingest.py` 不変。`is_file_ingested` + `only_files` / `modified_since` 設計と `INSERT OR REPLACE` の冪等性は維持。`ingested_files` に mtime/hash を持たない弱点も据え置き。
- **データ鮮度管理: 3/5** — `db.py` の `odds_fetched_at` 書き込み・`_ensure_column` マイグレは不変。SQL レベルの freshness フィルタは依然欠落 (消費側 = 今回触った rules.py / app.py に委ねる構造)。本改修で消費側ロジックは config 集約されたが、パイプライン層の評価軸には影響しない。
- **スキーマ整合性 / マイグレーション: 4/5** — `data/schema.sql` 不変、`db.py:init_db` の `_ensure_column` 経路も変更なし。`schema_version` 体系化が無い弱点も継続。
- **リトライ・タイムアウト・パフォーマンス: 3/5** — `JVLINK_OPEN_RETRIES` 系 env、WAL/FK 有効化はそのまま。`PRAGMA synchronous=NORMAL` / `temp_store=MEMORY` / `cache_size` チューニング欠如、3000+ 規模ベンチ未確認も未対処。

## 主な改善提案 (前回から不変・未着手)

1. **`ingested_files` に mtime/size を保存し ingest 時に自動再取込** — 未着手。`data/schema.sql:164` に `mtime REAL, size INTEGER` 追加 + `_ensure_column` migration、`is_file_ingested` を「名前一致 かつ mtime 同一」判定に変更。`scripts/fetch_*.py` 側の `only_files` 指定漏れを恒久ガード。
2. **`JVStatus` ループに timeout / cancel** — 未着手。`client.py:202-214` の `while True` に `JVLINK_DOWNLOAD_TIMEOUT_SEC` (デフォルト 600) と `on_progress` 戻り値による cancel を追加。
3. **DB チューニング PRAGMA** — 未着手。`db.py:23-29` に `PRAGMA synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-65536` を追加。週次バルク ingest が 2-3 倍速。

## 前回からの差分

- JV-Link エラー回復: 4 → 4 (±0) 該当ファイル無変更
- ingest idempotency: 4 → 4 (±0) 該当ファイル無変更
- データ鮮度管理: 3 → 3 (±0) `db.py` 無変更、SQL 層 freshness 未追加
- スキーマ整合性: 4 → 4 (±0) `schema.sql` 無変更
- リトライ/タイムアウト/パフォーマンス: 3 → 3 (±0) PRAGMA 追加なし

**前回優先課題 3 件 (mtime 保存 / JVStatus timeout / DB PRAGMA) はいずれも未着手のまま持ち越し**。
