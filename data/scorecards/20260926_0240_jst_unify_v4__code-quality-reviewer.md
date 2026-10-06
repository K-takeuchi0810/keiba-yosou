# コード品質 / 保守性レビュアー 採点 — JST 統一 v4 (27a260e, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象は `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify` HEAD=27a260e に固定。git は `git -C <wt>`、Read/Grep は worktree 絶対パス。テスト実行と変異はすべて隔離コピー (`git archive 27a260e` → scratchpad/gate4_quality/copy, copyB, copyC, copyD、比較用に a9f3969 → copyE) で行い、変異は `scripts/mutation_sandbox.py` 経由 (spec 4 本、25 変異)。行き先を変える再現は偽の本番 (scratch 内 `prodfake/`) に向けた。worktree・本番 checkout・Task Scheduler・Discord には触れていない。終了時 worktree `git status --short` = 空、本番 `data/logs` / `data/runtime` の `ls -la --time-style=full-iso` が開始時と **IDENTICAL** (確認済)。

**改修タイプ宣言**: type-B (テスト基盤 + 運用基盤、予測ロジック不変)。P25 固有ゲート (env_overrides / market_snapshot / weights / payout) は **N/A (対象外)**。汎用ゲートで採点。
**採点対象 (a9f3969 → 27a260e、5 commit、8 files +528/-9)**: `config.py` (`_require_daystamp` 一本化 + `OPEN_WINDOW_BOUNDS`) / `scripts/mutation_sandbox.py` (`refuses_target` / `check_production` / `PRODUCTION_WATCH`) / `web/publish_safety.py` (import 漏れ修正) / `tests/test_mutation_sandbox.py` (+139) / `tests/test_generator_today.py` (新規) / `tests/test_conftest_guard.py` (新規) / `tests/test_sealed_clock.py` (+52) / `docs/CLOCK_LEDGER.md` (runbook)。
**実測**: 隔離コピーで対象 7 ファイル **146 passed / 1 skipped** (68.7s)。全体 collect **936** (前回 897、+39)。全体 suite (archive コピー、.git 無し) は 27a260e で **901 passed / 24 failed / 11 skipped**、a9f3969 で 862 passed / 24 failed / 11 skipped — 失敗集合は両 SHA で同一 (23 件 = `git rev-parse HEAD` が .git 無しで exit 128、1 件 = `data/f3_phase0_0/metrics.json` 不在) で環境要因、**回帰なし**。変異 25 種 (下表): **23 KILLED / 2 SURVIVED** (どちらも別形式の表記に対するテスト欠落で、安全性は別経路で担保)。

## 判定: PASS

**理由**: 前回 (v3, PASS 4.2) の指摘 3 件 (CHAT 指定の是正範囲 1-3) はすべて是正を実測で確認した。(1) **`rel` 未検査** → `refuses_target` (`scripts/mutation_sandbox.py:126-143`) が `write_bytes` (`:272`) より前 (`:258`) で REFUSED を返し、`originals` の `_digest` も同じ検査で絞る (`:254-255`)。前回と同じ手順 (偽の本番 `prodfake/victim.py` に対し 絶対パス / 絶対パス `/` 区切り / `..\..\` / `../../` の 4 形) を再現し、**4 件すべて REFUSED、victim の bytes + mtime_ns は不変、テスト実行中に読んだ victim の中身も `PROD-ORIG` のまま** (前回はテスト中に `PROD-MUTATED` が見えていた)。対照の内側 `calc.py` は KILLED。(2) **本番不在で fail-open** → `check_production` (`:112-123`) が `run_mutants` の最初 (`:218-220`)、`check_sandbox` と baseline pytest より前で `SandboxError`。テストは marker ファイルで「1 本も流していない」ことまで見る (`tests/test_mutation_sandbox.py:355-391`)。(3) **config の二重検査** → inline 検査を削除し `_require_daystamp(..., allow_open_bounds=True)` に統一 (`config.py:374-380`)、`20261332` / `20260230` を弾く挙動テスト + source 検査 (`tests/test_sealed_clock.py:302-335`)。(4) は CHAT 指示でバックログ (据え置き、採点対象外)。新規 3 件 (`test_generator_today` / `test_conftest_guard` / runbook) も実物と照合済 (下記)。停止条件 (汎用) への抵触なし。
**残る主要所見 (安全性には影響しない、次の小 commit で)**: (a) 変異 **R9 生存**: `..` の表記検査を `/` 区切りだけにしても通る。`test_dotdot_is_refused_even_if_it_stays_inside` (`:416-431`) の 3 形がすべて `/` 区切りで、`\` 区切りの「コピーの中に収まる `..`」が無い (外へ出る `\` 形は `:302` で resolve 検査が捕まえるので安全性は保たれる)。(b) 変異 **K19 生存**: conftest の見張りを size のみ (mtime 無視) にしても `test_conftest_guard` は通る。3 ケース (`:42-46`) が全部サイズを変える書き込みで、**同サイズ上書き** (mtime だけ動く) が無い。(c) `PRODUCTION_WATCH` (`:109`) を新設したのに `snapshot_production` (`:166`) は依然 `("data/logs", "data/runtime")` を直書き、conftest `_RUNTIME_DIRS` (`tests/conftest.py:25`) も別記述 — 監視対象の集合が **3 箇所**になった (前回 2 箇所)。(d) `PRODUCTION_ROOT` (`:46`) と `register_auto_predict_task.ps1:19` の二重は残る (CHAT 認知済)。
**根拠ファイル**: `config.py:260-286,307-317,374-380` / `scripts/mutation_sandbox.py:109,112-123,126-143,166,218-223,254-258,262-263,272` / `web/publish_safety.py:33,66` / `web/generator.py:318-320,621` / `tests/test_mutation_sandbox.py:297-431` / `tests/test_conftest_guard.py:22-67` / `tests/test_generator_today.py:34-97,102-170` / `tests/test_sealed_clock.py:286-335` / `tests/conftest.py:25-38` / `scripts/register_auto_predict_task.ps1:7,19` / `scripts/auto_predict_daily.bat:17,22,30,39,73-74` / `scripts/run_auto_predict_daily.ps1:106` / `docs/CLOCK_LEDGER.md:86-115`
**次アクション**: 改善提案 1-2 (各 1 ケース追加、5 分) は merge 直後の小 commit で。3-5 は次回。

## 総合: 4.3 / 5 (前回 4.2、+0.1)

## 項目別

- **DRY / 単一出典: 4/5** (前回 4) — 加点: `config.py` の日付検査が `_require_daystamp` 1 つに (v3 (a) 解消)。`test_both_checks_share_one_validator` (`test_sealed_clock.py:330-335`) が `.isdigit()` の再出現を source で止める。減点: (i) 監視対象の集合が `PRODUCTION_WATCH` / `snapshot_production` 直書き / conftest `_RUNTIME_DIRS` の 3 箇所 (上記 (c))。`snapshot_production` が `PRODUCTION_WATCH` を回れば 1 つ減る。(ii) `OPEN_WINDOW_BOUNDS` (`config.py:263`) を作ったが、消費側 `scripts/prediction_accuracy.py:25-26` の `default="00000000"` / `"99999999"` と `config.py:170` の `default="00000000"` は依然リテラル。定数は「許す側」にしかなく「渡す側」は綴っている。(iii) `PRODUCTION_ROOT` ↔ ps1 (上記 (d))。(iv) conftest `_snapshot_runtime_dirs` と `snapshot_production` の重複は据え置き (前回 (b))。
- **dead code / 未使用シンボル: 4/5** (前回 4) — 新規 import (`re`, `PureWindowsPath`) は使用済。`refuses_target:136` の `win.root or rel.startswith(("/", "\\")) or os.path.isabs(rel)` は Windows では冗長 3 重だが POSIX 互換として許容。前回指摘の `tests/test_auto_predict_task_runner.py:357,387,392` の import 配置は **未対応のまま**。`_require_daystamp` の戻り値は依然どの呼び出しも捨てている (`config.py:311,313,379`)。`web/publish_safety.py:29-32` の 4 行コメントは事故記録として妥当。
- **マジックナンバー / 設定外出し: 4/5** (前回 4) — 加点: `OPEN_WINDOW_BOUNDS` が名前と根拠コメント付きの定数に、`PRODUCTION_WATCH` も同様。減点: 上記 (ii) 消費側リテラル、`PRODUCTION_ROOT` 直書き。`test_conftest_guard.py:39` の `timeout=120`、`test_generator_today.py:31` の FROZEN (2026-01-15) は根拠コメント付きで可。
- **テスト容易性 / 変更失敗モード: 5/5** (前回 5) — 実効変異 23/25 を挙動レベルで検出。前回の攻撃手順を同一形で再現し **書き込み前に止まる**ことを bytes + mtime_ns + テスト中の観測値の 3 点で確認。`refuses_target` の境界を 40 形でプローブ (下記): 大文字小文字 / `/` `\` / ドライブ付き相対 `C:calc.py` `c:calc.py` / ルート始まり / UNC (`\` `//`) / `\?\` 接頭辞 / **8.3 短縮名の絶対パス** / ジャンクション越し (resolve で実体を見る) / 空 / None / bytes / Path オブジェクト — すべて REFUSED。存在しないパス (`nope/nothere.py`) は resolve が strict でないため allowed → `:263 read_bytes` で `FileNotFoundError` の traceback (安全だが REFUSED/NOT_APPLIED ではない、観測性へ)。捕まえないもの: **コピーの中に作られたハードリンク** (`os.link` は resolve に見えない、実測 allowed。`check_sandbox` は DB のハードリンクしか見ない。攻撃には自分でコピー内にリンクを作る必要があり、低リスク)、`CON` (デバイス名、無害)、末尾空白/ドット (Windows が落とす、内側)。順序保証: `refuses_target` → `refuses` → `read_bytes` → `write_bytes` (`:258,263,272`) で、書き込みより前に 2 検査。`test_generator_today` は JST 時計を現実と 8 ヶ月離した日付に固定し、ローカル時計 / 前日 / today 省略 / 窓幅 -1 の 4 変異 (G14-G17) と publish_safety の 3 変異 (P12-P14) を全部殺す。**`empty_db` の記録の仕組みの脆さ**: `Recording.execute` は「SQL 文字列に `FROM races` を含む最初のクエリ」の params を採る (`:62-64`)。generator に races を先に触る別クエリが増えると窓が取り違えられるが、その場合は `assert == ("20260101","20260129")` が**大声で**落ちる (静かに通らない)。`cursor()` / `executemany` 経由に変わると `seen["window"]` が無く KeyError で落ちる (これも大声)。空 DB で `build_view_model` を最後まで通す統合寄りのテストで、schema.sql 依存 (schema 変更で `executescript` が落ちる = 意図どおり)。**`test_conftest_guard` の環境依存**: subprocess pytest に `sys.executable` + `PYTHONPATH` 除去 + `--rootdir` 明示 + `-p no:cacheprovider`、コピーした conftest は pytest / pathlib しか import しない。pyproject を持ち込まないので `pythonpath=["."]` は効かないが不要。ancestor の conftest は rootdir で切れる。4 起動で数秒。留保: 上記 R9 / K19。
- **エラー処理 / 観測可能性: 4.5/5** (前回 4) — 加点: fail-open が fail-fast に (`check_production` は理由に **どのパスが無いか**を含める `:121-123`)、`refuses_target` の理由は元の `rel` と解決先を両方出す (`:142`)、`check_production` が baseline より前なので「本番の監視を始められない」と「変異なしで赤い」を取り違えない。減点: (i) 存在しない対象は `FileNotFoundError` の生 traceback (`:263`、`originals` は `.exists()` で絞るのにループ側は絞らない非対称)。(ii) `run_mutants` の subprocess `timeout` は依然無し (`:236-239`、前回 (c))。(iii) 前回 (b) conftest の失敗が最後のテストの teardown ERROR に見える点は据え置き。

### 自分で植えた変異 (隔離コピー、`scripts/mutation_sandbox.py` 経由、spec 4 本)

| # | 壊し方 | 結果 | 検出したテスト |
|---|---|---|---|
| R1 | `..` の表記検査を外す | KILLED | test_dotdot_is_refused_even_if_it_stays_inside[sub/../calc.py] |
| R2 | 解決後の「コピーの中か」検査を外す | KILLED | test_a_target_through_the_venv_junction_is_refused |
| R3 | 絶対パス検査を外す | KILLED | test_a_target_outside_the_copy_is_refused_before_writing[<lambda>8] |
| R4 | ループから `refuses_target` を外す | KILLED | ..._refused_before_writing[<lambda>0] |
| R5 | `check_production` の呼び出しを外す | KILLED | test_a_missing_production_root_refuses_to_start |
| R6 | 本番ルート不在を `[]` (合格) に | KILLED | 同上 |
| R7 | `PRODUCTION_WATCH` から DB を落とす | KILLED | test_a_missing_watch_target_refuses_to_start[data/keiba.db] |
| R8 | `.resolve()` を外す (ジャンクション越し不可視) | KILLED | test_a_target_through_the_venv_junction_is_refused |
| R9 | `..` の分割を `/` だけに | **SURVIVED** (内側 `\` 形のテスト無し) | - |
| C9 | `OPEN_WINDOW_BOUNDS` を常に許す | KILLED | test_the_open_bounds_are_not_a_valid_today |
| C10 | guard を `allow_open_bounds` 無しに | KILLED | test_the_open_window_bounds_still_work |
| C11 | `allow_open_bounds` で strptime を全部飛ばす | KILLED | test_the_analysis_gate_uses_the_same_strict_check[20261332] |
| C12 | 99999999 を集合から落とす | KILLED | test_the_open_window_bounds_still_work |
| C13 | SEALED_FROM 検査を today 省略時だけに | KILLED | test_a_malformed_sealed_from_is_rejected_even_with_today |
| C14 | strptime を外す (8 桁のみ) | KILLED | test_a_malformed_today_is_rejected[20261332] |
| P12 | `from jst import current_jst_date` を外す (今回直したバグの再発) | KILLED | test_the_default_base_date_is_jst_today |
| P13 | `date.today()` に戻す | KILLED | 同上 |
| P14 | 注入 today を無視 | KILLED | test_an_injected_base_date_wins |
| G14 | generator の today を前日に | KILLED | test_the_default_window_is_jst_today_plus_minus_14 |
| G15 | `datetime.now().date()` に戻す | KILLED | 同上 |
| G16 | completeness に today を渡さない | KILLED | test_the_completeness_alert_gets_the_same_jst_today |
| G17 | 窓を -13 日に | KILLED | test_the_default_window_is_jst_today_plus_minus_14 |
| K17 | conftest の assert を無効化 | KILLED | test_a_test_that_writes_runtime_logs_fails_the_session[logs] |
| K18 | conftest の監視から runtime を外す | KILLED | 同 [runtime] |
| K19 | conftest を size のみ (mtime 無視) に | **SURVIVED** (同サイズ上書きのケース無し) | - |

前回の攻撃の再現 (偽の本番 `prodfake/victim.py`、`MARK = "PROD-ORIG"` → `"PROD-MUTATED"`): ABS / ABS-FWD / DOTDOT (`..\..\prodfake\victim.py`) / DOTDOT-FWD の 4 件 **REFUSED**、victim `(bytes, mtime_ns)` 開始時と一致、テスト本体が毎回 victim を読んで記録した内容は `PROD-ORIG | PROD-ORIG` (対照 CTRL と baseline の 2 回分。REFUSED の変異ではテストが 1 回も走っていないことも同時に示す)。

## 変更失敗モード分析

1. **`refuses_target` に新しい表記 (例: `\?\UNC\...` や環境変数展開) を足し忘れたとき**: 表記検査 (`:136-139`) を素通りしても `(copy_root / rel).resolve()` → `_inside` (`:140-142`) が後衛。ただし `%USERPROFILE%\x.py` は resolve でコピー内の `%USERPROFILE%` ディレクトリ扱い (allowed) で、`write_bytes` は存在しないディレクトリで `FileNotFoundError` — 外には書かないが REFUSED ではなく traceback。**静かには壊れない** (落ちる) が、理由が「対象パス」でなく「ファイル無し」に見える。
2. **`PRODUCTION_WATCH` に監視対象を 1 つ足すとき** (例: `data/results`): `check_production` は自動で存在確認するが、`snapshot_production:166` の直書きタプルと conftest `_RUNTIME_DIRS:25` は動かない → 「存在は要求するが変化は見ない」というちぐはぐが**静かに**成立する。`snapshot_production` を `PRODUCTION_WATCH` で回せば 2 箇所に減り、conftest を `mutation_sandbox` に寄せれば 1 箇所。
3. **`OPEN_WINDOW_BOUNDS` に第 3 の印を足すとき** (例: `"today"`): `_require_daystamp:278` の「8 桁数字」検査が先に走るので、数字でない印は `allow_open_bounds=True` でも弾かれる — **即座に落ちる** (良)。逆に既定値を綴っている `prediction_accuracy.py:25-26` を変えても config 側は知らない (上記 (ii))。

## 依頼への回答

- **refuses_target の網羅性**: 大文字小文字 (`_norm` = normcase)、区切り文字 (`re.split(r"[\/]+")` + PureWindowsPath)、8.3 短縮名 (絶対パスはドライブ検査、相対で内側に戻る形は `..` を含むので拒否、コピー側を短縮名で渡しても resolve で長い名前に揃う: 実測)、ジャンクション (resolve で実体)、存在しないパス (resolve strict=False で allowed → 後段 `FileNotFoundError`、外には書かない) — 要求 5 点はいずれも「外に書かない」を満たす。**書き込み前であることの保証**: `:258` で理由を得たら `continue`、`read_bytes` (`:263`) にも `write_bytes` (`:272`) にも到達しない。`originals` (`:254`) も同じ検査で絞るので `_digest` が外を読むこともない。捕まえないのはコピー内に人為的に作ったハードリンク (低リスク、記録のみ)。
- **check_production の判定**: `is_dir` → 3 監視対象の `exists()`。`run_mutants` の先頭 (`:218`) で `check_sandbox` より前、baseline より前。`PRODUCTION_ROOT` の二重 (ps1:19) は残るが、取り違えても今度は**止まる** (前回は黙って合格) ので事故クラスは「静かに通る」から「起動できない」に格下げされた。
- **allow_open_bounds の設計の妥当性**: 妥当。例外を「集計窓の門」だけに閉じ、封印の「今日」には使えない (C9 で確認)。`00000000` を from に、`99999999` を to に置く既定は `prediction_accuracy` の実運用そのもので、`clamped` の挙動テスト (`test_sealed_clock.py:313-319`) が「99999999 が封印手前で切られる」までを固定する。留保は上記 (ii) (定数の消費側がリテラル) と、from=`99999999` のような無意味な組み合わせも通る点 (門の責務外、許容)。
- **test_generator_today の脆さ**: 記録は「最初の `FROM races`」依存だが失敗は大声。空 DB で generator 全経路を通す形なので downstream (calibrator / portfolio) の変更で壊れうるが、その場合も import/実行エラーで見える。`_days()` の `date.today()` は「ローカル時計に戻す変異と区別する」ための意図的な対照で正しい。
- **test_conftest_guard の環境依存**: 上記 (テスト容易性)。subprocess 4 起動、`PYTHONPATH` を落として親の import 経路を持ち込まない、rootdir 明示。妥当。
- **runbook (`docs/CLOCK_LEDGER.md:86-115`) の実物照合**: ログ名 `auto_predict_daily_<日付>.log` (bat:22)、`DATE_FAILURE.log` (bat:30)、先頭行 `run date <日付> (JST) dryrun=[]` (bat:39、実際は `[日時] ` が前置されるので「含む」が正確)、watchdog `finish pid=... exit=` (ps1:106)、タスク名 `keiba-auto-predict` (register ps1:7)、終了コードのビット (bat:73-74) — すべて一致。
- **回帰**: 全体 suite の失敗集合が a9f3969 と 27a260e で同一 (環境要因 24 件)、passed +39 = 追加分。`jst.py` / `tests/test_today_single_source.py` は差分なし。既存テストの無効化なし。

## 停止条件チェック

- [ ] git_sha / env_overrides / market_snapshot / payout — **N/A** (type-B)
- [x] 汎用: 新規経路 (refuses_target / check_production / allow_open_bounds / publish_safety import / generator 既定窓 / conftest 見張り) すべてに回帰テストあり、実効変異 23/25 検出
- [x] 汎用: 例外の握り潰しの新設 — 無し
- [x] 汎用: 既存テストの無効化 — 無し
- [x] 汎用: 本番への痕跡 — 無し (data/logs, data/runtime IDENTICAL、worktree clean、HEAD=27a260e 不変)

## 反証の試み

- 「枠は `rel` 経由で外に書かない」→ 前回と同じ 4 形で **成立** (REFUSED、bytes/mtime 不変、テスト中の観測も不変)。8.3 / ジャンクション / UNC / `\?\` でも成立。
- 「本番不在なら止まる」→ 成立 (marker ファイルでテスト未実行まで確認、R5/R6/R7 KILLED)。
- 「config の検査は 1 つ」→ 成立 (`.isdigit()` は `_require_daystamp` にのみ、C14 で strptime 除去も検出)。
- 「今回直した import 漏れは再発しない」→ P12 KILLED で成立。
- 「`..` の表記そのものを拒否する」→ `/` 形では成立、`\` 形の内側は **未固定** (R9 生存、安全性は resolve 検査で担保)。

## 主な改善提案

1. **`tests/test_mutation_sandbox.py:416`** — parametrize に `"sub\..\calc.py"` を 1 件追加 (R9 を殺す)。
2. **`tests/test_conftest_guard.py:42-46`** — `existing.log` を **同サイズ**で上書きするケースを 1 件追加 (例: `"before\n"` → `"BEFORE\n"`) (K19 を殺す)。
3. **`scripts/mutation_sandbox.py:166`** — 監視対象を「ディレクトリ群 / DB」の 2 定数に分け、`snapshot_production` と `check_production` が同じ定数を回す。あわせて `tests/conftest.py:25-38` を `from scripts.mutation_sandbox import snapshot_production, diff_snapshots` に寄せる (前回提案 4)。
4. **`scripts/mutation_sandbox.py:262-263`** — `if not p.is_file(): results.append(Result(name, "NOT_APPLIED", ["対象ファイルが無い"])); continue` (traceback ではなく結果として出す)。`_pytest()` に `timeout=` (前回提案 5)。
5. **`scripts/prediction_accuracy.py:25-26`** — `default` を `config.OPEN_WINDOW_BOUNDS` 由来の名前付き定数から取る。`config.py:170` も同様。

## 前回からの差分 (20260926_0040 code-quality = 4.2 / PASS)

- DRY 4→4 (config 一本化 +、監視対象集合の 3 重化と `OPEN_WINDOW_BOUNDS` 消費側リテラルで相殺) / dead code 4→4 (据え置き) / マジックナンバー 4→4 (定数化 +、消費側リテラルと `PRODUCTION_ROOT` で相殺) / テスト容易性 5→5 (前回の攻撃が書き込み前に止まることを実測、23/25 検出、生存 2 件は表記の別形式のみ) / 観測可能性 4→**4.5** (+0.5: fail-open → fail-fast、理由にパスを含む。timeout 無しと生 traceback で満点は保留)
- 判定 PASS→**PASS**。総合 4.2→4.3 (+0.1)。-0.3 以上の低下項目なし。
