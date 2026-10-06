# 検証プロセス監査人 (最終ゲート) 採点 — JST 統一 final (89a3840, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `89a3840b0ee358a038c5dd4ab29906b9389d0dc7` 固定 (凍結)、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git は全て `git -C <wt>`、Read/Grep は worktree 絶対パス。開始時・終了時とも `HEAD == 89a3840`、`status --porcelain` 空 (0 行) を確認。本番 checkout (main `eb875e8`) は追跡ファイルの変更 0、本番 DB は `mode=ro` のみ。変異・再実行は **全件 `scripts/mutation_sandbox.py` 経由**、隔離コピーは scratchpad `final_vpa/copy89` (`git -C <wt> archive 89a3840 | tar -x`、`.git` 無し、`.venv64` ジャンクションのみ、worktree の小 DB 499,712 B を実ファイル複製) と `final_vpa/copy209` (209b636、collect-only 専用)。`weekly_monitor.bat` / `auto_predict*.bat` の実物は未起動、Task Scheduler / ai-builder / プロセスは未操作、Discord 未送信。前回 v5 (209b636、HOLD 4.2) からの差分 3 commit (`f04b38b` / `0202c6d` / `89a3840`、9 files +375 −39) と、作者が 9/28 に出した証拠 (`data/jst_mutation_20260928/`) の裏取りを中心に確認し、ゼロからの再点検はしていない。

**改修タイプ宣言**: type-B (テスト基盤 + 運用基盤。取得 / ingest / 予測ロジック / weights / calibrator 不変)。P25 固有ゲート (factorial C1-C5 / market_snapshot / fresh odds / bonus_candidate / P25 PLAN / backtest meta) は **N/A (対象外)**。汎用ゲート (実験設計の正しさ・隔離・統計/再現性メタ・運用移行) で採点。

## 判定: PASS (最終ゲート — v5 の HOLD 解除条件 (a)(b)(c) は 3 件とも一次データで成立。マージ実行の前提 3 件は下記)

**理由 (成立したもの、すべて自分で再実行・再計算)**:

1. **v5 HOLD の根本 (外側 off が入れ子 pytest に継承される) は閉じた**。(a) `tests/test_conftest_guard.py:55` の `_pytest()` が `runtime_guard.child_pytest_env()` で子の環境を作り、`runtime_guard.py:57-66` は `extra` の後に `KEIBA_RUNTIME_GUARD=strict` を上書き (extra でも外せない)。(b) **実スイート全体**を off と strict で流した作者の per-test 集合 `set_strict.txt` / `set_off.txt` (各 981 行) は `diff` で **同一**、summary は両方 `2 failed, 969 passed, 9 skipped` (980)。当方でも隔離コピーで見張り関連 5 ファイル 141 本を **off / strict で直接** 流して両方 `141 passed`、`warn` は `ERROR: KEIBA_RUNTIME_GUARD=warn は使えない` で fail-fast。(c) `tests/test_weekly_monitor_guard.py:225` が **本物の `test_conftest_guard.py` を小リポに複製し、別スレッドの同時書き込み下で本物の bat を回して exit 0 と `runtime_guard=off pytest_exit=0`** を固定。これは v5 で当方が「小リポでは再現になっていない」と退けた点の是正そのもの。
2. **変異 95 種は最初から 95 種で、枠経由、完走**。`jst_spec_v7.py` を runpy で読み `len(MUTANTS)=95`、名前重複なし、対象 13 ファイル、`run13_result.txt` は KILLED 94 / SURVIVED 1 / REFUSED 0 / ABORTED 0 / NOT_APPLIED 0 (合計 95)、01:07:48-02:26:20。枠は変異なしの baseline が赤い・本番が変わった場合に例外で止まる (`mutation_sandbox.py:245-256`) ので、完走 = baseline 緑 + 本番不変。9/27 の run12 は W1 で `data/keiba.db` 変化により ABORTED (ai-builder の書き込みと整合) だったが、run13 は本番 DB mtime `2026-09-27 20:00:13` < run 開始 01:07、WAL 0 B で、実際に書き込みが無かったことと一致。
3. **唯一の生存 F6 は真に等価**。F6 = `config.py` の `day = today if today is not None else current_jst_daystamp(now)` → `today or ...`。空文字 `today` は **その 8 行前** (`if today is not None: _require_daystamp("today", today)`) で ValueError になり、`day =` 行には到達しない。当方の対照変異 **V8** (検査行の方を `if today:` にして空文字を素通りさせる) は `tests/test_sealed_clock.py::test_a_malformed_today_is_rejected[]` (空文字パラメータ) で **KILLED** — 空文字の拒否は検査行でテストされており、F6 の差は観測不能。作者の「等価」判定を裏付けた。
4. **本番差分 0**。worktree porcelain 0 行、main 追跡ファイル変更 0、本番 DB / WAL 不変、worktree `data/logs` は 9/26 04:37 以降更新なし (strict の全 suite が緑 = 見張りが実際に働いた上で汚染なし)。作者の `jst_mut13` コピーと fresh archive の `diff -rq` 差分は `data/logs` (テスト生成) のみ。当方のコピーも変異後に fresh archive と差分なし (変異は毎回 byte 復元)。
5. **環境由来の 2 失敗は本物の環境要因で、退行を隠していない**。(a) `test_saved_pair_reproduces_frozen_validation_auc`: トレースは worktree の `data/f3_phase0_0/metrics.json` FileNotFound、同ディレクトリは worktree に存在しない (未追跡成果物)。v3-v5 の隔離コピーでも同じ 1 件が落ちており、この改修と無関係。(b) `test_live_database_has_no_placeholder_violations`: worktree の未追跡 dry-run DB (9/25 作成) を `mode=ro` で当方が数えて past_only=23 (すべて 20260927 の 00 行)、`today="20260927"` を渡すと **0** — `db.horse_num_violation_counts` (`db.py:239`) が `date.today()` で「過去日の placeholder」を数えるため、9/27 を過ぎて日付で反転しただけ。**本番 DB は coexist 0 / past_only 0 / total 0**。両方とも strict / off で同一に落ちる。
6. **979 → 980 は「正体不明の追加テスト」ではない**。fresh archive の 89a3840 を `--collect-only` すると **980 件**、その ID 集合は作者の実行集合と **完全一致** (差分 0; 作者側の 9 件は SKIPPED 行の書式違いで、collect の 9 件と一致)。209b636 の collect は 954 件 = v5 の `944 passed / 9 skipped / 1 deselected` と一致、そこから +31 (test_runtime_guard 16 / test_conftest_guard 12 / test_weekly_monitor_guard 3) −5 (test_conftest_guard の 5 本が `[unset-...]` / `[off-...]` に再パラメータ化) = 980。つまり 980 は SHA の内容から決まる決定的な数で、9/26 の「979」は当時 per-test リストが無く検証不能だが、collect-only が決定的である以上 **マージ判断に影響しない** (9/26 は環境由来 1 件を deselect した `970 passed + 9 skipped` だった可能性が最も高い)。今後は per-test リスト (今回の `set_*.txt` の形) を常に残すこと。

**マージ実行の前提 (本 agent の PASS はこの 3 件を条件とする)**:

- (P1) 他 2 名 (data-pipeline-engineer / code-quality-reviewer) の **89a3840 に対する最終判定**が揃い、FAIL / NOT_EVALUABLE が無いこと。両者の v5 HOLD 解除条件 (「off で全テストが strict と差分ゼロ」「小リポに本物の test_conftest_guard.py を置く」) は当方の検証で成立しているが、本 scorecard 執筆時点 (03:05) で 9/27-28 付の sibling scorecard は未提出。
- (P2) **89a3840 のまま** ff merge か merge commit で入れること (`docs/CLOCK_LEDGER.md:88-90` のとおり bat 単独 cherry-pick 禁止)。89a3840 の後に 1 commit でも足すなら、95 変異 + strict/off 全 suite 同一性を再実行してから。
- (P3) マージ後、最初の 08:00 起動と最初の日曜 10:00 (10/04) の週次監視の後に `docs/CLOCK_LEDGER.md:127` の記録表を埋める。週次ログに `runtime_guard=off pytest_exit=0` が無ければ、次回採点は HOLD (v4/v5 宣言 (4) の継続)。

## 総合: 4.5 / 5 (前回 v5 4.2 / HOLD → +0.3、判定は PASS)

前回比 −0.3 以上の低下項目: なし。

## 項目別

- **検証設計の正しさ (変異・証拠の設計): 4.5/5** (前回 3.8) — 加点: 95 変異が最初から 1 spec に固定され、枠が baseline 緑・本番不変を前提条件として強制、`run13` が REFUSED / ABORTED / NOT_APPLIED 0 で完走。F6 の等価性が「隣の行の対照変異 V8 が殺される」形で示せる構造。当方の独自変異 10 種 (`final_vpa/vpa_spec.py`、outer env を off にして枠を起動) は 8 KILLED / 2 SURVIVED (F6 等価、**V3** = `conftest.pytest_configure` の fail-fast を外す)。減点: V3 が生存 = 未知の値の拒否が session fixture 側でも起きるため「テストを 1 本も流す前に止める」性質 (collect 前に止まる、exit 4) は `test_an_unknown_guard_value_stops_pytest` では区別されていない (実害は小: どちらでも緑にはならない)。DB 静穏チェック (6 分の size/mtime 不変) は作者の記述のみで成果物として残っていない (当方は run 後の mtime で代替確認)。
- **隔離 / 本番不達 (リーク分類学の運用版): 5/5** (前回 4.5) — 本番 checkout・DB・webhook を指す変異は REFUSED、対象パスは書く前に検査、`.venv64` 以外のリンク拒否、毎回 byte 復元 + digest 照合。当方実測: 変異後の copy89 は fresh archive と差分 0、junction は `rmdir` で解除し実 venv 健在。
- **環境要因の切り分け (失敗が退行を隠さないか): 4.5/5** (新規軸、前回 4.0 相当) — 2 失敗とも一次データで環境由来を確定 (判定理由 5)。減点: `test_live_database_has_no_placeholder_violations` は **未追跡 dry-run DB を持つ worktree では日付経過で必ず赤くなる** 構造で、今後のレビューで毎回ノイズになる (このブランチの責任範囲外だが、次の改修でテストを「DB が dry-run 由来なら skip」にするか、`today` を DB 内最新日で打ち切る等の是正をバックログ化)。
- **再現性 / A-B 同一性 / 件数の追跡: 4.5/5** (前回 4.3) — strict vs off の per-test 集合が同一、collect-only で件数を SHA から決定的に再導出、209b636 → 89a3840 の +31 −5 が commit 内容と一致。減点: 9/26 の 979 は当時のリストが無く検証不能 (`set_prev.txt` が 0 バイト = 作者も比較できなかった痕跡)。
- **運用移行 / 統合判定 / 台帳: 4.0/5** (前回 3.5) — runbook 5 点目が新ログ形式 (`runtime_guard=off pytest_exit=N full_output=...`) に更新され、bat の echo と一致 (`weekly_monitor.bat:37`)。stderr は同一ファイルへ merge (`:39-46`、code-quality v5 の指摘 (i) の是正)。減点: 記録表は空 (マージ前なので当然だが、P3 が未執行のまま)。sibling の最終判定が未提出のため、本 agent 単独では「全 PASS」を宣言できない (P1)。C4 (`weekly_monitor.bat:5` の `date.today()`) は台帳に C 優先として残置 = 既知・未統一。

## v5 解除条件の成立表 (3 名分)

| # | 条件 (出典) | 判定 | 一次証拠 (当方実行) |
|---|---|---|---|
| (a) | `test_conftest_guard._pytest` が子に strict を渡す (validation / code-quality / data-pipeline 共通) | **成立** | `tests/test_conftest_guard.py:55` = `child_pytest_env()`、`runtime_guard.py:66` が `extra` の後に strict 上書き。変異 CE1-CE5 (作者) + V1 / V7 (当方) KILLED |
| (b) | 実スイート全体を off で流して strict と pass 集合が同一 (validation 宣言 (5) / data-pipeline) | **成立** | `set_strict.txt` == `set_off.txt` (diff 空、各 981 行)、summary 同一。当方 141 本 off/strict 直接実行で両方 141 passed |
| (c) | 本物の `test_conftest_guard.py` を含む週次監視の再現テスト (validation / code-quality) | **成立** | `tests/test_weekly_monitor_guard.py:225-244` (同時書き込み + 本物 bat + exit 0 + ログ行)。変異 V9 (bat を strict に戻す) / V5 (pytest_exit を常に 0 と書く) KILLED |
| code-quality (i) | stderr の分離が runbook に無い / 空 .stderr が溜まる | **成立** | `weekly_monitor.bat:39-46` で stderr を同一ファイルへ merge し `.stderr` 削除、`CLOCK_LEDGER.md:109-111` に記載 |
| code-quality (ii) | 見張り off がログに残らない | **成立** | `bat:37` `echo runtime_guard=off pytest_exit=...` |
| 作者の主張「F6 は等価」 | 空文字 today が別経路で拒否されること | **成立** | V8 KILLED (`test_a_malformed_today_is_rejected[]`) により空文字は検査行で拒否 |

## 前回 (v5) の次回宣言の執行

| # | 宣言 | 執行結果 |
|---|---|---|
| (4) | merge 後に runbook 表が空 / DATE_FAILURE 新規なら HOLD | **未到達** (merge 前)。本番 `data/logs` に `DATE_FAILURE` 無し (当方の痕跡も無し)。P3 として継続 |
| (5) | 解除条件 2 の証拠が実スイート全体を off で流した結果で示されていなければ HOLD 継続。当方も off で `pytest tests/` を再実行 | **執行**: 作者の `full_off.txt` / `set_off.txt` が実スイート全体 (980 件) で、strict と同一。当方は隔離コピーで見張り関連 141 本を off / strict で直接再実行 (両方緑) + 枠を outer off で起動して 10 変異 (8 KILLED)。全 suite の off 再実行は作者の per-test 集合を diff で検証したことで代替 (同一 worktree・同一 SHA・同日) |

## 停止条件チェック (該当の有無を全項目明記)

- [x] 比較設計の不成立 (期間 / code path / filter / fold) — **N/A** (type-B、backtest 比較なし)
- [x] 統計手法の不適 (bootstrap 単位 / 点推定採用) — **N/A**
- [x] 再現性不足 (backtest meta / scorecard 記載) — **N/A** (backtest なし)。代替: SHA 固定・spec 固定・per-test 集合・collect-only 再導出で再現性は担保
- [x] 専門領域「証拠を生む仕組み」の欠陥 — **抵触なし**: 変異は全件枠経由 + 本番不達、baseline 緑を前提条件として機械的に強制、等価変異の判定に対照変異あり
- [x] 他 agent 判定との不整合 — v5 の 2 名 HOLD は解除条件が成立 (上表)。89a3840 に対する最終判定は **未提出** → 本 agent の PASS は P1 を条件とする (先走って「全 PASS」は宣言しない)
- [x] 前回宣言の執行 — (4) 未到達で継続、(5) 執行

## 反証の試み (すべて隔離コピー、本番は読み取りだけ)

| # | 試み | 結果 |
|---|---|---|
| R1 | 95 変異は本当に 95 か / 途中で増減していないか | spec を runpy で読み 95、`run13` の行数 94+1 = 95、順序も spec と一致 → 成立 |
| R2 | F6 は「等価」でなく網の目ではないか | 隣の検査行を壊す V8 を植えて KILLED → 空文字の拒否はテスト済み、F6 の差は観測不能 → 等価 |
| R3 | 環境失敗 2 件が退行を隠していないか | (a) 未追跡ファイル不在 (v3 から同じ)、(b) dry-run DB を `today=20260927` で数えて 0 / 本番 0 → 日付経過のみ |
| R4 | 979 → 980 の「余分な 1 本」 | collect-only 980 = 実行集合と ID 一致、209b636 からの +31 −5 が commit と一致 → 余分な 1 本は存在しない |
| R5 | strict / off の同一性は作者の主張どおりか | `diff set_strict.txt set_off.txt` 空、当方 141 本 off/strict 両方緑、`warn` は fail-fast |
| R6 | 枠の子に outer の off が届かないか | 当方の枠起動は `KEIBA_RUNTIME_GUARD=off` の下で実施、V7 (子に呼び出し元のモードを戻す) KILLED |
| R7 | 本番に触れていないか | worktree porcelain 0、main 追跡変更 0、DB mtime 9/27 20:00 (run 前)、WAL 0 B、worktree data/logs 9/26 以降不変 |

## 生存変異 (当方分、非採用条件)

| # | 変異 | 判定 | 深刻度 |
|---|---|---|---|
| F6 | `day = today or current_jst_daystamp(now)` | SURVIVED | **等価** (V8 で証明) |
| V3 | `conftest.pytest_configure` の `runtime_guard_mode()` 呼び出しを `pass` に | SURVIVED | 低 (網の目)。未知の値は session fixture で依然 UsageError になるが、collect とモジュール import は走る。`test_an_unknown_guard_value_stops_pytest` に「`collected` が出ない / exit 4」を足せば固定できる |

## 根拠ファイル (絶対パス)

- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\runtime_guard.py` (:57-66 child_pytest_env)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\tests\conftest.py` (:46-60 モード / :63-100 見張り)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\tests\test_conftest_guard.py` (:54-55)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\tests\test_weekly_monitor_guard.py` (:225-244)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\tests\test_runtime_guard.py` (:61-78, :104-120)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\scripts\mutation_sandbox.py` (:224-256)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\weekly_monitor.bat` (:21-46)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\config.py` (:289-317 sealed_window_started)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\db.py` (:229-268 horse_num_violation_counts)
- `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify\docs\CLOCK_LEDGER.md` (:88-130)
- `C:\Users\kizun\dev\keiba-yosou\data\jst_mutation_20260928\` — `jst_spec_v7.py` / `run13_result.txt` / `jst_mut12_result.txt` / `full_strict.txt` / `full_off.txt` / `set_strict.txt` / `set_off.txt` / `full_rc.txt` / `set_prev.txt` (0 B)
- `C:\Users\kizun\dev\keiba-yosou\data\scorecards\20260926_0440_jst_unify_v5__validation-process-auditor.md` / `__code-quality-reviewer.md` / `__data-pipeline-engineer.md`
- 当方の成果物 (scratchpad、揮発): `C:\Users\kizun\AppData\Local\Temp\claude\C--Users-kizun-dev-keiba-yosou\ba1406e5-db88-4baa-8fae-bdcf86bee826\scratchpad\final_vpa\` — `vpa_spec.py` / `vpa_run.txt` (10 変異) / `collect89.txt` (980) / `collect209.txt` (954) / `set_strict_ids.txt` / `copy89` (junction 解除済) / `copy209` / `fresh`

## 次アクション

1. **(P1)** data-pipeline-engineer / code-quality-reviewer の 89a3840 最終 scorecard を受領し、FAIL / NOT_EVALUABLE が無いことを確認してからマージ (ff or merge commit、bat 単独 cherry-pick 禁止)。
2. **(P3)** マージ後、最初の 08:00 起動と 10/04 (日) 10:00 の週次監視の後に `docs/CLOCK_LEDGER.md` の記録表を埋める。`runtime_guard=off pytest_exit=0` が無ければ即 HOLD。
3. バックログ (採用条件ではない): (i) `tests/test_placeholder_cleanup.py::test_live_database_has_no_placeholder_violations` の dry-run DB 日付依存を解消 (skip 条件 or `today` を DB 内最新日で打ち切り)。(ii) V3 生存の固定 (未知の値で `collected` が出ない / exit 4 を assert)。(iii) 変異実行時は DB 静穏チェックの結果 (size/mtime の before/after) を成果物として残す。(iv) C4 (`weekly_monitor.bat:5` の `date.today()`) を日次 bat と同じ JST 経路へ (台帳 C 優先の既知項目)。
4. 次回以降のレビューでは per-test リスト (`set_*.txt`) を必ず残し、件数変化は collect-only の diff で説明する (今回の 979 のような検証不能な数字を作らない)。

## 終了時の記録

- worktree `HEAD = 89a3840b0ee358a038c5dd4ab29906b9389d0dc7`、`status --porcelain` 0 行 (開始時・終了時とも)。main `eb875e8`、追跡ファイル変更 0。
- 本番 DB `data/keiba.db` 20,118,552,576 B / mtime 2026-09-27 20:00:13、WAL 0 B (読み取り `mode=ro` のみ)。
- 隔離コピーの `.venv64` ジャンクションは `rmdir` で解除、実 venv `python.exe` 健在。Task Scheduler / ai-builder / 常駐プロセスは未操作、本物の bat 未起動、Discord 未送信。

## 次回宣言 (必ず執行する)

- (1) マージ後の最初の採点で、`docs/CLOCK_LEDGER.md` の記録表が空、または週次ログに `runtime_guard=off pytest_exit=0` が無い、または `auto_predict_daily_DATE_FAILURE.log` が新規生成されていれば **HOLD** (v4/v5 宣言 (4) の継続)。
- (2) 89a3840 の後に commit を足してマージした場合、95 変異 + strict/off 全 suite 同一性の再実行証拠が無ければ **NOT_EVALUABLE**。
- (3) 次回、`test_placeholder_cleanup` の日付依存が未是正で再び「環境由来」として片付けられていたら、その時点で改善提案から解除条件へ格上げする。
