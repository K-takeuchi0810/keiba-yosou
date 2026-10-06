# データパイプライン技術者 採点 — 1baab6c 「JST 統一」再レビュー (v2)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `1baab6c` (branch `jst-date-unify-20260920`)、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git はすべて `git -C <worktree>`、起動実験はすべて隔離コピー (`git archive 1baab6c` → scratchpad `gate_jst_pipeline{,_broken,_d0926}` + `.venv64/.venv32` ジャンクション + worktree の dry-run 用 DB) 上で **-DryRun のみ**。main checkout の bat/ps1・Task Scheduler・Discord は起動していない。終了時 worktree `git status --short` 空、main `data/logs` `data/runtime` に 22:39 以降の新規ファイル無し (find -newermt で確認)、ジャンクションは rmdir で解除済 (実 venv の python.exe 健在を確認)。

## 判定: PASS (条件 3 件つき)

**理由**: 前回 HOLD の 2 事由は両方解除を実測 — (a) 本番 checkout は `main` (d134b3b) に戻っており、scheduler `keiba-auto-predict` は LastRunTime 09/25 11:00 / LastTaskResult 0 / NextRunTime 09/26 08:00、(b) bat の縮退 (`auto_predict_daily_.log` へ無音で落ちる) は `exit 8` + `DATE_FAILURE.log` + stderr 保存に置き換わり、隔離コピーで **ps1 直接・wscript→vbs 経由の両方** で exit 8 が Task Scheduler まで届くことを確認。JST 0 時越え (9/26 = 開催日) の経路は時計を固定したコピーで dry-run し、`auto_predict_daily_20260926_dryrun.log` / `generate: 20260926 (24 races)` / `entry coverage 24/24` / `artifact_drift` 通過 / exit 0 / DB・docs/index.html の sha256 不変 / `notification_state.json` 未生成を確認。main は 1baab6c の祖先なので ff merge で `jst.py` と新 bat が **同時に** 入る。

**条件**: (1) merge は ff (または merge commit) で行い、bat だけの cherry-pick はしない — 新 bat + `jst.py` 無しのツリーは全トリガで exit 8 + Discord ERROR になる (本番 `data/logs/auto_predict_daily_DATE_FAILURE.log` に 22:29 / 22:32 / 22:34 の dry-run 痕跡 3 件が **既に** その形で残っている。私の実験より前・scheduler 由来でもない)。(2) その痕跡 (`DATE_FAILURE.log`、`rundate_stderr.txt` 235 byte) を merge 前に削除するか「22:29-22:34 は main に jst.py が無い状態での手動 dry-run」と注記する — 深夜障害時に運用者が最初に開くファイルなので、偽の障害記録を残さない。(3) merge 後の最初の起動 (非開催日で可) で `auto_predict_daily_<JST日付>.log` が生成され `DATE_FAILURE.log` が増えていないことを確認する。

**根拠ファイル**: `scripts/auto_predict_daily.bat:9,16-22,29-37`、`scripts/run_auto_predict_daily.ps1:15,54-57,89-91`、`scripts/auto_predict.py:299-301,357-371,373`、`config.py:260-277,280-304`、`jst.py:47-72`、`scripts/fetch_mining.py:8-12`、`tests/test_daily_bat_rundate.py`、`tests/test_auto_predict_task_runner.py:253-320`、`tests/test_sealed_clock.py`、`tests/test_today_single_source.py:52-60`、`docs/CLOCK_LEDGER.md`

## 対象・改修タイプ

- 対象: `main(d134b3b)..1baab6c` 29 files (+1743/-55)。コード: `jst.py` 新規、`config.py` (sealed_window_started に JST/now 注入)、`scripts/auto_predict.py` `scripts/auto_predict_daily.bat` `scripts/run_auto_predict_daily.ps1` `scripts/fetch_mining.py` `scripts/notify_dedup.py` `web/generator.py` `web/publish_safety.py` `gui/app.py`、tests 7 files。
- 改修タイプ: **type-D 相当 (運用層: 対象日・ログ名・封印時計の決定基盤。取得 / ingest / 予測ロジックは不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**。fresh odds を総合判定のゲートにしない。参考: `keiba-fresh-odds` は登録済・09/25 19:00 result 0・次回 09/26 09:00 (Get-ScheduledTaskInfo 実測)。
- 採点軸は前回と同じ 5 軸 (bat 起動経路 / 日付決定の単一出典 / 依存・起動コスト / 退行ガード / 反映運用) を維持し、前回比を出せるようにした。
- スコープ外: 通知文面、生成 HTML の中身、A1/A2 (predict_t10、台帳で別フェーズと合意済)。

## 総合: 4.2 / 5 (前回 3.8、+0.4)

## 項目別

- **bat 起動経路の堅牢性 (RUNDATE 決定・縮退・exit code): 4/5 (前回 3)** — 前回提案 2「縮退の受け皿」は提案より強い形で入った: `set "RUNDATE="` で環境の stale 値を捨て (`bat:16`)、`for /f` の stderr を `2^>` でファイルに残し (`:18`)、`findstr /r /x` の 8 桁検査を通らなければ `:date_failure` → `DATE_FAILURE.log` に traceback を `type` して exit 8 (`:29-37`)。**実測**: 壊した jst (ImportError) のコピーで ps1 直接 → rc 8、watchdog `finish exit=8`、`_dryrun.log` も `_2026*.log` も 0 件、DB sha256 不変。wscript→vbs 経由 (スケジューラと同一) でも `wscript exit=8` — つまり **LastTaskResult=8 として見える**。dry-run では Discord を呼ばず、本番のみ `notify_discord --message` (CLI `--message` 実在 `notify_discord.py:44`)。正常系: `cd /d "%~dp0.."` は main checkout では従来の絶対パスと同じディレクトリに解決 (テストで `cwd=` 一致を assert、隔離コピーでも `cwd=<copy root>` を実測)。ps1 の `""path""` 二重引用は plain / 空白+括弧 / `&` の 3 パスで `--dry-run` 有無ともに検証済 (71 passed に含む)。**残る穴 (減点理由)**: (i) 起動器レベルの失敗コードが bat のビットと衝突する — vbs 2 (ps1 不在) / ps1 2 (bat 不在) / bat 2 (予想失敗) が同じ 2、ps1 が構文エラーや `Start-Process` 例外 (`$ErrorActionPreference=Stop`) で死ぬと exit 1 = 「fresh odds gap」という **最も無害な値に見える**。merge が ps1 を壊した場合の見え方が最悪。(ii) 成功時も `auto_predict_daily_rundate_stderr.txt` (0 byte) が毎回 `data/logs` に残る (害は無いが「何かの失敗ファイル?」と読ませる)。(iii) `echo(%RUNDATE%| findstr` は `%RUNDATE%` を先に展開するので、Python 側が `&` を含む 1 トークンを stdout に出すとコマンドとして実行される。出典が自前の jst.py なので現実的な脅威ではないが、遅延展開か部分文字列検査の方が堅い。
- **日付決定の単一出典 / 境界一貫性: 4/5 (前回 4)** — 集約対象は前回の 4 箇所から `gui/app.py _date_range` / `fetch_mining normalize_date` / `publish_safety assess_race_completeness` / `config.sealed_window_started` を加えて 9 箇所 (`tests/test_today_single_source.py:52-60` の GUARDED 7 モジュール)。日次 bat 内に残る独自の「今日」は `fetch_full.py:36 date.today()` と `fresh_odds_coverage.py:80,151-152 datetime.now()` の 2 箇所 (前回 3 → 2、fetch_mining が寄った)。封印時計: `SEALED_FROM=None` を実測 (`active False / started False / drift []`)、`auto_predict.py:357` の `artifact_drift()` は dry-run でも `return 0` の前に通るので 9/26 固定時計の dry-run で本番と同じ順で実行されたことを確認。前回留保の「bat RUNDATE と auto_predict の today は別プロセス読取なので 0 時境界で不一致になりうる」は構造不変 (トリガ 08/09/11 なので手動起動のみ到達)。今回の dry-run 実測では bat → auto_predict 間 0.4 秒。
- **依存 / 起動コスト: 4.5/5 (前回 5)** — `jst.py` は依然 `datetime` のみ import、`config.py` は関数内 import で循環なし (実測 import 成功)。**減点**: `scripts/fetch_mining.py:10` が `from jst import` を `sys.path.insert` (`:13`) より **前** に置いた。`python -m scripts.fetch_mining` (bat の経路、cwd=repo) では動くが、`python scripts/fetch_mining.py` を別 cwd から叩くと `ModuleNotFoundError: No module named 'jst'` (`C:\` から実測)。main では同スクリプトは任意 cwd から動いたので、手動運用に限った小さな退行。1 行の並べ替えで直る。
- **退行ガード / テスト: 4.5/5 (前回 4)** — 隔離コピーで `test_daily_bat_rundate` (本物の bat を cmd で実行、5 失敗形 × dry/本番) + `test_auto_predict_task_runner` (ps1 exit 伝播 / timeout 124 / 孫プロセス kill / `-DryRun` 転送 3 パス / wscript→vbs 経由) + `test_sealed_clock` (JST 0 時境界 / naive 拒否 / 既定経路 = 注入経路 / **OS TZ 変更で答えが変わらない**) + `test_jst_date` + `test_today_single_source` (AST ガード + ガード自身の検出力テスト) = **71 passed / 17 s**。前回留保 (1)「ガードが 3 モジュール限定」は 7 モジュールへ拡大、(2) flap しうるテストは now 固定で解消。**減点**: `test_auto_predict_task_runner` は `RUNNER` (= 実行元リポの ps1) を動かすので、**main checkout で pytest を回すと本番 `auto_predict_watchdog.log` に pytest 由来の start/timeout 行が混ざる** (今日 21:43 / 22:03 の実例あり、134 KB のうち末尾 12 行が pytest)。テスト側でログ先を隔離できるようにするか、ps1 に `-LogPath` を足すのが筋。
- **反映運用 / 前回 HOLD 解除: 4/5 (前回 3)** — 解除確認: main checkout は `main` (`git rev-parse --abbrev-ref HEAD`、reflog 22:03 まで merge のみ)、scheduler 3 トリガ (08/09/11 Daily) すべて main の ps1 を指し WorkingDirectory 未指定 (bat の `cd /d "%~dp0.."` で吸収、実測)。9/25 の本番 run 3 回はすべて `skip: 開催日でない / done exit=0`。main は 1baab6c の祖先 → ff merge、`jst.py` と bat が同一操作で入る。**減点**: 本番 `data/logs` に **`auto_predict_daily_DATE_FAILURE.log` (22:29:00 / 22:32:07 / 22:34:50、いずれも dryrun=[1]、`No module named 'jst'`) と `rundate_stderr.txt`** が残っている。scheduler は 11:00 が最終起動、私の実験開始は 22:39 で隔離コピーのみなので、**別の手動 dry-run が新 bat を main のツリーに向けて 3 回走らせた** 痕跡。内容は「merge 前に bat だけを持ち込むと何が起きるか」をそのまま示している (= 条件 1 の根拠) が、本番のインシデント記録ファイルに偽陽性を残した状態で merge するのは避けたい (条件 2)。

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides: N/A (backtest artifact を生成しない改修)
- [x] baseline paired 比較: N/A
- [x] market_snapshot counts / payout 欠損: N/A
- [x] P25 fresh odds スケジューラ / coverage JSONL / bonus_candidate: N/A (type-D 運用層)。参考実測: `keiba-fresh-odds` 登録済、09/25 19:00 result 0、coverage JSONL 2.17 MB 09/25 19:00 更新
- [x] 専門領域 (本改修向け): partial write を残す経路 → なし (dry-run 3 系で DB sha256 不変、docs/index.html 不変、notification_state 未生成)。無限待ち → ps1 timeout 1200 s 健在 (`:63`)。lock 未掃除 → 該当コード無し。予想を 1 日落とす経路 → 「jst.py 無しのツリー + 新 bat」で全トリガ exit 8 (ff merge なら到達しない、cherry-pick で到達。条件 1)。**すべて不抵触** (条件つき)
- [x] テスト: 71 passed (隔離コピーで自分で再実行)

## 反証の試み (すべて隔離コピー、-DryRun のみ、`.venv64` は本物へのジャンクション)

| # | 反証シナリオ | 結果 |
|---|---|---|
| E1 | 正常系: 実クロック (JST 9/25 22:42、非開催日) を ps1 直接 -DryRun | rc 0、`auto_predict_daily_20260925_dryrun.log`、`skip: 開催日でない`、`fresh_odds_coverage` は `--notify` 無し、DB sha 不変。**成立** |
| E2 | 壊した jst (ImportError) を ps1 直接 -DryRun | rc 8、`DATE_FAILURE.log` に traceback、dated log ゼロ、後段未実行、Discord 未呼出。**成立** |
| E3 | 同上を wscript→vbs 経由 (スケジューラ同一経路) | `wscript exit=8` = LastTaskResult 8 になる。**成立** |
| E4 | JST 0 時越え (時計を JST 9/26 00:05 に固定した jst.py) を wscript→vbs 経由 -DryRun | rc 0、`auto_predict_daily_20260926_dryrun.log`、`generate: 20260926 (24 races)`、`entry coverage 24/24`、`artifact_drift` 通過、DB / docs/index.html sha 不変、runtime に状態ファイル無し。**開催日経路も成立** |
| E5 | 封印時計 `SEALED_FROM` | None → `sealed_window_active False / started False / drift []` を実測。`sealed_window_started` は `now` 注入で 10/01 JST 00:00 境界と OS TZ 変更をテスト済 (`test_sealed_clock` 8 件) |
| E6 | ff merge 可能か | `merge-base --is-ancestor main 1baab6c` 真。jst.py + bat は同一 checkout 操作で入る |
| E7 | 「本番 checkout は main で運用」(前回 E9) | **成立**: HEAD main、scheduler 3 トリガとも main の ps1、09/25 3 run 正常 |
| E8 | 本番 data/logs の DATE_FAILURE は scheduler 由来か | **否**: LastRunTime 11:00、痕跡は 22:29-22:34 dryrun=[1]。手動 dry-run が main (jst.py 無し) を向いた痕跡 |
| E9 | fetch_mining を別 cwd からファイル指定で起動 | `ModuleNotFoundError: No module named 'jst'` (import が sys.path.insert より前)。bat 経路 (`-m`, cwd=repo) は無影響 |
| E10 | 起動器レベルの失敗コード衝突 | vbs 2 / ps1 2 / bat 2 が同値、ps1 死亡 = 1 = gap 警告と同値。**衝突あり** (設計上の穴、今回の改修で悪化はしていない) |

## 台帳 (docs/CLOCK_LEDGER.md) 未対応項目のうちパイプラインに効くものの優先度

- **A4 `fetch_fresh_odds.py:186,279`** — `now = datetime.now()` (naive local) から `target_date` と `minutes_until` (`:208`) の両方を作り、`:279` で取得直前に **もう一度** `datetime.now()` を読んで再判定している (これは「発走時刻変更に対する再判定」として正しい設計)。ホストが JST である限り無害だが、OS の TZ が変わると **発走前/後の判定がずれて post-start オッズが fresh 扱いになる** (2026-06-28 の 97% 汚染と同じ事故クラス)。DB `start_time` が naive なので `jst.py` の aware をそのまま渡すと TypeError → 台帳どおり `jst_now_naive()` 相当のヘルパを **A1 (predict_t10) と同じ PR** で入れるべき。**優先度 A のまま、B1 より先**。同 bat `fetch_fresh_odds.bat:12-13` は PowerShell `Get-Date` (local) + `unknown` フォールバックで、日次 bat が今回捨てた「無音縮退」型が残っている — A4 のとき一緒に揃える。
- **A5 `check_fresh_odds_health.py:516`** — 同型だが出力は警告の要否だけで数字を書かない。**A4 と同時に直せば追加コストほぼゼロ**、単独では B 相当。
- **B1 `fetch_results.py:24,26`** — `yesterday` が JST 00:00 直後に一昨日を指す (UTC ホストのみ)。結果取得は後段の `fetch_full` でも補われるので **B のまま**、JST 基盤 merge 後にまとめて。
- 今回の merge をブロックする項目ではない。ただし「半統一状態」(予想は JST、fresh odds はローカル) は TZ 変更時に **2 系統の今日が混在**する点で、全ローカルだった main より読みにくくなる。台帳がそれを明記しているので可。

## 主な改善提案 (優先順)

1. **本番 `data/logs/auto_predict_daily_DATE_FAILURE.log` / `rundate_stderr.txt` の始末** (merge 前、1 分) — 削除するか先頭に注記。今後「手動 dry-run は必ず隔離コピーか worktree で」を `docs/CLOCK_LEDGER.md` の進め方に 1 行足す。
2. **起動器レベルの exit code を bat のビットと分離** (`run_auto_predict_daily.ps1:22` の `exit 2` → 例えば 122、vbs は変更不可なら README に「LastTaskResult 2 は 3 義」と明記) — 深夜に LastTaskResult だけ見て切り分ける場面で効く。
3. `scripts/fetch_mining.py:10` の `from jst import` を `sys.path.insert` の後ろへ (1 行移動)。
4. `tests/test_auto_predict_task_runner.py` の ps1 ログ先を隔離 (ps1 に `-LogPath` を足す or テストで一時 repo にコピーして動かす) — main で pytest を回すと本番 watchdog log が汚れる。
5. 成功時の `auto_predict_daily_rundate_stderr.txt` (0 byte) を `:run` 冒頭で `del` するか、失敗時だけ残す。

## 前回からの差分

- 前回 (本 agent、同改修 v1、`37eaf61`): **3.8 / HOLD** → 今回 (`1baab6c`): **4.2 / PASS (条件 3 件)** (+0.4)。
- 前回 HOLD 事由: (a) checkout が feature ブランチ → **解除** (main、scheduler 3 run 正常)。(b) bat 縮退が無音 → **解除** (exit 8 + DATE_FAILURE.log + stderr、ps1/vbs 経由で伝播を実測)。
- 前回提案 3 件のうち (1) checkout 復帰・(2) 縮退受け皿は完了、(3) ガード範囲拡大・flap 解消も完了。
- 項目別: bat 3→4、単一出典 4→4、依存 5→4.5 (fetch_mining import 順の退行)、テスト 4→4.5、反映運用 3→4。-0.3 以上下がった項目なし。
- 今回新たに見つけたもの: 本番ログの偽 DATE_FAILURE 痕跡 (E8)、起動器 exit code 衝突 (E10、既存)、fetch_mining import 順 (E9)、pytest による本番 watchdog log 汚染 (既存)。いずれも code の停止条件には当たらない。
