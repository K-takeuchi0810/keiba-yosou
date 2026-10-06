# コード品質 / 保守性レビュアー 採点 — JST 統一 v5 (209b636, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象は `C:/Users/kizun/dev/keiba-yosou/.claude/worktrees/jst-unify` HEAD=209b636 に固定。git は `git -C <wt>`、Read/Grep は worktree 絶対パス。テスト実行と変異はすべて隔離コピー (`git archive 209b636` → scratchpad/gate5_quality/copy, copyA〜copyD) で行い、変異は `scripts/mutation_sandbox.py` 経由 (spec 5 本、23 変異)。本物の `weekly_monitor.bat` は隔離コピーでも起動していない (コピーに DB も webhook も無いが `scripts.notify_discord` が本物のため)。bat の挙動は `tests/test_weekly_monitor_guard.py` (スタブ付き仮リポ) と、bat が pytest に渡す環境 (`KEIBA_RUNTIME_GUARD=off`) を直接与えた pytest 実行で見た。worktree・本番 checkout・Task Scheduler・Discord には触れていない。終了時 worktree `git status --short` = 空、HEAD=209b636 不変、本番 `data/logs` / `data/runtime` の `ls -la --time-style=full-iso` が開始時と IDENTICAL、本番に `data/monitor_runs` 無し (確認済)。

**改修タイプ宣言**: type-B (テスト基盤 + 運用基盤、予測ロジック不変)。P25 固有ゲート (env_overrides / market_snapshot / weights / payout) は **N/A (対象外)**。汎用ゲートで採点。

**採点対象 (27a260e → 209b636、3 commit、8 files +362/-13)**: `tests/conftest.py` (見張り 2 値化 `runtime_guard_mode` / `pytest_configure`) / `weekly_monitor.bat` (off 化 + 出力を `data/monitor_runs/` へ) / `scripts/mutation_sandbox.py` (子プロセスを strict 固定、+5 行) / `tests/test_weekly_monitor_guard.py` (新規 201 行、10 テスト) / `tests/test_conftest_guard.py` (+1 同サイズ上書き) / `tests/test_mutation_sandbox.py` (+3 テスト、`..` のバックスラッシュ形 3 件) / `tests/test_sealed_clock.py` (+1) / `docs/CLOCK_LEDGER.md` (runbook 5 点目 + C4)。

**実測**: 隔離コピーで対象 4 ファイル 115 passed (93s)。全体 suite (archive コピー、.git 無し) は strict で 919 passed / 24 failed / 11 skipped (前回 901 passed、+18 = 追加分と一致)。失敗 24 件は前回と同じ環境要因 (23 件 = `tests/test_build_daily_results.py` が `git rev-parse HEAD` を .git 無しで実行、1 件 = `data/f3_phase0_0/metrics.json` 不在) で strict では回帰なし。**同じ suite を `KEIBA_RUNTIME_GUARD=off` (= weekly_monitor.bat が pytest に渡す環境) で流すと 28 failed / 915 passed** — 増えた 4 件はすべて `tests/test_conftest_guard.py` (下記)。変異 23 種: 19 KILLED / 4 SURVIVED、前回の生存 2 件 (R9 / K19) は今回 KILLED を実測。

## 判定: HOLD

**理由 (1 件、是正は 1 行 + 再実行)**: 今回の設計目標「週次監視と conftest の見張りが両立する」が、本物の tests/ に対しては成立していない。`weekly_monitor.bat:30` が `KEIBA_RUNTIME_GUARD=off` を set してから `pytest tests/` を起動するが、`tests/test_conftest_guard.py:34` の `_pytest()` は子 pytest の環境を `os.environ` から `PYTHONPATH` だけ落として作るので、`off` がそのまま仮リポの conftest に届き、「ログに書くテストが失敗すること」を確かめる 4 テスト (`:47` の 3 パラメータ + `:70` 同サイズ上書き) が「1 passed」で期待外れの緑になり、外側が赤くなる。隔離コピーで全体 suite を `off` で流して 4 件増を実測 (strict との差分がこの 4 件のみ)。結果、9/27 (日) 10:00 の最初の週次監視から毎週 pytest ビット (exit 2) が立ち、Discord に WARN が出続ける — conftest docstring (`tests/conftest.py:79-80`) が「毎週ほぼ確実に出る警告は読まれなくなる」と退けた状態を、別の経路で作ってしまう。新設の `tests/test_weekly_monitor_guard.py` がこれを捕まえないのは、仮リポの中に置くのが `_INNER_TEST` (`:45-59`、通知隔離 + 0.5 秒待ち) だけで、本物の tests/ にある「子 pytest を起動するテスト」を含まないから。`_env()` (`test_weekly_monitor_guard.py:108-113`) は `KEIBA_RUNTIME_GUARD` を落としているのに、同じ役目の `_pytest()` (`test_conftest_guard.py:33-39`) は落としていない — 同じ事実 (子 pytest に親の見張り設定を持ち込まない) が 2 箇所に別々に書かれ、片方だけ更新された典型 (DRY 減点の根拠)。

**是正案**: (a) `tests/test_conftest_guard.py:34` の env 構築で `KEIBA_RUNTIME_GUARD` を落とす (または `env["KEIBA_RUNTIME_GUARD"] = "strict"` を明示。`scripts/mutation_sandbox.py:238` と同じ「内側は常に strict」)。(b) 再発防止: `test_weekly_monitor_guard.weekly_repo` (`:62-80`) が本物の `tests/test_conftest_guard.py` も仮リポにコピーし、bat 経由で緑になることを見る (子 pytest を起動するテストは今後も増える)。(c) 是正後に `KEIBA_RUNTIME_GUARD=off` で `pytest tests/` を隔離コピーで 1 回流し、strict との失敗集合の差が空であることを確認してから merge。

CHAT 設計 4 点 (2 値 + fail-fast / bat の off 隔離と `data/monitor_runs/` / 枠の strict 固定 / R9・K19 閉鎖) 自体はいずれも実装・テスト・変異で確認できた (下記)。停止条件 (汎用) への抵触なし。

**根拠ファイル**: `tests/conftest.py:43-62,88-92` / `weekly_monitor.bat:22-37` / `scripts/mutation_sandbox.py:234-238` / `tests/test_weekly_monitor_guard.py:45-59,62-80,83-105,108-113,121-135,138-152,155-168,171-182,185-201` / `tests/test_conftest_guard.py:33-39,70-88` / `tests/test_mutation_sandbox.py:417-422,439-455,458-468,471-478` / `tests/test_sealed_clock.py:338-349` / `docs/CLOCK_LEDGER.md:69,93-121` / `.gitignore:10` / `scripts/auto_predict.py:71`

**次アクション**: 是正案 (a)(c) は 10 分、(b) は 20 分。その後 v6 で再採点 (この 1 件が閉じれば PASS 相当、テスト容易性は 4.5 へ戻る見込み)。

## 総合: 3.8 / 5 (前回 4.3、-0.5) — -0.3 以上の低下: DRY (4→3.5)、テスト容易性 (5→3.5)

## 項目別

- **DRY / 単一出典: 3.5/5** (前回 4) — 減点: (i) 子 pytest の環境構築が 2 箇所 (`test_conftest_guard._pytest:34` / `test_weekly_monitor_guard._env:109-110`) で、落とす変数の集合が乖離 (`PYTHONPATH` のみ vs `PYTHONPATH` + `KEIBA_RUNTIME_GUARD`) — 判定 HOLD の直接原因。(ii) 環境変数名 `KEIBA_RUNTIME_GUARD` の綴りが 5 箇所 (`conftest.py:46` の定数、`mutation_sandbox.py:238` リテラル、`weekly_monitor.bat:30,36`、`test_mutation_sandbox.py:445,452`、`test_weekly_monitor_guard.py:110,176,181,196`)。conftest だけ定数化しても他が参照していないので単一出典になっていない (bat は仕方ないが、Python 側 3 ファイルは `tests.conftest.RUNTIME_GUARD_ENV` か小さな共有モジュールを参照できる)。(iii) `_mini_repo` (`test_conftest_guard.py:22-30`) と `weekly_repo` (`test_weekly_monitor_guard.py:62-80`) は「本物の conftest をコピーした仮リポ」を別々に組み立てる。加点: 見張りの許容値は `RUNTIME_GUARD_MODES` 1 箇所 (`conftest.py:47`) で、エラー文言もそこから生成 (`:56`)。据え置き (バックログ、採点対象外): 監視対象の集合 3 重 (`conftest.py:27` / `mutation_sandbox.py:109` / `:166`)。
- **dead code / 未使用シンボル: 4/5** (前回 4) — 新規 import (`os` in conftest、`time` in test_mutation_sandbox、`shutil`/`threading`/`time` in test_weekly_monitor_guard) は使用済。`set "KEIBA_RUNTIME_GUARD="` (`bat:36`) は process-scoped なので実効なし (変異 B6 生存) だが衛生として可。`pytest_configure` (`conftest.py:60-62`) は本体を消しても fixture 側の `runtime_guard_mode()` が同じ例外を出すためテストで区別できない (変異 W3 生存: exit 1 の ERROR になるが「1 本も流さない」は保たれる)。前回指摘の `test_auto_predict_task_runner.py` import 配置は据え置き (バックログ)。
- **マジックナンバー / 設定外出し: 4/5** (前回 4) — `0.5` 秒 (`test_weekly_monitor_guard.py:55-58`)、`0.02` 秒 (`:97`)、`0.05` 秒 (`test_conftest_guard.py:82`)、`0.02` 秒 (`test_mutation_sandbox.py:465`) は根拠コメント付きで可 (0.5 s / 20 ms は 25 倍の余裕、負荷時も安定)。`.stderr` 接尾辞 (`bat:34`) と `data/monitor_runs` (`bat:27-28`) はリテラルだが bat 内 1 箇所ずつ。`600*1000` は既存。`timeout=300` (`:130,142`) と `120` は他のテストと同じ流儀。
- **テスト容易性 / 変更失敗モード: 3.5/5** (前回 5) — 加点: 10 テスト新設で bat と conftest の 2 値を実物のファイルをコピーして検査、変異 19/23 検出 (下表)。前回の R9 (`..` の分割を `/` だけに) は `test_dotdot_is_refused_even_if_it_stays_inside` のバックスラッシュ形パラメータで、K19 (見張りをサイズだけに) は `test_a_same_size_overwrite_fails_the_session` で今回 KILLED (再植え付けで実測)。枠の strict 固定は変異なし実行 + 変異ごとの両方で環境変数を記録する形 (`test_mutation_sandbox.py:439-455`) で、外す / off にする両変異を検出。`_ConcurrentWriter` (`:83-105`) は daemon スレッド + `join`、`writes` は join 後に読むのでレースなし、`assert w.writes > 0` (`:131`) で「再現になっていない」を弾く。後始末: ジャンクションは `os.rmdir` (`:80`)、pytest tmp に残骸なし (実測)。減点: (i) 判定理由の回帰 (本物の suite を off で流すと 4 件赤、新テストは仮リポのスタブしか流さないので見えない)。(ii) 変異 B7 生存: bat の `exit $p.ExitCode` を `exit 0` にしても全テスト緑 — 「赤い pytest が bat の exit 2 ビットに乗る」ことを見るテストが無く、`bat:31-33` の `$null=$p.Handle` 注意書き (2026-07-19 実測) も今もテストでは固定されていない。仮リポに失敗するテストを 1 本置いて `returncode & 2` を見るケースが 1 つあれば閉じる。(iii) W6 生存: `.strip()` を外しても通る (`" off "` のケース無し、bat は正確に `off` を渡すので実害なし)。
- **エラー処理 / 観測可能性: 4/5** (前回 4.5) — 加点: 未知の値は `pytest.UsageError` で exit 4、テスト 0 本 (実測: `warn` → `ERROR: KEIBA_RUNTIME_GUARD='warn' は使えない (使えるのは strict, off)`)、bat の週次ログに `pytest exit N (full output: <path>)` (`bat:37`) が残り、Discord 文言 (`bat:54`) → `LOGFILE` → `PYTESTLOG` の 2 hop で原因に辿れる (通常の FAILED は stdout なので `.log` に出る)。減点: (i) stderr の分離が runbook に無い: `-RedirectStandardError '%PYTESTLOG%.stderr'` (`bat:34`) により、この改修が作った fail-fast (UsageError) は stderr にしか出ない (実測: stdout 空) ので `weekly_pytest_<日付>.log` は空ファイルになり、週次ログが指す「full output」に原因が無い。`bat:37` の echo と `docs/CLOCK_LEDGER.md:108-109` に `.stderr` を併記するか、`cmd /c ... 2>&1` で 1 ファイルにまとめる。(ii) 見張りが off だったことがログに残らない: `conftest.py:89` の print は session fixture の中なので `-q` で捕捉され、緑なら出力に現れない (実測: `weekly_pytest_*.log` は `3 passed` のみ)。bat 側の echo (`bat:29`) にも `KEIBA_RUNTIME_GUARD=off` の文字が無いので、半年後に「この週の pytest は見張り無しで通った」と読めるのは bat のソースだけ。`bat:29` の echo に `guard=off` を足せば足りる。(iii) 緑のたびに 0 バイトの `.stderr` が `data/monitor_runs/` に溜まる (実測 0 バイト)。`data/*` は gitignore (`.gitignore:10`) なので checkout は汚れないが、保持期限の仕組みは無い。

### 自分で植えた変異 (隔離コピー、`scripts/mutation_sandbox.py` 経由、spec 5 本)

| # | 壊し方 | 結果 | 検出したテスト |
|---|---|---|---|
| W1 | 未知の値を黙って strict に | KILLED | test_an_unknown_guard_value_stops_pytest[foo] |
| W2 | 未知の値を黙って off に | KILLED | 同上 |
| W3 | `pytest_configure` を no-op に | SURVIVED (fixture 側の同じ例外で止まる、区別不能) | - |
| W4 | `.lower()` を外す | KILLED | test_strict_is_the_default_and_detects_changes[STRICT] |
| W5 | 空文字を off 扱いに | KILLED | 同 [空文字] |
| W6 | `.strip()` を外す | SURVIVED (空白付きのケース無し) | - |
| W7 | off で通知隔離まで外す | KILLED | test_the_weekly_monitor_passes_while_others_write_logs |
| W8 | 見張りを常に off に | KILLED | test_the_same_writes_fail_a_strict_run |
| W9 | `warn` を許容値に足す | KILLED | test_an_unknown_guard_value_stops_pytest[warn] |
| S1 | 枠が呼び出し元の見張り設定を継承 | KILLED | test_mutant_runs_ignore_a_caller_side_guard_off |
| S2 | 枠が off を強制 | KILLED | 同上 |
| S3 | 本番 snapshot を `rglob` → `glob` | KILLED | test_a_leak_into_a_production_subdirectory_is_detected |
| S4 | 本番 snapshot をサイズだけに | KILLED | test_a_same_size_overwrite_in_production_is_detected |
| B1 | bat の off を外す | KILLED | test_the_weekly_monitor_passes_while_others_write_logs |
| B2 | pytest 出力を data/logs に | KILLED | test_pytest_output_does_not_go_to_data_logs |
| B3 | stdout redirect を外す | KILLED | 同上 |
| B4 | bat が `warn` を渡す | KILLED | test_the_weekly_monitor_passes_while_others_write_logs |
| B5 | `pytest exit N` の echo を外す | KILLED | test_pytest_output_does_not_go_to_data_logs |
| B6 | off の解除を外す | SURVIVED (process-scoped、実害なし) | - |
| B7 | `exit $p.ExitCode` → `exit 0` | SURVIVED (赤い pytest のケース無し) | - |
| B8 | `mkdir data/monitor_runs` を外す | KILLED | test_the_weekly_monitor_passes_while_others_write_logs |
| R9 | (前回生存) `..` の分割を `/` だけに | KILLED | test_dotdot_is_refused_even_if_it_stays_inside[バックスラッシュ形] |
| K19 | (前回生存) 見張りをサイズだけに | KILLED | test_a_same_size_overwrite_fails_the_session |

## 変更失敗モード分析

1. **子 pytest を起動するテストを 1 本足すとき** (今回の実例): 親の `KEIBA_RUNTIME_GUARD` を落とし忘れると、開発時 (strict 既定) は緑、週次監視 (off) だけ赤 — 開発者の手元では静かに通り、日曜に Discord で見つかる。構造的には「子 pytest の環境を作る関数」を 1 つ (例: `tests/_subprocess.py` の `child_env()`) にして、`_pytest` / `_env` / `mutation_sandbox._pytest` が全部それを使うのが本筋。今回はそこが 2 箇所に分かれた瞬間に乖離した。
2. **環境変数名を変えるとき**: `conftest.py:46` の定数を変えても `mutation_sandbox.py:238` は古い名前を strict にし続け、新しい名前は呼び出し元から素通り — 静かに壊れる (`test_mutant_runs_ignore_a_caller_side_guard_off` も古い名前のリテラルを読むので緑のまま)。Python 側だけでも `tests.conftest.RUNTIME_GUARD_ENV` を参照すれば即座に落ちる形にできる。
3. **見張りに第 3 のモードを足すとき** (例: `warn`): `RUNTIME_GUARD_MODES` に足しただけでは fixture の `== "off"` 分岐 (`conftest.py:88`) は strict と同じ挙動 → 「受け付けるが何も変わらない」が静かに成立。ただし `test_an_unknown_guard_value_stops_pytest[warn]` が即座に落ちる (変異 W9 で確認) ので、警告モード禁止の設計意図はテストが守っている (良)。

## 依頼への回答 (重点項目)

- **conftest の 2 値の実装**: `runtime_guard_mode()` (`:50-57`) は `.strip().lower() or "strict"` で大文字・前後空白・空文字を吸収し、`("strict", "off")` 以外は `pytest.UsageError`。`pytest_configure` (`:60-62`) で最初に呼ぶのでテスト 0 本で exit 4 (実測)。off の範囲: `_tests_do_not_touch_runtime_logs` の前後比較 (`:88-92`) だけ。`_isolate_notification_state` (`:14-24`) は無条件で、W7 で外すと bat 経由の `test_notification_state_is_still_isolated` が落ちるのを確認。枠 (`mutation_sandbox.py:238`) は strict 固定 (S1/S2)。範囲は設計どおり。
- **weekly_monitor.bat**: `-RedirectStandardOutput` / `-RedirectStandardError` は別ファイル (同一ファイルは Start-Process が拒否するので正しい)。相対パスは `cd /d "%~dp0"` 後の cwd 基準で、テストは `cwd=weekly_repo.parent` (`:129`) から起動して cd を検証。環境変数は `set "..=off"` → powershell → `set "..="` (`:30,36`) で、PowerShell は cmd の環境を継承。ASCII / CRLF: bat は ASCII、CRLF (index は LF、autocrlf で作業ツリー CRLF、`file` で確認)。`$null=$p.Handle` の注意書き (`:31-33`) は redirect 追加後もそのまま有効 (Handle 参照は変えていない) が、テストでは固定されていない (B7 生存)。失敗時の観測性: 通常の赤は `.log` に、この改修の fail-fast は `.stderr` に (上記)。
- **test_weekly_monitor_guard.py の質**: スタブ (`:37-41`) は `scripts.monitor` / `fresh_odds_coverage` / `notify_discord` を記録専用に差し替え、Discord には届かない。同時書き込みスレッドは `Event` + `join` で確実に止まり、`writes > 0` を前提条件として検査。0.5 秒待ち (`:58`) は 20 ms 周期の 25 倍で、strict 対照テストは前後比較の間に必ず書き込みが入る。後始末はジャンクション `rmdir` のみで、tmp_path 以外に書かない (calls.txt も仮リポ内)。弱点: 仮リポの中身がスタブ 3 本だけなので、本物の tests/ が off で通るかは見ていない (判定理由)。
- **枠の strict 固定**: `mutation_sandbox.py:237-238` で `os.environ` 展開後に上書き、テスト (`test_mutation_sandbox.py:439-455`) は変異なし実行と変異 1 本の両方で `"strict"` を記録。S1/S2 KILLED。
- **回帰**: strict の全体 suite は失敗集合が前回と同一 (環境要因 24 件)、+18 passed。バックログ 4 件 (監視対象 3 重 / NOT_APPLIED / timeout / import 配置) は差分に無く据え置き (`mutation_sandbox.py` の差分は 5 行のみ)。off での全体 suite に 4 件の新規失敗 (判定理由)。

## 停止条件チェック

- [ ] git_sha / env_overrides / market_snapshot / payout — N/A (type-B)
- [x] 汎用: 新規経路 (2 値の見張り / bat の off と出力先 / 枠の strict 固定) すべてに回帰テストあり、変異 19/23 検出、前回生存 2 件は閉鎖
- [x] 汎用: 例外の握り潰しの新設 — 無し (未知の値は UsageError)
- [x] 汎用: 既存テストの無効化 — 無し
- [x] 汎用: 本番への痕跡 — 無し (data/logs, data/runtime IDENTICAL、data/monitor_runs 無し、worktree clean、HEAD=209b636 不変)
- [ ] 汎用: 本番運用経路で赤にならない — NG (週次監視の環境で `tests/test_conftest_guard.py` 4 件が赤、HOLD 理由)

## 反証の試み

- 「週次監視と見張りは両立する」→ 仮リポ (スタブ) では成立、本物の tests/ では不成立 (off で 4 件赤)。
- 「未知の値でテストは 1 本も流れない」→ 成立 (exit 4、stdout 空、W1/W2/W9 KILLED)。
- 「off で止まるのは前後比較だけ」→ 成立 (W7 KILLED、通知隔離は生きている)。
- 「枠は呼び出し元の off を持ち込まない」→ 成立 (S1/S2 KILLED)。
- 「R9 / K19 は閉じた」→ 成立 (両方 KILLED を再植え付けで実測)。
- 「赤い pytest は bat の exit に乗る」→ 未固定 (B7 生存、テスト無し)。

## 主な改善提案

1. **`tests/test_conftest_guard.py:34`** — env から `KEIBA_RUNTIME_GUARD` を落とす (または `"strict"` を明示)。HOLD 解除の必須 1 行。
2. **`tests/test_weekly_monitor_guard.py:62-80`** — `weekly_repo` に本物の `tests/test_conftest_guard.py` もコピーし、bat 経由で緑になることを見る。あわせて仮リポに失敗するテスト 1 本を置くケースを足し、bat の returncode に 2 ビットが立つこと (B7、`$null=$p.Handle` の固定) を見る。
3. **`weekly_monitor.bat:29,37` + `docs/CLOCK_LEDGER.md:108-109`** — echo に `guard=off` と `.stderr` の場所を併記 (または `cmd /c ... 2>&1` で 1 ファイルに)。
4. **子 pytest の環境構築を 1 箇所に** — `_pytest` / `_env` / `mutation_sandbox._pytest` の env 生成を共通化し、Python 側の `KEIBA_RUNTIME_GUARD` リテラルは `tests.conftest.RUNTIME_GUARD_ENV` 参照に。
5. (前回から継続) 監視対象集合の 3 重 / `NOT_APPLIED` / `_pytest()` の timeout / import 配置 — バックログのまま。

## 前回からの差分 (20260926_0240 code-quality = 4.3 / PASS)

- DRY 4→3.5 (-0.5: 子 pytest 環境の 2 重が乖離、env 名 5 箇所) / dead code 4→4 / マジックナンバー 4→4 / テスト容易性 5→3.5 (-1.5: 本番運用経路 (週次監視) で 4 件赤になる回帰を新テストが捕まえない、B7 生存。R9/K19 閉鎖と 10 テスト新設は加点済) / 観測可能性 4.5→4 (-0.5: fail-fast の出力が `.stderr` にしか無く runbook が指していない、off の記録が残らない)
- 判定 PASS→HOLD。総合 4.3→3.8 (-0.5)。-0.3 以上の低下 2 項目 (DRY、テスト容易性) — 警告。
