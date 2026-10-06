# 検証プロセス監査人 (最終ゲート) 採点 — JST 統一 v5 (209b636, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `209b636` 固定、worktree `C:/Users/kizun/dev/keiba-yosou/.claude/worktrees/jst-unify`。git は全て `git -C <wt>`、Read/Grep は worktree 絶対パス。変異は **全件 `scripts/mutation_sandbox.py` 経由** (隔離コピー A = `git archive 209b636 | tar -x` → scratchpad `gate5_validation` + `.venv64` ジャンクション + worktree の小 DB 499,712 B 複製。枠の事前検査: `check_production()` = 空、`check_sandbox(コピー)` = 空、`check_sandbox(worktree)` = 「本番 checkout の中」「.git あり」で拒否)。週次監視の再現は別の隔離コピー B (`gate5_weekly`、同じ archive + ローカル `git init` で HEAD を用意 = `git rev-parse HEAD` 依存の 23 テストを本番と同条件に、webhook ファイル無し) で実施。worktree・本番 checkout のファイルは未編集、SHA 不動、Task Scheduler は `Get-ScheduledTask` の読取のみ、Discord 未送信 (コピー B の bat は `discord_webhook.txt` 不在で「notification failed」= 送信経路に到達せず)。前回 v4 (27a260e、PASS 4.5) からの差分 3 commit (8 files +362 −13) と CHAT 指定の解除条件 5 件 + 前回生存変異 4 件の閉鎖を中心に確認し、ゼロからの再点検はしていない。表記: 前回の V-Xc プライム (V-Xc-p と書く) はプライム記号の代替。

## 判定: HOLD (最終ゲート — CHAT 指定の解除条件 2 と 5 が **実スイートでは不成立**。他 agent の v5 判定は本 scorecard 執筆時点で未提出)

**理由 (1 件、是正は 1 行だが merge 前に必須)**: 週次監視が `KEIBA_RUNTIME_GUARD=off` で pytest を回すと、その環境変数は **pytest の中から子 pytest を起動するテストにも継承される**。`tests/test_conftest_guard.py:34` の `_pytest()` は `PYTHONPATH` だけを落として環境を引き継ぐので、本物の conftest を複製した小リポの見張りも off になり、「ログに書くテストは失敗すること」を期待する 4 本 (`test_a_test_that_writes_runtime_logs_fails_the_session[logs / logs-append / runtime]`、`test_a_same_size_overwrite_fails_the_session`) が **assert `returncode != 0` で落ちる**。隔離コピー B で **本物の `weekly_monitor.bat` (209b636) を、20 ms ごとに `data/logs` と `data/runtime` に書く別スレッド (8,607 回) の下で流した結果: `pytest exit 1` → `5 failed, 940 passed, 9 skipped` (4 件が上記、1 件 `test_f3_phase0_0_eval::test_saved_pair_reproduces_frozen_validation_auc` はコピー環境由来 = 未追跡 `metrics.json` 不在、strict の対照でも同じ 1 件が落ちる) → bat 終了コード 3 (bit 1 = 小 DB で `scripts.monitor` が WARN = 環境、**bit 2 = pytest = 欠陥**) → Discord 通知経路へ進んだ (webhook 不在で失敗)。つまり **9/27 (日) 10:00 の本番では `WARN: weekly monitor alert (... pytest=1 ...)` が飛ぶ** — data-pipeline v4 が HOLD にした症状 (毎週の偽警報) が、経路を変えて残っている。作者の `test_the_weekly_monitor_passes_while_others_write_logs` が緑なのは、その小リポに `test_inner.py` (3 本) しか無く、**入れ子 pytest を起動する本物のテストが含まれていない**ため。同じ形の継承漏れを `scripts/mutation_sandbox.py:238` は「常に strict」で塞ぎ、`test_weekly_monitor_guard._env()` も自分では落としているのに、`test_conftest_guard._pytest()` だけが漏れている。
**成立しているもの**: 解除条件 1 (strict は検出する: 対照 B で exit 1、見張りの message に同時書込みの 2 ファイル名)、3 (pytest の出力は `data/monitor_runs/` に、`data/logs` の週次ログに "passed" 無し)、4 (枠の子は常に strict = V-S1 撃墜、通知状態の隔離は off でも有効 = V-W21 撃墜)、未知の値 `warn` は **テストを 1 本も流さず exit 4** (probe C)、前回生存 4 件 (V-R2b / V-E3c / V-Xc-p / V-F7b) は **当方の再植で全て KILLED**、runbook 5 点目 + 文言 2 件 + C4 行、全 suite **944 passed / 9 skipped / 1 deselected × 2** (PYTHONIOENCODING 未設定 / utf-8) で作者の実測と **一致**。
**改修タイプ**: type-B (テスト基盤 + 運用基盤。predictor / backtest / GUI 非接触)。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN) は **N/A (対象外)**。
**根拠ファイル**: `tests/conftest.py:43-62,88-92` / `tests/test_conftest_guard.py:33-39` / `tests/test_weekly_monitor_guard.py:107-112,127-141` / `weekly_monitor.bat:22-37` / `scripts/mutation_sandbox.py:231-243` / `tests/test_mutation_sandbox.py:417-480` / `tests/test_sealed_clock.py:338-350` / `docs/CLOCK_LEDGER.md:69,93-131` / scratchpad `gate5_spec_{s,ws,wc,wb}.py` + `_result.txt` / `gate5_weekly_repro.py` + `gate5_weekly_repro_result.txt` / `gate5_probe_off_inherit.txt` / `gate5_weekly/data/monitor_runs/{weekly_pytest_20260926.log,control_strict.log,probe_warn.log}` / `gate5_suite_run{1_noenc,2_utf8}.txt` / `gate5_prod_snapshot_before.json`
**解除条件 (本 agent)**: (a) `tests/test_conftest_guard.py::_pytest` の env から `KEIBA_RUNTIME_GUARD` を落とす (`test_weekly_monitor_guard._env` と同じ形) か `"strict"` を明示する。(b) **本物のテスト集合**が off でも同じ結果になる証拠を 1 つ: 隔離コピーで `KEIBA_RUNTIME_GUARD=off` の `pytest tests/` が strict と同じ pass 集合になること (作者の実測でよいが、当方も再実行する)。(c) それを固定するテスト: 週次監視の小リポに本物の `tests/test_conftest_guard.py` も複製する (依存は conftest だけ) か、`test_conftest_guard.py` を off の subprocess で流して exit 0 を見るテスト。(a) から (c) が揃えば、当方は PASS に戻す (他 agent に FAIL / NOT_EVALUABLE が無いことが前提)。

## 総合: 4.2 / 5 (前回 4.5 / PASS → −0.3、判定は HOLD)

低下根拠: 「週次監視が緑」の証拠が実スイートを含まない小リポで作られ、実スイートでは赤 (項目 1 −0.7、項目 5 −0.8 = 警告閾値超)。上昇要素: 前回の網の目 4 件の閉鎖、未知の値の fail-fast、枠の子の strict 固定、runbook の補強。

## CHAT 指定の解除条件 — 成立表

| # | 解除条件 | 判定 | 一次証拠 (自分で実行したもの) |
|---|---|---|---|
| 1 | strict では本番 runtime の変更を検出して fail する | **成立** | 対照 B (コピー B、bat と同じ PowerShell 行、env に `KEIBA_RUNTIME_GUARD` 無し = 既定 strict、同時書込み 7,624 回): **exit 1**、message 「テストが運用ログ置き場を変更した … [data/logs/fresh_odds_concurrent.log, data/runtime/concurrent_state.json]」。変異: V-W19 (`.lower()` 無し) → `[STRICT]` で KILLED、V-W22 (空文字の既定を off) → `[]` で KILLED、V-E3c (mtime 無視) / V-K19b (mtime を秒単位) → `test_a_same_size_overwrite_fails_the_session` で KILLED |
| 2 | 週次監視では global guard を明示的に off にして正常完走する | **不成立** | コピー B で本物の bat を実スイートに対して実行: **`pytest exit 1` / 5 failed, 940 passed** (4 件 = `test_conftest_guard.py` が off を子 pytest に継承、1 件 = コピー環境)。直接 probe (bat を介さず `KEIBA_RUNTIME_GUARD=off` で `test_conftest_guard.py test_weekly_monitor_guard.py test_mutation_sandbox.py`): **4 failed, 60 passed**、失敗の message は「logs への書き込みを見逃した … 1 passed in 0.06s」= 子 pytest の見張りが止まっていた証拠。作者の `test_the_weekly_monitor_passes_while_others_write_logs` は suite の中では緑 (小リポの 3 本だけが対象) |
| 3 | 週次監視自身は本番 data/logs へ pytest の出力を書かない | **成立** | bat 実行後: `data/logs` = `weekly_monitor_20260926.log` (+ 当方の同時書込みファイル) のみ、その中身に "passed" 無し、`pytest exit 1 (full output: data/monitor_runs/weekly_pytest_20260926.log)` の 1 行だけ。`data/monitor_runs/` = `weekly_pytest_20260926.log` (11,385 B) + `.stderr` (0 B)。`data/monitor_runs` は `.gitignore` `data/*` で無視 (git status を汚さない)。**網の目**: V-W14 (stderr だけ data/logs へ) **SURVIVED** — テストは `weekly_monitor_*.log` の glob と stdout しか見ない (低) |
| 4 | off が変異の枠などの別の安全機構を無効化しない | **成立** | V-S1 (枠の子に strict を渡さず継承) → `test_mutant_runs_ignore_a_caller_side_guard_off` で KILLED。V-W21 (off で通知状態の隔離も止める) → 週次監視の内側テスト `test_notification_state_is_still_isolated` 経由で KILLED。`grep KEIBA_RUNTIME_GUARD` の読み手は conftest / 枠 / 2 テストファイル / bat / 台帳のみ。**ただし** off は環境変数なので、それを落とさない子プロセスには継承される — 条件 2 の欠陥はこの裏面 |
| 5 | 9/27 10:00 と同等の同時書き込み条件を再現して exit 0 | **不成立 (実スイート)** | 上記 2。bat 終了コード 3 のうち bit 2 (pytest) が欠陥。作者の小リポ版 (suite 内 `test_weekly_monitor_guard.py`) は当方の 2 回の suite 実行でも緑 = 「小リポでは exit 0」までは成立 |

補助 probe: **C** `KEIBA_RUNTIME_GUARD=warn` → `ERROR: KEIBA_RUNTIME_GUARD=warn は使えない (使えるのは strict, off)`、**exit 4、"passed" 無し** (テストを 1 本も流さない = 警告モード不在の設計どおり)。**D** リダイレクト先ディレクトリ不在 (mkdir を落とした場合) → PowerShell **exit 1** → `TESTCODE=1` (黙って 0 にならない = fail-closed)。

## 前回生存変異の閉鎖 (CHAT 指示分) — 当方の再植

| 前回 ID | 変異 | 今回 | 撃墜テスト |
|---|---|---|---|
| V-R2b / R9 | `..` の検査を `/` 区切りだけに | **KILLED** | `test_dotdot_is_refused_even_if_it_stays_inside[sub..calc.py]` (バックスラッシュ区切りのケース) |
| V-E3c / K19 | conftest の見張りが mtime を見ない | **KILLED** | `test_a_same_size_overwrite_fails_the_session` |
| V-Xc-p | 枠の snapshot を rglob → glob | **KILLED** | `test_a_leak_into_a_production_subdirectory_is_detected` |
| V-F7b | SEALED_FROM 検査を today/now 指定時だけ | **KILLED** | `test_a_malformed_sealed_from_is_rejected_on_the_default_path` |

## 変異表 (独立設計、`scripts.mutation_sandbox` 経由、fresh .pyc、毎回 byte 復元、本番 snapshot 差分ゼロ)

21 種: **16 KILLED / 5 SURVIVED** (等価 2、網の目 3。挙動の欠陥は変異ではなく条件 2 の実測で発見)。

| spec / ID | 変異 | 結果 | 備考 |
|---|---|---|---|
| s V-F7b (再) | SEALED_FROM 検査を today/now 指定時だけ | KILLED | 既定経路テストが機能 |
| s V-F7c | artifact_drift が門を迂回して自前で比べる | KILLED | 同上 |
| ws V-S1 | 枠の子に strict を渡さない | KILLED | |
| ws V-Xc-p (再) | 枠 snapshot rglob → glob | KILLED | |
| ws V-R2b (再) | `..` を `/` 区切りだけ | KILLED | |
| ws V-R9c | `..` をバックスラッシュ区切りだけ | KILLED | `[sub/../calc.py]` |
| ws V-S2 | 枠 snapshot の mtime を落とす | KILLED | `test_a_same_size_overwrite_in_production_is_detected` |
| wc **V-W8** | `pytest_configure` の fail-fast を外す (fixture の検査だけ) | **SURVIVED** | 等価に近い: session fixture が UsageError → 全テスト ERROR、本体は 1 本も走らない。安全差なし |
| wc V-W19 | `.lower()` を落とす | KILLED | `[STRICT]` |
| wc V-W20 | 未知の値を黙って off に | KILLED | `[foo]` |
| wc V-W21 | off で通知状態の隔離も止める | KILLED | 内側テスト経由 |
| wc V-W22 | 空文字の既定を off に | KILLED | `[]` |
| wc **V-W29** | off 判定を `!= "strict"` に | **SURVIVED** | 等価 (値は 2 つに限定済) |
| wc V-E3c (再) | conftest 見張りが mtime を見ない | KILLED | |
| wc V-K19b | conftest 見張りの mtime を秒単位に | KILLED | `existing.log` の作成と上書きが別秒に落ちるため。境界依存 (低) |
| wc **V-Xc3** | conftest 見張りを rglob → glob | **SURVIVED** | 枠は閉じたが conftest 側は未閉鎖 (監視対象が 3 箇所に散る code-quality (c) の帰結)。本番にサブディレクトリ無し (低) |
| wb **V-W14** | pytest の stderr を data/logs へ | **SURVIVED** | 条件 3 の網の目 (低) |
| wb V-W24 | 見張りを `warn` で流す | KILLED | bat exit ≠ 0 |
| wb V-W25 | `monitor_runs` を作らない | KILLED | probe D と整合 (fail-closed) |
| wb **V-W26** | bat が pytest の終了コードを捨てる (`TESTCODE=0`) | **SURVIVED** | 赤い pytest → bit 2 のテストが無い (中)。今回見つけた欠陥は **まさに bit 2 で顕在化する**ので、この網の目は次回までに閉じる価値が高い |
| wb V-W30 | off を pytest の前で外す (strict で流れる) | KILLED | |

作者の 85 種 (`jst_mut10_result.txt`): 84 撃墜 / F6 生存を読んだ。F6 (`today or …`) は `_require_daystamp` が空文字を先に落とすので等価 — 前回と同じ判断。W1〜W7 / K19 / Xc2 / R9 / F7b の撃墜は当方の再植と整合。

## 従来項目の回帰確認

| 項目 | 判定 | 証拠 |
|---|---|---|
| 全 suite | 一致 | worktree で **944 passed / 9 skipped / 1 deselected** × 2 (160 s / 264 s、rc 0)。作者の実測と一致。`test_provenance.py:144` は未追跡コード無しで skip (作者説明どおり) |
| conftest 見張り (strict) | 機能 | 対照 B で検出。worktree `data/logs` `data/runtime` の `ls --full-time` は開始時と suite 2 回後・終了時で **完全一致** |
| 枠 (`mutation_sandbox`) | 機能 | 21 変異 + 4 spec の変異なし実行で本番 snapshot 差分ゼロ (途中 ABORT 無し) |
| runbook (`docs/CLOCK_LEDGER.md`) | 更新あり | 5 点目 (週次監視: LastTaskResult / `pytest exit 0` / `data/monitor_runs`) + 項目 1 「含まれる」+ 項目 3 タイムアウト時 `finish` 行無し + 確認コマンド 2 行 + 記録表の列追加 + C4 (bat のローカル日付) — data-pipeline v4 の提案 2 (i)(ii)(iii) を全て消化。**ただし** 5 点目の `pytest exit 0` は現状のままだと 9/27 に `pytest exit 1` が記録される |
| Task Scheduler (読取) | 不変 | `keiba-yosou-weekly-monitor` Ready、次回 09/27 10:00、直近 09/20 result 0、Action は main の `weekly_monitor.bat`。`keiba-fresh-odds` 次回 09/26 09:00、healthcheck 09:15、auto-predict 08:00 (本 review は 04:40〜05:02 に完了、本番書込み開始前) |
| main | 不変 | 本番 HEAD `d134b3b`、`merge-base --is-ancestor d134b3b 209b636` 真 (ff 可能) |

## 前回 (v4) の次回宣言の執行

| # | 宣言 | 執行結果 |
|---|---|---|
| (1) | bat だけの cherry-pick で main 反映なら FAIL | **未発生** (main `d134b3b` 不動) |
| (2) | SEALED_FROM 設定と時計の同居なら FAIL | **非該当** (`config.py:232` `SEALED_FROM = None`、この差分に config.py 無し) |
| (3) | 枠を経由しない変異証拠は不成立 | **全件経由** (spec 4 本、コピー A) |
| (4) | merge 後の runbook 表が空 / DATE_FAILURE 新規なら HOLD | **未到達** (merge 前。本番に `auto_predict_daily_20260926.log` / `DATE_FAILURE` は無し = 当方の痕跡も無し) |
| (5) | 提案 3 (SEALED_FROM 既定経路テスト) が config.py を触る commit に無ければ 4.0 上限 | **消化** (config.py は未変更だが 87f54c4 でテストが先に入った。V-F7b / V-F7c 撃墜) |

## 項目別

- **検証設計の正しさ (証拠が持続するか): 4.0/5** (前回 4.7、−0.7 警告) — 加点: 前回の網の目 4 件を閉鎖、未知の値の fail-fast、枠の子を strict 固定、strict の対照テスト。減点: 「週次監視が緑」の証拠が **実スイートに含まれる入れ子 pytest のテストを含まない小リポ**で作られ、実スイートでは赤。環境変数による 2 値切替は「子プロセスに継承される」性質を持ち、その洗い出し (`grep` で読み手を列挙し、子 pytest を起動する箇所 = `test_conftest_guard._pytest` / `test_weekly_monitor_guard._env` / `mutation_sandbox._pytest` の 3 つ全てを見る) が 1 つ抜けた。
- **時間境界 (リーク分類学①の運用版): 4.5/5** (前回 4.5) — この差分は時計に触れていない。C4 (bat のローカル日付) が台帳に載った。
- **変異テスト (独立設計): 4.5/5** (前回 4.6) — 21 種 16/5。前回生存 4 件は全て閉鎖。新しい網の目 3 件 (V-Xc3 / V-W14 / V-W26) のうち V-W26 は今回の欠陥と同じ経路 (bit 2) にあるので中。
- **A/B・再現性: 4.6/5** (前回 4.6) — 944/9/1 × 2 で一致、ff 可能、SEALED_FROM None。
- **運用移行 / 統合判定 / 台帳: 3.5/5** (前回 4.3、−0.8 警告) — runbook は補強されたが、merge すると **9/27 10:00 の週次監視が pytest=1 で赤 + Discord WARN** になる (data-pipeline v4 HOLD の症状そのもの)。v5 sibling (data-pipeline / code-quality) は未提出。data-pipeline v4 の解除条件 (a) の文言「隔離コピーで data/logs へのリダイレクト付きの pytest が緑」は小リポでは満たすが、実スイートでは満たさない — 同 agent も HOLD 継続と見込む。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides / market_snapshot / factorial / bootstrap — **N/A** (type-B)
- [x] 比較設計 (期間 / code path / filter / fold) — N/A
- [x] 専門領域「証拠を生む仕組み」の欠陥 — **抵触あり (HOLD 相当)**: 採用条件 2 / 5 の証拠が対象集合を縮めた再現で作られ、実対象では不成立。変異は枠経由で本番不達
- [x] 他 agent 判定との不整合 — v5 sibling 未提出。v4 data-pipeline HOLD の症状が経路を変えて残る → 本 agent も HOLD
- [x] 前回宣言の執行 — 上表 (1)(2) 非該当、(3) 全件経由、(4) 未到達、(5) 消化
- [x] SEALED_FROM = None のまま — `config.py:232`

## 反証の試み

- 「週次監視は off で完走する」→ 実スイート + 本物の bat + 同時書込み → **pytest exit 1 (4 件が off の継承)** → **不成立**
- 「strict は同じ条件で落ちる」→ 対照 B → 成立 (2 ファイル名を挙げて落ちる)
- 「未知の値は 1 本も流さず止まる」→ `warn` → exit 4、"passed" 無し → 成立
- 「off は枠 / 通知隔離を外さない」→ V-S1 / V-W21 KILLED → 成立
- 「pytest 出力は data/logs に無い」→ 週次ログに "passed" 無し、`monitor_runs` にある → 成立 (stderr は未固定)
- 「944 passed」→ 当方 944 × 2 → 一致
- 「前回生存 4 件は閉じた」→ 再植 4/4 KILLED → 成立
- 「F6 は等価」→ 前回と同じ判断 → 成立

## 改善提案 (解除条件以外、採用条件ではない)

1. `tests/test_conftest_guard.py:34` — `if k.upper() not in ("PYTHONPATH", "KEIBA_RUNTIME_GUARD")` (**解除条件 (a)**)。
2. `tests/test_weekly_monitor_guard.py::weekly_repo` — 本物の `tests/test_conftest_guard.py` も小リポに複製する (**解除条件 (c)** の最短形。同ファイルは conftest 以外に依存しない)。
3. `tests/test_weekly_monitor_guard.py` — 内側テストに **赤いテスト** を 1 本足したケースで bat の終了コードに bit 2 が立つこと (V-W26)。
4. 同 — data/logs に `weekly_pytest_*.stderr` 等が **無い**ことも見る (V-W14)。
5. `tests/conftest.py` の off 分岐 — `print` (-q では見えない) ではなく `warnings.warn` / `config.issue_config_warning` 相当で summary に 1 行出す (off で流れたことが後から読める。「警告モード」ではなく off の可視化)。
6. `tests/conftest.py:36` — rglob を維持しつつ `test_conftest_guard` にサブディレクトリの 1 件 (V-Xc3)。監視対象の集合を `mutation_sandbox.PRODUCTION_WATCH` に寄せれば code-quality (c) と同時に解消。

## 前回からの差分

- 前回 (20260926_0240、27a260e): 4.5 / PASS → 今回 (209b636): 4.2 / **HOLD** (−0.3)。−0.3 以上の低下 2 項目 (検証設計 −0.7、運用移行 −0.8) = 警告。
- 前回提案の消化: 2 (バックスラッシュ `..`) 済 / 3 (SEALED_FROM 既定経路) 済 / 4 (同サイズ上書き) 済 / 5 (サブディレクトリ、枠側) 済 (conftest 側は未) / 1 (FROZEN 08:00 JST) 未 / 6 (naive now / index.html / PRODUCTION_ROOT) 未。

## 終了時の記録

- worktree `git status --short` = **空** (開始時・suite 2 回後・終了時)、HEAD = `209b636` 不動。本番 HEAD `d134b3b` 不動。
- 本番 `data/logs` + `data/runtime` + DB (3,172 エントリ) の開始 / 中間 / 終了 snapshot 差分 = **空**。本番に `data/monitor_runs` **無し**、`weekly_monitor_20260926.log` / `auto_predict_daily_20260926.log` / `DATE_FAILURE.log` **無し** (当方の痕跡なし)。worktree `data/logs` `data/runtime` の `ls --full-time` は開始時と **完全一致**。
- ジャンクション 2 本 (`gate5_validation/.venv64`、`gate5_weekly/.venv64`) は `rmdir` で解除 (不在を確認)、実 venv `python.exe` 健在 (site-packages 107)。隔離コピー (リンク無し) と spec / 結果 / probe / 週次ログは scratchpad `gate5_*` に残置。
- Task Scheduler 未操作 (読取のみ)、Discord 未送信、SEALED_FROM = None。すべての実験は 04:40〜05:02 JST に完了 (本番の 08:00 起動前)。

## 次回宣言 (必ず執行する)

- (1) main への反映が **bat だけの cherry-pick** (jst.py 不在) なら **FAIL** (継続)。
- (2) `SEALED_FROM` に日付を入れる commit が時計・bat の変更と同居していたら **FAIL** (継続)。
- (3) 変異テストの結果が `scripts/mutation_sandbox.py` を経由せずに報告された (または隔離コピーが本番 checkout の中にある) 場合、その変異証拠は **不成立** (継続)。
- (4) merge 後にこの系列を採点するとき、runbook 表が空のまま、または `DATE_FAILURE.log` が merge 後に新規生成されていたら **HOLD** (継続)。
- (5) **新規**: 次回、解除条件 2 の証拠が **実スイート全体を off で流した結果** (または本物の `test_conftest_guard.py` を含む再現) で示されていなければ、作者の小リポテストが緑でも **HOLD 継続**。当方は隔離コピーで `KEIBA_RUNTIME_GUARD=off` の `pytest tests/` を必ず再実行する。
- (6) **新規**: `weekly_monitor.bat` を次に触る commit に「赤い pytest → 終了コード bit 2」のテスト (V-W26) が無ければ、その回の「運用移行」項目を 4.0 上限にする (ゲートではない)。
