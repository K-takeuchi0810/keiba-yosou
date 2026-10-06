# 検証プロセス監査人 (最終ゲート) 採点 — JST 統一 v3 (a9f3969, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `a9f3969` 固定、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git は全て `git -C <wt>`、Read/Grep は worktree 絶対パス。変異は **今回追加された枠 `scripts/mutation_sandbox.py` を通して** 実行 (隔離コピー 2 つ = `git archive a9f3969 | tar -x` → scratchpad `gate3_validation` / `gate3_validation_b` + `.venv64` ジャンクション + worktree の小 DB (499,712 B) を実ファイル複製)。worktree・本番 checkout のファイルは未編集、SHA 不動、Task Scheduler 未操作、Discord 未送信 (コピーに `data/discord_webhook.txt` 無し + 通知はスタブ差替)、本番 bat 未起動。前回 v2 (1baab6c、PASS 4.1) からの差分 10 commit (`git -C <wt> log 1baab6c..a9f3969`、11 files / +980 −22) を中心に確認し、ゼロからの再点検はしていない。

## 判定: HOLD (最終ゲート — 前回宣言 (2) の執行。CHAT 指定の必須項目 A〜H はすべて成立)

**理由**: CHAT 指定の必須確認 A〜H は **全件成立** (下表)。前回の生存変異 S-f / B-10 / P-4 は **全て撃墜** を独立変異で確認。是正の中身は一次データ (テスト・実経路 dry-run・変異) で裏が取れており、検証設計上の停止条件には抵触しない。しかし前回 v2 の次回宣言 (2)「**M2''/M14' (generator 既定 `today` の意味テスト) が依然素通りなら HOLD 上限**」を執行する: 今回 `web/generator.py:318` の `today = current_jst_date()` を「別名経由のローカル時計」(M2'') と「1 日前」(M14') に、`web/publish_safety.py:60` を `date.today()` (PS') に変えた 3 変異は、generator / publish_safety を触る 11 テストファイルで **3/3 生存** (枠 `mutation_sandbox` で実行、fresh .pyc)。台帳 (H) 自身が「AST ガードだけを防御線にしない。見張り対象のモジュールには挙動のテストを必ず一緒に置く」と書いたのに、既にガード対象の `web/generator.py` にその挙動テストが無い状態のまま。この 1 点だけで PASS を保留する。**解除条件は小さい** (下「次アクション」1)。宣言の不執行は監査の信頼を毀損するため、スコープ (A〜H) 外を理由に免除しない。
**改修タイプ**: type-B/C (運用基盤: 時計・bat・ps1・変異テストの枠。predictor / backtest / GUI 非接触)。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN) は **N/A (対象外)**。他 agent 統合: v3 の sibling 判定は本 scorecard 執筆時点で未提出 (v2 は code-quality PASS 4.0 / data-pipeline PASS 4.2 条件 3 件)。v3 sibling に FAIL / NOT_EVALUABLE が出た場合は本判定もそれに従う。
**根拠ファイル**: `config.py:260-307` / `jst.py:47-72` / `scripts/auto_predict_daily.bat:16-36,73-80` / `scripts/run_auto_predict_daily.ps1:12-17,33-58,82-107` / `scripts/mutation_sandbox.py:70-145,171-243` / `scripts/fetch_mining.py:8-14` / `tests/conftest.py:25-62` / `tests/test_sealed_clock.py:205-283` / `tests/test_daily_bat_rundate.py:39-44,202-274` / `tests/test_auto_predict_task_runner.py:346-484` / `tests/test_fetch_mining_entry.py` / `tests/test_mutation_sandbox.py` / `docs/CLOCK_LEDGER.md:48-55,69,90-98` / scratchpad `gate3_spec_a.py` `gate3_spec_a_result.txt` `gate3_spec_b.py` `gate3_spec_b_result.txt` `gate3_suite_run1_noenc.txt` `gate3_suite_run2_utf8.txt` `gate3_prod_snapshot_before.json`
**次アクション**: (1) **HOLD 解除条件 (1 commit、テストのみ)**: `web/generator.py` の既定 `today` の意味テスト — `build_view_model(from_date=None, to_date=None)` の窓 (today±14) と `assess_race_completeness(rendered_days, today=)` に渡る基準日が `current_jst_date(now)` と一致すること (jst の時計を monkeypatch で固定し、UTC 15:00 境界の前後 2 点)。`web/publish_safety.py:60` の `base_date` に同じ注入テスト 1 本 (または AST ガードの TARGET_NAMES に `base_date` を追加)。これで M2''/M14'/PS' が撃墜されれば本 agent は PASS に上げる。(2) merge は ff (main `d134b3b` は a9f3969 の祖先で ff 可能を確認)。bat だけの cherry-pick は前回宣言どおり FAIL。(3) 作者主張「883 passed」に対し当方は **887 passed / 9 skipped / 1 deselected** を 2 回 (PYTHONIOENCODING 未設定 / utf-8) — 数が合わない。どの SHA で数えたかを作者が明記すること (緑であることは変わらない)。

## 総合: 4.3 / 5 (前回 4.1 / PASS → +0.2、判定は宣言執行により HOLD)

上昇根拠: 前回の生存変異 3 件 (S-f / B-10 / P-4) の閉鎖を独立変異で確認 / 変異テストが本番に届かない仕組み (枠) を自分で REFUSED・ABORT の両方向に叩いて確認 / conftest の運用ログ保護を「漏れるテスト」を植えて発火確認 / 実経路 dry-run (wscript → vbs → ps1 → bat) を隔離コピーで再現。判定が HOLD なのは点数の問題ではなく、宣言 (2) の執行。

## CHAT 指定の必須確認項目 — 成立表

| # | 項目 | 判定 | 一次証拠 (自分で実行したもの) |
|---|---|---|---|
| A | dry-run のタイムアウトでも Discord POST 0 件。本番起動の対照あり | **成立** | `ps1:46-49` で `Send-WatchdogAlert` 内に `$DryRun` 判定 (パラメータ解析時の連動ではなく関数内)。テスト `test_a_dry_run_timeout_never_notifies` (hang + `-DryRun` + スタブ通知 → marker 無し + ログ `notification suppressed: dry-run`) と対照 `test_a_real_timeout_does_notify` (marker に `scripts.notify_discord`)。独立再現: コピー B で hang.cmd + `-DryRun` + **`-NotifyPython` 無し (本番既定の python)** → rc 124、ログ `notification suppressed: dry-run (timed out after 1 seconds)`、対照 (dry-run 無し + スタブ) → rc 124 + スタブ起動 `-m scripts.notify_discord --message "WARN: ... timed out after 1 seconds"`。bat 側の dry-run 経路も POST 0: coverage は `--notify` 無し (`:58`)、日付失敗通知は `if not defined DRYRUN` (`:35`)、fetch 失敗通知は非 dry-run 分岐内 (`:41-46`)。変異 V-P4 (抑止ログを残して return を落とす = 挙動版 P-4) / V-P7 (`$DryRun -and $SkipNotification`) 共に **KILLED** |
| B | 日付取得後の Python 非 0 が bat → ps1 → vbs/wscript まで保持 | **成立** | `test_a_later_python_failure_reaches_the_bat_exit_code` 6 組 (スタブの終了コードを `STUB_EXIT_<module>` で注入: auto_predict=1→2 / coverage=1→1 / 両方→3 / fetch_full→4 / fetch+predict→6 / 全成功→0)、`test_the_exit_code_reaches_the_scheduler[False/True]` (ps1 直 / wscript→vbs→ps1) = 2、`test_the_date_failure_reaches_the_scheduler` = 8。-rs 出力で wscript 経路が skip でなく実行されたことを確認 (vbs は `%LOCALAPPDATA%\ScheduledTaskRunner\` に現存、`WScript.Quit exitCode` で伝搬)。変異 V-B10 (`FINALCODE=0`、前回生存の再植) / V-B11 (coverage ビット落とし) / V-B12 (予想ビット 2→1) / V-P9 (timeout で exit 0) **全て KILLED** |
| C | 月の途中 (2026-10-15) の境界。月単位・年単位に壊すと落ちる | **成立** | fixture `sealed_from_1015` + 8 instant (10/01・10/14 00:00・10/14 23:59:59・10/15 00:00・UTC 10/14 14:59:59・15:00:00・10/31・9/30) + 既定経路 2 点。直接 probe: today 20261014→False / 20261015→True / UTC 14:59:59→False / 15:00:00→True / 同月月初→False / 翌年→True。変異 V-Sf (`day[:6] >= SEALED_FROM[:6]`、前回生存 S-f 再植) **KILLED** (`test_a_mid_month_start_is_compared_by_day`)。作者の C1 (月) / C2 (年) も撃墜を結果ファイルで確認 |
| D | fetch_mining の import 順と起動テスト | **成立** | `scripts/fetch_mining.py:8-11` sys.path 挿入後に `from jst import ...`。コピー B の venv で `/tmp` を cwd に PYTHONPATH 無しでファイル指定 `--help` → rc 0、`-m` 形式 → rc 0。変異 V-D2 (`sys.path.insert` 行削除) **KILLED** (`test_the_script_starts_from_another_directory`) |
| E | テストが本番ログ (data/logs, data/runtime) を触らない。main で pytest を回しても watchdog log に書かない | **成立 (等価論法つき)** | 全 suite を worktree で 2 回 (887/9/1、rc 0) 実行し、worktree の `data/logs` `data/runtime` の `ls -la --full-time` が前後で **完全一致**。runner 呼出は全て `-LogDir` (AST テスト `test_runner_tests_leave_the_production_log_alone`)。conftest のセッション fixture (`:44-62`) の発火をコピー B で確認: `<copy>/data/logs/leak_probe.log` を書くテスト 1 本 → `ERROR ... assert not [data/logs/leak_probe.log]` rc 1、tmp_path だけに書く対照 → 緑。変異 V-P11 (ps1 が `-LogDir` を守りつつ `$repo/data/logs/probe.log` にも書く) は **この fixture が KILLED**。**限定**: 本番 checkout は main (`d134b3b`、是正前) なので「main で pytest」は当方では実行していない (旧コードで回すと本番ログを汚す)。a9f3969 の同一コードが worktree で 0 バイト差 → main でも同じ、という等価論法。変異 V-E3 (fixture の assert を無効化) は **SURVIVED** = ガード自体の自己テストが無い (提案 2) |
| F | `sealed_window_started` の不正引数 fail-fast | **成立** | `config.py:260-275` `_require_daystamp` (str・8 桁・isdigit・strptime)、`:296-302` 同時指定 / today / SEALED_FROM を **active ゲートより前** に検査。直接 probe (SEALED_FROM=None): today+now → ValueError「同時」/ today=2026-10-01 (ハイフン) / 20261001 (int) / 20260230 (実在しない) → ValueError / SEALED_FROM=2026-10-15 は判定済み (JUDGMENT_DONE=True) でも ValueError。変異 V-Sk (同時指定で now 優先、前回生存 S-k 再植) / V-F10 (today 検査を封印設定時だけ) / V-F12 (検査を active ゲートの後ろへ) **KILLED**。V-F7 (SEALED_FROM 検査を today 省略時だけ) **SURVIVED** (テストが now 経路しか使わない、影響低)。**留意**: `now` が naive のときは封印未定なら `False` を黙って返す (`now` の検査は `current_jst_daystamp` 到達時のみ) — today と非対称 (提案 4) |
| G | 変異テストの枠が本番に到達しない | **成立 (層構造の限界を明記)** | 事前検査 (実物で実行): worktree → 拒否 (「本番 checkout の中」+ `.git`)、本番 checkout → 拒否 6 件 (中 / 含む / `.git` / `data/discord_webhook.txt` 実在 / DB 同一 / worktree の `.venv64` リンク)、コピー A・B → 空。変異ごと: V-R1 (`cd /d` を本番 checkout `C:\Users\kizun\dev\keiba-yosou` へ) / V-R2 (`/c/Users/...` 形式) → **REFUSED**、V-R3 (ダミー `C:\nonexistent\keiba-yosou`) → 流れて KILLED。事後検査 (偽の本番で): 相対パス (`parents[1]/prod/keiba-yosou/data/logs` と `.../data/runtime`) で逃げる変異は `refuses()` を **素通り** するが、実行後に **ABORTED** で全体停止 (ただし書込みそのものは起きた後 = 事後検査は「止血」であって「予防」ではない)。変異なしの事前実行 (`:202-210`)、実行ごとの `PYTHONPYCACHEPREFIX` (`:191-193`、テスト `test_every_run_gets_a_fresh_bytecode_cache`)、WAL はサイズのみ (`:142-144`、X10/X11)。枠自体への変異: V-Xd (ハードリンク) / V-Xe (ジャンクション) / V-Xi (PRODUCTION_ROOT) / V-Xk (`/c/` marker) **KILLED**、V-Xc (snapshot から `data/runtime` を外す) / V-Xj (変異なし実行の本番差分を無視) **SURVIVED** (枠のテストが logs 漏れしか植えていない — コードは偽本番 probe で runtime 漏れも捕まえることを確認済み)。**監視対象外**: `docs/index.html` (Pages) / `predictor/*` / git 操作は snapshot に無い |
| H | 台帳の更新 (A7/A8/C3、A4/A5 の TZ 前必須、AST ガードの限界) | **成立** | 参照行を a9f3969 で全件実在確認: `web/generator.py:491` (`now=datetime.now()`) / `gui/app.py:437,441` / `scripts/payout_finality_monitor.py:70` (独自 JST 定数) / `fetch_fresh_odds.py:186,279` / `check_fresh_odds_health.py:516` / `gui/app.py:2219,2223` / `fresh_odds_coverage.py:80,151-152` / `predict_t10.py:120,249`。「ホスト / OS の TZ を変える前に必須」2 箇所 (A4/A5)、「AST ガードの限界」節 (`:93-98`)。**指摘**: その節が命じる「見張り対象には挙動のテストを必ず一緒に置く」が `web/generator.py` / `web/publish_safety.py` に未適用 (= HOLD の理由) |

## 前回 (v2) の次回宣言の執行

| # | 宣言 | 執行結果 |
|---|---|---|
| (1) | bat だけの cherry-pick で main 反映なら FAIL | **未発生** (main `d134b3b` は未 merge、a9f3969 の祖先 → ff 可能)。merge 時に再適用 |
| (2) | M2''/M14' が依然素通りなら HOLD 上限 | **発動 → HOLD**。spec B (枠経由、コピー B): M2'' / M14' / PS' **3/3 SURVIVED** |
| (3) | SEALED_FROM 設定と時計の同居なら FAIL | **非該当**: `config.py:232` `SEALED_FROM = None`、range 内で config を触った commit は `01758b8` (C/F) のみ、`test_the_real_setting_is_still_unset` 健在 |
| (4) | P-4 放置のまま「dry-run は Discord 無効」を再主張したら不成立 | **P-4 閉鎖** (A 欄)。主張は今回 **成立** と記録 |

## 変異表 (独立設計、枠 `scripts.mutation_sandbox` で実行、fresh .pyc、毎回 byte 復元)

spec A (コピー A、テスト = 作者と同じ 8 ファイル、baseline 緑を枠が確認): **26 種 → 20 KILLED / 2 REFUSED (期待どおり) / 4 SURVIVED**。

| ID | 変異 | 結果 | 備考 |
|---|---|---|---|
| V-Sf | 月粒度比較 (前回生存 S-f 再植) | KILLED | 中旬 fixture |
| V-Sk | today+now 同時で now 優先 (前回生存 S-k 再植) | KILLED | |
| **V-F7** | SEALED_FROM 検査を today 省略時だけ | **SURVIVED** | 低。テストは now 経路のみ |
| V-F10 | today 検査を封印設定時だけ | KILLED | 「未定でも」を固定 |
| V-F12 | 検査を active ゲートの後ろへ | KILLED | |
| V-J1 | `astimezone(JST)` → `astimezone()` | KILLED | OS TZ テスト |
| V-B10 | `FINALCODE=0` (前回生存 B-10 再植) | KILLED | |
| V-B11 | coverage ビット落とし | KILLED | |
| V-B12 | 予想ビット 2→1 | KILLED | |
| V-B14 | DATEERR 追記 (前回生存 B-14 再植) | KILLED | 今回は dry-run テストの 0 B 確認で捕まる |
| V-B15 | 日付失敗を通知しない | KILLED | |
| V-R1 | `cd` を本番 checkout へ | **REFUSED** | 枠の期待動作 |
| V-R2 | `cd` を `/c/Users/...` へ | **REFUSED** | 同上 |
| V-R3 | `cd` をダミーへ (対照) | KILLED | 流れて撃墜 |
| V-P4 | dry-run 抑止をログのみで return 無し | KILLED | 挙動 (marker) で検出 |
| V-P7 | `$DryRun -and $SkipNotification` | KILLED | |
| V-P9 | timeout で exit 0 | KILLED | |
| V-P11 | `-LogDir` を守りつつ repo `data/logs` にも書く | KILLED | **conftest fixture が捕捉** (E) |
| V-D2 | `sys.path.insert` 削除 | KILLED | |
| **V-Xc** | snapshot から `data/runtime` を外す | **SURVIVED** | 枠のテストは logs 漏れのみ |
| V-Xd | ハードリンク検査削除 | KILLED | |
| V-Xe | ジャンクション不検出 | KILLED | |
| V-Xi | PRODUCTION_ROOT を別パスに | KILLED | |
| **V-Xj** | 変異なし実行の本番差分を無視 | **SURVIVED** | 低 (事後検査が拾う) |
| V-Xk | `/c/` marker 削除 | KILLED | |
| **V-E3** | conftest の比較を無効化 | **SURVIVED** | ガードの自己テスト無し (手動発火は確認) |

spec B (コピー B、generator / publish_safety を触る 11 ファイル): **M2'' / M14' / PS' 3/3 SURVIVED** → HOLD。
偽本番 probe (枠の関数を直接): 相対パス逃げ ×2 (logs / runtime) → `refuses()` None → 実行後 ABORTED (書込みは発生)。
作者の 56 種 (`jst_mut7_result.txt`): 55 撃墜 / F6 生存を読んだ。F6 (`today or ...`) は `_require_daystamp` が空文字を先に落とすので **等価** — 作者主張は正しい (当方では再実行していない)。

## 項目別

- **検証設計の正しさ (証拠が持続するか): 4.5/5** — A の「関数内で判定」+ スタブ差替 + 対照、B の失敗スタブ注入 (6 組) と起動器 2 段、E の runner 全呼出 `-LogDir` + セッション fixture、G の枠。証拠が「気を付ける」から「機械が止める」に移った。減点: conftest ガードと枠の runtime 漏れに自己テストが無い (V-E3 / V-Xc)。
- **時間境界 (リーク分類学①の運用版): 4.5/5** — 中旬 fixture + 既定経路、fail-fast を active ゲートの前に。naive `now` は封印未定だと黙って False (非対称)。
- **変異テスト (独立設計): 4.2/5** — 26 種で 20/2/4、生存はすべて網の粗さで挙動の欠陥ではない。ただし generator 再植 3/3 生存 = 前回宣言の未消化。
- **A/B・再現性・merge 検証: 4.3/5** — suite 2 回 887/9/1 (作者 883 と不一致、要説明)。main は祖先で ff 可能、SEALED_FROM None 不動、range の config 変更は C/F のみ。
- **運用移行 / 統合判定 / 台帳: 4.0/5** — 台帳 13 参照行すべて実在、A4/A5 に TZ 前必須、AST 限界を明記。だがその明記した規律が既存ガード対象 (generator) に未適用。本番 `data/logs` に前回 data-pipeline が指摘した DATE_FAILURE 痕跡は現存せず (条件 (2) 解消)。v3 sibling 未提出。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides / market_snapshot / factorial / bootstrap — **N/A** (type-B/C、backtest JSON 生成なし)
- [x] 比較設計 (期間 / code path / filter / fold) — N/A
- [x] 専門領域「証拠を生む仕組み」の欠陥 — **抵触なし** (時限テスト無し、既定経路は両極、変異は枠経由で本番不達)
- [x] 他 agent 判定との不整合 — v3 sibling 未提出 (提出後に FAIL / NOT_EVALUABLE があれば従う)。v2 sibling は PASS/PASS
- [x] 前回宣言の執行 — (2) 発動 → HOLD。(1)(3) 非該当、(4) 閉鎖
- [x] SEALED_FROM = None のまま — `config.py:232` + `test_the_real_setting_is_still_unset`

## 反証の試み

- 「883 passed」→ 当方 887 passed × 2 (未設定 / utf-8)、rc 0 → **緑は成立、数は不一致**
- 「実経路 dry-run: 開催日 9/26 exit 0、24 レース 24/24」→ コピー B で wscript→vbs→ps1→bat `-DryRun` を再現: exit 0、`run date 20260926 (JST)`、`generate: 20260926 (24 races)`、`covered=24`、DATE_FAILURE 無し → **成立** (jst を壊した exit 8 は前回 V3 + 今回 `test_the_date_failure_reaches_the_scheduler` で代替)
- 「dry-run は timeout でも Discord へ送らない」→ hang + `-DryRun` + 既定 python で抑止ログ、対照は送信 → **成立**
- 「55 撃墜 / F6 のみ生存 = 等価」→ F6 の等価性をコードで確認 → **成立**
- 「枠は本番に届かない」→ 事前検査は本番パス文字列で REFUSED、相対パスは素通り → 事後 ABORT で止血 → **層としては成立、予防としては限定**
- 「テストは本番ログを触らない」→ worktree 0 バイト差 + 漏れテストで fixture 発火 → **成立** (main 実行は等価論法)

## 主な改善提案

1. **(HOLD 解除)** generator 既定 `today` / publish_safety `base_date` の挙動テスト (次アクション 1)。
2. conftest ガードの自己テスト: tmp のミニプロジェクトに `conftest.py` を複製し、`data/logs` に書くテストを subprocess pytest で回して rc≠0 を assert (V-E3 を殺す)。
3. `test_mutation_sandbox.py` に `data/runtime` 漏れ (V-Xc) と「変異なし実行で本番が変わる」(V-Xj) のケース。
4. `sealed_window_started`: `now` の tz 検査 (`current_jst_datetime(now)`) を active ゲートより前に (naive `now` を封印未定でも fail-fast)。
5. `test_a_malformed_sealed_from_is_rejected` に today 経路 1 点 (V-F7)。
6. 枠の snapshot に `docs/index.html` (Pages 出力) を追加するか、監視対象外であることを docstring に明記。

## 前回からの差分

- 前回 (20260925_2240、1baab6c): 4.1 / PASS → 今回 (a9f3969): 4.3 / **HOLD** (+0.2、判定は宣言 (2) の執行)。
- 前回提案の消化: 1 (P-4) ✓ / 2 (B-10) ✓ / 3 (S-f) ✓ / 5 (台帳 A4/A5) ✓ / **4 (M2''/M14' 意味テスト + `base_date`) ✗** → HOLD。

## 終了時の記録

- worktree `git status --short` = **空** (開始時・全 suite 後・終了時)、HEAD = `a9f3969` 不動。
- 本番 `data/logs` + `data/runtime` + DB (3,173 エントリ) の開始 / 終了 snapshot 差分 = **`data/keiba.db-shm` の mtime のみ** (サイズ 32,768 不変、読み手側の共有メモリ。当方のコピーは自前の小 DB を使い本番 DB を開いていない。並走中の別 agent / 常駐プロセスの読取と判断)。`data/logs` `data/runtime` は **無差分**。
- ジャンクション 2 本は `rmdir` で解除 (`rm -rf` 不使用)、実 venv `python.exe` 健在 (site-packages 107)。隔離コピー (リンク無し) と spec / 結果は scratchpad に残置。
- Task Scheduler 未操作、Discord 未送信、SEALED_FROM = None。

## 次回宣言 (必ず執行する)

- (1) main への反映が **bat だけの cherry-pick** (jst.py 不在) なら **FAIL** (継続)。
- (2) 次にこの系列を採点するとき、M2''/M14'/PS' が **依然素通りなら FAIL** (2 回目の不消化。HOLD 上限からの格上げ)。挙動テストで撃墜されていれば PASS 候補。
- (3) `SEALED_FROM` に日付を入れる commit が時計・bat の変更と同居していたら **FAIL** (継続)。
- (4) 変異テストの結果が `scripts/mutation_sandbox.py` を経由せずに報告された (または隔離コピーが本番 checkout の中にある) 場合、その変異証拠は **不成立** として扱う。
