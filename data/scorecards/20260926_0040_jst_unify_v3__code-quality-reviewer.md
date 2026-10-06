# コード品質 / 保守性レビュアー 採点 — JST 統一 v3 (a9f3969, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象は `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify` HEAD=a9f3969 に固定。git は `git -C <wt>`、Read/Grep は worktree 絶対パス。テスト実行と変異はすべて隔離コピー (`git archive a9f3969` → scratchpad/gate3_quality/copy, copy2) で行い、変異は `scripts/mutation_sandbox.py` 経由 (spec 5 本)。行き先を変える探索は偽の本番 (scratch 内) に向けた。worktree・本番 checkout・Task Scheduler・Discord には触れていない。終了時 worktree `git status --short` = 空、本番 `data/logs` / `data/runtime` の `ls -la --time-style=full-iso` が開始時と **IDENTICAL** (確認済)。

**改修タイプ宣言**: type-B (運用基盤 + テスト基盤、予測ロジック不変)。P25 固有ゲート (env_overrides / market_snapshot / weights / payout) は **N/A (対象外)**。汎用ゲートで採点。
**採点対象 (1baab6c → a9f3969、10 commit、11 files +980/-22)**: `config.py` (fail-fast) / `scripts/run_auto_predict_daily.ps1` (-LogDir / -NotifyPython / dry-run 抑止) / `scripts/fetch_mining.py` (import 順) / `scripts/mutation_sandbox.py` (新規) / `tests/conftest.py` (セッション比較) / `tests/test_mutation_sandbox.py` `tests/test_fetch_mining_entry.py` (新規) / `tests/test_auto_predict_task_runner.py` `tests/test_daily_bat_rundate.py` `tests/test_sealed_clock.py` (追加) / `docs/CLOCK_LEDGER.md`。
**実測**: 隔離コピーで対象 6 ファイル **120 passed** (pure 74 件 29.5s + runner/bat 46 件 29.2s)。全体 collect 897 件 (前回 837、+60)。変異 27 種を枠経由で植えた (下表): 実効 25 種のうち **24 KILLED / 1 SURVIVED** (S1、コードは正しいがテスト無し)、等価変異 1、私の spec 記述ミス 1。

## 判定: PASS

**理由**: 前回 (v2, PASS 4.0) の指摘 5 件はすべて是正を実測で確認した。(1) runner テストの本番 watchdog log 汚染 → `-LogDir` 全起動に付与 + AST ガード + conftest セッション比較 (別コピーで `data/logs` へ書くテストを植えて teardown ERROR になることを確認)。(2) `fetch_mining` の import 順 → 修正 + 起動テスト (変異 F1 で検出)。(3) AST ガードの限界 → 台帳 `docs/CLOCK_LEDGER.md:93-98` に「名前が違えば素通り、挙動テストを必ず併置」と明記。(4) `sealed_window_started` → 同時指定 / 形式違い / 実在しない日付 / SEALED_FROM の形式をすべて ValueError (変異 C1/C2/C3/C6/C7 で検出、封印未定でも落ちることを C7 が固定)。(5) 台帳 A7/A8/C3 追加、A6/B2 の行番号訂正 (実コードと照合済)。新規 3 件 (A: dry-run タイムアウトで通知しない / B: 終了コードの bat→ps1→wscript 伝搬 / C: 月の途中の開始日) も変異 P1/B1-B5/C4 で検出。本番起動 (引数なし) の ps1 は既定値が旧コードと同じパスに解決し等価 (下記)。停止条件 (汎用) への抵触なし。
**残る主要所見 (正しさには影響しないが、枠を「必ず通す」前提にするなら merge 前の小 commit で)**: (a) **`mutation_sandbox` は spec の `rel` を検査しない**。`rel` に絶対パスや `..` を渡すと隔離コピーの外のファイルを実際に変異する (偽の本番で実測: テスト実行中に本番側ファイルが `PROD-MUTATED`、終了後に復元)。2026-09-21 の「稼働中 checkout への変異」と同型で、`refuses()` は `new` しか見ず、事後スナップショットは logs/runtime/DB しか見ないのでソース改変は検知できない。(b) `production_root` が存在しなくても `check_sandbox` は空 (= 合格)、`snapshot_production` は `{}` を返し、枠は **黙って何も守らない** (実測)。`PRODUCTION_ROOT` は `register_auto_predict_task.ps1:19` と Python↔PS1 の二重記述で、checkout を移した瞬間に (b) が現実になる。(c) `config._require_daystamp` (`:260-274`) と `guard_analysis_window` の inline 検査 (`:363-368`) が同じ事実 (YYYYMMDD、同じ事故コメント) を同一ファイルに 2 回書いており、後者は実在しない日付 (`20261332`) を通す (変異 C8 が「2 件一致」で未適用になったのはこのため)。
**根拠ファイル**: `config.py:260-274,289-306,363-368` / `scripts/run_auto_predict_daily.ps1:12-17,22-24,33-37,43-58,75` / `scripts/mutation_sandbox.py:45,70-104,115-121,124-145,212-243` / `tests/conftest.py:25-62` / `tests/test_mutation_sandbox.py:110-135,197-217` / `tests/test_auto_predict_task_runner.py:346-354,357,387-393,409-484` / `tests/test_daily_bat_rundate.py:40-45,203-274` / `tests/test_sealed_clock.py:205-283` / `tests/test_fetch_mining_entry.py:23-33` / `scripts/fetch_mining.py:8-14` / `scripts/register_auto_predict_task.ps1:19` / `docs/CLOCK_LEDGER.md:48-56,69,93-98`
**次アクション**: 改善提案 1-2 (合計 15 分) を merge 前 or 直後に。3-5 は次の小 commit。

## 総合: 4.2 / 5 (前回 4.0、+0.2)

## 項目別

- **DRY / 単一出典: 4/5** (前回 4) — 台帳は実コードと一致 (A7 `web/generator.py:491`、A8 `gui/app.py:437,441`、C3 `payout_finality_monitor.py:70`、A6 `:2219,:2223`、B2 `:151-152` を照合)。留保 (新規の二重記述 3 件): (a) `config.py:260-274` `_require_daystamp` と `:363-368` の inline 検査 — 同じ「`"-" < "1"` で素通り」事故を 2 箇所に書き、厳しさが違う (helper は strptime まで、inline は桁数のみ)。helper を足したのに既存側を寄せていない (前回の `_run_runner` と同じパターン)。(b) `tests/conftest.py:25-38` `_snapshot_runtime_dirs` と `scripts/mutation_sandbox.py:124-145` `snapshot_production` — 同じ走査 (`("data/logs","data/runtime")` + rglob + `(size, mtime_ns)`) を 2 回。tests は既に `from scripts import mutation_sandbox` しているので conftest 側を import に寄せられる (DB の監視が conftest 側に無い非対称も同時に消える)。(c) `scripts/mutation_sandbox.py:45` `PRODUCTION_ROOT` と `scripts/register_auto_predict_task.ps1:19` `$repo` — 言語境界 (Python↔PS1) をまたぐ同じ絶対パス。
- **dead code / 未使用シンボル: 4/5** (前回 4) — `fetch_mining.py:8` の未使用 `datetime` は消えた。前回指摘の `tests/test_auto_predict_task_runner.py:357` `import pytest  # noqa: E402` (ファイル中盤) と `:387,:392` の関数内 `import os` / `import pytest` は **未対応のまま** (提案 1 の「あわせて」部分)。`_require_daystamp` の戻り値 (`config.py:274`) は 2 呼び出しとも捨てられている (`:300,:302`)。変異 C5 (`today or ...` へ戻す) が生存したのは等価変異 (空文字は手前で拒否) で問題なし。
- **マジックナンバー / 設定外出し: 4/5** (前回 4) — ps1 のログ置き場と通知プログラムがパラメータ化され (`:15,:17`)、既定は旧コードと同じ (`Join-Path $repo "data\logs"` / `.venv64\Scripts\python.exe`)。留保: `PRODUCTION_ROOT` は直書きで存在確認が無い (上記 (b))。`mutation_sandbox.py:127` の監視対象ディレクトリと `:142-144` の WAL 特別扱いは定数化されておらず conftest と乖離しうる。ps1 `exit 2` と bat bit 2 の衝突は CHAT 指示でバックログ (据え置き)。
- **テスト容易性 / 変更失敗モード: 5/5** (前回 4) — 実効変異 24/25 を挙動レベルで検出 (下表)。runner 系は全起動が `-LogDir` 付きで、AST ガード (`:456-471`、同ファイルの list literal のみ) + conftest セッション比較 (別コピーで実証) の二重。ps1 の 3 条件 (dry-run / -SkipNotification / 本番) を通知スタブで **送った・送らなかった** の両側から固定 (`:424-445,:474-484`)。bat の終了コードは `STUB_EXIT_<module>` で 6 通り + 起動器 2 経路 (`test_daily_bat_rundate.py:203-274`)。`test_sealed_clock.py:207-235` は開始日を 10/15 にして「月単位比較」への退行を殺す (C4)。`test_mutation_sandbox.py` は偽の本番で事故 2 件を再現 (`:110-119` cd 先、`:197-217` 変異時のみ漏れる形)。留保: (i) `refuses()` の大文字小文字非依存は S1 で生存 (テストが exact-case のみ)。(ii) 変異 spec の `rel` に対する検査が無い (上記 (a))。(iii) 時間: 対象 6 ファイルで約 60s (runner/bat 29s、sandbox 自身の subprocess pytest 25s)。全体 suite に +60s。環境依存は vbs 存在 (無ければ skip、`test_daily_bat_rundate.py:236` / `test_auto_predict_task_runner.py:391`)、`mklink /J`、`ping` 待ちの 1-2s タイムアウト (負荷で伸びても `timeout=60` 内)。
- **エラー処理 / 観測可能性: 4/5** (前回 4) — 抑止理由がログに残る (`ps1:47,:51` `notification suppressed: dry-run / -SkipNotification`)、ValueError が両方の値を出す (`config.py:297-298`)、`SandboxError.results` で途中経過を捨てない (`mutation_sandbox.py:159-164,:237`)、変異なしで赤いと流さない (`:207-210`)、WAL は size のみ (読むだけの接続で偽 ABORT しない、`:135-144`)。留保: (a) 上記の「本番ルート不在で黙って何も守らない」(fail-open)。(b) conftest の失敗は最後に走ったテストの teardown ERROR として出る (`2 passed, 1 error` の形) ので、定期実行との同時刻衝突で赤くなったとき原因が「そのテスト」に見える。docstring (`:49-50`) は認めているが、差分ファイル名で本番起動かを判定する手順はそこにしかない。(c) `run_mutants` の subprocess に timeout が無い (`:194-197`)。変異で pytest 自体が固まると `finally` に到達せず、強制終了すれば変異が植わったまま残る (隔離コピーなので実害は小)。(d) `bat:35` の二次失敗の握り潰し / `DATEERR` の常時生成は CHAT 指示でバックログ。

### 自分で植えた変異 (隔離コピー、`scripts/mutation_sandbox.py` 経由、spec 5 本)

| # | 壊し方 | 結果 | 検出したテスト |
|---|---|---|---|
| C1 | `today` と `now` の同時指定チェックを外す | KILLED | test_today_and_now_together_are_rejected |
| C2 | `today` の形式検査を外す | KILLED | test_a_malformed_today_is_rejected[2026-10-01] |
| C3 | `SEALED_FROM` の形式検査を外す | KILLED | test_a_malformed_sealed_from_is_rejected |
| C4 | `day[:6] >= SEALED_FROM[:6]` (月単位比較) | KILLED | test_a_mid_month_start_is_compared_by_day |
| C5 | `today or current_jst_daystamp(now)` に戻す | SURVIVED (等価: 空文字は手前で拒否) | - |
| C6 | strptime (実在日付) を外す | KILLED | test_a_malformed_today_is_rejected[20261332] |
| C7 | 検査を `sealed_window_active()` の後へ (未定なら素通り) | KILLED | test_a_malformed_today_is_rejected_even_when_unset |
| C8 | `len == 8` を外す | NOT_APPLIED (**config.py:364 に同文が存在**) | (DRY 所見) |
| F1 | `from jst import` を `sys.path.insert` の前へ戻す | KILLED | test_the_script_starts_from_another_directory |
| B1-B4 | bat の bit 2 / bit 4 / `exit /b 0` / `PREDICTCODE=0` | KILLED x4 | test_a_later_python_failure_reaches_the_bat_exit_code |
| B5 | `:date_failure` の `exit /b 8` → 0 | KILLED | test_a_missing_date_aborts_loudly |
| P1 | Send-WatchdogAlert の DryRun チェック削除 | KILLED | test_a_dry_run_timeout_never_notifies |
| P2 | `-NotifyPython` を無視 | KILLED | test_a_real_timeout_does_notify |
| P3 | `-LogDir` を無視 (本番 data\logs へ) | KILLED | test_a_dry_run_timeout_never_notifies (+ conftest) |
| P4 | `-SkipNotification` を無視 | KILLED | test_skip_notification_is_honoured_on_timeout |
| P5 | `--dry-run` を bat に渡さない | KILLED | test_watchdog_forwards_dry_run_to_the_batch |
| P6 | timeout の `exit 124` → 0 | KILLED | test_watchdog_times_out_and_returns_124 |
| S1 | `refuses()` を大文字小文字依存に | **SURVIVED** (テストが exact-case のみ) | - |
| S2 | `_inside` を常に False | NOT_APPLIED (私の spec のエスケープ誤り) | - |
| S3 | 漏れ検知後に raise しない | KILLED | test_a_leak_caused_only_by_the_mutant_aborts |
| S4 | WAL の size を見ない | KILLED | test_a_db_write_is_a_change[wal] |
| S5 | `/c/Users/...` variant を落とす | KILLED | test_the_real_production_markers_are_recognised |
| S6 | ジャンクションをリンク扱いしない | KILLED | test_only_the_venv_may_be_a_junction |
| S7 | PYTHONPYCACHEPREFIX を渡さない | KILLED | test_a_normal_run_kills_and_restores |
| S8 | 赤い baseline を無視 | KILLED | test_a_red_baseline_runs_no_mutant |
| S9 / S10 | `.git` / webhook ファイルの検査を外す | KILLED x2 | test_a_copy_with_git_is_rejected / ..._webhook_is_rejected |
| S11 | `finally` で元に戻さない | KILLED | test_a_normal_run_kills_and_restores |

枠の判定境界の直接プローブ (`refuses()`): 大文字 / `/` / `\` エスケープ / git-bash `/c/` / WSL `/mnt/c/` / `\?\` 接頭辞 / webhook (大文字・ptb・canary) は REFUSED。`%USERPROFILE%\dev\keiba-yosou` / `$env:USERPROFILE` / `~/dev/keiba-yosou` / `Path.home()/'dev'/'keiba-yosou'` / `%~dp0..\..\..\..\keiba-yosou` / `Path('C:/Users/kizun')/'dev'/'keiba-yosou'` / 区切り混在 `C:\Users/kizun\dev/keiba-yosou` は **allowed** (文字列一致の限界。事後スナップショットが後衛だが、ソース改変や logs/runtime/DB 以外への書き込みは見えない)。`check_sandbox` の走査は 1,154 ファイルで 0.13s、`snapshot_production` は本番 3,172 エントリで 0.32s (コストは問題なし。`.venv64` はリンクなら中に入らない)。

## 変更失敗モード分析

1. **spec に `rel="../../keiba-yosou/jst.py"` (or 絶対パス) を書いたとき**: `refuses()` は `new` だけを見て通し (`mutation_sandbox.py:216`)、`p = copy_root / rel` (`:220`) は pathlib の仕様で `..` も絶対パスもそのまま外へ出る。テストが走っている間、本番のソースが変異したまま。`finally` で戻るが、途中で強制終了されれば残る (2026-09-21 の事故と同じ終わり方)。事後スナップショット (`:234`) は logs/runtime/DB しか見ないので **静かに通る**。`(copy_root / rel).resolve()` を `_inside(..., copy_root)` で検査して REFUSED にすれば即座に落ちる (5 行)。
2. **checkout を移す / 別マシンで枠を使うとき**: `PRODUCTION_ROOT` (`:45`) が古いままだと `check_sandbox` は `_inside` が False で合格、`snapshot_production` は `is_dir()` False で空 dict → 差分ゼロ → 「本番が変わらない」と **常に報告される** (実測)。`register_auto_predict_task.ps1:19` を直しても Python 側は直らない (二重記述)。`production_root.is_dir()` を `check_sandbox` の先頭で要求すれば fail-fast。
3. **`config.py` に日付引数を取る 3 つ目の関数を足すとき**: `_require_daystamp` と `guard_analysis_window:363-368` のどちらを真似るかで厳しさが変わる (片方は `20261332` を通す)。inline 側を helper に寄せれば 1 経路になる。加えて `SEALED_FROM` の形式検査は **呼ばれたときだけ** 走る (`:301-302`)。`SEALED_FROM = "2026-10-01"` と書いた場合、テスト (`test_sealed_holdout.py:77` 等は `is None` を見るだけ) は通り、08:00 の `artifact_drift()` → `sealed_window_started()` で初めて ValueError → 日次 pipeline が exit 2 (loud だが本番で初めて出る)。module 末尾で `if SEALED_FROM is not None: _require_daystamp(...)` を 1 回走らせれば import 時 (= pytest collect 時) に出る。

## 依頼への回答

- **mutation_sandbox の設計**: 本番パスの判定は「本番ルートの 4 綴り + webhook 2 ドメイン、大文字小文字非依存」で、典型的な綴り違い (区切り・エスケープ・git-bash・WSL・UNC 接頭辞) は捕まえる。捕まえないのは環境変数・ホーム・相対 (`..`)・pathlib 結合・区切り混在。これは文字列一致の限界として設計上許容できるが、**`rel` を検査しない**のは限界ではなく穴 (上記 1)。`PRODUCTION_ROOT` のハードコードは「枠は物理的な本番ツリーを守る」という意図では正しいが、存在確認が無いので不在時に fail-open (上記 2)。走査コスト: 問題なし (0.13s / 0.32s)。スナップショットの誤検知: 定期実行との同時刻衝突は docstring で認知済。追加で、DB を **読むだけ** の接続が最後に閉じるとき SQLite が checkpoint して WAL を truncate/削除しうる (`(size, 0)` でも size 変化・キー消失で ABORT)。頻度は低いが、ABORT 時に「本番の pipeline が同時刻に動いていたか」を判定する手順 (watchdog log の start 行) を docstring に 1 行あると復旧が早い。例外時の後始末: `finally` で復元 + digest 照合 (`:240-242`) は良、subprocess timeout 無しは留保 (c)。テストの質: 偽の本番で事故 2 件を再現し、REFUSED / ABORTED / KILLED / NOT_APPLIED / 赤 baseline / .pyc / WAL / 途中結果保持を個別に固定。良い。
- **ps1 の等価性 (引数なし)**: `$LogDir=""` → `Join-Path $repo "data\logs"` (旧 `:25` と同じ)、`$NotifyPython=""` → `Join-Path $repo ".venv64\Scripts\python.exe"` (旧 `:37` と同じ)。`-DryRun` が `$SkipNotification` を立てなくなったが、`$SkipNotification` の参照は `Send-WatchdogAlert` のみで、そこで `$DryRun` を先に見る (`:46`)。`register_auto_predict_task.ps1:33` は新引数を渡さない。等価。`start` 行の書式も不変。
- **テストの脆さ**: 実プロセス起動は runner 17 起動 + bat 20 起動 + wscript 3 起動で 29s。`ping -n 30` の hang fixture を 1-2s で kill する形は負荷で遅れても `timeout=60` 内。`STUB_EXIT_<module>` は env 経由で cmd → python に届く (6 通り緑)。conftest の並行定期実行での偽陽性は上記 (b)。追加した `_run_via_runner` (`test_daily_bat_rundate.py:222-247`) は runner の AST ガード (別ファイル) の対象外だが `-LogDir` を渡しており、conftest が後衛。
- **前回からの回帰**: `jst.py` / `tests/test_today_single_source.py` は差分なし。`test_sealed_clock.py` 既存 6 節はそのまま + 4 節追加。runner 既存 3 テストは引数追加のみ。回帰なし。

## 停止条件チェック

- [ ] git_sha / env_overrides / market_snapshot / payout — **N/A** (type-B)
- [x] 汎用: 新規経路 (fail-fast / -LogDir / -NotifyPython / dry-run 抑止 / 終了コード伝搬 / import 順 / 枠) すべてに回帰テストあり、実効変異 24/25 検出
- [x] 汎用: 例外の握り潰しの新設 — 無し (枠の fail-open は握り潰しでなく検査の欠落、減点のみ)
- [x] 汎用: 既存テストの無効化 — 無し
- [x] 汎用: 本番への痕跡 — 無し (data/logs, data/runtime IDENTICAL、worktree clean)

## 反証の試み

- 「枠は本番に届く変異を流さない」→ `new` については成立 (REFUSED)。`rel` については **不成立** (偽の本番で実測、テスト中に外部ファイルが変異)。
- 「枠は本番の変化で止まる」→ 本番ルートが存在するときは成立 (S3 で確認)。存在しないときは **常に「変化なし」** (実測)。
- 「conftest がログ汚染を捕まえる」→ 書き込みは捕まえる (別コピーで ERROR)。作成→削除で元に戻す形は捕まえない (設計上妥当、size/mtime 比較の限界)。
- 「ps1 の新引数は本番と等価」→ 既定値の解決先を読み合わせ、等価。
- 「fail-fast は封印未定でも効く」→ C7 で成立 (`sealed_unset` で ValueError)。

## 主な改善提案

1. **`scripts/mutation_sandbox.py:215-220`** — `rel` を検査: `target = (copy_root / rel).resolve()`、`Path(rel).is_absolute()` or `not _inside(target, copy_root)` なら `Result(name, "REFUSED", ["対象がコピーの外"])`。`tests/test_mutation_sandbox.py` に絶対パスと `..` の 2 件 (偽の本番で、テスト中も本番側が不変であることを見る)。
2. **同 `:70-75` `check_sandbox`** — `if not production_root.is_dir(): problems.append("本番 checkout が見つからない (PRODUCTION_ROOT を確認)")`。テスト 1 件。あわせて `PRODUCTION_ROOT` の出典を `register_auto_predict_task.ps1:19` と共有する (どちらかを読む、または両方を照合するテスト)。
3. **`config.py:363-368`** — inline 検査を `_require_daystamp(label, value)` 呼び出しに置換 (厳しさが揃う)。`config.py` 末尾で `SEALED_FROM` / `SEALED_UNTIL` を import 時に 1 回検査 (pytest collect で出る)。
4. **`tests/conftest.py:25-38`** — `from scripts.mutation_sandbox import snapshot_production, diff_snapshots` に寄せる (`root` 引数はテスト対象 checkout)。DB の監視も同時に手に入る。
5. **`refuses()` のテスト** (`tests/test_mutation_sandbox.py:122-130`) に小文字・大文字混在の 1 件 (S1)。`run_mutants` の subprocess に `timeout` (既定 1800s 程度)。`tests/test_auto_predict_task_runner.py:357,387,392` の import 配置 (前回提案 1 の残り)。

## 前回からの差分 (20260925_2240 code-quality = 4.0 / PASS)

- DRY 4→4 (台帳の欠落 3 件は解消。新規の二重記述 3 件 = `_require_daystamp` vs inline、conftest vs sandbox の snapshot、`PRODUCTION_ROOT` vs ps1 で相殺) / dead code 4→4 (fetch_mining 解消、テストの import 配置は据え置き) / マジックナンバー 4→4 (ps1 のパラメータ化は加点、`PRODUCTION_ROOT` の存在確認なしで相殺) / テスト容易性 4→**5** (+1: 実効変異 24/25、通知の両側固定、終了コード 2 経路、偽の本番で事故再現、conftest 後衛を実証) / 観測可能性 4→4 (抑止理由・途中結果・fail-fast は加点、枠の fail-open と `rel` 未検査で相殺)
- 判定 PASS→**PASS**。総合 4.0→4.2 (+0.2)。-0.3 以上の低下項目なし。
