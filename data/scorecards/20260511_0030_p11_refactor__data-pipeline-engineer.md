# データパイプライン技術者 採点

## 総合: 4.0 / 5 (前回 4.0 → 4.0, ±0)

P1-1 は `predictor/` 内部リファクタ。担当範囲 (`jvlink_client/*`, `db.py`, `data/schema.sql`, `data/raw/`) は一切無変更。スコア据え置き。**前回優先課題 3 件が 5 連続未着手**。

## 項目別

- **JV-Link エラー回復: 5/5** — `client.py` 不変。logger 化・finally `JVClose`・rc=-1/-3 分岐・`TRANSIENT_OPEN_RCS` リトライ維持。
- **ingest idempotency: 4/5** — `ingest.py` 不変。`is_file_ingested` + `INSERT OR REPLACE` 冪等性維持、mtime/size 欠如 **5 連続持ち越し**。
- **データ鮮度管理: 3/5** — `db.py` 不変。`odds_fetched_at` SQL フィルタ欠落継続。
- **スキーマ整合性: 4/5** — `schema.sql` / `_ensure_column` 無変更。`schema_version` 体系欠如継続。
- **リトライ/タイムアウト/パフォーマンス: 3/5** — `JVStatus` ループ timeout 欠如・PRAGMA チューニング欠如 **5 連続持ち越し**。

## 警告: 5 連続未着手の優先課題

predictor 層の改修が 5 回連続。データ層の負債が固定化しつつある。次回は predictor 改修より下記のいずれかを優先すべき。

## 主な改善提案 (優先順、5 連続持ち越し)

1. **`ingested_files` mtime/size カラム追加** — `data/schema.sql` に `mtime REAL, size INTEGER` + `_ensure_column` migration、`is_file_ingested` を「名前 + mtime 一致」判定へ。週次 RACE 上書き恒久ガード。ingest 軸 4 → 5 の必須条件。
2. **`JVStatus` 待機ループ timeout** — `client.py` の `while True` に `JVLINK_DOWNLOAD_TIMEOUT_SEC` (デフォルト 600) と progress cancel 戻り値追加。ハング自動復帰。
3. **DB チューニング PRAGMA** — `db.py:open_db` に `synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-65536` 追加。バルク ingest 2-3 倍速見込み。

## 前回からの差分

- JV-Link エラー回復: 5 → 5 (±0)
- ingest idempotency: 4 → 4 (±0) mtime 課題 **5 連続持ち越し**
- データ鮮度管理: 3 → 3 (±0)
- スキーマ整合性: 4 → 4 (±0)
- リトライ/タイムアウト/パフォーマンス: 3 → 3 (±0) PRAGMA **5 連続持ち越し**

担当範囲未変更で 4.0 維持。次の改修で **mtime カラム** に着手すれば 4.0 → 4.2 が射程。
