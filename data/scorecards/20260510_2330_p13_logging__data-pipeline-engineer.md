# データパイプライン技術者 採点

## 総合: 4.0 / 5 (前回 3.8 → 4.0, +0.2)

P1-3 で `jvlink_client/client.py` の 9 箇所の `except Exception: pass` がすべて `logger.warning(..., exc_info=True)` に置換され、`ingest.py:196` の運用パスエラーも `print` から `logger.error(..., exc_info=True)` へ移行。COM 失敗が **サイレントから観測可能に** なった点を JV-Link エラー回復軸に反映し +1。他軸はコード不変につき据え置き。

## 項目別

- **JV-Link エラー回復: 5/5** — `client.py:131/156/184/273/314/372/400/413/544` の例外握り潰しが全て `logger.warning(..., exc_info=True)` に統一。`TRANSIENT_OPEN_RCS` リトライ・rc=-1 正常扱い・rc=-3 タイムアウト・finally `JVClose` の既存構造はそのままで、JVClose / JVStatus / FreeMemory 失敗が stderr とハンドラ経由で必ず追跡可能になった。サイレント失敗ゼロは同種アプリの中でも上位水準なので満点。
- **ingest idempotency / 二重取込防止: 4/5** — `ingest.py` のロジックは未変更だが、`196` の `print` が `logger.error("ingest failed: %s", f.name, exc_info=True)` に置換され、ファイル単位 ingest 失敗の特定が容易に。`is_file_ingested` + `INSERT OR REPLACE` の冪等性は維持。`ingested_files` に mtime/hash を持たない弱点は据え置きで満点ではない。
- **データ鮮度管理: 3/5** — `db.py` 不変、SQL 層 freshness フィルタも依然欠落。本改修は観測性のみで鮮度パイプラインに直接寄与せず据え置き。
- **スキーマ整合性 / マイグレーション: 4/5** — `data/schema.sql` / `_ensure_column` 経路ともに無変更。`schema_version` 体系欠如も継続。
- **リトライ・タイムアウト・パフォーマンス: 3/5** — `JVLINK_OPEN_RETRIES` 系 env・WAL/FK は不変。`PRAGMA synchronous=NORMAL` / `temp_store=MEMORY` / `cache_size` チューニング欠如、3000+ 規模ベンチ未確認も未対処。`logger.warning` は I/O コストほぼ無視可で性能影響なし。

## 観測性追加が JV-Link エラー回復軸に与える影響

JV-Link COM は rc を握り潰すと「DL は終わっているはずなのに DB が更新されない」「RT 取得後に JVClose が黙って失敗し次の Open が rc=-201 で詰まる」のような、再現困難なサイレント不整合を生む。9 箇所すべてが `exc_info=True` 付き logger.warning に揃ったことで、運用中に GUI ログ / stderr / 任意 handler から **どの dataspec のどのフェーズで COM が落ちたか** が pid / traceback 単位で追える。回復ロジック (リトライ・finally・rc 分岐) 自体は同じでも、「失敗を観測してから次手を打てる」状態は観測不能から大幅前進で 4 → 5 に引き上げる根拠となる。残課題は `JVStatus` ループに timeout / cancel が無いことだが、これも今後ハングが起きれば warning ログから即座に切り分けられる土台が整った。

## 主な改善提案 (優先順)

1. **`ingested_files` に mtime/size カラム追加** — 未着手 3 連続持ち越し。`data/schema.sql` の `ingested_files` に `mtime REAL, size INTEGER` 追加 + `_ensure_column` migration、`is_file_ingested` を「名前一致 かつ mtime 同一」判定へ変更し、週次 RACE 同名上書きの取りこぼしを恒久ガード。
2. **`JVStatus` ダウンロード待機ループに timeout / cancel** — 未着手。`client.py` の `while True` に `JVLINK_DOWNLOAD_TIMEOUT_SEC` (デフォルト 600) と `on_progress` コールバック戻り値による cancel を追加。今回の logger 整備でハング検知は容易になったので、次は自動復帰を入れたい。
3. **DB チューニング PRAGMA** — 未着手。`db.py:open_db` に `PRAGMA synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-65536` 追加で週次バルク ingest 2-3 倍速見込み。

## 前回からの差分

- JV-Link エラー回復: 4 → 5 (+1) 9 箇所全ての例外握り潰しを `logger.warning(exc_info=True)` 化、サイレント失敗ゼロ達成
- ingest idempotency: 4 → 4 (±0) ロジック不変、ただし `print` → `logger.error` で運用観測性のみ向上
- データ鮮度管理: 3 → 3 (±0) `db.py` 無変更
- スキーマ整合性: 4 → 4 (±0) `schema.sql` 無変更
- リトライ/タイムアウト/パフォーマンス: 3 → 3 (±0) PRAGMA 追加なし

前回優先課題 3 件 (mtime / JVStatus timeout / DB PRAGMA) は依然 3 連続持ち越しだが、観測性土台が整ったので **次の改修で JVStatus timeout に着手すれば回復軸が完成形**。データ層スコアを 4.0 超に押し上げるには ingest 層 (mtime) 着手が必須。
