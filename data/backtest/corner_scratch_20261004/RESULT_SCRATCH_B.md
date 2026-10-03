# Scratch B (本番の対象行だけの縮小 clone に backfill を当てる) — 結果 (2026-10-04)

- コード: scripts/backfill_corner_orders.py (afeb94d 時点)。clone と比較は scratch_b.py
- 本番 DB は mode=ro で開き、**1 つの読み取りトランザクション** で horse_races と races の対象行
  (JRA、2021-01-01〜2026-06-30) をコピーした。読み取りは 05:18:46〜05:18:51。本番 DB 本体の mtime (10/03 20:00:19) と
  WAL の mtime (10/04 00:05:10) は読み取りの前後で不変
- clone: horse_races 262,885 行 / races 19,056 行。そこに `backfill_corner_orders --apply` を当てた (raw は本番の data/raw/RACE)
- 結果: scratch_b_result.json / scratch_b_backfill_report.json (raw のファイルの一覧と sha256 を含む) / scratch_b.log

## 判定: **合格**

| 項目 | 結果 |
|---|---|
| backfill | applied、更新 262,113 行 = 予定 262,113 行、raw にあって DB に無いキー 0 |
| 適用後の検収 | 合格 (2021-01〜2026-06 の月ごとの `corner_order_4 > 0` は最小 96.56%、順位 > 出走頭数 0 件) |
| 主キーの集合 | 前後で同一 (262,885 行) |
| 変わったセルの列 | **corner_order_1〜4 だけ** (各 262,113 セル) |
| 個別に見た列 | win_odds / odds_fetched_at / odds_dataspec / win_popularity / jockey_code / jockey_short_name / burden_weight / horse_weight / weight_change_sign / weight_change_diff / finish_order / confirmed_order / finish_time / abnormal_code / final_3f / leg_quality_code / data_div / blood_register_num が **全行で完全一致** |
| NULL のまま | 772 行。すべて `data_div = 9` (中止になったレース) で確定着順が無い (走っていないので NULL が正しい) |

2026-05/06 の `odds_fetched_at` の刻印がある行も、`win_odds` と刻印の両方が変わっていない
(SE の再 upsert で起きる「発走前の刻印 + 確定オッズ」の PIT の汚染が、この処理では構造的に起きないことの E2E の確認)。

## 3 名のレビューの後に足したもの (コードの v2、変異 K15〜K21)

- `--apply` では計画・更新・検収を 1 つの書き込みトランザクション (BEGIN IMMEDIATE) で行う (計画と適用が同じ snapshot)
- 前の状態の assert: 対象の行の corner がすでに入っている件数が想定 (既定 0) と違えば止める (本番は 10/04 時点で 0 行)
- 対象外の horse_races の行 (地方・範囲外の日付) の行数とチェックサムを前後で比べ、違えば rollback。この接続の総変更件数が
  更新件数と一致することも検査する (ほかのテーブルに書いていないことの機械的な確認)
- COMMIT の後に `PRAGMA wal_checkpoint(TRUNCATE)` を打ち、結果をレポートに残す
- 失敗時もレポートに内訳 (計画の検収・前の状態など) を残す。`sqlite3.Error` も捕まえる。raw のファイルが 0 件なら明示のエラー
- Scratch B の clone には当日 (10/04) の races が無かったので、開催日の拒否は E2E では空振りだった (単体テストのみ。本番の
  races には 10/04 の JRA 行が 24 件あり、本番では働くことを data-pipeline が確認)

## 本番の backfill について (別のゲート)

本番 DB への実行は 10/05 以降に、非開催の確認 → ai-builder / fresh odds などの書き手の停止の確認 → DB / WAL の静止の確認 →
本番での dry-run → **ユーザーの明示の承認** → `--apply` → 適用後の監査 → ai-builder の互換確認、の順で行う。
`--apply` の開催日の拒否は安全装置の 1 つにすぎず、ユーザーの承認の代わりにはならない。

本番の手順で固定すること (3 名のレビュー):
1. 非開催日である (JRA のカレンダーと races の当日行 0)。`MAIBuilder Live JRA Data` のタスクが無効、fresh odds / auto_predict /
   20:00 の傾向収集バッチの時刻を避ける。keiba.db を開いているプロセスが無い (`fetch_fresh_odds.lock` /
   ai-builder の `fetch-live-jvdata.lock` も確認)。WAL が 0 B で mtime が動いていない。**`keiba.db-shm` の mtime も動いていない**
   (10/04 は WAL 0 B のまま shm だけ 05:44 に動いていた = 誰かが接続を開いた。shm の方が鋭い)
2. main に入ったコードを main checkout から、`--raw-dir C:/Users/kizun/dev/keiba-yosou/data/raw/RACE` を明示して dry-run →
   `db_rows == 262,885`、`planned_updates == 262,113`、`null_remaining_after == 772`、`raw_keys_not_in_db == 0`、`nonnull_before == 0`、
   raw の manifest の sha256 が scratch_b_backfill_report.json と一致
3. ユーザーの明示の承認 → `--apply` → `updated_rows == 262,113`、`acceptance_after.ok`、`outside_before == outside_after`、
   `wal_checkpoint.busy == 0` と `state_after` の WAL 0 B (TRUNCATE の成功時の戻り値は (0, 0, 0) なので、WAL の規模は
   `state_after_commit` で見る)。書き込みトランザクションの保持は 1〜3 分、WAL のピークは 200〜250 MB 以下の見込み (data-pipeline)
4. 適用後の監査: 本番で対象範囲の corner_order_4 が NULL の行が 772 (すべて data_div 9)、月ごとの最小が 0.9655 以上
5. 取り消しの経路 (前の状態 = 対象範囲は全行 NULL を 10/04 に実測): `UPDATE horse_races SET corner_order_1=NULL, ... _4=NULL
   WHERE (race_year||race_month_day) BETWEEN '20210101' AND '20260630' AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10`。
   `--expected-nonnull-before 0` で通った適用に対してだけ有効 (0 以外で上書きした場合はこの SQL では戻せない)。非開催日・書き手の停止の下で
   1 トランザクションで行い、rowcount == 262,885 を確かめる (clone で 0.7 秒、取り消し → 再適用で同じ digest に収束することを data-pipeline が確認)
6. ai_builder_impact は **requires_followup**: ai-builder は keiba.db の corner 列を直接読まないが、`compute_features` の
   `recent_4corner_*` を計算列に持つ。行列のキャッシュ (`out/matrix/`) の鍵は DB の中身を含まないので、backfill の後は
   古いキャッシュ (None / 0) と新しく計算した月 (実値) が混ざりうる。学習の重みは 0 なので予想は不変の見込みだが、キャッシュの
   扱い (版の繰り上げ・破棄) は ai-builder 側の判断が要る。keiba-yosou 側では backfill の前後で `recent_corner_stats` の差の
   規模を記録し、ai-builder のコードには触れない
7. backfill の後、GUI / webapp など常駐しているプロセスを再起動する (`gui/app.py` の `_pred_cache` と `predictor/features.py` の
   `_corner_data_present` は起動中のメモリに古い値 (通過順位なし) を持ち続ける。予想への影響はほぼ無いが、鮮度の原則として)

## v2 のコードでの再実行 (2026-10-04 05:38、a2f33cf)

`scratch_b_result.json` / `scratch_b_backfill_report.json` / `scratch_b.log` は v2 の結果 (v1 の結果は `*_v1.*` に改名して残す)。
本番の読み取り 05:38:20〜24 (本番 DB / WAL は前後で不変)、clone 262,885 行、更新 262,113 行 = 予定、`nonnull_before = 0`、
変わったセルは corner 4 列だけ、監視 18 列は全行一致、適用後の検収は合格 (最小 96.56%)。
clone には対象の行しか入れていないので、対象外の行のチェックサムは 0 行で空振り (同一)。対象外の行についての E2E の証拠は、
本番の実行のレポートの `outside_before` / `outside_after` で取る。clone は WAL モードではないので checkpoint は (0, -1, -1)。

## 本番の実行手順 — 確定版 (2026-10-04、v3 の限定再レビューと外部の指示者の追加要件を反映。上の手順 1〜7 より優先)

対象のコード: main に入った backfill v4 (このブランチ) のマージ後の SHA。**dry-run と apply は同じ Git SHA・同じ script の sha256 で**
行う (main は auto_predict の自動の push で進みうるので、最終レビュー済みの SHA に固定した clean な worktree で実行する)。

1. **非開催の確認**: JRA のカレンダーと、本番の races の当日の JRA 行が 0 (10/04 は 24 件、10/05 は 0 件を確認済み)
2. **書き手の停止の確認**: タスク `MAIBuilder Live JRA Data` と `MAIBuilder Live JRA Data Controller` (Controller が Live を
   再起動しうる) が無効、`keiba-fresh-odds` / `keiba-fresh-odds-healthcheck` / `keiba-morning-odds` / `keiba-auto-predict` /
   `keiba-trend-collect-raceday` (20:00) の実行時刻を避ける。`Get-Process python*,pythonw*,wscript*` を目視し、
   `fetch_fresh_odds.lock` / ai-builder の `fetch-live-jvdata.lock` も確認
3. **静止の確認 (dry-run の前に)**: keiba.db の mtime、WAL 0 B、**shm の mtime** が数分動かない。dry-run (mode=ro) と確認者の
   読み取りの接続でも shm の mtime は動くので、静止の確認は dry-run の **前** に行い、その後に動くのは正常とする
4. **固定した worktree を作る**:
   `git -C C:/Users/kizun/dev/keiba-yosou worktree add --detach C:/Users/kizun/dev/keiba-yosou/.claude/worktrees/backfill-prod <SHA>`、
   `git status --short` が空、`git rev-parse HEAD` と `sha256sum scripts/backfill_corner_orders.py` を記録、
   `python -c "import config; print(config.PROJECT_ROOT, config.CORNER_BYTES_VERIFIED)"` が worktree のパス / True
5. **dry-run** (固定した worktree から、`--db` / `--raw-dir` / `--report` は絶対パス):
   `.venv64/Scripts/python.exe -m scripts.backfill_corner_orders --db C:/Users/kizun/dev/keiba-yosou/data/keiba.db
   --raw-dir C:/Users/kizun/dev/keiba-yosou/data/raw/RACE --report <main>/data/backtest/corner_scratch_20261004/prod_dryrun_<SHA>.json`
6. **計画値の確認 (すべて満たさなければ承認を求めずに中止)**:
   - (a) Scratch B の 335 ファイルが、dry-run の manifest に **部分集合として** 含まれ、sha256 が全件一致
   - (b) 追加のファイルがあれば、その名前の日付は 20260630 より後 (例: 10/04 20:00 以降の週次 SE)
   - (c) `raw_records_used == 309,865`、`raw_keys == 262,113`、`planned_updates == 262,113`、`db_rows == 262,885`、
     `null_remaining_after == 772`、`nonnull_before == 0`、`raw_keys_not_in_db == 0`、`acceptance_planned.ok`
     ((c) が一致すれば、追加のファイルの寄与が 0 であることの機械的な証明になる)
   - 「対象外の更新 0」は dry-run のレポートには無い (対象外の行のチェックサムと接続の変更件数の検査は apply のトランザクションの中でだけ取れる)。
     apply のレポートで確認する
7. **dry-run の結果を提示してユーザーの明示の承認** (SHA・script の sha256・6 の数値・所要時間を添える)。承認の後、**同じ worktree・
   同じ静止の窓で** (20:00 の傾向収集のバッチをまたがない) apply する
8. **apply**: 5 と同じコマンドに `--apply --expected-nonnull-before 0`、レポートは `prod_apply_<SHA>.json`。確認:
   `updated_rows == 262,113`、`acceptance_after.ok`、`outside_before == outside_after`、`wal_checkpoint.busy == 0`、
   `state_after_commit` の WAL の大きさ、`state_after` の WAL 0 B。**rc が 1 でも `result == "applied"` なら COMMIT 済み**
   (例: checkpoint の失敗)。その場合は再び --apply せず、適用後の監査で判断する
9. **適用後の監査**: 本番で対象範囲の corner_order_4 が NULL の行が 772 (すべて data_div 9)、月ごとの最小が 0.9655 以上
10. **常駐プロセスの再起動 (重要)**: GUI / webapp など、`_pred_cache` や `_corner_data_present` をメモリに持つプロセス。
    特徴のキャッシュの鍵に DB の中身が無いので、再起動するまで古い recent_4corner_* を持ち続ける
11. **ai-builder の互換確認** (読み取り側の import と特徴の生成。ai-builder のコードには触れない)、2 つのレポートを main にコミット
12. 取り消しの経路は上の手順 5 のとおり (`--expected-nonnull-before 0` で通った適用にだけ有効)
