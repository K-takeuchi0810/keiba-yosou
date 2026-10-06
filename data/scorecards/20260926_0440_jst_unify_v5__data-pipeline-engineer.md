# データパイプライン技術者 採点 — 209b636 「JST 統一」再レビュー (v5)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `209b636` (branch `jst-date-unify-20260920`)、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git はすべて `git -C <worktree>`。起動実験はすべて隔離コピー (`git archive 209b636` → scratchpad `gate5_pipeline` + `.venv64` ジャンクション + worktree の dry-run 用 DB 499,712 byte + コピー内だけの `git init` (test_build_daily_results の `rev-parse` 用) + 本番 `data/f3_phase0_0/metrics.json` の読み取りコピー) 上。**本物の `weekly_monitor.bat` を隔離コピーで実行** (scripts.monitor / fresh_odds_coverage / notify_discord は本物のまま、`data/discord_webhook.txt` が無いことを事前確認 → notify は `WARN: Discord notification failed: [Errno 2]` で POST 前に終了、Discord には届いていない)。main checkout の bat/ps1・Task Scheduler・Discord は起動していない (タスクは `Get-ScheduledTask*` の読み取りのみ)。終了時: worktree `git status --short` 空 (HEAD 209b636、main HEAD d134b3b 不変、ff 可能)、本番 `data/logs` `data/runtime` + `keiba.db` (+`-wal`) の (path, size, mtime) **3,173 行が開始時スナップショットと完全一致**、本番に `weekly_monitor_20260926.log` / `data/monitor_runs/` は存在しない、ジャンクション rmdir 後に実 `.venv64/Scripts/python.exe` 健在、コピー (`gate5_pipeline` / `gate5_fix`) は削除済、同時書き込み用プロセスは kill 済 (残存なし)。変異の再実行はしていない (作者の 84/85 撃墜を報告値として受け取る。今回の指摘は変異の集合の外側にある = どの変異テストも「本物の全テストを off で流す」形を持たない)。

## 判定: HOLD (前回 4.3 HOLD → 4.4、+0.1)

**理由 (1 件、是正は 1 行だが merge 前に必須)**: 見張りの 2 値化 (strict / off、未知の値は fail-fast、枠の子は常に strict、pytest 出力は `data/monitor_runs/`) は設計どおり入っており、**個々の解除条件 1・3・4 は成立**。しかし **解除条件 2・5 は不成立**: `weekly_monitor.bat` が流すのは `tests/` 全体で、その中の `tests/test_conftest_guard.py::_pytest` (:34) は環境変数のうち `PYTHONPATH` しか落とさない。そのため週次監視が立てた `KEIBA_RUNTIME_GUARD=off` が **入れ子の pytest に継承され**、「ログ置き場に書くテストはセッション失敗になる」ことを確かめる 4 本 (`test_a_test_that_writes_runtime_logs_fails_the_session` ×3 + `test_a_same_size_overwrite_fails_the_session`) が「入れ子が緑になった」で **失敗する**。隔離コピーで実測: 全テスト strict = `944 passed / 1 failed (環境: lgbm_cache npz 不在) / 9 skipped / 166 s`、同じコピーで `KEIBA_RUNTIME_GUARD=off` = `940 passed / 5 failed` で **差分はちょうどこの 4 本**。本物の `weekly_monitor.bat` を同時書き込み (別プロセスが `data/logs/fresh_odds_concurrent.log` に 20 ms ごと、実測 10,284 行) の下で実行 → 週次ログ `pytest exit 1 (full output: data\monitor_runs\weekly_pytest_20260926.log)` / `Weekly Monitor End (exit 3)` (= monitor 1 [環境: dry-run DB に直近レコード無し] + **pytest 2**) / notify_discord が呼ばれた (webhook 無しで不達)。つまり **merge 後の最初の日曜 (09/27 10:00) は v4 と同じく `pytest=1` の WARN が Discord に飛ぶ**。機構は違う (v4: 見張りが同時書き込みで落ちる / v5: 見張りを止めたことを見張りのテストが検出する) が、運用上の結果は同じ。作者の `tests/test_weekly_monitor_guard.py` は小さなリポジトリ (inner test 3 本) で bat を回すので、この経路は見えない (**「9/27 と同等の条件で exit 0」の主張は、全テストを流す本物の形では成り立たない**)。

**解除条件**: `tests/test_conftest_guard.py:34` の `_pytest` で `KEIBA_RUNTIME_GUARD` を落とす (`test_weekly_monitor_guard._env` と同じ形) か、より明示的に `env["KEIBA_RUNTIME_GUARD"] = "strict"` を立てる (開発者のシェルに off が残っていても見張りのテストが緩まない)。捨てコピーで前者を当てて実測: off で `5 passed`、strict で `5 passed`、`foo` で `ERROR: KEIBA_RUNTIME_GUARD=foo は使えない` rc=4 (fail-fast 維持)。あわせて `test_weekly_monitor_guard` の mini repo に **本物の `tests/test_conftest_guard.py` も置いて** bat を回す case を 1 本足す (「入れ子 pytest を使うテストは自分で strict を立てる」を固定する。これが無いと同じ穴が再発する)。是正後に隔離コピーで **全テストを `KEIBA_RUNTIME_GUARD=off` で流して strict と差分ゼロ** を確認してから merge。

**根拠ファイル**: `tests/conftest.py:43-62,88-92`、`tests/test_conftest_guard.py:33-39`、`tests/test_weekly_monitor_guard.py:108-113,121-135`、`weekly_monitor.bat:22-37`、`scripts/mutation_sandbox.py:234-238`、`docs/CLOCK_LEDGER.md:69,93-124`、`scripts/notify_discord.py:29-38`

## 対象・改修タイプ

- 対象: `27a260e..209b636` 3 commits / 8 files (+362/-13)。`tests/conftest.py` (2 値の見張り + `pytest_configure` の fail-fast)、`weekly_monitor.bat` (off + `data/monitor_runs/` へリダイレクト)、`scripts/mutation_sandbox.py` (子を常に strict)、tests 4 files (新規 `test_weekly_monitor_guard.py` 201 行)、`docs/CLOCK_LEDGER.md` (runbook 5 点目・C4)。
- 改修タイプ: **type-D (運用層 + テスト基盤。取得 / ingest / 予測ロジック不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**、fresh odds を総合判定のゲートにしない。参考実測 (読み取り): `keiba-yosou-weekly-monitor` Ready / 日曜 10:00 / Action = wscript → vbs → `cmd C:\Users\kizun\dev\keiba-yosou\weekly_monitor.bat` / LastRun 09/20 10:00 result 0 / **NextRun 09/27 10:00**。`keiba-fresh-odds` / `keiba-fresh-odds-healthcheck` Ready。本番の直近 09/20 週次ログは `664 passed, 6 skipped in 321.84s` / `End (exit 0)`。

## 総合: 4.4 / 5 (前回 4.3、+0.1)

## 項目別

- **bat 起動経路の堅牢性 (RUNDATE 決定・縮退・exit code): 4.5/5 (前回 4.5、変化なし)** — 日次 bat / ps1 は差分なし。`weekly_monitor.bat` の変更は実測で意図どおり: `set "KEIBA_RUNTIME_GUARD=off"` は `:run` 内で pytest の直前に立て直後に消す (monitor / coverage / notify には渡らない)、`Start-Process -RedirectStandardOutput/-RedirectStandardError` の相対パスは cmd の cwd (repo root) 基準で解決され `data\monitor_runs\weekly_pytest_<日付>.log` (17,143 byte) と `.stderr` (0 byte) ができた、`$null=$p.Handle` と 600 s timeout → exit 124 は維持、`pytest exit N (full output: ...)` の 1 行が週次ログに残る。小さな残り: 成功時も 0 byte の `.stderr` が毎週 1 つ増える / `data/monitor_runs/` にローテーション無し (gitignore 対象なので tree は汚れない)、RUNDATE は `date.today()` のまま (C4 として台帳に載った)。
- **日付決定の単一出典 / 境界一貫性: 4.5/5 (前回 4.5、変化なし)** — コード差分なし。C4 (`weekly_monitor.bat:5` のローカル日付) が台帳に追記された。減点理由は前回と同じ (A4 / A5 / A7 / A8 の naive `now` 未着手)。
- **依存 / 起動コスト: 5/5 (前回 5、変化なし)** — `conftest.py` は `os` を足しただけ。`pytest_configure` の検査は環境変数 1 つの参照。全テスト 166 s (600 s 上限に余裕)。
- **退行ガード / テスト: 4/5 (前回 4、変化なし)** — 良い点 (実測): (i) 未知の値は **テストを 1 本も流さず** `UsageError` rc=4 (`foo` で確認、作者テストは `foo` / `warn` / `OFFF` / `0`)。`strict` / `STRICT` / 空 は strict。(ii) strict は同時書き込みを検出する (コピーで別プロセスが書く下で `tests/test_jst_date.py tests/test_sealed_clock.py` → `62 passed, 1 error: ... [data/logs/fresh_odds_concurrent.log]`)。(iii) 枠の子は常に strict (`mutation_sandbox.py:237-238` が env に `"KEIBA_RUNTIME_GUARD": "strict"` を上書き、`test_mutant_runs_ignore_a_caller_side_guard_off` が変異なし + 変異 1 の両方で `["strict","strict"]` を固定、off の下でも pass)。通知の状態ファイルの隔離 (`_isolate_notification_state`、function-scope autouse) は無条件で、off の inner test でも `NOTIFY_STATE_PATH` が tmp を指す。(iv) 同じサイズの上書き (K19) / 本番サブディレクトリへの漏れ (Xc2) / `\` 区切りの `..` (R9) / 既定経路の SEALED_FROM 形式 (F7b) が固定された。**減点理由**: 上の判定理由。見張りを止めたときに「見張りが働くこと」を確かめるテストが自分で strict を立てておらず、本番の呼び出し形 (全テストを off で流す) で赤くなる。`test_weekly_monitor_guard` は「同じ条件の再現」を掲げるが、流すテストが本物の suite でないので再現になっていない。点は据え置き (機構は前進、運用結果は同じ)。
- **反映運用 / 前回条件の解除: 4/5 (前回 3.5、+0.5)** — 前回指摘 3 点は **すべて文書化された** (`docs/CLOCK_LEDGER.md`): 5 点目 (週次監視の `LastTaskResult` 0 / 週次ログの `pytest exit 0` / pytest 出力は `data/monitor_runs/`、off の理由つき、:105-109)、項目 1 の「先頭行に ... が含まれる (行頭は `[日付 時刻]`、行末に `cwd=`)」(:96-98)、項目 3 の「タイムアウトした起動には `finish` 行が出ない ... exit 124」(:104-105)、確認コマンド 2 行と記録表の列追加。**減点理由**: このまま merge すると runbook 5 点目は最初の日曜に **満たされない** (`pytest exit 1`) — 文書は正しく、それが赤を検出する側に回る。`weekly_monitor.bat` のコメントと `conftest.py` の docstring の「off で流せば通る」は全テストでは未達。

## 解除条件の成立 / 不成立 (CHAT 指定 5 + 文言 3)

| # | 条件 | 判定 | 根拠 (実測) |
|---|---|---|---|
| 1 | strict は本番 runtime の変更を検出して fail する | **成立** | 同時書き込み下の strict pytest → `1 error: テストが運用ログ置き場を変更した ... [data/logs/fresh_odds_concurrent.log]` rc=1。`test_conftest_guard.py` strict 5 passed、`test_strict_is_the_default_and_detects_changes[strict/STRICT/空]` pass |
| 2 | 週次監視では global guard を明示的に off にして正常完走する | **不成立** | bat は off を立てている (週次ログに `pytest exit 1`、見張りの AssertionError は出ていない) が、全テストを off で流すと `test_conftest_guard.py` の 4 本が「入れ子 pytest が off を継承」で失敗 → `pytest exit 1` → bit 2 |
| 3 | 週次監視自身は本番 data/logs へ pytest の出力を書かない | **成立** | コピーの `data/logs` は `weekly_monitor_20260926.log` (777 byte、`passed` を含まない) + 同時書き込みファイルのみ。pytest 出力は `data/monitor_runs/weekly_pytest_20260926.log` 17,143 byte。`grep -l passed data/logs/*` = 0 件 |
| 4 | off が変異の枠などの別の安全機構を無効化しない | **成立** | `mutation_sandbox.py:237-238` で子は常に strict、`test_mutant_runs_ignore_a_caller_side_guard_off` が off 環境下でも pass。`_isolate_notification_state` は無条件 (`conftest.py:14-24`)、inner test `test_notification_state_is_still_isolated` が bat 経由で pass |
| 5 | 9/27 10:00 と同等の同時書き込み条件を再現して exit 0 | **不成立** | 本物の bat + 全テスト + 別プロセスの 20 ms 書き込み (10,284 行) → `Weekly Monitor End (exit 3)`。内訳 monitor=1 (環境: dry-run DB に直近レコード無し、本番 09/20 は 0) / **pytest=1 (条件 2 の 4 本)** / gap=0。是正 (1 行) を当てた捨てコピーでは `test_conftest_guard.py` off で 5 passed |
| 6 | runbook 5 点目 (merge 後最初の日曜 10:00 の週次監視) | **成立** | `CLOCK_LEDGER.md:93-94,105-109,118-119,121-123` |
| 7 | 先頭行の表現 (「含まれる」) | **成立** | `:96-98` |
| 8 | タイムアウト時の exit 124 | **成立** | `:104-105` |
| - | 未知の値は黙って off にせず fail-fast | **成立** | `foo` → `ERROR: KEIBA_RUNTIME_GUARD=foo は使えない (使えるのは strict, off)` rc=4、テスト 0 本実行 |

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides: N/A (backtest artifact を生成しない改修)
- [x] baseline paired 比較: N/A
- [x] market_snapshot counts / payout 欠損: N/A
- [x] P25 fresh odds スケジューラ / coverage JSONL / bonus_candidate: N/A (type-D)。参考: 3 タスクとも Ready
- [x] 専門領域: partial write → なし。無限待ち → 週次 600 s / 124 健在。lock 未掃除 → 該当なし。dry-run が Discord に届く経路 → 遮断 (webhook 無しで POST 前に終了を実測)。テストが本番運用ログを汚す経路 → 実測ゼロ差分 (3,173 行一致)。**本番の定期実行が新たに失敗する経路 → あり (週次 pytest の 4 本、判定理由)** → HOLD
- [x] テスト: strict 944 passed / off 940 passed (隔離コピー、環境由来 1 件を除く差分は判定理由の 4 本のみ)

## 反証の試み (すべて隔離コピー、本番は読み取りだけ)

| # | 反証シナリオ | 結果 |
|---|---|---|
| F1 | `test_conftest_guard.py` を off で流す | **4 failed / 1 passed** (入れ子 pytest が `1 passed` で返り `assert 0 != 0`)。strict は 5 passed。**退行を確認** |
| F2 | 全テストを strict / off で流し差分を取る | strict `944 passed, 1 failed (env), 9 skipped, 166 s` / off `940 passed, 5 failed, 9 skipped, 223 s`。**差分 = F1 の 4 本のみ** |
| F3 | 本物の `weekly_monitor.bat` + 別プロセスの 20 ms 書き込み (9/27 10:00 相当) | `pytest exit 1` / `End (exit 3)` / notify 呼び出しあり (不達)。`data/logs` に pytest 出力なし、`data/monitor_runs/` にあり。**条件 3 成立、条件 2・5 不成立** |
| F4 | 同じ書き込み下の strict pytest (対照) | `62 passed, 1 error` 見張りのメッセージ。**見張り自体は健在** |
| F5 | 未知の値 `foo` | rc=4、テスト 0 本。**fail-fast 成立** |
| F6 | off が枠の子 / 通知隔離を外すか | 枠の子 `["strict","strict"]`、inner test の `NOTIFY_STATE_PATH` は tmp。**外さない** |
| F7 | 是正案 (`_pytest` で `KEIBA_RUNTIME_GUARD` を落とす) を捨てコピーで | off 5 passed / strict 5 passed / foo rc=4。**1 行で解決** |
| F8 | notify_discord が webhook 無しで POST するか | `read_text` が `FileNotFoundError` → `_post_webhook` 未到達 (`notify_discord.py:31-37`)。**しない** |
| F9 | 全実験前後の本番 data/logs / data/runtime / DB | 3,173 行 (path, size, mtime) 完全一致。本番に `weekly_monitor_20260926.log` / `monitor_runs` なし。**成立** |
| F10 | 本日以降の本番起動への影響 | 本番 HEAD d134b3b (main の conftest に見張り無し)、Action は main の bat。**merge までは影響なし** |

## 主な改善提案 (優先順)

1. **(HOLD 解除条件)** `tests/test_conftest_guard.py:34` で `KEIBA_RUNTIME_GUARD` を落とす / `strict` を明示 + `test_weekly_monitor_guard` の mini repo に本物の `test_conftest_guard.py` を同居させる case を追加 + 全テストを off で流して strict と差分ゼロを確認。
2. `data/monitor_runs/` の 0 byte `.stderr` は成功時に消す (or stderr も同じファイルへ)、古い `weekly_pytest_*.log` の掃除 (週 2 ファイルずつ増える)。
3. `weekly_monitor.bat:5` の RUNDATE を日次 bat と同じ JST + 失敗検出の形へ (C4、台帳どおり main 反映後)。
4. 起動器レベルの exit code 分離 / 成功時の 0 byte `rundate_stderr.txt` (前回提案のまま)。
5. A4 / A5 / A7 / A8 の naive `now` (台帳どおり)。

## 前回からの差分

- v1 (`37eaf61`) 3.8 HOLD → v2 (`1baab6c`) 4.2 PASS → v3 (`a9f3969`) 4.7 PASS → v4 (`27a260e`) 4.3 HOLD → **v5 (`209b636`) 4.4 HOLD** (+0.1)。
- 前回の解除条件 (a) 「見張りと weekly_monitor.bat の両立」: 設計 (2 値 / fail-fast / 出力先分離 / 枠は strict) は入ったが、**全テストを off で流す本物の形で 4 本が赤い** ため未達。前回条件の文書 3 点 (runbook 5 点目 / 「含む」 / 124) は完了。
- 項目別: bat 4.5→4.5、単一出典 4.5→4.5、依存 5→5、テスト 4→4、反映運用 3.5→4 (+0.5)。-0.3 以上の低下項目なし。
