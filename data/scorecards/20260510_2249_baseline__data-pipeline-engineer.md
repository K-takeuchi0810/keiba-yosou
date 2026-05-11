# データパイプライン技術者 採点

## 総合: 3.8 / 5

## 項目別

- **JV-Link エラー回復: 4/5** — `client.py:51,157,366` の `TRANSIENT_OPEN_RCS` でリトライ、rc=-1 を realtime 側で正常扱い (`client.py:387-411`)、rc=-3 にタイムアウト (`JVLINK_REALTIME_NO_DATA_SEC`)、rc=-402/-403 で `JVFiledelete` 後に継続、`finally` で `JVClose` を必ず呼んでいる。減点理由: `JVStatus` ループ (`client.py:202-214`) に上限/cancel が無く、ネットワーク不調時に無限待機しうる。
- **ingest idempotency / 二重取込防止: 4/5** — `is_file_ingested` のファイル名判定に加え、`only_files` / `modified_since` で同名更新の取りこぼしを救う設計 (`ingest.py:166-176`)。upsert は全て `INSERT OR REPLACE` で冪等。減点理由: `ingested_files` に mtime/hash を保存していないため、`only_files` 等を呼び忘れた経路では週次 RACE 上書きを静かに見逃す。
- **データ鮮度管理: 3/5** — `odds_fetched_at` / `odds_dataspec` を `_ensure_column` で後付けしており (`db.py:49`)、`update_win_odds` で書き込み (`db.py:118-146`)。fetched_at はファイル mtime ベースで実用的。減点理由: 30 分超オッズの自動除外ロジックが本パイプライン層には無く、消費側 (predictor/gui) に委ねる構造で、SQL レベルでの freshness フィルタが提供されていない。
- **スキーマ整合性 / マイグレーション: 4/5** — `schema.sql` の 5 テーブルは実 DB と一致。`_ensure_column` による単純な ADD COLUMN マイグレーションが入っており、新カラム追加で古い DB が壊れない。`idx_horse_races_blood_datekey` 等の partial index で hot path をカバー。減点理由: マイグレーションがコード散在 (`db.py:init_db` 内 2 行のみ) で、`schema_version` テーブル等の体系的管理が無く、列追加が増えると見落としやすい。
- **リトライ・タイムアウト・パフォーマンス: 3/5** — `JVLINK_OPEN_RETRIES` / `JVLINK_REALTIME_NO_DATA_SEC` で挙動切替可、WAL モード / FK 有効化 (`db.py:27-28`)、ストリーム書き込みでメモリ抑制。減点理由: `ingest_all` が 1 ファイル毎に individual upsert で transaction 単一化 (`open_db` の最後 1 回 commit) のため大量ファイルで途中失敗時に進捗が消える。`PRAGMA synchronous=NORMAL` `temp_store=MEMORY` `cache_size` 等のチューニング無し。3000+ レース規模のベンチが未確認。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`ingested_files` に mtime / size を保存し ingest 時に自動再取込** — 現状 `only_files` / `modified_since` を呼び出し側が指定しないと同名更新を見逃す。`record_ingested_file` のシグネチャに mtime/size を足し、`is_file_ingested` を「ファイル名一致 かつ mtime 同一」判定にすれば、`scripts/fetch_*.py` 側の指定漏れ事故を恒久的に防げる。`data/schema.sql:164` の `ingested_files` に `mtime REAL, size INTEGER` を追加し `_ensure_column` で migration。
2. **`JVStatus` ループに timeout と cancel を追加** — `client.py:202-214` の `while True` は最大経過秒のチェックが無く、サーバー応答が止まると GUI ごと固まる。`JVLINK_DOWNLOAD_TIMEOUT_SEC` (デフォルト 600) と `on_progress` の戻り値で cancel 判定する仕組みを `fetch_realtime` と同じ流儀で入れる。
3. **DB チューニング PRAGMA を `connect()` に追加** — `db.py:23-29` に `PRAGMA synchronous=NORMAL`, `PRAGMA temp_store=MEMORY`, `PRAGMA cache_size=-65536` (64MB) を足す。週次バルク 3000+ レコードの ingest が 2-3 倍速くなり、WAL の crash safety はほぼ維持される。

## 前回からの差分

ベースライン採点のため前回スコアなし。
