# データパイプライン技術者 採点 — 27a260e 「JST 統一」再レビュー (v4)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `27a260e` (branch `jst-date-unify-20260920`)、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git はすべて `git -C <worktree>`。起動実験はすべて隔離コピー (`git archive 27a260e` → scratchpad `gate4_pipeline` + `.venv64` ジャンクション + worktree の dry-run 用 DB 499,712 byte) 上で **-DryRun のみ**。main checkout の bat/ps1・Task Scheduler・Discord は起動していない (タスクは `Get-ScheduledTask` / `Get-ScheduledTaskInfo` の読み取りのみ)。終了時: worktree `git status --short` 空 (HEAD 27a260e、main HEAD d134b3b 不変、ff 可能)、本番 `data/logs` `data/runtime` 3,170 ファイル + `keiba.db` (20,092,399,616 byte) + `-wal` (0 byte) の (path, size, mtime) 3,172 行が開始時スナップショットと **完全一致**、ジャンクション rmdir 後に実 `.venv64/Scripts/python.exe` 健在、コピーは削除済。本番の `auto_predict_daily_20260926*.log` / `DATE_FAILURE.log` / `rundate_stderr.txt` は存在しない (自分の痕跡なし)。

## 判定: HOLD (前回 4.7 PASS → 4.3、-0.4)

**理由 (1 件、是正は小さいが merge 前に必須)**: a9f3969 で入った `tests/conftest.py` のセッション見張り (`data/logs` `data/runtime` を 1 バイトも変えないこと) は、**本番の定期実行 `keiba-yosou-weekly-monitor` (毎週日曜 10:00、Action = `C:\Users\kizun\dev\keiba-yosou\weekly_monitor.bat`) と両立しない**。`weekly_monitor.bat` は `call :run >> data\logs\weekly_monitor_<日付>.log 2>&1` の中で `pytest tests/ -q` を回す = **pytest 自身の stdout が data/logs の中のファイルに追記され続ける**ので、見張りは必ず「`weekly_monitor_<日付>.log` が変わった」で session error になる。隔離コピーで最小再現: 同じ形 (`pytest tests/test_jst_date.py tests/test_sealed_clock.py -q >> data\logs\weekly_monitor_REPRO.log 2>&1`) で **exit 1 / `ERROR ... AssertionError: assert not ['data/logs/weekly_monitor_REPRO.log']`**、出力先を data/logs の外にした対照は exit 0 (61 passed)。加えて日曜 10:00 は開催日で `keiba-fresh-odds` (09:00 から 10 分毎) と `keiba-fresh-odds-healthcheck` (09:15 から 15 分毎) が data/logs に書くので、docstring の「まれに」ではなく **毎回** 落ちる。結果: merge 後の最初の日曜から `TESTCODE=1` → bat の exit bit 2 → Discord に `WARN: weekly monitor alert (... pytest=1 ...)` が **毎週** 飛ぶ。main (d134b3b) の conftest にこの見張りは無く (`git show d134b3b:tests/conftest.py` に該当関数 0 件)、本番の直近 09/20 10:00 の weekly monitor は `664 passed, 6 skipped in 321.84s` / `exit 0` で緑なので、これは **merge で新たに入る退行**。データ損失ではないが、fresh odds gap / Brier 劣化の実警報と同じチャンネルを毎週偽警報で埋める (深夜に本物を見分けられなくなる) ので、私の判断原則 3 (自動防御は本物だけに発火する) に反する。**これは v3 で私が見落としたもの** (a9f3969 時点で存在した)。今回の差分 (c882f4e の runbook 4 点) はこの経路を対象にしていない。

**解除条件**: 次のいずれか 1 つを入れ、隔離コピーで `>> data\logs\x.log 2>&1` 付きの pytest が緑になることを確認する。(a) `weekly_monitor.bat` の pytest 出力先を `data/logs` の外 (例 `data/test_logs/`) にし、fresh odds との重なりを避けるため見張りは `weekly_monitor.bat` が立てる環境変数 (例 `KEIBA_PYTEST_SCHEDULED=1`) のときは **fail ではなく警告出力** にする、または (b) 見張りの対象を「テストが書きうるファイル」(watchdog log / `auto_predict_daily_*` / `DATE_FAILURE` / `rundate_stderr` / `notification_state.json`) の明示リストに絞る。(a) が本命 (見張りの目的は開発者 / agent の汚染防止で、本番スケジュールの pytest は対象でない)。あわせて runbook に 5 点目「merge 後最初の日曜 10:00 の `weekly_monitor_<日付>.log` 末尾が `Weekly Monitor End (exit 0)`」を足す。

**根拠ファイル**: `tests/conftest.py:25-62`、`weekly_monitor.bat:7-25`、`docs/CLOCK_LEDGER.md:86-116`、`config.py:260-286,355-380`、`web/publish_safety.py:29-33,66`、`scripts/mutation_sandbox.py:108-144,215-262`、`tests/test_generator_today.py`、`tests/test_conftest_guard.py`、`tests/test_mutation_sandbox.py:295-431`、`tests/test_sealed_clock.py:285-335`

## 対象・改修タイプ

- 対象: `a9f3969..27a260e` 5 commits / 8 files (+528/-9)。コード: `config.py` (`_require_daystamp` に `allow_open_bounds`、`guard_analysis_window` が同じ検査を使う)、`web/publish_safety.py` (`from jst import current_jst_date` の欠落を補う)、`scripts/mutation_sandbox.py` (`check_production` / `refuses_target`)、tests 4 files (新規 2)、`docs/CLOCK_LEDGER.md` (runbook)。
- 改修タイプ: **type-D (運用層 + テスト基盤。取得 / ingest / 予測ロジック不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**、fresh odds を総合判定のゲートにしない。参考実測 (読み取り): `keiba-fresh-odds` 09/25 19:00 result 0 / 次回 09/26 09:00、healthcheck 次回 09:15、`keiba-auto-predict` 09/25 11:00 result 0 / 次回 09/26 08:00 (トリガ 08:00 / 09:00 / 11:00 の 3 本)、Action は main の `run_auto_predict_daily.ps1` 引数なし。
- 採点軸は v1〜v3 と同じ 5 軸。

## 総合: 4.3 / 5 (前回 4.7、-0.4)

## 項目別

- **bat 起動経路の堅牢性 (RUNDATE 決定・縮退・exit code): 4.5/5 (前回 4.5、変化なし)** — 今回の差分は bat / ps1 に触れていない。実時計 (JST 9/26 02:42、開催日) の wscript→vbs→ps1 `-DryRun` を 27a260e のコピーで再実行: `wscript exit=0`、watchdog `start ... dryrun=True` → `finish pid=35740 exit=0`、dated log `run date 20260926 (JST) dryrun=[1]` / `[DRY-RUN] skip fetch_full / fetch_mining` / `generate: 20260926 (24 races)` / `scheduled=24 cancelled=0 eligible=24 covered=24` / `done exit=0`、DB sha `3cbf8e3d…` 不変、`docs/index.html` sha `2eb3cca2…` 不変、runtime 不変 (作者主張と一致)。残る穴は前回と同じ (起動器 exit code の衝突、成功時の 0 byte `rundate_stderr.txt` が今回も生成)。
- **日付決定の単一出典 / 境界一貫性: 4.5/5 (前回 4.5、変化なし)** — (ca6b0ad) `guard_analysis_window` の独自検査 (`.isdigit()` のみ) を `_require_daystamp(allow_open_bounds=True)` に統一。実測 (コピー): `("00000000","99999999")` と `("20260101","20260816")` は通り、`20260231` / `20261332` は「実在しない日付」、`"2026-02-01"` / `None` は「YYYYMMDD の文字列で渡すこと」で ValueError。**本番の定期実行・分析スクリプトで新たに ValueError になる呼び出しは無い** (実引数を追った): 定期系 — `keiba-auto-predict` (`auto_predict` → generator は `live=True` / `current_jst_date().strftime`、門を通らない)、`keiba-yosou-weekly-monitor` (`scripts.monitor` は `datetime.now().date()` からの strftime → 実在日、`list_races` 非 live で門を通るが値は実在日)、`keiba-trend-collect-raceday` / `trend-validation-weekly` (別リポ `傾向収集/` の bat。この repo の `fetch_full` / `ingest_all` / `fetch_results` のみ呼び、門を通る script は呼ばない)、`keiba-oos-backtest-auto` (Disabled。中身は `--from 20260101 --to 20260614` 固定)、`run_independent_verify_detached.ps1` (既定 `20260101`〜`20260816`)。GUI — `_track_trends` / `_recent_backtest` の日付は `<input type="date">` (gui/app.py:1980,1984) 由来で `_normalize_date` が数字だけ残す → 実在日か空、空は `_date_range` が JST の今日に落とす (:396-406)、DB 由来 (`horse_races` の `race_year||race_month_day`) も実在日。CLI 既定 — `prediction_accuracy` `00000000/99999999` (許容)、`analyze_simple_edges` `20210101/20260816`、`analyze_lgbm` `20240101/20251231`、`bias_scan` `DATA_PERIODS`、market 系 `DATA_SPLIT["strategy_dev"]` `20260509/20260831`、`oracle_diagnose` FOLD_PERIODS、`f3_phase0_0_eval` `20260101/20260614`、`sim/prod_probs` `20260701/20260913` — 全部実在日。`default=None` の script (filter_sweep 等) は旧検査でも `len(None)` で TypeError だったので新規ではない。新たに弾かれるのは「8 桁だが実在しない日付」だけで、その出所は人間の CLI 入力に限られる (弾くのが正しい)。**減点理由は前回と同じ** (A4 / A5 / A7 / A8 のオッズ鮮度 naive `now` が未着手の半統一状態)。`test_the_open_bounds_are_not_a_valid_today` で端の印を「今日」に使えないことも固定されている (封印判定への流入防止)。
- **依存 / 起動コスト: 5/5 (前回 5、変化なし)** — (ce0e5d9) `web/publish_safety.py` は 2026-09-21 に `date.today()` を `current_jst_date()` に置き換えたとき **import が抜けており、`today` 省略の経路は NameError で必ず落ちていた**。本番経路への影響: `web/generator.py:621` は常に `today=today` を渡す (:318 で `current_jst_date()`) ので本番の `auto_predict` → generator では到達せず、GUI が import する `assert_safe_to_publish` も無関係。つまり **本番の挙動は変わらない** が、`today` 省略で呼ぶ将来の呼び出し (テストや CLI) が JST の今日に落ちるようになった。module import 時に `jst` を要求するようになった点は、`publish_safety` を import する 2 経路 (`gui/app.py:59`、`web/generator.py`) がすでに `jst` を top-level import しているので新たな起動失敗は無い。`test_generator_today.py` は `jst.datetime` を 2026-01-15 に固定し、既定の窓 `("20260101","20260129")` と完全性アラートの基準日 `date(2026,1,15)` を **挙動** で固定 (AST ガードの「別名 import / 1 日ずらし」変異が素通りした穴を塞ぐ)。
- **退行ガード / テスト: 4/5 (前回 5、-1.0)** — 良い点: (d06e30a / 27a260e) 変異の枠は「書く前に拒否」になった。コピー上で実測: `scripts/auto_predict_daily.bat` / `scripts\run_auto_predict_daily.ps1` / `config.py` は通る、`.venv64/Scripts/python.exe` は「コピーの外を指す → C:\Users\kizun\dev\keiba-yosou\.venv64\...」で拒否 (ジャンクション越しの解決が効いている)、`../gate4_pipeline/config.py` は `..` で拒否 (解決後は中に収まるのに拒否 = 27a260e の R2 固定どおり)、絶対パス (コピー内 / 本番の bat) / `/config.py` / 空文字 / `None` はすべて拒否。`check_production()` は本番で `[]` (`data/logs` `data/runtime` `data/keiba.db` 全部実在)、存在しない root は「本番 checkout が見つからない」、worktree を渡すと「本番の中 / .git あり」で拒否。**運用上の誤検知は増えない**: 増えた事前拒否は「本番の場所が無い / 監視対象が無い」だけで、正常な本番では成立しない。`test_conftest_guard.py` は見張り自身を nested pytest で固定 (書く 3 種は fail、書かない対照は pass)。**減点理由**: その見張りが、上の判定理由のとおり **本番の週次 pytest (weekly_monitor.bat) と構造的に両立しない**。見張りが「正しく」働いた結果、本番の定期実行が毎週赤くなる = 見張りの設計が本番の呼び出し形を考慮していない。全テスト実測 (コピー): `pytest tests/ -q` **903 passed / 24 failed / 9 skipped / 141 s** (600 秒上限に対し余裕。09/20 本番は 664 件 322 s)。24 failed はすべてコピー環境由来 — 23 件は `git rev-parse HEAD` が archive (.git 無し) で 128 (`test_build_daily_results.py`)、1 件は untracked の `data/f3_phase0_0/metrics.json` 不在 (`test_f3_phase0_0_eval.py`) — 本ブランチの退行ではない。
- **反映運用 / 前回条件の解除: 3.5/5 (前回 4.5、-1.0)** — 前回の条件 (merge 後の確認手順) は **文書化された** (c882f4e、`docs/CLOCK_LEDGER.md:86-116`): ff / merge commit 指定と cherry-pick 禁止の理由、4 点、PowerShell コマンド 4 行、記録表、満たさないときの初動 (DATE_FAILURE / rundate_stderr を見る)。コマンドは **本番に対して読み取りで実行し、すべて動く**: `Get-Content ...20260926.log -TotalCount 1` は (まだ無いので) PathNotFound を返す = 「ログが無い」を正しく検出、`Test-Path DATE_FAILURE` → False、`Get-Content watchdog -Tail 2` → 直近 2 行、`Get-ScheduledTaskInfo keiba-auto-predict` → LastRunTime `2026/09/25 11:00:01` / LastTaskResult `0`。項目 3 の「非開催日なら出馬表なしで 0」は `auto_predict.py:337-338` (`return 0`) と一致、「失敗なら 2 など」は bat の bit 2 と一致。**不足**: (i) 点検対象が `keiba-auto-predict` だけで、**同じ merge で挙動が変わる `keiba-yosou-weekly-monitor` (日曜 10:00 の pytest) が runbook に無い** — そして実際にそこが赤くなる (判定理由)。(ii) 項目 1 の「先頭行が `run date ... dryrun=[]` になっている」は実際の先頭行 `[2026/09/26  2:42:53.35] run date 20260926 (JST) dryrun=[1] cwd=...` の部分一致なので「先頭行に ... を含む」と書くべき (完全一致と読むと不一致で慌てる)。(iii) 項目 3 はタイムアウト経路だと `finish` 行が出ない (`ps1:88-103` は `timeout` / `tree terminated` / `notification ...` で `exit 124`) ので「`finish` 行が無ければ timeout、`exit=124` 相当」と 1 行足すと深夜に迷わない。ff は依然可能 (`merge-base --is-ancestor d134b3b 27a260e` 真)。本日 08:00 の本番起動は main (d134b3b) のまま (本番 `rev-parse HEAD` = d134b3b、scheduler Action は main の ps1) で、本ブランチの影響なし。

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides: N/A (backtest artifact を生成しない改修)
- [x] baseline paired 比較: N/A
- [x] market_snapshot counts / payout 欠損: N/A
- [x] P25 fresh odds スケジューラ / coverage JSONL / bonus_candidate: N/A (type-D)。参考: `keiba-fresh-odds` 登録済 result 0、healthcheck 登録済
- [x] 専門領域: partial write を残す経路 → なし (dry-run で DB / index.html sha 不変、runtime 不変)。無限待ち → ps1 timeout 1200 s 健在 (実測 log `timeout_sec=1200`)。lock 未掃除 → 該当なし。予想を 1 日落とす経路 → cherry-pick 禁止を runbook が明記。dry-run が Discord に届く経路 → 前回のまま遮断。テストが本番運用ログを汚す経路 → 実測ゼロ差分 (3,172 行一致)。**本番の定期実行が新たに失敗する経路 → あり (weekly_monitor の pytest、判定理由)** → HOLD
- [x] テスト: 903 passed (隔離コピー、24 failed は環境由来と特定)

## 反証の試み (すべて隔離コピー、-DryRun のみ、本番は読み取りだけ)

| # | 反証シナリオ | 結果 |
|---|---|---|
| F1 | 実時計 (JST 9/26 02:42、開催日) を wscript→vbs→ps1 -DryRun (27a260e) | `wscript exit=0`、`generate: 20260926 (24 races)`、`covered=24`、`done exit=0`、DB / index.html sha 不変、runtime 不変。**成立 (作者主張と一致)** |
| F2 | weekly_monitor.bat と同じ形 (pytest stdout を data/logs 内へ追記) で見張り | **exit 1、見張りが `weekly_monitor_REPRO.log` で落ちる**。対照 (出力先を外) は exit 0。**退行を確認** (判定理由) |
| F3 | 本番の直近 weekly monitor (09/20) は緑だったか | `664 passed, 6 skipped in 321.84s` / `Weekly Monitor End (exit 0)`、タスク result 0。main の conftest に見張り無し。**merge で新規に赤くなる** |
| F4 | 門の統一で定期実行 / 分析 / GUI が新たに ValueError になるか | 全呼び出しの実引数を追跡 (項目別 2 参照)。実在しない 8 桁は人間の CLI 入力のみ。**新規失敗なし** |
| F5 | 開いた端 `00000000` / `99999999` と独立検証の既定 `20260101/20260816` | 通る。`20260231` / `20261332` / `2026-02-01` / `None` は ValueError。**成立** |
| F6 | publish_safety の import 修正が本番経路を変えるか | generator は常に `today=` を渡す (:318,621)。到達しない。import 元 2 経路はすでに jst を import 済。**本番挙動不変** |
| F7 | 変異の枠: 本番相当パス / ジャンクション越し / `..` / 絶対 / 空 / None | 上記すべて期待どおり REFUSED、コピー内相対は通る。`check_production()` 本番 `[]`。**誤検知の増加なし** |
| F8 | 全テスト 600 秒上限 | 141 s (936 件)。**余裕** |
| F9 | runbook の 4 コマンド (本番、読み取り) | すべて実行可能、値は現状と整合。**成立**、ただし対象タスクが 1 つ足りない (項目別 5) |
| F10 | 全実験前後の本番 data/logs / data/runtime / DB | 3,172 行 (path, size, mtime) 完全一致。**成立** |
| F11 | 本日 08:00 の本番起動への影響 | 本番 HEAD d134b3b、Action は main の ps1 引数なし。**影響なし** |

## 主な改善提案 (優先順)

1. **(HOLD 解除条件)** 見張りと `weekly_monitor.bat` の両立 — 上の解除条件 (a) 推奨。`weekly_monitor.bat` はこのブランチに含まれているので同じ PR で直せる。
2. runbook に 5 点目 (merge 後最初の日曜 10:00 の weekly monitor が `exit 0`) と、項目 1 の「含む」表現、項目 3 の「`finish` 行が無い = timeout (124)」を足す。
3. 起動器レベルの exit code 分離 (`ps1:30` の `exit 2` 等、前回提案 2 のまま)。
4. 成功時の `auto_predict_daily_rundate_stderr.txt` (0 byte) の掃除 (前回提案 3 のまま、今回も生成を確認)。
5. A4 / A5 / A7 / A8 は同一 PR で `jst_now_naive()` で揃える (台帳どおり)。

## 前回からの差分

- v1 (`37eaf61`) 3.8 HOLD → v2 (`1baab6c`) 4.2 PASS (条件 3) → v3 (`a9f3969`) 4.7 PASS (条件 1) → **v4 (`27a260e`) 4.3 HOLD** (-0.4)。
- 前回条件 (merge 後の確認手順の文書化): **完了** (c882f4e)。ただし対象が `keiba-auto-predict` のみ。
- 指示元の追加是正: config の日付検査統一 → 完了・新規 ValueError なしを実引数で確認。publish_safety import → 完了・本番挙動不変。変異の枠の本番保護 → 完了・誤検知増なし。実経路 dry-run → 自分で再現、作者主張と一致。
- 項目別: bat 4.5→4.5、単一出典 4.5→4.5、依存 5→5、**テスト 5→4 (-1.0)**、**反映運用 4.5→3.5 (-1.0)** — -0.3 以上の低下 2 項目 (警告)。低下の原因は今回の差分ではなく、a9f3969 で入った見張りが本番の週次 pytest と衝突することを **v3 で私が見落としていた** ため。27a260e の差分自体に退行は無い。
