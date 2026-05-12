# データパイプライン技術者 採点

## 総合: 4.0 / 5 (前回 4.0 → 4.0, ±0)

今回改修は `config.BUY_FILTER_DEFAULT` を `wl_ex_unsure_pop_1_4` → `wl_odds_8_20` に切替え (+ `gui/app.py`, `web/generator.py`, `scripts/filter_sweep.py`)。担当範囲 (`jvlink_client/`, `db.py`, `data/schema.sql`, `data/raw/`) は **完全無変更**。スコア据え置き。**前回優先課題 3 件が 8 連続未着手** — データ層技術的負債が固定化、放置リスク臨界域突破。

## 項目別

- **JV-Link エラー回復: 5/5** — `client.py` 不変。logger 化・finally `JVClose`・rc=-1/-3 分岐・`TRANSIENT_OPEN_RCS` リトライ機構維持。フィルタ閾値変更のみで COM 層は完全 untouched。
- **ingest idempotency: 4/5** — `ingest.py` の `only_files` / `modified_since` 機構維持。mtime/size カラム化欠如 **8 連続持ち越し**、週次 RACE 同名上書き恒久ガード未整備のまま。
- **データ鮮度管理: 3/5** — `db.py` 不変。`odds_fetched_at` ベースの SQL 自動除外フィルタ欠落継続 (GUI 表示のみ)。今回 `wl_odds_8_20` はオッズ帯絞り込みだが鮮度自動カットとは別軸。
- **スキーマ整合性: 4/5** — `schema.sql` / `_ensure_column` 無変更。`schema_version` 体系欠如継続。
- **リトライ/タイムアウト/パフォーマンス: 3/5** — `JVStatus` 待機ループ timeout 欠如・WAL 以外の PRAGMA 未投入 **8 連続持ち越し**。

## 警告: 8 連続未着手の優先課題 (臨界域)

UI/predictor/フィルタ調整が 8 回連続。データ層の技術的負債が累積し、本番運用で踏むリスク (週次 RACE 取りこぼし・JVStatus ハング・バルク ingest 遅延) が現実化。`wl_odds_8_20` 切替えでオッズ帯 8〜20 倍に依存度が増した今、**オッズ鮮度の SQL レベル自動除外** が無いままだと「古いオッズで 8〜20 倍判定 → 直前で 20 倍超過」誤発火リスクが拡大する。次回は **必ず** 下記のいずれか 1 件をデータ層改修として組み込むこと。

## 主な改善提案 (優先順、8 連続持ち越し)

1. **`ingested_files` mtime/size カラム追加** — `data/schema.sql` に `mtime REAL, size INTEGER` + `_ensure_column` migration、`is_file_ingested` を「名前 + mtime 一致」判定へ。週次 RACE 上書き恒久ガード。ingest 軸 4 → 5 必須。
2. **`JVStatus` 待機ループ timeout** — `client.py` の `while True` に `JVLINK_DOWNLOAD_TIMEOUT_SEC` (デフォルト 600) と progress cancel 戻り値追加。ハング自動復帰。
3. **DB チューニング PRAGMA** — `db.py:open_db` に `synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-65536` 追加。バルク ingest 2-3 倍速見込み。

## 前回からの差分 (20260511_2345_ae 比)

- JV-Link エラー回復: 5 → 5 (±0)
- ingest idempotency: 4 → 4 (±0) mtime 課題 **8 連続持ち越し**
- データ鮮度管理: 3 → 3 (±0) `wl_odds_8_20` 採用で鮮度自動カット不在の影響度↑
- スキーマ整合性: 4 → 4 (±0)
- リトライ/タイムアウト/パフォーマンス: 3 → 3 (±0) PRAGMA / timeout **8 連続持ち越し**
