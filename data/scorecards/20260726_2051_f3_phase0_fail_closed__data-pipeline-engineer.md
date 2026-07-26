# データパイプライン技術者 採点 — F3 Phase 0 fail-closed

## 判定: PASS

**理由**: type-C（ledger / schema migration）を中心に、type-D/CLI の consumer 契約を
連動させた改修。blocked 空runは冪等な sentinel として残り、旧DB行は
`full` / `[]` へ後方互換 migration、Pythonの生成・ledger境界では mode/reason が
閉じている。monitorも仕様どおり observation/blocked をBrier母集団から除外せず、
race単位の内訳を併記する。採用を止めるデータ破壊・silent fallback・schema不整合は
再現しなかった。

**根拠ファイル**: `db.py:199-203`, `db.py:745-809`,
`data/schema.sql:626-651`, `predictor/rules.py:34-64`,
`predictor/rules.py:276-327`, `scripts/monitor.py:88-130`,
`tests/test_db_migration.py:54-75`, `tests/test_prediction_log.py:52-99`,
`tests/test_prediction_consumers.py:48-85`

**次アクション**: `prediction_log` の直接SQL経路にも mode CHECK と
`error_reasons` JSON妥当性を付け、monitorに `predict_race` 例外件数を明示する。

## 総合: 4.5 / 5（前回 4.1 → 今回 4.5、差分 +0.4）

前回は `20260720_1905_f3_morning_anchor__data-pipeline-engineer.md` の 4.1 / HOLD。
今回のPASSは fail-closed実装の採用可否であり、前回HOLDだった「開催日の実JV-Link取得」
受入を解除するものではない。

## 改修タイプとスコープ

- **type-C**: `db.py` / `data/schema.sql` のprediction ledgerと旧DB migration。
- **隣接type-D/CLI**: `web/generator.py` / GUI / CLI / monitorへの構造化状態伝播。
- JV-Link/raw ingest本体は差分外。既存回復性の非回帰だけを確認した。
- P25のbacktest採用、収益性、market snapshot Required Evidenceは **N/A**。

## 項目別

### 1. JV-Link エラー回復: 4.6 / 5

- 今回差分外だが、`fetch_realtime` はJVRTOpen `rc=-1`を正常なno-dataとして空結果で返す
  (`jvlink_client/client.py:476-503`)。
- transient open rcは環境変数ベースの回数/遅延でretryし、JVGets `rc=-3` は
  `JVLINK_REALTIME_NO_DATA_SEC`（既定30秒）、2秒heartbeat、callback cancel経路を持つ
  (`jvlink_client/client.py:450-474`, `jvlink_client/client.py:541-590`)。
- 読取区間は `finally` で `JVClose` を実行する
  (`jvlink_client/client.py:621-629`)。今回COM実機runはしていないため満点ではない。

### 2. ingest idempotency / ledger二重取込防止: 4.7 / 5

- 既存ingestは `only_files` / `modified_since` で同名更新を強制再取込し、
  指定外の未取込ファイルも回収する (`jvlink_client/ingest.py:294-317`,
  `jvlink_client/ingest.py:358-371`)。upsert主キーも維持される。
- blockedかつ0頭でも `horse_num=''` のsentinel 1行を生成し、同一generated_at/raceを
  2回書いてもPK + `INSERT OR REPLACE` により1行に収束した
  (`db.py:773-799`、監査実測 `sentinel_rows=1`)。
- observation/fullは従来どおり馬単位、blocked空runだけsentinelとなるため、
  「縮退したが行が0で監査不能」を解消した。既存 `prediction_accuracy` は
  `mark='◎'` とhorse_races JOINを使うため、空馬番sentinelを成績件数へ混入させない
  (`scripts/prediction_accuracy.py:37-58`)。
- sentinelの行種別専用列やDDL制約はなく、将来のledger consumerには
  `horse_num=''` の知識が必要な点を0.3減点。

### 3. データ鮮度 / mode監視: 4.5 / 5

- live予測は既存PIT cutoffと `max_odds_age_min` を使い、NULL/T-10超過をE03、
  30分超をE02として構造化する (`predictor/rules.py:308-332`)。新しい閾値は発明していない。
- monitorは確定raceごとにmodeを1回、reasonを1回数え、予測レコード自体は
  observation/blockedでも従来どおりBrierへ残す
  (`scripts/monitor.py:91-130`)。これは指示書の「除外判断はユーザに委ねる」と一致する。
- consumer focused testでobservation 1 race / E02 1件 / Brier 1 recordを再現した
  (`tests/test_prediction_consumers.py:48-85`)。
- `predict_race` の予期せぬ例外はwarning後continueされ、mode分母にも失敗件数にも残らない
  (`scripts/monitor.py:103-107`)。残るsilent undercountとして0.5減点。

### 4. スキーマ整合性 / migration: 4.4 / 5

- 新規DB定義と既存DB補修の双方に
  `prediction_mode TEXT NOT NULL DEFAULT 'full'` /
  `error_reasons TEXT NOT NULL DEFAULT '[]'` がある
  (`data/schema.sql:645-646`, `db.py:202-203`)。
- 実DBの現行 `prediction_log` CREATE SQLと実在1行をmemory DBへ複製して
  `init_db()` を実行し、行数1のまま `full` / `[]` へ移行することを再導出した。
  focused migration/ledger testsもgreen。
- 実DBは指示どおり未変更で、新列はまだ存在しない。最初のwriter `open_db()` が
  migrationを担い、read-only monitorはmigrationしない設計 (`db.py:140-186`)。
- Python APIは未知mode/reason、`full+reason`、非fullのreason欠落に加え、
  `observation+E04` のようなseverity矛盾も拒否する
  (`predictor/rules.py:55-73`, `db.py:764-781`)。
- ただしDDLに `CHECK (prediction_mode IN (...))` / `json_valid(error_reasons)` はない。
  memory DBへの直接SQLで `invalid-direct-sql` / `not-json` が1行入ることを反証確認した。
  closed contractがPython境界依存のため0.6減点。

### 5. リトライ・タイムアウト・性能 / DB非変更: 4.2 / 5

- `connect()` はWAL、foreign_keys、busy_timeout=5000を設定し、
  monitorは `open_db_readonly()` のquery_only接続を使う
  (`db.py:127-183`, `scripts/monitor.py:94`)。
- 実DBは `journal_mode=wal` / `busy_timeout=5000`。19,488,182,272 bytes、
  `prediction_log=2,836`行。監査開始/終了とも main DBのsize、mtime
  (`2026-07-26 11:00:19 UTC`)、行数、旧18列が一致し、DB差分は0。
  開始時SHA-256は
  `3C5CD0BD1C133F2E5FEE358DC2075A34CAB973AFBEA1E47843B49C4C4A0DD075`。
- migrationは定数DEFAULTの2列追加で、既存2,836行の値をPythonループ更新しない。
  mode/reasonは各馬行にJSONを重複保存するが、現ledger規模では問題にならない。
- 本番19GB DBへのmigration実行は「DBの中身を変更しない」ガードレールにより未実施。
  実schema cloneで代替検証したためPASS可能だが、実ファイルのlock時間は未実測。

## 停止条件チェック

- [x] type-Cのschema新規作成と旧DB後方互換migrationを確認。
- [x] blocked空runが監査ledgerから消えず、同一run再実行で増殖しない。
- [x] Pythonの生成境界・ledger境界でmode/reason列挙が閉じている。
- [x] monitorはmode/reason内訳を出し、仕様に反する暗黙除外をしない。
- [x] 実DB・raw・production artifactを変更していない。
- [x] focused 62 passed / 0 failed（1.95秒）。
- [x] P25固有のpaired baseline / market_snapshot / payoutゲートはtype-C/DのためN/A。
- [x] 専門領域のFAIL / NOT_EVALUABLE条件に不抵触。

## 反証の試み

1. **blocked空runが消える/二重化する** — 同一keyを2回挿入しsentinel 1行を実測。
   主張は成立。
2. **旧DB行がNULL化・破壊される** — 実DBのCREATE SQL + 実在1行cloneでmigrationし、
   行数1、`full` / `[]` を実測。主張は成立。
3. **自由文字列が混入する** — Python APIはValueErrorで拒否したが、直接SQLは通った。
   アプリ契約は成立、DB単独の閉鎖性は不成立。
4. **monitorが縮退runを隠す** — observationをBrierへ1件残しつつmode/reason各1件を実測。
   主張は成立。予期せぬ例外件数だけは未観測のまま。

## 実測メモ

- `git log --stat -3`: baseは `2d6e6f6`、直前2件はfresh odds healthcheck修正。
- raw先頭: `0B12`, `0B13`, `0B14`, `0B17`, `0B31`, `BLOD`, `COMM`, `DIFN`,
  `HOSE`, `HOYU`。例: 0B12=5,444,043 bytes、DIFN=1,130,259,969 bytes。
- `data/fetch_state.json`: RACE=`20260725112820`、MING=`20260713133747` 等を確認。
- focused:
  `test_prediction_fail_closed`, `test_prediction_consumers`, `test_db_migration`,
  `test_prediction_log`, `test_filter`, `test_template_render`,
  `test_auto_predict_artifacts` = **62 passed**。

## 主な改善提案

1. **DB境界も閉じる** — 新規schemaにはmode CHECKとJSON妥当性を追加し、既存DBは
   insert前/読出し時validatorを共通化する。`data/schema.sql:645-646`。
2. **monitor失敗分母** — `predict_race` exceptを
   `prediction_failures` / reason相当の明示カウンタへ加える。`scripts/monitor.py:103-107`。
3. **sentinel契約を明示** — ledger reader用helperで `horse_num=''` をrun status行として
   分離し、通常馬件数へ混ぜない。`db.py:773-799`。

## 前回からの差分

- JV-Link回復: 4.6 → 4.6（変更なし）。
- ingest/二重防止: 4.5 → 4.7（blocked空runの冪等sentinel追加）。
- 鮮度/no-op監視: 3.2 → 4.5（PIT/stale理由とmode/reason集計を構造化）。
- schema/DB競合: 4.4 → 4.4（後方互換migration追加、DB CHECKは未実装）。
- retry/性能/観測性: 3.8 → 4.2（readonly monitorとDB不変を確認、例外分母は未記録）。
- 前回判定HOLD → 今回PASS。前回の開催日end-to-end受入HOLDは別課題として継続。
