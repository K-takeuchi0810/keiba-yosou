# データパイプライン技術者 採点 — a9f3969 「JST 統一」再レビュー (v3)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `a9f3969` (branch `jst-date-unify-20260920`)、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git はすべて `git -C <worktree>`。起動実験はすべて隔離コピー (`git archive a9f3969` → scratchpad `gate3_pipeline` / `gate3_pipeline_broken` + `.venv64` ジャンクション + worktree の dry-run 用 DB 499 KB) 上で **-DryRun のみ**。main checkout の bat/ps1・Task Scheduler・Discord は起動していない。終了時: worktree `git status --short` 空 (HEAD a9f3969)、本番 `data/logs` `data/runtime` 全 3,170 ファイルの (path, size, mtime) が開始時スナップショットと **完全一致**、本番 `keiba.db` (20,092,399,616 byte / mtime 09-25 20:00:05) と `-wal` (0 byte / mtime 09-26 00:05:17) も不変、ジャンクション rmdir 後に実 `.venv64/Scripts/python.exe` 健在、コピーは削除済。

## 判定: PASS (条件 1 件、前回 4.2 → 4.7、+0.5)

**理由**: 前回の条件 3 件のうち (2) は完了を実測 (本番 `auto_predict_daily_DATE_FAILURE.log` / `rundate_stderr.txt` は消えている、原因 = 変異 B8 が `mutation_sandbox.py` の docstring に記録され、同型の変異は REFUSED になることを実測)。(1) は依然 ff 可能 (`merge-base --is-ancestor d134b3b a9f3969` 真)。指示元の是正 A / B / E は **コードとテストの両方で入り、隔離コピーで自分で再現**した: -DryRun のタイムアウトで通知 0 件 (`notification suppressed: dry-run`)、本番相当 (引数なし) のタイムアウトでは通知プロセスが `-m scripts.notify_discord --message "WARN: ... timed out after 1 seconds; ..."` で起動 (stub が引数を記録)、Python 非 0 → bat ビット → ps1 → wscript の伝播は 6 組合せ + 2 起動経路のテストで固定、壊した jst のコピーでは wscript 経由 `exit=8`。実時計 (JST 9/26 00:31、開催日) の wscript→vbs→ps1 -DryRun は exit 0 / `generate: 20260926 (24 races)` / `covered=24` / DB と `docs/index.html` の sha256 不変 / runtime に状態ファイル無し。本日 08:00 の本番起動は main (d134b3b) の旧 bat (`cd /d C:\Users\kizun\dev\keiba-yosou` + `date.today()`、jst 不使用) で動き、本ブランチは main のファイルに一切触れていない。

**条件 (1 件、前回 (1)+(3) を統合)**: merge は **非開催日に ff (または merge commit)** で行い、bat / ps1 だけの cherry-pick はしない。merge 後の最初の起動 (非開催日で可) で (a) `data/logs/auto_predict_daily_<JST日付>.log` が生成され (b) `auto_predict_daily_DATE_FAILURE.log` が **存在しない** (c) `auto_predict_watchdog.log` の末尾が `finish pid=... exit=0` (d) `schtasks` の LastTaskResult が 0、を確認する。この手順は branch のどの文書にも書かれていない (台帳「進め方」は「次の非開催日にマージ (dry-run + 再レビュー後)」のみ)。merge PR の本文か `docs/CLOCK_LEDGER.md` 「進め方」に 4 行で足すこと。

**根拠ファイル**: `scripts/run_auto_predict_daily.ps1:12-17,43-71`、`scripts/auto_predict_daily.bat:16-36,73-80`、`config.py:260-306`、`scripts/fetch_mining.py:11-14`、`scripts/mutation_sandbox.py:70-145,171-243`、`tests/conftest.py:25-62`、`tests/test_auto_predict_task_runner.py:346-484`、`tests/test_daily_bat_rundate.py:201-274`、`tests/test_sealed_clock.py:205-283`、`tests/test_fetch_mining_entry.py`、`tests/test_mutation_sandbox.py:245-270`、`docs/CLOCK_LEDGER.md:48-52,69,93-98`

## 対象・改修タイプ

- 対象: `1baab6c..a9f3969` 10 commits / 11 files (+980/-22)。コード: `run_auto_predict_daily.ps1` (-DryRun 抑止を通知関数内へ、`-LogDir` `-NotifyPython`)、`config.py` (`_require_daystamp`、today/now 同時指定拒否)、`fetch_mining.py` (import 順)、`scripts/mutation_sandbox.py` 新規、`tests/conftest.py` (セッション前後で data/logs・data/runtime 不変ガード)、tests 5 files、`docs/CLOCK_LEDGER.md`。
- 改修タイプ: **type-D (運用層 + テスト基盤。取得 / ingest / 予測ロジック不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**、fresh odds を総合判定のゲートにしない。参考実測 (Get-ScheduledTaskInfo): `keiba-fresh-odds` 09/25 19:00 result 0 / 次回 09/26 09:00、`keiba-fresh-odds-healthcheck` 次回 09/26 09:15 (台帳 A5 の「09:15」と一致)、`keiba-auto-predict` 09/25 11:00 result 0 / 次回 09/26 08:00、Action は main の `run_auto_predict_daily.ps1` (引数なし、WorkingDirectory 未指定)。
- 採点軸は v1 / v2 と同じ 5 軸。

## 総合: 4.7 / 5 (前回 4.2、+0.5)

## 項目別

- **bat 起動経路の堅牢性 (RUNDATE 決定・縮退・exit code): 4.5/5 (前回 4)** — (B) 前回は「日付失敗の 8」しか伝播を見ていなかったが、日付取得 **後** の Python 非 0 が bat のビット (1/2/4) に載ること 6 組合せ、それが ps1 直接と wscript→vbs→ps1 (スケジューラ同一経路) で exit 2 のまま届くこと、exit 8 の wscript 経由、をテストで固定 (`test_daily_bat_rundate.py:201-274`、隔離コピーで pass)。(A) `Send-WatchdogAlert` の **中で** `$DryRun` を見る (`ps1:46-49`) ので、引数解釈の変更で dry-run が Discord に届く経路が消えた。実測: hang fixture + `-TimeoutSeconds 1` で `-DryRun` → rc 124 / 通知 stub 未起動 / ログ `notification suppressed: dry-run (timed out after 1 seconds)`、`-SkipNotification` → 同様に抑止、引数なし → stub が `-m scripts.notify_discord --message "WARN: keiba auto predict watchdog timed out after 1 seconds; see data/logs/auto_predict_watchdog.log"` を受信 / `notification exit=0` (= 本番の送信は止めすぎていない)。変異でも確認: `if ($DryRun)`→`if ($false)` は `test_a_dry_run_timeout_never_notifies` で KILLED、bat `exit /b %EXITCODE%`→`exit /b 0` と ps1 `exit $exitCode`→`exit 0` はそれぞれ伝播テストで KILLED。**残る穴 (前回と同じ、悪化なし)**: (i) 起動器レベルの失敗コード衝突 — vbs 2 (ps1 不在) / ps1 2 (bat 不在) / bat 2 (予想失敗) が同値、ps1 自体の死亡 = 1 = 「fresh odds gap」と同値 (`ps1:30`)。(ii) 成功時も `auto_predict_daily_rundate_stderr.txt` 0 byte が `data/logs` に残る (今回の dry-run でも 0 byte で生成)。
- **日付決定の単一出典 / 境界一貫性: 4.5/5 (前回 4)** — (C/F) `sealed_window_started` が `"2026-10-01"` を `"-" < "1"` で **黙って False** にしていた経路 (封印開始済みを「まだ」と答える = 封印の実効性に直結) を `_require_daystamp` で ValueError に (`config.py:260-275,295-302`)。`today` と `now` の同時指定も拒否。SEALED_FROM=20261015 の fixture で 10/14 23:59:59 JST → False、10/15 00:00 JST (= UTC 10/14 15:00) → True、既定経路でも同じ (`test_sealed_clock.py:205-247`)。**評価**: 封印が None の今は到達しないが、10/01 以降に効く欠陥を開始前に塞いだ点は正しい順序。集約対象 9 箇所は不変、日次 bat 内に残る独自の「今日」は `fetch_full.py:36` と `fresh_odds_coverage.py:80,151-152` の 2 箇所 (前回と同じ)。**減点理由**: A4 / A5 / A7 / A8 (オッズ鮮度の naive `now`) が未着手のため「予想日 = JST、鮮度 = local」の半統一状態が続く (台帳が明記、TZ 変更前に必須)。`_require_daystamp` の関数内 import は実害なしだが `config.py` 冒頭で import できない事情もない。
- **依存 / 起動コスト: 5/5 (前回 4.5)** — (D) `fetch_mining.py:11-14` で `sys.path.insert` の後に `from jst import` を移し、未使用 `datetime` import を削除。別 cwd からのファイル指定起動と `-m` 形式の両方をテスト (`test_fetch_mining_entry.py`、PYTHONPATH を落として素の起動を再現、`PYTHONIOENCODING` 固定で cp932 依存を排除)。`jst.py` は依然 `datetime` のみ、`config.py` は循環なし。前回の減点事由は解消。
- **退行ガード / テスト: 5/5 (前回 4.5)** — (E) 前回の減点「main で pytest を回すと本番 watchdog log が汚れる」は 3 層で塞がった: ps1 `-LogDir` + runner のテストすべてが tmp へ (`_run_runner`、`_run_via_runner` は `root.parent / "watchdog-logs"`)、AST ガード `test_runner_tests_leave_the_production_log_alone` (`str(RUNNER)` を含むリストに `'-LogDir'` が無ければ fail)、conftest のセッション autouse fixture が `data/logs` `data/runtime` の (size, mtime_ns) を前後比較 (`conftest.py:41-62`)。実測: 隔離コピーで対象 7 ファイル **131 passed / 62 s**、その前後で本番 `data/logs` `data/runtime` 3,170 ファイルに差分なし、本番 watchdog log 末尾は 09/25 22:03 の pytest 行のまま (= 今回の是正前に付いた汚染、以後増えていない)。変異の枠 (`mutation_sandbox.py`): (a) 事前検査 — worktree パスを渡すと「本番 checkout の中 / .git あり」で拒否、本番 checkout 自体は 6 理由で拒否、隔離コピーは空リスト。(b) 変異ごと — `cd /d C:\Users\kizun\dev\keiba-yosou` (前回事故 B8 の再現) は **REFUSED** で植えられず、同じ変異をダミーパス `C:\nonexistent\gate3_dummy` にすると KILLED (テストが bat の cwd 一致で落とす)。`/c/Users/...` 形と webhook URL も拒否、ダミーパスは通る。(c) 変異なし baseline を先に流し、`PYTHONPYCACHEPREFIX` を実行ごとに新規、終了時に digest で復元を確認 (実測: bat / ps1 とも a9f3969 と一致)。**DB 監視の妥当性 (作者主張の検証)**: 本番 `-wal` は 0 byte で mtime だけ 09-26 00:05:17 (本体 mtime は 09-25 20:00) — 「開いただけで WAL の時刻が動く」は本番の状態と整合。捨て DB で実測: 書き込み (commit) で WAL サイズ 0 → 16,512、`wal_checkpoint(TRUNCATE)` で WAL 0 に戻るが本体サイズ 499,712 → 503,808 / mtime 更新 — つまり **書き込みは「WAL サイズ増」か「本体 size/mtime 変化」の少なくとも一方に必ず出る** ので、WAL を時刻でなくサイズで見る規則は書き込み検出を落とさない。読み取り専用 (mode=ro) の open+read+close は WAL の size も mtime も動かさなかった (mtime が動くのは WAL の生成 / 切り詰めのとき)。**注記**: 別プロジェクトの常駐 `fetch-live-jvdata` (09/20 13:03 起動、cmd + python で 55 プロセス) が本番 DB を **書く** タイミングと変異の実行が重なれば、枠は ABORT を出す (誤検知側に倒れる = 保守的)。ABORT の理由を読むとき「外部の書き手が居る」ことを知っている必要がある。減点なし: conftest の fixture が定期実行 (08:00 / 09:00 / 09:15 / 11:00 / 20:00) と重なると偽陽性になるのは docstring に明記済。sandbox の rc は NOT_APPLIED も 1 (設計どおり、`main():263`)。
- **反映運用 / 前回条件の解除: 4.5/5 (前回 4)** — 条件 (2) **完了**: 本番 `DATE_FAILURE.log` / `rundate_stderr.txt` は存在せず、痕跡の原因 (変異 B8 = bat の cd 先を本番に戻す) は `mutation_sandbox.py:6-11` に記録、同型は REFUSED を実測。条件 (1) **成立可能**: main (d134b3b) は a9f3969 の祖先。本日 08:00 への影響 **なし**: main の bat は旧形 (`cd /d C:\Users\kizun\dev\keiba-yosou`、`date.today()`、jst 不使用) で、ブランチのファイルは worktree にしか無い、scheduler は main の ps1 を引数なしで呼ぶ (= `-LogDir` 既定 `data\logs`、`-NotifyPython` 既定 `.venv64` — 新 ps1 を merge しても既定値は従来と同じ)。**減点理由**: 条件 (3) の「merge 後最初の起動の確認手順」が branch のどこにも書かれていない (上の条件参照)。前回提案 5 (成功時の 0 byte stderr 掃除) は未採用 (害なし)。

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides: N/A (backtest artifact を生成しない改修)
- [x] baseline paired 比較: N/A
- [x] market_snapshot counts / payout 欠損: N/A
- [x] P25 fresh odds スケジューラ / coverage JSONL / bonus_candidate: N/A (type-D)。参考実測: `keiba-fresh-odds` 登録済 result 0、healthcheck 09:15 登録済
- [x] 専門領域 (本改修向け): partial write を残す経路 → なし (実時計 dry-run で DB / docs/index.html の sha256 不変、runtime 不変)。無限待ち → ps1 timeout 1200 s 健在 (`:6,82`)。lock 未掃除 → 該当コード無し。予想を 1 日落とす経路 → 「新 bat + jst.py 無し」は cherry-pick でのみ到達 (条件)。dry-run が Discord に届く経路 → 通知関数内で遮断、変異で確認。テストが本番運用ログを汚す経路 → 3 層で遮断、実測ゼロ差分。**すべて不抵触**
- [x] テスト: 131 passed (隔離コピーで自分で再実行)

## 反証の試み (すべて隔離コピー、-DryRun のみ)

| # | 反証シナリオ | 結果 |
|---|---|---|
| E1 | 実時計 (JST 9/26 00:31、開催日) を wscript→vbs→ps1 -DryRun | `wscript exit=0`、`auto_predict_daily_20260926_dryrun.log` に `run date 20260926 (JST)` / `[DRY-RUN] skip fetch_full / fetch_mining` / `generate: 20260926 (24 races)` / `scheduled=24 cancelled=0 eligible=24 covered=24` / `done exit=0`。DB sha `3cbf8e3d…` 不変、`docs/index.html` sha `2eb3cca2…` 不変、runtime に状態ファイル無し。**成立** (作者主張と一致) |
| E2 | 壊した jst (ImportError) を wscript→vbs→ps1 -DryRun | `wscript exit=8`、`DATE_FAILURE.log` に `RUNDATE=[] dryrun=[1]` + traceback + `abort exit=8`、dated log ゼロ、watchdog `finish exit=8`。**成立** |
| E3 | -DryRun でタイムアウト (hang.cmd、timeout 1 s) | rc 124、通知 stub 未起動、`notification suppressed: dry-run`。**成立 (A)** |
| E4 | -SkipNotification でタイムアウト | rc 124、未起動、`notification suppressed: -SkipNotification`。**成立** |
| E5 | 引数なし (本番相当) でタイムアウト | rc 124、stub が `-m scripts.notify_discord --message "WARN: … timed out after 1 seconds; …"` を受信、`notification exit=0`。**成立 (対照: 止めすぎていない)** |
| E6 | 変異 `if ($DryRun)`→`if ($false)` | KILLED (`test_a_dry_run_timeout_never_notifies`)。**成立 (A の退行ガード)** |
| E7 | 変異 bat `exit /b %EXITCODE%`→`exit /b 0` / ps1 `exit $exitCode`→`exit 0` | 両方 KILLED (bit 伝播 / scheduler 伝播テスト)。**成立 (B の退行ガード)** |
| E8 | 変異 `cd /d C:\Users\kizun\dev\keiba-yosou` (前回事故 B8) | **REFUSED**、植えられず、本番に変化なし。ダミーパス版は KILLED。**成立** |
| E9 | 枠の事前検査に worktree / 本番 checkout を渡す | worktree: 「本番の中 / .git あり」で拒否。本番: 6 理由で拒否 (webhook ファイル・本番 DB 同一・許可外リンク `.claude/worktrees/jst-unify/.venv64` を含む)。**成立** |
| E10 | pytest 131 件 + 全実験の前後で本番 data/logs / data/runtime / DB | 3,170 ファイルの (size, mtime) 完全一致、DB 本体・WAL 不変。**成立 (E)** |
| E11 | WAL 監視規則 (捨て DB で実測) | 読取のみ: WAL size/mtime 不変。書込: WAL 0→16,512 byte。TRUNCATE checkpoint: WAL 0 に戻るが本体 size/mtime 変化。**書き込みを見逃す組合せなし** |
| E12 | 本日 08:00 の本番起動への影響 | main の bat / ps1 は d134b3b のまま (jst 不使用)、scheduler Action は main の ps1 引数なし。**影響なし** |
| E13 | 起動器の exit code 衝突 (前回 E10) | 不変 (vbs 2 / ps1 2 / bat 2、ps1 死亡 = 1)。今回の対象外、悪化なし |

## 台帳 (docs/CLOCK_LEDGER.md) A4 / A5 / A7 / A8 の記載検証

- **A4** `fetch_fresh_odds.py:186` (`now = datetime.now()`) と `:279` (`mins_now = (start - datetime.now())`) — 行番号・内容とも実コードと一致。「毎日 09:00 起動」= `keiba-fresh-odds` 次回 09/26 09:00 で一致。「ホスト / OS の TZ を変える前に必須」「post-start 汚染が再発」は前回私が書いた指摘のとおりで妥当。修正案 `jst_now_naive()` 型ヘルパも、DB `start_time` が naive である事実 (A1 行に記載) と整合。
- **A5** `check_fresh_odds_health.py:516` — 一致。「毎日 09:15 起動」= `keiba-fresh-odds-healthcheck` 次回 09/26 09:15 で一致。「A4 に同乗」は妥当 (単独では B 相当)。
- **A7** `web/generator.py:491` `is_buy_candidate(..., now=datetime.now())` — 一致。「`odds_fetched_at` も naive local なので TZ が変わらない限り両辺は揃う」は正しい記述で、A4 と **同じヘルパで両辺を揃える** 方針も正しい (片側だけ JST にすると取得時 TZ ≠ 判定時 TZ の事故を自分で作る)。
- **A8** `gui/app.py:437` (`now=datetime.now()`) / `:441` (`odds_age_minutes(fetched_at, datetime.now())`) — 一致。「A7 と同時に」妥当。
- 併せて A6 `:2219, :2223`、B2 `:80, :151-152`、C3 `payout_finality_monitor.py:70` の行番号も一致。「AST ガードの限界」(代入先の名前に依存、`now = ...` 形は素通り) の追記は、A4/A5/A7/A8 がまさに `now = datetime.now()` 形で **ガードに引っかからない** ことの説明になっており、挙動テスト併置の要求は正しい。
- 台帳に無い指摘: 「進め方」に merge 後の確認手順が無い (条件参照)。

## 主な改善提案 (優先順)

1. **merge 後の最初の起動の確認手順を文書化** (条件、4 行) — `docs/CLOCK_LEDGER.md` 「進め方」1. に (a)-(d) を足す。
2. 起動器レベルの exit code 分離 (`ps1:30` の `exit 2` → 122 等、前回提案 2 のまま) — 深夜に LastTaskResult だけで切り分ける場面で効く。今回の対象外。
3. 成功時の `auto_predict_daily_rundate_stderr.txt` (0 byte) を `:run` 冒頭で `del` (前回提案 5 のまま)。
4. `mutation_sandbox.py` の ABORT メッセージに「本番 DB には外部の書き手 (`fetch-live-jvdata`) が居る。`data/keiba.db` だけが変わった場合はそれを疑う」を 1 行足す — 今回 55 プロセスが本番 DB を開いたまま常駐しており、偽陽性の読み違いを防ぐ。
5. A4 / A5 / A7 / A8 は **同一 PR** で `jst_now_naive()` を入れて揃える (台帳どおり)。半統一状態 (予想日 = JST、オッズ鮮度 = local) は現機では無害だが、TZ 変更の前に必ず。

## 前回からの差分

- v1 (`37eaf61`) 3.8 HOLD → v2 (`1baab6c`) 4.2 PASS (条件 3) → **v3 (`a9f3969`) 4.7 PASS (条件 1)** (+0.5)。
- 前回条件: (1) ff merge → 成立可能のまま (条件として継続)、(2) 本番の偽 DATE_FAILURE 痕跡 → **完了** (削除 + 原因記録 + 枠で再発防止)、(3) merge 後の確認 → 未文書化 (条件として継続、(1) と統合)。
- 前回提案: 3 (fetch_mining import 順) **完了**、4 (テストのログ隔離) **完了** (提案より強い 3 層)、2 (exit code 分離) 未着手、5 (0 byte stderr) 未着手。
- 項目別: bat 4→4.5、単一出典 4→4.5、依存 4.5→5、テスト 4.5→5、反映運用 4→4.5。-0.3 以上下がった項目なし。
- 今回新たに見つけたもの: merge 後手順の未文書化 (条件)、外部の書き手による sandbox ABORT の読み違いリスク (提案 4)。code の停止条件に当たるものなし。
