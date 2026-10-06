# コード品質 / 保守性レビュアー 採点 — JST 統一 v2 (1baab6c, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象は `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify` HEAD=1baab6c に固定。git は `git -C <wt>`、Read/Grep は worktree 絶対パス。実験 (テスト実行・変異) はすべて隔離コピー (`git archive 1baab6c` → scratchpad/gate_jst_quality) で行い、worktree・本番 checkout・Task Scheduler・Discord には触れていない。終了時 worktree `git status --short` = 空 (確認済)。

**改修タイプ宣言**: type-B (運用基盤、予測ロジック不変)。P25 固有ゲート (env_overrides / market_snapshot / weights / payout) は **N/A (対象外)**。汎用ゲートで採点。
**採点対象 (main d134b3b → 1baab6c)**: `config.py` (84c6f4b) / `scripts/auto_predict_daily.bat` + `scripts/run_auto_predict_daily.ps1` (ab3fbf0) / `tests/test_sealed_clock.py` `tests/test_daily_bat_rundate.py` `tests/test_auto_predict_task_runner.py` `tests/test_today_single_source.py` / merge 67e365d / `docs/CLOCK_LEDGER.md`。前回 (20260921_0040, 37eaf61, HOLD 3.0) の指摘の消化状況も確認。
**実測**: 隔離コピーで関連 9 ファイル 148 passed / 1 skipped (21.9s)。全体 collect 837 件。変異 9 種を植えて検出力を測定 (下表)。

## 判定: PASS

**理由**: 前回 HOLD の 3 理由 (翌日から赤くなる既存テスト / jst_today と JST 再エクスポートの別名 / 表記依存の正規表現ガード) はすべて解消を確認 (`tests/test_notify_dedup.py:263-279` は注入方式へ、`notify_dedup.py` から `jst_today` と `JST` は消え grep 0 件、ガードは AST 化)。今回分 (config / bat / ps1) は **挙動テストが変異 9/9 を検出** し、失敗モードが「静かに壊れる」から「exit 8 + 失敗ログ + 通知」に変わった。停止条件 (汎用) への抵触なし。
**残る主要所見 (merge 前に直すのが望ましいが、正しさには影響しない)**: (1) `tests/test_auto_predict_task_runner.py` の runner 系テストが **本番 checkout の `data/logs/auto_predict_watchdog.log` に書く** (main 側実測: 1,396 行中 426 行が pytest 由来のパス、worktree 側 140 行中 60 行)。この branch で runner 起動テストが 4 → 11 回に増え、汚染が加速する。(2) `scripts/fetch_mining.py:10` の `from jst import` が `sys.path.insert` (`:13`) より前にあり、`python scripts/fetch_mining.py` 形式では `ModuleNotFoundError: No module named 'jst'` (実測)。bat は `-m` 起動なので本番経路は無事。同ファイル `:8` の `from datetime import datetime` は未使用になった。(3) AST ガードは代入先の名前でしか対象日を見分けないため、**修正前の原文 (`now = today or date.today()...`) と代入なしのインライン形は素通り** (実測、下表 M1/M3)。`test_sealed_clock.py` が挙動で捕まえるので防御は二重だが、ガード単体の保証範囲は台帳の記述より狭い。
**根拠ファイル**: `config.py:260-277` / `scripts/auto_predict_daily.bat:9-36,73-74` / `scripts/run_auto_predict_daily.ps1:15,22,54-61` / `tests/test_today_single_source.py:38,108-117` / `tests/test_sealed_clock.py:54-67,101-124,183-202` / `tests/test_daily_bat_rundate.py:53-69,75-80` / `tests/test_auto_predict_task_runner.py:15-38,340-346,349,373-397` / `scripts/fetch_mining.py:8-13` / `scripts/payout_finality_monitor.py:70,182` / `web/generator.py:491` / `gui/app.py:437,441` / `docs/CLOCK_LEDGER.md:50,57`
**次アクション**: 改善提案 1-3 (合計 30 分規模) を merge 前 or 直後の小 commit で。台帳への追記 (提案 4) は同時に。

## 総合: 4.0 / 5 (前回 3.0、+1.0)

## 項目別

- **DRY / 単一出典: 4/5** (前回 3) — `jst_today` / `JST` 再エクスポートの廃止で「同じ事実に 2 つの名前」は解消。`config.sealed_window_started` も `jst` へ寄り、同一 bat 内の `fetch_mining` / `publish_safety` / `gui._date_range` も揃った。留保: (a) merge 67e365d で main から入った `scripts/payout_finality_monitor.py:70` が `JST = timezone(timedelta(hours=9), "JST")` を **独自定義** (`jst.JST` と同値の 2 つ目の定数)。`:182` の `datetime.now(JST)` は tz 付きで挙動は正しいが、台帳に載っていない。(b) `web/generator.py:491` と `gui/app.py:437,441` の `now=datetime.now()` (naive local) は **オッズ鮮度判定** (`is_buy_candidate` / `odds_age_minutes`) の基準時刻で、台帳の定義では A 級 (PIT / オッズ直結) なのに台帳に行が無い (A1 と同じ「DB の naive 文字列と比較するので naive のまま」問題)。(c) 台帳の行番号が既にずれている: A6 `:2214` → 実際は `gui/app.py:2218-2219`、B2 `:150` → `:151-152`。行番号は動く前提で「関数名 + 用途」を主キーにすべき。(d) `config.SEALED_FROM is None` の assert が `test_sealed_clock.py:147` / `test_sealed_holdout.py:77` / `test_data_split.py:60` の 3 箇所 (意図的な多重防御としては許容範囲)。
- **dead code / 未使用シンボル: 4/5** (前回 3) — 前回指摘の未使用 import 2 件 (`auto_predict.date` / `notify_dedup.timezone`) と死んだ引数 `jst_today(now)` は消えた。新規: `scripts/fetch_mining.py:8` の `from datetime import datetime` が未使用 (grep で import 行のみ)。`tests/test_auto_predict_task_runner.py:349` の `import pytest  # noqa: E402` (ファイル中盤) と `:379,:384` の関数内 `import os` / `import pytest` は、モジュール先頭に寄せるべき (noqa で黙らせる理由が無い)。同ファイル `:15-115` の 3 テストは `_run_runner` (`:340`) と同じ powershell 起動配列を 3 回手書きしており、ヘルパを後から足したのに既存側を寄せていない。
- **マジックナンバー / 設定外出し: 4/5** (前回 4) — bat の `cd /d` が固定パス `C:\Users\kizun\dev\keiba-yosou` から `"%~dp0.."` へ (改善。register → wscript vbs → ps1 `$CommandPath = Join-Path $PSScriptRoot` → bat の経路で本番は同じディレクトリに解決、`test_daily_bat_rundate.py:114` が cwd を実測)。exit code は bat 側 1/2/4 (bit) + 8 (日付失敗、他は未実行なので bit 和 <= 7 と衝突しない) で `bat:73-74` に集約記述あり。留保: ps1 側の `exit 2` (`run_auto_predict_daily.ps1:22`、command not found) が **bat の bit 2 (prediction failure) と同じ値** で、watchdog log の `finish exit=2` だけでは区別できない (既存だが、今回 8 を足して「終了コードの意味表」を作った以上、ps1 の 2/124/125 も同じ表に載せるべき)。`DATEERR` のパス (`bat:17`) と `DATE_FAILURE.log` 名 (`bat:30,35`) は 2 回ずつ直書き (通知文言内は変数展開不可なので許容)。
- **テスト容易性 / 変更失敗モード: 4/5** (前回 2) — 変異 9 種すべてを **挙動レベルで検出** (下表)。`test_sealed_clock.py` は境界 8 点 + naive 拒否 + 既定経路 (fake datetime を `jst.datetime` に差す) + 注入/既定の一致 + OS TZ 3 種 subprocess (TZ が効いていることを `time.timezone` の相違で自己検証 `:198`) と層が厚い。fake `FrozenDatetime.now(tz=None)` が **ローカル naive を返す** (`:62-65`) のは本物と同じ契約で、実装が naive に退行すれば `ValueError` で赤くなる (静かに通らない)。bat テストはスタブ + ジャンクションで DB/Discord/Pages に触れず、`_OK` が固定日付 "20261001" なので時刻非依存。留保: (i) **AST ガードは名前依存** — M1 (原文復活 `now = ...`) と M3 (代入なしインライン) を素通り。commit 本文の「変数名を day にそろえた」は、ガードに見えるようコードを合わせた、の意で、ガードがコードを守っているのではなくコードがガードに合わせている。`TARGET_NAMES` に無い名前 (now / base / d / stamp) で書けばいつでも通る。(ii) runner テストの後始末: `$repo = Split-Path -Parent $PSScriptRoot` で **テスト対象 checkout の本番 watchdog log に追記** する (上記)。`data/*` は gitignore なので git には見えないが、「沈黙 = 未起動」を読む運用ログにテストのゴミが 3 割混ざる。(iii) `test_dry_run_through_the_scheduler_launcher` (`:373`) は `%LOCALAPPDATA%\ScheduledTaskRunner\...vbs` の存在に依存 (無ければ skip)。実環境の起動経路を踏むテストとして価値はあるが、skip が常態化した環境では「通っている」と誤読される。(iv) `tmp_path` 下のジャンクション削除は `os.rmdir` で正しい (中身を消さない)。`.venv32` 作成が失敗すると `.venv64` のジャンクションが残るが、pytest の rmtree はリパースポイントを辿らないので実害なし。
- **エラー処理 / 観測可能性: 4/5** (前回 3) — 主目的の「日付が取れないと `auto_predict_daily_.log` へ無音で落ちる」は解消: `set "RUNDATE="` 初期化 (`bat:16`、環境残留 `RUNDATE` の再利用を `test:178` が実測)、8 桁 regex 検証 (`bat:20`)、stderr 保存 (`bat:18` → `DATE_FAILURE.log` に `type`、Traceback が残ることを `test:167` が確認)、exit 8、本番のみ Discord。ps1 の start 行に `dryrun=` を追加。留保: (a) `bat:35` の失敗通知は `>nul 2>&1` で握り潰す。日付失敗の最頻原因 = `.venv64` 自体の破損なら通知も同じ python で失敗し、残るのは `DATE_FAILURE.log` と watchdog log の `exit=8` のみ (許容だが、DATE_FAILURE.log に「通知の成否」を 1 行残すべき)。(b) `auto_predict_daily_rundate_stderr.txt` は **成功時も毎回作られる** (空 or 警告のみ) 上、上書きなので前回の失敗内容は DATE_FAILURE.log 側にしか残らない。成功時は削除するか、ファイル名に日付を含めるか。(c) 上記の本番 watchdog log 汚染。

### 自分で植えた変異 (隔離コピー、対象テストのみ実行)

| # | 壊し方 | AST ガード | 挙動テスト | 実害 (未検出の場合) |
|---|---|---|---|---|
| M1 | `config.py:276` を **原文** `now = today or date.today().strftime(...)` に戻す | **素通り** | 検出 (`test_sealed_clock` 7 failed) | UTC ホストで封印初日 9 時間が dev 窓 |
| M1b | 同上を `day = ...` に代入 | 検出 | - | (ガードは名前で見ている、の対照) |
| M2 | `current_jst_daystamp()` に (now 無視) | (対象外) | 検出 (5 failed) | 注入テストが契約でなくなる |
| M3 | 代入なしのインライン `(today or date.today()...) >= SEALED_FROM` | **素通り** | 検出 (7 failed) | M1 と同じ |
| M4 | bat `set "RUNDATE="` 削除 | - | 検出 (1 failed: 環境残留) | 古い RUNDATE で別日のログへ |
| M5 | bat `goto :date_failure` 削除 | - | 検出 (13 failed) | 修正前の無音退行 |
| M6 | bat `cd /d "%~dp0"` (scripts/ に cd) | - | 検出 (14 failed) | venv 不在で全滅 |
| M7 | ps1 の引用符を一重に戻す | - | 検出 (`a&b` の 1 件のみ) | `&` を含むパスで分断 |
| M8 | ps1 `--dry-run` を渡さない | - | 検出 (4 failed) | dry-run のつもりで本番 |
| M9 | bat dry-run 側にも `--notify` | - | 検出 (1 failed) | dry-run で Discord 送信 |

挙動レベル 9/9 検出。AST ガード単体では config 3 形態中 1 形態のみ。前回 (主目的変異 0/7 検出) から大幅改善。

## 変更失敗モード分析

1. **`sealed_window_started` に第 3 の指定方法を足す / 引数を取り違える**: 現 API は `today: str` (位置) と `now: datetime` (キーワード限定) が併存し、**両方渡すと `today` が黙って勝つ** (`config.py:276`、`now` は捨てられる)。`sealed_window_started(some_datetime)` と位置で渡せば `datetime >= str` の `TypeError` で即落ち (fail-fast、良)。だが `sealed_window_started("2026-10-01")` (ハイフン形式) は `"2026-" < "20261"` で **静かに False** — `config.py:337` に同型の事故 (`"-" < "1"`) の記録があるのに、この関数には形式検証が無い。1 行 `if today is not None and now is not None: raise ValueError` と、`today` の 8 桁チェックを足せば両方 fail-fast になる。
2. **8 つ目の GUARDED モジュールを足すとき**: 書き手は `TARGET_NAMES` にある名前で代入しないとガードが働かない事実を知らないまま追加する。台帳 `docs/CLOCK_LEDGER.md:87` は「AST ガードが主要モジュールを見張っている」と書き、`test_today_single_source.py` docstring `:24-26` も名前で見分けると明記するが、**「名前が違えば見えない」側の帰結は書いていない**。挙動テスト (test_sealed_clock 相当) が無いモジュールでは、ガードだけが防御線 = 実質防御なし。ガード追加時は「そのモジュールの挙動テストがあるか」をセットで要求する規約が要る。
3. **bat に 5 段目のステップを足すとき**: dry-run 分岐が `if defined DRYRUN ( A ) else ( B )` で 2 箇所 + `goto :skip_fetch` で 1 箇所と、3 通りの書き方が混在。次のステップを足す人はどれかを真似るが、`--notify` のような「dry-run で落とすフラグ」を持つコマンドは M9 の形で漏れやすい。`set "NOTIFY=--notify"` / `if defined DRYRUN set "NOTIFY="` の 1 変数方式なら分岐が消え、テスト (`test:117`) も現状のまま効く。

## 依頼への回答

- **単一出典と台帳の一致**: 集約済 10 行は実コードと一致 (grep で `jst_today` 0 件、旧 `date.today()` は docstring/コメントのみ)。未対応 A1/A2/A4/A5/B1-B4/C1 の取得方法は実コードと一致、行番号は A6・B2 がずれ。**台帳に無い時計**: `payout_finality_monitor.py:70,182` (独自 JST、main 由来)、`web/generator.py:491` / `gui/app.py:437,441` (オッズ鮮度の now、A 級相当)、`config.py:382` (sealed access log の刻印、C)。
- **AST ガードは config.py を見張れているか**: 現行コード (`day = ...`) は見ている。**原文復活は見えない** (M1 実測)。`test_sealed_clock.py` が代替で捕まえるので config.py については実害なし。
- **sealed_window_started の API**: 分かりやすさは中 (docstring `:269-270` で両方の使い方は説明済)。取り違え余地は上記 1。`now` に型注釈が無い (`today: str | None` はあるのに)。
- **bat**: 可読性は良 (REM が「なぜ」を書いている)。exit code 衝突は bat 内では無し、ps1 の 2 と衝突。dry-run 分岐重複は上記 3。ASCII/CRLF: `file` で両ファイル ASCII + CRLF、`git ls-files --eol` で `i/lf w/crlf` (checkout 時 CRLF)。`git archive` 経由の隔離コピーでも CRLF だったので、Task Scheduler が main checkout の bat を読む経路と同じ改行。`%~dp0..` は等価 (register ps1 → ps1 `$CommandPath=Join-Path $PSScriptRoot` → 同 checkout の bat)。
- **テストの脆さ**: 環境依存は win32 skipif (`test_daily_bat_rundate.py:32`)、vbs 存在 (`test_auto_predict_task_runner.py:381-385`、無ければ skip)、`mklink /J` (管理者権限不要、OK)。時間依存はスタブが固定日付を返すので無し。後始末はジャンクションのみ `os.rmdir`、**watchdog log は後始末されず本番ログに残る**。スタブは argv を 1 行記録するだけで妥当 (`--dry-run` の到達を文字列一致で確認、`calls[-1] == "auto_predict "` の末尾空白はスタブの `name + " " + args` 由来で意図的)。既定経路の fake datetime は妥当 (上記)。
- **merge 67e365d**: import 競合の解消は正しい (`auto_predict.py:29-34` に `db` と `jst` を併記、3 関数すべて使用 `:206,:222,:301`; `generator.py:21-22` 同様 `:302,:318,:690`)。テスト仮 DB に `data_div TEXT` + `'6'` を足したのは `db.sql_evaluable_race` (`db.py:122`: `IS NULL OR <> '9'`) と整合。ただし `'6'` は「実施予定」のマジック値で、`db.py` に `CANCELLED_DATA_DIV` はあるが正常値の定数は無い。3 ファイル (`test_jst_date.py` / `test_notify_e2e.py` x2 / `test_auto_predict_artifacts.py`) に同じ CREATE TABLE が 4 回コピーされており、次にスキーマが変わると 4 箇所を直す (今回まさにそれが起きた)。共通 fixture 化の候補。

## 停止条件チェック

- [ ] git_sha / env_overrides / market_snapshot / payout — **N/A** (type-B)
- [x] 汎用: 新規経路 (config 時計 / bat 日付失敗 / ps1 -DryRun) に回帰テストあり、変異 9/9 検出
- [x] 汎用: 例外の握り潰しの新設 — `bat:35` の `>nul 2>&1` は失敗通知の通知失敗を捨てる (二次失敗、DATE_FAILURE.log は残る) → 減点のみ
- [x] 汎用: 既存テストの無効化 — 無し (前回の時限テストは修復済)

## 反証の試み

- 「AST ガードが config.py を見張っている」→ 原文復活 (M1) と代入なし (M3) で不成立。`day` 代入 (M1b) のみ成立。ガードの保証範囲は「TARGET_NAMES に代入する書き方」に限る
- 「dry-run は本番と同じ経路」→ bat 内では `fetch_full`/`fetch_mining` を丸ごと skip (`bat:41`) なので、日付・cd・coverage・auto_predict の経路は同じだが取り込み段は通らない。commit 本文の "Everything else is the same path" は正確
- 「テストは DB/Discord/Pages に触れない」→ bat テストはスタブで真。**runner テストは本番 watchdog log に触れる** (実測 426 行)
- 「%~dp0.. は本番で等価」→ register → vbs → ps1 → bat の経路を読み、`$PSScriptRoot` = checkout の scripts/ なので等価。テストも cwd を実測

## 主な改善提案

1. **runner テストのログ書き先を隔離** — `run_auto_predict_daily.ps1` に `[string]$LogDir = ""` (既定 `$repo\data\logs`) を足し、`tests/test_auto_predict_task_runner.py` の全起動で `-LogDir <tmp_path>` を渡す。あわせて `:15-115` の 3 テストを `_run_runner` に寄せ、`:349,:379,:384` の import をファイル先頭へ。本番 `data/logs/auto_predict_watchdog.log` の既存 426 行は `pytest-of-` を含む行を 1 回だけ掃除する。
2. **`scripts/fetch_mining.py:8-13`** — `from datetime import datetime` を削除、`from jst import current_jst_daystamp` を `sys.path.insert` の後 (`from db import open_db` の隣) へ移動。`tests/test_fetch_mining.py` に `subprocess.run([python, "scripts/fetch_mining.py", "--help"])` 1 本を足せば import 順の退行が見える。
3. **`config.sealed_window_started`** — `now: datetime | None = None` の型注釈、`today` と `now` の同時指定を `ValueError`、`today` は `len == 8 and isdigit()` を検証 (`config.py:337` の事故の再発防止)。`test_sealed_clock.py` に「両方渡すと落ちる」「ハイフン形式は落ちる」の 2 件。
4. **台帳の補完** — `docs/CLOCK_LEDGER.md` に `payout_finality_monitor.py` (独自 JST → `jst.JST` へ、C)、`generator.py:491` / `gui/app.py:437,441` (オッズ鮮度の now、A、A1 と同じ naive 比較の制約) を追加。A6/B2 の行番号を訂正し、行番号でなく関数名を主キーに。「AST ガードは代入先の名前で見るので、名前が違えば見えない。GUARDED に足すときは挙動テストを同時に」を「使い方」節に 1 行。
5. (任意) bat の dry-run 分岐を `set "NOTIFY=--notify"` 方式に統一、`bat:73-74` の exit code 表に ps1 の 2/124/125 を併記、`DATEERR` を成功時に `del`。

## 前回からの差分 (20260921_0040 code-quality = 3.0 / HOLD)

- DRY 3→4 (+1: 別名・再エクスポート廃止、同一 bat 内 2 源を寄せた。台帳の欠落 3 件で満点でない) / dead code 3→4 (+1: 前回 3 件解消。新規は fetch_mining の import 1 件 + テストの import 配置) / マジックナンバー 4→4 (固定パス除去は加点、ps1 exit 2 衝突と分岐重複で相殺) / テスト容易性 2→4 (+2: 挙動変異 9/9、fake datetime の契約が正しい。ガードの名前依存と本番ログ汚染で満点でない) / 観測可能性 3→4 (+1: 無音退行の根絶。二次失敗の握り潰しと stderr ファイルの常時生成で相殺)
- 判定 HOLD→**PASS**。総合 3.0→4.0 (+1.0)。-0.3 以上の低下項目なし。
