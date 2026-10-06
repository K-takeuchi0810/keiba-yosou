# データパイプライン技術者 採点 — 89a3840 「JST 統一」最終ゲート (final)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `89a3840b0ee358a038c5dd4ab29906b9389d0dc7` (branch `jst-date-unify-20260920`、凍結)、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git はすべて `git -C <worktree>`。開始時・終了時ともに HEAD = `89a3840`、`git status --porcelain` = 0 行。main HEAD は `eb875e8` で不変。起動実験はすべて隔離コピー (`git archive 89a3840` → scratchpad `final_dpe\copy89a3840`、`.venv64` だけジャンクション、worktree の 499,712 byte dry-run DB を複製、`.git` 無し・`data/discord_webhook.txt` 無しを確認) の中だけ。本番 DB は `mode=ro` でしか開いていない。main checkout の bat/ps1・Task Scheduler・ai-builder・プロセスには触れていない (タスク定義とプロセス一覧は読み取りのみ)。終了時: 本番 `data/logs` / `data/runtime` / `keiba.db` / `keiba.db-wal` の (path, size, mtime) **3,246 行が開始時スナップショットと完全一致**。差分は `keiba.db-shm` の mtime 1 件のみで、これは開始スナップショットの直後に同じコマンド内で開いた自分の `mode=ro` 接続が触ったもの (サイズ 32,768 不変、`keiba.db` 20,118,552,576 byte / mtime 09/27 20:00 不変、`-wal` 0 byte 不変 = 書き込みなし)。ジャンクションは rmdir 済 (実 `.venv64\Scripts\python.exe` 健在)。

## 判定: PASS (前回 v5 4.4 HOLD → 4.4 PASS)

**理由**:

1. **v5 の HOLD 条件 (外側 off が入れ子 pytest に漏れて test_conftest_guard の 4 本が週次監視でだけ赤くなる) は解除された**。`runtime_guard.py` (f04b38b) が見張りのモードと子 pytest の環境の唯一の出典になり、`child_pytest_env()` が **extra の後に** `KEIBA_RUNTIME_GUARD=strict` を上書きする (`runtime_guard.py:61-67`、変異 CE3 で順序を固定)。`tests/test_conftest_guard.py` は `outer_guard` fixture で **unset と off の両方**を毎回流し (:28-39)、`tests/test_weekly_monitor_guard.py::test_the_real_conftest_guard_tests_pass_under_the_weekly_monitor` (:225-244) が **本物の test_conftest_guard.py を同居させた** mini repo で bat を回して exit 0 を固定する (v5 で要求した case そのもの)。`scripts/mutation_sandbox.py:240` と `scripts/foundation_repair_audit.py:252-259` も同じ関数を使う。
2. **作者の証拠を自分で再現した**。隔離コピーで対象 14 ファイルを strict で流して 277 passed / 1 skipped / 154 s、見張りのテスト 3 ファイルを `KEIBA_RUNTIME_GUARD=off` で流して 41 passed (どちらも rc=0)。作者の全テスト (`data/jst_mutation_20260928/full_strict.txt` / `full_off.txt`) は 2 failed / 969 passed / 9 skipped で、失敗集合が strict と off で完全一致 (`set_strict.txt` と `set_off.txt` の diff → IDENTICAL)。
3. **環境由来とされる 2 件の失敗は本当に環境由来で、改修の退行を隠していない**。(a) `tests/test_f3_phase0_0_eval.py::test_saved_pair_reproduces_frozen_validation_auc` は worktree に無い未追跡ファイル `data/f3_phase0_0/metrics.json` の FileNotFoundError (本番には 07/20 の 6,511 byte が実在)。(b) `tests/test_placeholder_cleanup.py::test_live_database_has_no_placeholder_violations` は assert 23 == 0。本番 DB を mode=ro で開いて `db.count_horse_num_violations` = **0**、worktree の dry-run DB では horse_num=00 の行が 2026-09-27 に **23 行**、と自分で両方を実測した。どちらのテストも改修が触っていない経路 (`db.py` / F3 評価) を読むだけで、`jst.py` / `config.py` / bat / ps1 / conftest を通らない。したがって隠れる退行は無い。ただし (b) が「9/27 を過ぎた瞬間に違反に化けた」仕組みは `db.py:239` の `today = today or date.today()` であり、**この時計は `docs/CLOCK_LEDGER.md` に載っていない** (改善提案 1)。
4. **本番の起動経路 (wscript → vbs → ps1 → bat → Python) を隔離コピーで実走させた**。`C:\Users\kizun\AppData\Local\ScheduledTaskRunner\run-scheduled-task-hidden.vbs` (本番と同じ) 経由で `-DryRun -TimeoutSeconds 300` → `data/logs/auto_predict_daily_20260928_dryrun.log` の先頭行が `run date 20260928 (JST) dryrun=[1] cwd=<コピー>`、次いで `[DRY-RUN] skip fetch_full / fetch_mining (no DB writes)`、coverage は `--notify` 無し (コピーに JSONL が無いので gap 警告 = bit 1)、`auto_predict --dry-run` は「出馬表なし」で 0、bat `done exit=1`、watchdog `finish pid=... exit=1`、**wscript の終了コードも 1** (bit が最後まで届く)。`auto_predict_daily_rundate_stderr.txt` は 0 byte。Discord には何も送っていない (webhook 無し + dry-run 遮断)。
5. **改修は取得 / ingest / schema / raw に触れていない** (`git diff --stat d134b3b..89a3840` に `db.py` / `jvlink_client/**` / `data/schema.sql` / raw 形式は含まれない)。main が merge-base 以降に触ったファイルと branch が触ったファイルの共通集合は **空** (comm -12 で 0 件)、`git merge-tree --write-tree main 89a3840` は衝突なしで tree `f400574` を返した。ff / merge commit のどちらでも安全。

**停止条件の該当**: なし (下の表)。

**根拠ファイル**: `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\runtime_guard.py:40-67`、`...\tests\conftest.py:44-97`、`...\tests\test_conftest_guard.py:28-59`、`...\tests\test_weekly_monitor_guard.py:111-119,225-244,247-263`、`...\weekly_monitor.bat:30-51`、`...\scripts\auto_predict_daily.bat:9-36,73-80`、`...\scripts\run_auto_predict_daily.ps1:43-71,73-107`、`...\scripts\auto_predict.py:301,332,372,392,401-402`、`...\config.py:260-317,374-379`、`...\jst.py:47-72`、`...\scripts\mutation_sandbox.py:45-46,236-244`、`...\docs\CLOCK_LEDGER.md:87-132`、`C:\Users\kizun\dev\keiba-yosou\db.py:239`、`C:\Users\kizun\dev\keiba-yosou\docs\EXTERNAL_DEPENDENTS.md:39-67`、`C:\Users\kizun\dev\keiba-yosou\data\jst_mutation_20260928\` (run13_result.txt / full_strict.txt / full_off.txt / set_strict.txt / set_off.txt / jst_spec_v7.py)、`C:\Users\kizun\AppData\Local\ScheduledTaskRunner\run-scheduled-task-hidden.vbs`

## 対象・改修タイプ

- 対象: `d134b3b..89a3840` 32 commits / 40 files (+3,920 / -70)。Python 本体は `jst.py` (新規 72 行)、`config.py` (+67: `_require_daystamp` / `OPEN_WINDOW_BOUNDS` / `sealed_window_started(today=, *, now=)`)、`runtime_guard.py` (新規)、`scripts/auto_predict.py` (JST 化 + 生成失敗も最終確認の対象)、`scripts/fetch_mining.py`、`scripts/notify_dedup.py`、`web/generator.py`、`web/publish_safety.py` (import 漏れ修正)、`gui/app.py` (1 行)、`scripts/mutation_sandbox.py` (新規 315 行)。運用: `scripts/auto_predict_daily.bat`、`scripts/run_auto_predict_daily.ps1`、`weekly_monitor.bat`、`tests/conftest.py`。tests 14 files。
- 改修タイプ: **type-D 相当 (運用層 + テスト基盤 + 日付の単一出典。取得 / ingest / 予測ロジック不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)** で、fresh odds を総合判定のゲートにしない。参考実測 (読み取り): `keiba-auto-predict` Ready / 08:00・09:00・11:00 / LastRun 09/27 11:00 result 0 / **NextRun 09/28 08:00** (本日、非開催日)、`keiba-yosou-weekly-monitor` Ready / LastRun 09/27 10:00 result 0 / NextRun 10/04 10:00、`keiba-fresh-odds` Ready / LastRun 09/27 19:00 result 0、`MAIBuilder Live JRA Data` **Disabled** (LastRun 09/27 18:05)。`fetch-live-jvdata` の残留プロセスは 09/27 08:48 起動のものが残っている (読み取りのみ、触っていない)。

## 総合: 4.4 / 5 (前回 v5 4.4、変化なし。判定は HOLD → PASS)

## 項目別

- **bat 起動経路の堅牢性 (RUNDATE 決定・縮退・exit code): 4.5/5 (前回 4.5、変化なし)** — 実走で確認: `cd /d "%~dp0.."` により別 cwd から起動しても自分の repo で動く (ログの cwd=)、RUNDATE は Python (`jst.current_jst_daystamp`) から取り `findstr /r /x` の 8 桁パターンで検査、取れなければ DATE_FAILURE.log + exit 8 + (本番のみ) Discord (:date_failure)、bit 1/2/4 が bat → ps1 → vbs → wscript まで届く (実走 exit=1、テスト test_the_exit_code_reaches_the_scheduler[True] / test_the_date_failure_reaches_the_scheduler)。08:00 / 09:00 / 11:00 の各起動で bat の RUNDATE と auto_predict の `today = current_jst_date()` (:301) は同じ JST 時計から出るので、JST 00:00 をまたがない限り一致する。`_is_final_attempt` も JST (:204-206)。**残り (減点)**: 成功時も `data/logs/auto_predict_daily_rundate_stderr.txt` (0 byte) を毎回書く / `weekly_monitor.bat:5` の RUNDATE は `date.today()` のままで失敗検出も無い (台帳 C4、main 反映後に日次 bat と同じ形へ)。
- **日付決定の単一出典 / 境界一貫性: 4.5/5 (前回 4.5、変化なし)** — `jst.py` は naive を拒否し (`utcoffset() is None` まで見る)、now 注入可。`config._require_daystamp` は 8 桁 + strptime で実在日付を要求し、`guard_analysis_window` は OPEN_WINDOW_BOUNDS (00000000 / 99999999) だけを開いた端として許す (実測: 20260931 → ValueError、開いた端 → 通過)。`sealed_window_started(today="")` は ValueError (変異 F6 「空文字の today を今日扱い」は **等価変異** — 変異を当てたコピーで today="" → 依然 ValueError、None → True、"20260928" → True と実測。94/95 は実質 94/94)。**減点理由**: A4 / A5 / A7 / A8 (fetch_fresh_odds / check_fresh_odds_health / generator と GUI の鮮度判定の naive now) は設計どおり未着手。加えて **`db.py:239` `horse_num_violation_counts` の `date.today()` が台帳に無い** (B 級: 掃除カナリア・`tests/test_placeholder_cleanup.py`・`scripts/monitor.py` の判定日を決める)。
- **依存 / 起動コスト / 外部依存 (ai-builder) 互換: 4.5/5 (新設)** — `EXTERNAL_DEPENDENTS.md` 「確認のしかた 1」を 89a3840 の tree に対して実行: `.venv32` で `db.open_db` / `JVLinkClient` / `_split_records` / `ingest_all` / `parse_av,cc,jc,tc,we` の import **成功**、`.venv64` で `db.open_db_readonly` / `predictor.rules.predict_race,is_tentative` / `predictor.features.compute_features,horse_past_runs` / `predictor.sire_lines` / `scripts.backtest.list_races,horses_for_race,get_payout_row,payout_from_row,popularity_config,race_odds_untrusted` / `web.codes.track_type,track_name` の import **成功**。`jst` を import するのは `config.py` (関数内 lazy) / `gui/app.py` / `scripts/auto_predict.py` / `scripts/fetch_mining.py` / `scripts/notify_dedup.py` / `web/generator.py` / `web/publish_safety.py` で、ai-builder が import する一覧には無い。ai-builder が到達しうる唯一の挙動差は `scripts.backtest.list_races` (live=False) → `guard_analysis_window` が **実在しない 8 桁日付 (例 20260931) を新たに拒否する**こと。ai-builder は DB の開催日 / 実在日付を渡している (`keiba_bridge.py:146`、`matrix_daily.py:70`、読み取りのみ) ので実害は無い。**5 にしない理由**: この契約確認がテストとして repo に固定されておらず、今回も人手 (本 scorecard) で実行した。
- **退行ガード / テスト / 変異: 4.5/5 (前回 4、+0.5)** — run13_result.txt: 95 変異中 94 KILLED / 1 SURVIVED (F6、等価) / 0 REFUSED / 0 ABORTED、開始 01:07:48 → 終了 02:26:20。撃墜側が固定したもの: 見張りの既定 strict / 未知の値 fail-fast (W1, W2, CE5) / 子は常に strict (CE1, CE3, CE4, W7) / PYTHONPATH 落とし (CE2) / 週次の bit 2 と stderr 合流 (WB1-4) / 枠の本番検査 (X1-X12, R1-R9, Xc, Xj, Xc2) / bat の全分岐 (B1-B17) / ps1 (P1-P4, A1-A3, E1-E2) / 封印の時計 (S1-S9, C1-C2, F1-F7b, U1-U3) / generator と publish_safety (G1-G3, PS1-PS2)。全テストの失敗集合が strict / off で一致 (2 件、いずれも環境)。自分の再実行: strict 277 passed / off 41 passed。**減点理由**: 全テストの実行環境 (worktree の dry-run DB + metrics.json 不在) のせいで「緑」を人が読み替える必要があった。本番で流す週次監視 (10/04 10:00) では両方とも通る条件 (metrics.json 実在、violations 0) を今回は実測したが、test_live_database_has_no_placeholder_violations は `db.py:239` の時計次第で日曜朝の過渡 00 行を拾いうる (改修前からの性質)。
- **反映運用 / runbook: 4.0/5 (前回 4、変化なし)** — runbook (`CLOCK_LEDGER.md:87-132`) は **十分かつ安全**: ff / merge commit で `jst.py` と bat / ps1 を同時に入れる指示 (bat だけ cherry-pick すると全起動 exit 8)、最初の 08:00 の後の 4 点、最初の日曜の後の 1 点、確認コマンド、記録表。本日 09/28 (月) は非開催日で NextRun 08:00 → auto_predict は「出馬表なし」で 0、coverage `--last 1` は本番 JSONL の 09/27 を見る (fresh odds は 09/27 19:00 まで result 0)。**減点理由 (3 点、いずれも 1 行)**: (i) マージ後に本番で dry-run を打つ場合、`-LogDir` を渡さないと本番の `auto_predict_watchdog.log` に dryrun=True の start / finish 行が混ざり、runbook 項目 3 「最後の finish 行」の読みが 1 回ぶんずれる。書くのはそれと `auto_predict_daily_<日付>_dryrun.log` / `rundate_stderr.txt` だけ (`auto_predict --dry-run` は :401 で生成前に return、coverage は読むだけ、Discord は --notify 無し + watchdog 遮断) なので害は無いが、`-LogDir <本番外>` を推奨として書き足すべき。(ii) CLAUDE.md 必須ルール 5 (main `3e90a84`) により、マージコミットかこの記録に `ai_builder_impact` が要る (下に記す)。(iii) `db.py:239` の台帳漏れ。

## ai_builder_impact (CLAUDE.md 必須ルール 5)

**`ai_builder_impact: none`** — 理由: (1) 改修は `db.py` / `jvlink_client/**` / ingest / DB schema / raw の保存形式 / JV-Link の初期化・終了 / `.venv32` の中身のいずれも変更しない (diffstat で確認)。(2) `EXTERNAL_DEPENDENTS.md` の読み取り側関数一覧 (`predictor.rules` / `predictor.features` / `scripts.backtest` / `web.codes`) の名前と戻り値も変更していない。(3) 「確認のしかた 1」の import を 89a3840 の tree に対して `.venv32` / `.venv64` の両方で実行し成功。(4) 到達しうる唯一の差 (`list_races` → `guard_analysis_window` が実在しない 8 桁日付を拒否) は、ai-builder が実在日付しか渡さないので効かない。(5) 稼働中の残留プロセスは旧コードを既に import 済みで、マージの影響を受けない。新規起動は `MAIBuilder Live JRA Data` が Disabled のため次の開催日の Controller 判断まで無い。**マージコミットの本文に 1 行 (`ai_builder_impact: none — db.py / jvlink_client / schema / raw 形式に変更なし、import 契約を 32/64bit で確認`) を書くこと**。

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides: N/A (backtest artifact を生成しない改修)
- [x] baseline paired 比較: N/A
- [x] market_snapshot counts / payout 欠損: N/A
- [x] P25 fresh odds スケジューラ / coverage JSONL / bonus_candidate: N/A (type-D 相当)。参考: 3 タスクとも Ready / result 0
- [x] 専門領域: partial write → なし (取得 / ingest 不変)。無限待ち → 日次 1,200 s / 124・125、週次 600 s / 124 健在。lock 未掃除 → 該当なし。0 byte raw → 該当なし。dry-run が Discord に届く経路 → 遮断 (bat `if not defined DRYRUN`、ps1 `Send-WatchdogAlert` 冒頭、auto_predict の `if not args.dry_run` ×3、実走で不達)。テストが本番運用ログ / DB を汚す経路 → 実測ゼロ (3,246 行一致、-shm の mtime は自分の ro 接続)。**本番の定期実行が新たに失敗する経路 → なし** (v5 の 4 本は解消、全テスト strict / off 一致)。マージ衝突 → なし (merge-tree 衝突なし、共通ファイル 0)
- [x] テスト: 作者 strict 969 passed / off 969 passed (失敗 2 は環境、両方を本番側で反証済み)。自分 strict 277 passed / off 41 passed

## 反証の試み (すべて隔離コピー、本番は読み取りだけ)

| # | 反証シナリオ | 結果 |
|---|---|---|
| F1 | 本番 DB (ro) と worktree DB の 00 行 / count_horse_num_violations | 本番 **0** 違反、worktree の dry-run DB は 2026-09-27 に **23 行**。環境由来を確認 |
| F2 | metrics.json の実在 | 本番 `data/f3_phase0_0/metrics.json` 6,511 byte (07/20)、worktree に無い。環境由来を確認 |
| F3 | 全テストの失敗集合 strict vs off | set_strict.txt / set_off.txt の diff → IDENTICAL (2 件) |
| F4 | 対象 14 ファイルを strict で再実行 | 277 passed / 1 skipped / rc=0 |
| F5 | 見張りのテスト 3 ファイルを off で再実行 (週次監視の形) | 41 passed / rc=0 (v5 で赤かった 4 本を含む) |
| F6 | 変異 F6 の等価性 | 変異を当てたコピーで today="" → ValueError (変異前と同じ)。等価変異 |
| F7 | 本番と同じ起動器 (wscript → vbs → ps1 → bat) で dry-run | JST 日付ログ / cwd / bit 伝搬 (wscript exit=1) / 取り込み・通知なし |
| F8 | ai-builder の import 契約 (32bit 取り込み側 / 64bit 読み取り側) | どちらも import 成功。guard_analysis_window は実在日付と開いた端を通し 20260931 を拒否 |
| F9 | main との衝突 | 共通変更ファイル 0、merge-tree 衝突なし |
| F10 | 全実験前後の本番 data/logs / data/runtime / DB | 3,246 行一致。keiba.db / -wal のサイズ・mtime 不変 |

## 主な改善提案 (優先順)

1. **`docs/CLOCK_LEDGER.md` に `db.py:239` (`horse_num_violation_counts` の `date.today()`) を B 群として追記** (マージ前に文書 1 行で可)。`scripts/monitor.py` のカナリアと `tests/test_placeholder_cleanup.py` の判定日を決める時計で、今回の環境失敗はこの時計が 9/27 を越えて起きた。
2. **runbook にマージ後 dry-run の作法を 1 行**: `powershell -File scripts\run_auto_predict_daily.ps1 -DryRun -LogDir <本番外>` (本番 watchdog log に dry-run の行を混ぜない)。
3. **マージコミット本文に `ai_builder_impact: none` を記す** (上の理由つき)。
4. `weekly_monitor.bat:5` の RUNDATE を日次 bat と同じ JST + 失敗検出の形へ (C4、main 反映後)。
5. 成功時の 0 byte `auto_predict_daily_rundate_stderr.txt` を消す (or 失敗時だけ残す)。
6. ai-builder の import 契約 (`EXTERNAL_DEPENDENTS.md` 「確認のしかた 1」) をテストとして固定する (次の db / jvlink_client 変更の前に)。
7. A4 / A5 / A7 / A8 の naive now (台帳どおり、別フェーズ)。

## 次アクション

1. main に **ff merge か merge commit** で `89a3840` を入れる (`jst.py` と bat / ps1 を同時に)。コミット本文に `ai_builder_impact: none` を書く。
2. 本日 09/28 08:00 の起動後に runbook 1-4 を確認して `CLOCK_LEDGER.md` の表に記入 (非開催日なので auto_predict は「出馬表なし」で exit 0 の見込み、LastTaskResult 0)。
3. 10/04 (日) 10:00 の週次監視後に runbook 5 (`runtime_guard=off pytest_exit=0 full_output=data\monitor_runs\weekly_pytest_20261004.log`) を確認。
4. 改善提案 1-3 は文書だけなのでマージと同じセッションで。

## 前回からの差分

- v1 (`37eaf61`) 3.8 HOLD → v2 (`1baab6c`) 4.2 PASS → v3 (`a9f3969`) 4.7 PASS → v4 (`27a260e`) 4.3 HOLD → v5 (`209b636`) 4.4 HOLD → **final (`89a3840`) 4.4 PASS**。
- v5 の解除条件 (子 pytest で KEIBA_RUNTIME_GUARD を strict に / 本物の test_conftest_guard.py を同居させた週次 case / 全テストを off で流して strict と差分ゼロ) は **3 つとも成立** (f04b38b + 作者の full_strict / full_off + 自分の再実行)。
- 項目別: bat 4.5→4.5、単一出典 4.5→4.5、依存 5→4.5 (外部依存互換の観点を加えて再定義)、テスト 4→4.5 (+0.5)、反映運用 4→4。-0.3 以上の低下項目なし。
