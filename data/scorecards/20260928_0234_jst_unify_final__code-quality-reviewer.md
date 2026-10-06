# コード品質 / 保守性レビュアー 採点 — JST 統一 最終ゲート (89a3840, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象は `C:/Users/kizun/dev/keiba-yosou/.claude/worktrees/jst-unify` HEAD=`89a3840b0ee358a038c5dd4ab29906b9389d0dc7` (凍結)。開始時・終了時ともに `git -C <wt> status --porcelain` = 空、HEAD 不変。git は `git -C <wt>`、Read/Grep は worktree 絶対パス。テスト収集と変異は `git archive 89a3840` の隔離コピー (`scratchpad/final_cqr/copy`、.venv64 ジャンクションのみ、.git 無し、data/keiba.db 無し) で `scripts/mutation_sandbox.py` 経由。本番 DB は `mode=ro` で 1 回読んだだけ。worktree・本番 checkout・bat・Task Scheduler・ai-builder・Discord には触れていない。本番 checkout に modified な追跡ファイルは無し (未追跡は開始時と同じ)。

**改修タイプ宣言**: type-B/C (運用基盤 + テスト基盤 + 「今日」の単一出典化、予測ロジック不変)。P25 固有ゲート (meta.env_overrides / market_snapshot / weights / payout) は **N/A (対象外)**。汎用ゲートで採点。

**採点対象**: `git -C <wt> diff d134b3b 89a3840` = 40 files (+3920/-70)。うち本体: `jst.py` (新規 72 行) / `runtime_guard.py` (新規 67 行) / `config.py` (`_require_daystamp` + `sealed_window_started(today, *, now)`) / `scripts/auto_predict.py` / `scripts/notify_dedup.py` (`jst_today` 廃止) / `web/generator.py` / `web/publish_safety.py` / `scripts/fetch_mining.py` / `gui/app.py` / `scripts/auto_predict_daily.bat` (JST 日付 + exit 8 + dry-run) / `scripts/run_auto_predict_daily.ps1` / `weekly_monitor.bat` (off + `data/monitor_runs/`) / `scripts/mutation_sandbox.py` (新規 315 行) / `tests/conftest.py` / 新規テスト 12 ファイル / `docs/CLOCK_LEDGER.md`。

**主張された証拠の検証 (`data/jst_mutation_20260928/`)**:
- `run13_result.txt`: 95 変異 = 94 KILLED / 1 SURVIVED (F6) / 0 REFUSED / 0 NOT_APPLIED / 0 ABORTED — ファイルを読んで確認。
- **F6 は真に等価**: 変異は `day = today if today is not None else ...` を `day = today or ...` にするもの。その 3 行上の `if today is not None: _require_daystamp("today", today)` が空文字を `len(value) == 8` で ValueError にするので、空文字は変異行に到達しない (`config.py:305-306,311`)。生存は正当。
- `full_strict.txt` / `full_off.txt`: どちらも `2 failed, 969 passed, 9 skipped`、失敗集合が同一 (v5 の HOLD 理由 = off でだけ 4 件赤、は解消)。
- 失敗 2 件は環境要因と **自分で確認**: (a) `tests/test_f3_phase0_0_eval.py::test_saved_pair_reproduces_frozen_validation_auc` は `data/f3_phase0_0/metrics.json` (gitignore `data/*`) を直読みし、main には有る (2026-07-20) が worktree には無い。テストファイル自体は差分に含まれない (main と同一)。(b) `tests/test_placeholder_cleanup.py::test_live_database_has_no_placeholder_violations` は `config.DB_PATH` の実 DB を読む。worktree の未追跡 `data/keiba.db` (9/25 22:20 の dry-run 残骸) を ro で数えると `past_only=23` (today=20260928)、`today=20260927` を渡すと 0 → 「日付が過ぎて違反化した」主張どおり。本番 DB は 0。
- **979 と 980**: 隔離コピーで `--collect-only` = **980**、ID 集合は今日の実行 (`set_strict.txt` の PASSED/FAILED/SKIPPED 980 行) と 1 対 1 で一致。計算で決まる parametrize は `test_today_single_source.py:121` の定数 `GUARDED` だけで、環境依存の収集は無い (データ依存テストは skip で消えない)。0202c6d から 89a3840 でテスト追加も無し。よって 89a3840 の収集数は決定的に 980 で、9/26 の「979」は本 SHA の成果物からは再現できない (set_prev.txt は 0 バイト)。**マージ阻害ではない**が、マージコミット文か runbook に「collect-only 980」を基準として残すことを推奨。
- `git -C <main> merge-tree --write-tree eb875e8 89a3840` は衝突なし (tree `f400574`)。main が d134b3b 以降に触ったファイルと branch の 40 ファイルの重なりは **0**。

## 判定: PASS

**理由**: v5 (209b636) の HOLD 理由 (週次監視の off が入れ子 pytest に届き `tests/test_conftest_guard.py` 4 件が赤) は f04b38b で **構造的に** 閉じた: 子 pytest の環境は `runtime_guard.child_pytest_env()` の 1 箇所で作り (`runtime_guard.py:51-67`)、`extra` の後に `env[RUNTIME_GUARD_ENV] = STRICT` を強制 (`:66`、変異 CE1/CE3 KILLED)、利用箇所は `tests/test_conftest_guard.py` / `tests/test_weekly_monitor_guard.py` / `tests/test_runtime_guard.py` / `scripts/mutation_sandbox.py:240` / `scripts/foundation_repair_audit.py:259` の 5 つで、直接 `os.environ` を展開する経路は残っていない。主防御は **実際に子 pytest を起動して** 子から見た値が strict であることを見る `test_a_real_child_pytest_sees_strict_while_the_parent_is_off` (`tests/test_runtime_guard.py:61-78`)、補助として `subprocess.run([... "pytest" ...])` を AST で列挙し `env=` と `child_pytest_env` の使用を要求する `test_every_child_pytest_goes_through_child_pytest_env` (`:104-120`、対照実験 `:123-129` 付き)。strict/off の全体 suite で失敗集合が同一であることを成果物で確認。停止条件 (汎用) への抵触なし。**マージ前必須の是正は無し**。下記「次アクション」はいずれもマージ後の follow-up ticket で足りる (main の同じ箇所はいずれも今より悪い状態なので、マージで退行する箇所は無い)。

**根拠ファイル**: `jst.py:47-72` / `runtime_guard.py:40-67` / `config.py:260-317,374-380` / `tests/conftest.py:41-97` / `tests/test_runtime_guard.py:48-129` / `tests/test_today_single_source.py:38-60,76-118` / `tests/test_fetch_mining_entry.py:36-54` / `tests/test_generator_today.py:140-169` / `scripts/mutation_sandbox.py:74-108,213-290` / `scripts/auto_predict_daily.bat:9-40` / `weekly_monitor.bat:22-51` / `docs/CLOCK_LEDGER.md:25-70,134-147` / `db.py:229-239` / `scripts/monitor.py:208-211` / `data/jst_mutation_20260928/` (run13_result.txt, full_strict.txt, full_off.txt, set_strict.txt, jst_spec_v7.py) / 自作変異 `scratchpad/final_cqr/` (cqr_spec.py, cqr_mutants_result.txt)

## 総合: 4.1 / 5 (前回 v5 3.8、+0.3) — -0.3 以上の低下項目なし

## 項目別

- **DRY / 単一出典: 4.0/5** (前回 3.5) — 加点: (i) 子 pytest の環境構築が `child_pytest_env` 1 箇所に収束 (v5 の HOLD 直接原因の構造的解消)。(ii) `KEIBA_RUNTIME_GUARD` の綴りは Python 側 `runtime_guard.RUNTIME_GUARD_ENV` 1 箇所 + bat のリテラル 2 箇所 + テストの assert 1 箇所 (`test_weekly_monitor_guard.py:190`) だけになり、bat との言語境界の乖離は本物の bat コピーを本物の conftest で流す `test_the_weekly_monitor_passes_while_others_write_logs` が捕まえる (変異 W5 KILLED = 名前を変えて bat を直し忘れれば日曜でなく手元で赤)。(iii) 日付形式の検査が `_require_daystamp` 1 つに統一され、`guard_analysis_window` の独自検査 (8 桁数字なら通す) を廃止 (`config.py:374-380`、U1 KILLED)。(iv) `notify_dedup.JST` / `jst_today` を廃止して `jst.JST` に一本化。減点: (a) **`docs/CLOCK_LEDGER.md` が「残作業の単一出典」を自称しながら 7 箇所を落としている**: `db.py:239` (`horse_num_violation_counts` の `date.today()`、**`scripts/monitor.py:211` が `today` を渡さず呼ぶので週次カナリアの判定日 = ローカル日付**、B 相当)、`scripts/monitor.py:101,165` (Brier rolling 窓の端、B)、`scripts/predict.py:75` (`is_buy_candidate(now=datetime.now())`、A7 と同型)、`scripts/fetch_full.py:36`、`webapp/server.py:49`、`predictor/risk.py:170,194`、`scripts/rolling_select.py:144`。(b) 監視対象集合の 3 重 (`conftest._RUNTIME_DIRS` / `mutation_sandbox.PRODUCTION_WATCH` / `snapshot_production` 内リテラル) と `_snapshot_runtime_dirs` と `snapshot_production` の近似重複は据え置き (v3 からのバックログ)。(c) `tests/test_fetch_mining_entry.py:23-33` `_env_without_pythonpath` は `child_pytest_env` の PYTHONPATH 落とし + UTF-8 と同じ処理の再実装 (pytest の子ではないので AST 補助は鳴らないが、同じ事実の 2 箇所目)。
- **dead code / 未使用シンボル: 4.0/5** (前回 4) — 差分内の import を確認: `auto_predict` の `date` 削除・`datetime` は `:429` で使用継続、`notify_dedup` の `timezone` 削除、`fetch_mining` の `datetime` 削除、`gui/app.py` の `datetime` は刻印・A8 で使用継続。89a3840 自体が `child_pytest_env` の PYTHONPATH 落としの重複ループを削る commit で、方向は正しい。残: `weekly_monitor.bat:38` の `set "KEIBA_RUNTIME_GUARD="` は process-scoped で実効なし (v5 指摘、衛生として可)。未実装 env を前提にした記述は無し (`PRED_DISABLE_BLEND` は本改修と無関係、N/A)。
- **マジックナンバー / 設定外出し: 4.0/5** (前回 4) — `FINAL_ATTEMPT_HOUR = 11` 定数化済・`now` 注入可 (自作 M5 KILLED)。bat の終了コード 8 は末尾コメントと `:date_failure` の両方に意味が書かれ、`docs/CLOCK_LEDGER.md:103` からも辿れる。`OPEN_WINDOW_BOUNDS` は frozenset 1 箇所 + 根拠コメント。減点: bat の `findstr /r /x "20[0-9][0-9][01][0-9][0-3][0-9]"` (`auto_predict_daily.bat:20`) は Python 側 `_require_daystamp` (実在日付まで見る) より緩い「YYYYMMDD 契約」の言語境界越し平行記述 (月 19 / 日 39 を通す)。Python が出した値の sanity check なので実害は無いが、形式を変えるとき 2 箇所。
- **テスト容易性 / 変更失敗モード: 4.0/5** (前回 3.5) — 加点: 95 変異 94 KILLED (F6 等価)、`now` 注入 + `frozen_jst` fixture で境界 (UTC 15:00 = JST 00:00) を実時刻に依存せず固定、bat は仮リポ + スタブで exit ビットまで固定 (B14-B17)、ps1 の dry-run 通知抑止も実プロセスで検証 (A1-A3)。**自作変異 8 種 (隔離コピー、sandbox 経由、v7 spec に無い箇所)**: M1 auto_predict 対象日を前日 = KILLED (`test_the_entry_point_uses_the_single_source`)、M5 最終起動の境界 = KILLED、M6 daystamp 書式 = KILLED、M8 `record` の `date_jst` 前日 = KILLED、**M2 `fetch_mining.normalize_date("today")` を前日 = SURVIVED**、**M3 `gui/app.py` `Api._date_range` の今日を前日 = SURVIVED**、**M4 `notify_dedup.decide` をローカル時計 (`datetime.now()`) = KILLED だが AST ガード (`test_today_single_source`) のみ。`test_notify_dedup.py` / `test_notify_e2e.py` は全緑 = 挙動テストは時計を固定していない** (JST 機では同値)、M7 `db.py:239` の `today` を固定 = SURVIVED (台帳外・想定どおり、branch 外)。台帳自身が `:141-146` で「AST ガードだけを防御線にしない、見張り対象には挙動テストを必ず置く」と規則を書いているのに、集約済み 8 箇所のうち `scripts/fetch_mining.py` と `gui/app.py` は挙動テストが無い (fetch_mining のテストは `--help` の起動確認のみ、gui は `test_gui_js_contract` のみ)。fetch_mining の `return current_jst_daystamp()` は代入ではないので、`return datetime.now().strftime(...)` へ戻す同型回帰も AST ガードを **素通り**する (台帳の言う限界そのもの)。テスト衛生: (a) `tests/test_auto_predict_artifacts.py` (8 箇所) / `tests/test_cancelled_races.py:369,406` は期待値を `date.today()` で作り、コード側は JST なので、UTC ホストの JST 00:00-09:00 (この改修が守ろうとしている状況そのもの) でテストがコードより先に赤くなる。`tests/test_notify_dedup.py:251` のように `current_jst_daystamp()` を使うべき。(b) 未追跡データに依存して skip でなく **fail** するテストが 2 本 (上記)。`test_live_database_has_no_placeholder_violations` は「本番 DB のカナリア」であり単体テストではない (他の DB 依存テストは `pytest.skip` に統一されている)。(c) 収集数の基準 (980) が記録されていない。
- **エラー処理 / 観測可能性: 4.5/5** (前回 4) — fail-fast が一貫: naive `now` は ValueError (`jst.py:58-61`、`utcoffset()` が None の tzinfo も弾く)、`today`+`now` 同時指定 / 形式違い / 実在しない日付 / `SEALED_FROM` の形式は封印未定でも ValueError (F1-F5, F7, F7b KILLED)、bat は日付が取れなければ exit 8 + `auto_predict_daily_DATE_FAILURE.log` に stderr 込みで記録 + dry-run 以外は Discord ERROR (B2/B4/B9/B10/B13 KILLED)、`runtime_guard` の未知の値は `pytest.UsageError` でテスト 0 本、`mutation_sandbox` は本番の不在・コピーの外・本番を指す文字列を **書く前に** 拒否 (R1-R6 KILLED)。v5 の観測性 3 点 (stderr が別ファイル / off の記録が無い / 空 .stderr が溜まる) はすべて閉じた (`weekly_monitor.bat:38-51`: `runtime_guard=off pytest_exit=N full_output=...` の 1 行、`:merge_stderr` で同一ファイルに併合、0 バイトは削除、WB1-WB4 KILLED)。生成失敗も `_final_confirmation` の対象にして「3 回同じ rc で失敗した日が 1 通のあと沈黙」を解消 (`auto_predict.py:411-414`)。減点: `test_live_database_has_no_placeholder_violations` の失敗メッセージに「どの DB / どの today で数えたか」が無く、今日の worktree 残骸 DB の切り分けにレビュー側の時間を使わせた (`assert ... == 0` に `DB_PATH` と counts の dict を載せれば 1 行)。

## 変更失敗モード分析

1. **新しく「今日」を作る関数を足すとき**: GUARDED (`test_today_single_source.py:52-60`) の 7 モジュール内で `today = datetime.now()...` と **代入**すれば即座に落ちる (自作 M4 で実測)。しかし (a) `return datetime.now().strftime(...)` のように代入しない形、(b) GUARDED 外のモジュール (`db.py` / `scripts/monitor.py` など台帳に無い 7 箇所) は **静かに通る**。台帳の規則「挙動テストを併置」がこの穴を埋める設計だが、fetch_mining / gui で規則が守られていない (M2/M3 生存)。触り忘れたときの症状: その日の mining 特徴だけ欠ける / GUI の「今日開催あり」が前日を指す。どちらもログに出ない。
2. **`KEIBA_RUNTIME_GUARD` の名前を変えるとき**: Python 側は `RUNTIME_GUARD_ENV` 1 箇所。bat を直し忘れると `test_the_weekly_monitor_passes_while_others_write_logs` が本物の bat コピーを流し、conftest が strict のまま同時書き込みを検出して **手元で即赤** (W5 で実測)。良い形。
3. **監視対象ディレクトリを足すとき** (例: `data/monitor_runs`): `conftest._RUNTIME_DIRS` に足しても `mutation_sandbox.snapshot_production` は見ない → 枠が黙って守らない。3 重のまま (バックログ)。
4. **`_require_daystamp` の呼び出し側を増やすとき**: 開いた端 (`00000000` / `99999999`) を渡す新しい呼び出しは `allow_open_bounds` を付け忘れると即 ValueError (U2/U3 で両方向を固定)。fail-fast で良い。

## 依頼への回答 (重点項目)

- **JST の単一出典に残る判定経路のローカル時計**: 台帳 A1-A8 / B1-B4 / C1-C4 は据え置き (合意済み)。**台帳に無い** のは `db.py:239` (週次カナリア `monitor.py:211` から `today` 無しで呼ばれる = 判定日がローカル)、`scripts/monitor.py:101,165`、`scripts/predict.py:75`、`scripts/fetch_full.py:36`、`webapp/server.py:49`、`predictor/risk.py:170,194`、`scripts/rolling_select.py:144`。いずれも branch 外で main と同一、マージで悪化しない。台帳の追記は文書のみなのでマージ後の別 commit で可。
- **fail-fast**: 上記「観測可能性」のとおり一貫。黙って既定に落ちる経路は差分内に無し。
- **dead code**: 無し (bat の no-op `set` 1 行のみ衛生問題)。
- **テストの質 / F6**: 変異の狙う挙動は 94/95 で固定、F6 は等価。自作 8 変異で **2 生存 + 1 AST のみ** の穴を特定 (上記)。
- **runtime_guard / mutation_sandbox の保守性**: `runtime_guard.py` は 67 行・依存なし・docstring が「なぜ」を書く。`mutation_sandbox.py` は `PRODUCTION_ROOT` を定数で持ち、本番が無ければ **始めない** (R5) ので checkout を移すと大声で止まる (静かに無防備にならない)。`run_mutants` が 78 行で最長だが、事前検査 / 変異ごと / 事後検査の 3 段が読める。改善余地: `Result.status` の 5 値は文字列リテラル (Enum 化)、`main()` の `survived` に NOT_APPLIED を含める意図 (spec の typo を生存扱いで可視化) はコメントが無い。
- **テスト衛生の follow-up**: 上記 (a)(b)(c)。マージ阻害ではない。
- **979 と 980**: 上記のとおり 980 が決定的、9/26 の数字は再現不能。マージ前に説明を要求しない。基準として 980 を記録。

## 停止条件チェック

- [ ] git_sha / env_overrides / market_snapshot / payout — N/A (type-B/C)
- [x] 汎用: 新規経路 (JST 集約 / 封印判定の注入 / bat 日付 fail-fast / dry-run / 見張り 2 値 / 子 pytest strict / 枠の安全検査) すべてに回帰テストあり、変異 94/95 + 自作 5/8 検出
- [x] 汎用: 例外の握り潰しの新設 — 無し
- [x] 汎用: 既存テストの無効化 — 無し (差分内のテスト変更は追加・強化のみ)
- [x] 汎用: 本番運用経路で赤にならない — OK (strict/off の失敗集合が同一、差分 0)
- [x] 汎用: 本番への痕跡 — 無し (sandbox が変異なし実行と変異ごとに本番 data/logs・data/runtime・DB を前後比較し ABORT 0、worktree porcelain 空、HEAD 不変)
- [x] 汎用: main との衝突 — 無し (merge-tree クリーン、重なりファイル 0)

## 反証の試み

- 「週次監視 (off) と入れ子 pytest の strict は両立する」→ 成立 (実子プロセスのテスト + strict/off 全体 suite の失敗集合一致 + CE1/CE3/CE4/W7 KILLED)。
- 「F6 は等価」→ 成立 (コード読解: `_require_daystamp` が先に落とす)。
- 「集約済み 8 箇所はすべて挙動で固定されている」→ **不成立** (fetch_mining / gui は生存、notify_dedup は AST のみ)。
- 「2 件の失敗は環境要因」→ 成立 (metrics.json は main にのみ存在、worktree DB は today=20260927 で 0 件、本番 DB 0 件)。
- 「収集数は環境で揺れる」→ 不成立 (隔離コピーで 980、ID 集合一致、計算 parametrize は定数のみ)。

## 次アクション (すべてマージ後の follow-up、優先順)

1. **挙動テスト 2 本** (30 分): `scripts/fetch_mining.normalize_date("today")` と `gui/app.py` `Api._date_range` を `frozen_jst` (monkeypatch `jst.current_jst_*` または `now` 注入) で固定し、前日化 / ローカル時計化の両変異が落ちること。あわせて `tests/test_notify_dedup.py` の `decide` / `record` に時計を固定するケースを 1 つ (M4 を挙動で殺す)。
2. **`docs/CLOCK_LEDGER.md` に 7 行追記** (15 分、文書のみ): `db.py:239` (+ `monitor.py:211` の呼び出し) / `monitor.py:101,165` / `predict.py:75` / `fetch_full.py:36` / `webapp/server.py:49` / `risk.py:170,194` / `rolling_select.py:144`。`db.horse_num_violation_counts` は Group B の先頭候補 (週次カナリアの判定日)。
3. **テスト衛生 ticket** (30 分): `test_auto_predict_artifacts.py` / `test_cancelled_races.py` の `date.today()` を `current_jst_daystamp()` に; `test_saved_pair_reproduces_frozen_validation_auc` は `metrics.json` 不在で `pytest.skip`; `test_live_database_has_no_placeholder_violations` はカナリアとして marker 化 or 失敗メッセージに `DB_PATH` と counts を載せる。
4. マージコミット文または runbook に「collect-only 980 (2026-09-28、隔離コピー)」を記録し、次回の比較基準にする。
5. (継続バックログ) 監視対象集合の 3 重 / `_env_without_pythonpath` の `child_pytest_env` 化 / bat の no-op `set` 削除 / `Result.status` の Enum 化。

## 前回からの差分 (20260926_0440 v5 code-quality = 3.8 / HOLD)

- DRY 3.5→4.0 (+0.5: 子 pytest 環境の単一出典化、env 名の Python 側一本化、日付検査の統一) / dead code 4→4 / マジックナンバー 4→4 / テスト容易性 3.5→4.0 (+0.5: HOLD 理由の回帰を実子プロセスで固定、B7 相当 (WB1/WB2) も閉鎖。自作変異で 2 生存 + AST のみ 1 を新たに特定したため 4.5 には届かず) / 観測可能性 4→4.5 (+0.5: v5 の 3 指摘すべて閉鎖)
- 判定 HOLD→PASS。総合 3.8→4.1 (+0.3)。-0.3 以上の低下なし。
