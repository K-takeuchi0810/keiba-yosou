# データパイプライン技術者 採点

## 総合: 4.0 / 5 (前回 4.0 → 4.0, ±0)

P0-3 重賞ホワイトリストは `predictor/rules.py` 限定の改修で、担当範囲 (`jvlink_client/*`, `db.py`, `data/schema.sql`, `data/raw/`) には一切変更なし。前回 P1-3 で達成した観測性 (logger 化) も維持されたまま。スコア据え置き。

## 項目別

- **JV-Link エラー回復: 5/5** — `client.py` の 9 箇所 `logger.warning(exc_info=True)` は不変。サイレント失敗ゼロ・finally `JVClose`・rc=-1/-3 分岐・`TRANSIENT_OPEN_RCS` リトライも前回水準を保持。
- **ingest idempotency / 二重取込防止: 4/5** — `ingest.py` 無変更。`is_file_ingested` + `INSERT OR REPLACE` の冪等性維持、ただし `ingested_files` mtime/size 欠如は **4 連続持ち越し**。
- **データ鮮度管理: 3/5** — `db.py` 無変更。`odds_fetched_at` SQL フィルタ欠落も継続。本改修は予想ロジック層のため寄与なし。
- **スキーマ整合性 / マイグレーション: 4/5** — `schema.sql` / `_ensure_column` 経路ともに無変更。`schema_version` 体系欠如継続。
- **リトライ・タイムアウト・パフォーマンス: 3/5** — `JVLINK_OPEN_RETRIES` 系 env / WAL / FK 不変。`JVStatus` ループ timeout 欠如・PRAGMA チューニング (synchronous=NORMAL / temp_store=MEMORY / cache_size) 欠如も **4 連続持ち越し**。

## 改修対象外コメント

P0-3 は重賞判定をレース名正規表現から `data/grade_races.json` ホワイトリスト参照へ切替える `predictor/rules.py` 内の純ロジック改修で、データ取り込み経路 (raw → DB) には触れていない。ただし副作用としてホワイトリストファイル自体が新たな静的データ依存になったため、将来 `ingest` 経路で JSON のスキーマ検証 (起動時 1 回 `json.load` + 必須キー assert) を入れると堅牢度が上がる。現状はスコア影響なし。

## 主な改善提案 (優先順、4 連続持ち越し)

1. **`ingested_files` に mtime/size カラム追加** — `data/schema.sql` に `mtime REAL, size INTEGER` 追加 + `_ensure_column` migration、`is_file_ingested` を「名前一致 かつ mtime 同一」判定へ。週次 RACE 同名上書き恒久ガード。データ層スコア 4.0 突破の必須条件。
2. **`JVStatus` ダウンロード待機ループに timeout / cancel** — `client.py` の `while True` に `JVLINK_DOWNLOAD_TIMEOUT_SEC` (デフォルト 600) と progress callback 戻り値 cancel を追加。logger 化済みなのでハング検知から自動復帰へ。
3. **DB チューニング PRAGMA** — `db.py:open_db` に `PRAGMA synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-65536` 追加。週次バルク ingest 2-3 倍速見込み。

## 前回からの差分

- JV-Link エラー回復: 5 → 5 (±0) `client.py` 不変
- ingest idempotency: 4 → 4 (±0) `ingest.py` 不変、mtime 課題 4 連続持ち越し
- データ鮮度管理: 3 → 3 (±0) `db.py` 不変
- スキーマ整合性: 4 → 4 (±0) `schema.sql` 不変
- リトライ/タイムアウト/パフォーマンス: 3 → 3 (±0) PRAGMA 4 連続持ち越し

担当範囲未変更で 4.0 維持。次の改修で **mtime カラム** に着手すれば ingest 軸 4 → 5、総合 4.0 → 4.2 が射程。
