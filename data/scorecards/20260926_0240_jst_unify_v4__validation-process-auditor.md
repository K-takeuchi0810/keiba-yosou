# 検証プロセス監査人 (最終ゲート) 採点 — JST 統一 v4 (27a260e, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `27a260e` 固定、worktree `C:/Users/kizun/dev/keiba-yosou/.claude/worktrees/jst-unify`。git は全て `git -C <wt>`、Read/Grep は worktree 絶対パス。変異は **全件 `scripts/mutation_sandbox.py` 経由** (隔離コピー = `git archive 27a260e | tar -x` → scratchpad `gate4_validation` + `.venv64` ジャンクション + worktree の小 DB 499,712 B を実ファイル複製。枠の事前検査: コピー = 問題なし / worktree = 「本番 checkout の中」「.git あり」で拒否)。worktree・本番 checkout のファイルは未編集、SHA 不動、Task Scheduler 未操作 (状態の読取のみ)、Discord 未送信 (コピーに webhook ファイル無し)。前回 v3 (a9f3969、HOLD 4.3) からの差分 5 commit (8 files +528 −9) と CHAT 指定の解除条件 5 件を中心に確認し、ゼロからの再点検はしていない。表記: 変異名 M2″ / M14′ / PS′ は前回 scorecard の同名変異 (本ファイルではプライム記号)。

## 判定: PASS (最終ゲート — 前回宣言 (2) の解除条件が成立。他 agent 判定の統合結果)

**理由**: 前回 HOLD の唯一の理由 = `web/generator.py:318` の既定 `today` と `web/publish_safety.py:60` の `base_date` に挙動テストが無く M2″/M14′/PS′ が素通りしていたこと。今回 `tests/test_generator_today.py` (JST の時計を 2026-01-15 に固定し、空 DB で `build_view_model` を最後まで流して最初の races クエリの窓と `assess_race_completeness` に渡る `today` を記録) が追加された。**当方の独立変異 (spec G、TESTS は挙動テスト 2 本だけ = AST ガード `test_today_single_source.py` を意図的に外して実行) で M2″ / M2b / M14′ / M14b / CA / CA2 / PS′ / PSb / PSc の 9/9 が挙動テストだけで KILLED**。作者の結果 (`jst_mut9_result.txt`) では G1 が AST ガードで先に落ちていて挙動テスト単独の検出力が読めなかったので、この分離実行が今回の裏取りの核心。
CHAT 追加の解除条件 2〜5 も、枠の関数を偽の本番に対して直接叩く probe (12 種の対象パス全て書込み前に REFUSED、外のファイルは bytes / mtime 不変、対照は流れて KILLED / 本番 root 不在・runtime 不在・DB 不在の 3 通りで **テスト 1 本も走らずに** 停止) と、独立変異 39 種 (33 KILLED / 1 REFUSED (期待どおり) / 5 SURVIVED = すべて網の粗さで挙動の欠陥ではない、下表) で成立を確認した。従来項目 A/B/C/D/E/F/H の再植変異は全て KILLED、実経路 dry-run (wscript → vbs → ps1 → bat) を自分のコピーで再現 (exit 0 / `run date 20260926 (JST) dryrun=[1]` / `generate: 20260926 (24 races)` / `covered=24` / DATE_FAILURE 無し / 本番 diff 空)。全 suite は **926 passed / 9 skipped / 1 deselected を 2 回** (PYTHONIOENCODING 未設定 / utf-8、rc 0) で作者の実測と **一致**。他 agent: v4 sibling は本 scorecard 執筆時点で未提出、v3 sibling は code-quality PASS 4.2 / data-pipeline PASS 4.7 (条件 1 件 = merge 後確認手順の文書化 → `docs/CLOCK_LEDGER.md:86-117` runbook で **解消**)。FAIL / NOT_EVALUABLE / HOLD は無い → 統合判定ロジック 4 (全 PASS かつ検証設計に欠陥なし) で PASS。
**改修タイプ**: type-B/C (運用基盤: 時計・bat・ps1・変異テストの枠・テスト基盤。predictor / backtest / GUI 非接触)。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN) は **N/A (対象外)**。
**根拠ファイル**: `config.py:260-283,289-310,372-379` / `web/generator.py:313-322` / `web/publish_safety.py:29-33,58-60` / `scripts/mutation_sandbox.py:108-143,210-223,254-258` / `tests/conftest.py:25-62` / `tests/test_generator_today.py` / `tests/test_conftest_guard.py` / `tests/test_mutation_sandbox.py:293-431` / `tests/test_sealed_clock.py:284-336` / `docs/CLOCK_LEDGER.md:86-117` / scratchpad `gate4_spec_{g,x,s,b}.py` + `gate4_spec_{g,x,s,b}_result.txt` / `gate4_suite_run1_noenc.txt` `gate4_suite_run2_utf8.txt` / `gate4_prod_snapshot_before.json` / `gate4_dryrun.ps1`
**次アクション**: (1) merge は ff (main `d134b3b` は 27a260e の祖先、`merge-base --is-ancestor` 真)。bat だけの cherry-pick は継続宣言どおり FAIL。(2) merge 後の最初の 08:00 起動後に runbook 表 (`docs/CLOCK_LEDGER.md:110-112`) を埋める (次回宣言 (4))。(3) 小さな網の目 5 件 (下「改善提案」) は次の小 commit で。採用条件ではない。

## 総合: 4.5 / 5 (前回 4.3 / HOLD → +0.2、判定は PASS)

上昇根拠: 前回の生存変異 M2″/M14′/PS′ を挙動テスト単独で撃墜 / conftest の見張り・枠の runtime 監視・変異なし実行の差分にそれぞれ自己テストが付き、前回生存の V-E3 / V-Xc / V-Xj / V-F7 が全て閉鎖 / 枠の「書いてから戻す」が「書く前に拒否」に変わった (code-quality v3 所見 (a)(b) の閉鎖を当方でも実測) / 日付の検査が 1 か所に統一され 20261332 が両方で拒否される。

## CHAT 指定の解除条件 — 成立表

| # | 解除条件 | 判定 | 一次証拠 (自分で実行したもの) |
|---|---|---|---|
| 1 | generator / publish_safety の 3 変異 (M2″ / M14′ / PS′) が死亡 | **成立** | spec G (TESTS = `test_generator_today.py` + `test_publish_safety.py` のみ、AST ガード除外): V-M2″ (`from datetime import datetime as _clock; today = _clock.now().date()`) / V-M2b (`time.localtime` 経由) / V-M14′ (1 日前) / V-M14b (1 日後) → `test_the_default_window_is_jst_today_plus_minus_14` で KILLED。V-CA (アラートに翌日) / V-CA2 (today を渡さない) → `test_the_completeness_alert_gets_the_same_jst_today` で KILLED。V-PS′ (`date.today()`) / V-PSb (JST 1 日前) / V-PSc (`from jst import current_jst_date` を削除 = 作者が見つけた NameError の再現) → `test_the_default_base_date_is_jst_today` で KILLED。作者主張「import 漏れを発見」は V-PSc で裏取り。**限定**: 固定時刻が 2026-01-15 **10:00 JST** (= 同日 01:00 UTC) で UTC 境界をまたがないため、この挙動テストは「JST か UTC か」を区別しない (V-JU = `current_jst_date` が UTC の日付を返す変異は spec G で **SURVIVED**、spec S の `test_jst_date.py::test_jst_midnight_is_the_boundary` で KILLED)。区別は jst 層のテストに委ねる構造で、ゲートとしては成立。固定時刻を 08:00 JST (前日 23:00 UTC) にすれば 0 コストで両方を 1 本で見られる (提案 1) |
| 2 | 絶対パス / `..` が **書き込み前に** REFUSED、外のファイルが 1 バイトも変わらない | **成立** | `scripts/mutation_sandbox.py:126-143` `refuses_target` (空 / 非 str / ドライブ・ルート・UNC・スラッシュまたはバックスラッシュ始まり / `..` を区切り文字に関係なく / `resolve()` 後にコピーの外 = ジャンクション越し)。`:254-258` で対象パス検査を `refuses()` より前に、`originals` の digest 対象からも除外。直接 probe (コピーの枠を偽本番に対して): 絶対パス (両区切り) / `../` / バックスラッシュ区切りの `..` / `sub/../../` / `sub/../calc.py` (中に収まる `..`) / `/outside.py` / UNC / `C:outside.py` (ドライブ付き相対) / 空文字 / None / `calc.py/../calc.py` の **12/12 REFUSED**、外のファイルの (bytes, mtime_ns) **不変**、対照 `calc.py` は KILLED、コピーの `calc.py` は復元済み。変異: V-R1′ (絶対パス検査を落とす) → `[<lambda>8]` (ドライブ付き相対) で KILLED、V-R4′ (解決後の検査を落とす) → ジャンクション越しテストで KILLED。**V-R2b (`..` の検査をスラッシュ区切りだけに) SURVIVED** = 「中に収まる」バックスラッシュ区切りの `..` (sub＼..＼calc.py) はテストが無い (外へ出る形は解決後の検査で捕まる = 層として塞がっている。probe で現行コードは同パスを拒否することを確認)。提案 2 |
| 3 | 存在しない PRODUCTION_ROOT / 監視対象欠如で実行を開始しない (変異なしの実行より前) | **成立** | `:108-123` `check_production` (root 不在 / `data/logs` `data/runtime` `data/keiba.db` のいずれか不在)、`:218-220` で `check_sandbox` よりも前に呼ぶ。直接 probe: 印を残すテストを持つコピーで root 不在 / runtime 不在 / DB 不在 の 3 通り → SandboxError「本番の監視を始められない」、**印ファイル無し = テスト 1 本も走っていない**。変異: V-R5′ (root 不在を空リストで返す) / V-R8 (検査を変異なし実行の後へ = 検査削除) → `test_a_missing_production_root_refuses_to_start` で KILLED、V-R6′ (DB を監視対象から外す) → `[data/keiba.db]` で KILLED。実物の本番に対する `check_production()` = 空 (監視対象 3 件実在) |
| 4 | 監視対象を削る系の 4 変異が死亡 (F7 / Xc / Xj / E3) | **成立** | V-E3′ (conftest の見張りを `autouse=False`) / V-E3b (見張りから `data/runtime` を外す) → `test_conftest_guard.py` (本物の conftest を複製した小リポで subprocess pytest) で KILLED。V-Xj′ (`before` を変異なし実行の後に取る = 事前実行の差分を無視する別形) → `test_a_leak_in_the_baseline_run_is_reported_as_such` で KILLED。作者の F7 / Xc / Xj / E3 の 4 件は結果ファイルで KILLED を確認。**残る網の目 (低)**: V-F7b (SEALED_FROM の検査を today / now のどちらかを渡したときだけに) **SURVIVED** — テストは now 経路と today 経路のみで **既定経路 (引数なし) が未検査**。既定経路は本番の `artifact_drift` (`config.py:332` `sealed_window_started()`) が使う経路。V-Xc′ (snapshot を rglob → glob) SURVIVED — 漏れテストが直下にしか書かない (本番 `data/logs` `data/runtime` に現状サブディレクトリ無し、実害なし)。V-E3c (conftest が mtime を見ない) SURVIVED — 同サイズ上書きのケースが無い。提案 3-5 |
| 5 | 20261332 が共通の検証 `_require_daystamp` で拒否 (両関数)、開いた端 00000000 / 99999999 は guard だけ | **成立、例外は妥当** | `config.py:263` `OPEN_WINDOW_BOUNDS` frozenset / `:266-283` keyword-only `allow_open_bounds=False` (既定は厳格) / `:377-379` guard だけ `allow_open_bounds=True` / `sealed_window_started` は `:300` で既定 (厳格)。テスト `test_the_analysis_gate_uses_the_same_strict_check` (20261332 / 20260230 / ハイフン / 6 桁 / int を from・to 両側) / `test_the_open_window_bounds_still_work` / `test_the_open_bounds_are_not_a_valid_today` / `test_both_checks_share_one_validator`。変異: V-U1′ (allow_open_bounds なら strptime を丸ごと飛ばす) / V-U6 (OPEN_WINDOW_BOUNDS に 20261332 を足す) / V-G1 (guard で to_date の検査を落とす) → `[20261332]` で KILLED、V-U2′ (today の検査で開いた端を許す) → `test_the_open_bounds_are_not_a_valid_today` で KILLED、V-U5 (実在チェックを月まで) → `[20260230]` で KILLED。**例外の妥当性**: 00000000 / 99999999 は YYYYMMDD の文字列順序と単調に整合する (門の `to_date < SEALED_FROM` 等が壊れない) / 例外は keyword-only フラグ + 定数集合の 2 重で限定 / 「今日」の経路からは到達不能 (テスト + 変異で固定)。`prediction_accuracy.py:25-26` の既定値が `OPEN_WINDOW_BOUNDS` を参照せず直書き (二重記述、code-quality 領分) |

## 従来項目 (A〜H) の回帰確認

| 項目 | 判定 | 証拠 |
|---|---|---|
| A dry-run のタイムアウトで Discord 0 件 | 回帰なし | V-A (`if ($DryRun -and $false)`) → `test_a_dry_run_timeout_never_notifies` KILLED。V-B15 (日付失敗を dry-run でも通知) → `test_the_failure_is_notified_only_outside_dry_run` KILLED |
| B 終了コードの伝搬 | 回帰なし | V-B (`exit /b 0`) / V-B2 (予想ビット 2→1) → `[True-fails0-2]` KILLED、V-P (ps1 `exit 0`) → `test_the_exit_code_reaches_the_scheduler[False]` KILLED |
| C 月の途中の開始日 | 回帰なし | V-Cm (`day[:6] + "01" >= SEALED_FROM`) → `test_a_mid_month_start_is_compared_by_day[now3-True]` KILLED |
| D fetch_mining の import 順 | 回帰なし | V-D → `test_the_script_starts_from_another_directory` KILLED |
| E テストが本番ログを触らない | 回帰なし | worktree `data/logs` `data/runtime` の `ls --full-time` が suite 2 回の前後 + 終了時で **完全一致**、本番 snapshot (3,172 エントリ) の diff = **空** (suite 後 / dry-run 後 / 終了時)。V-E (ps1 が `-LogDir` を無視) → KILLED |
| F fail-fast | 回帰なし (網の目 1 件) | V-Fs (検査を active ゲートの後ろへ) → `test_a_malformed_today_is_rejected_even_when_unset` KILLED。V-F7b は上表 4 |
| H 台帳 | 更新あり | `docs/CLOCK_LEDGER.md:86-117` runbook (ff / merge commit 必須、08:00 後の 4 点確認 + 記録表)。data-pipeline v3 の条件 1 を満たす |
| 実経路 dry-run | 再現 | 自分のコピーで wscript → vbs → ps1 → bat `-DryRun` (JST 9/26 03:02): wscript exit 0、`run date 20260926 (JST) dryrun=[1]`、`generate: 20260926 (24 races)`、`scheduled=24 ... covered=24`、`done exit=0`、watchdog `finish ... exit=0`、DATE_FAILURE 無し、コピーの DB / `docs/index.html` sha256 不変、本番 diff 空。作者主張 (02:36 実施) と一致 |

## 前回 (v3) の次回宣言の執行

| # | 宣言 | 執行結果 |
|---|---|---|
| (1) | bat だけの cherry-pick で main 反映なら FAIL | **未発生** (main `d134b3b` 不動、27a260e の祖先 → ff 可能) |
| (2) | M2″/M14′/PS′ が依然素通りなら FAIL、撃墜されていれば PASS 候補 | **撃墜を独立変異で確認 → PASS** (上表 1) |
| (3) | SEALED_FROM 設定と時計の同居なら FAIL | **非該当**: `config.py:232` `SEALED_FROM = None`、range の config 変更は検査の統一のみ |
| (4) | 枠を経由しない変異証拠は不成立 | **全件経由** (spec 4 本。probe も枠の関数を直接呼ぶ形) |

## 変異表 (独立設計、`scripts.mutation_sandbox` 経由、fresh .pyc、毎回 byte 復元)

39 種: **33 KILLED / 1 REFUSED (期待どおり) / 5 SURVIVED** (うち 1 は spec の設計上の予定 = V-JU@G、4 は網の粗さ。挙動の欠陥ゼロ)。

| spec / ID | 変異 | 結果 | 備考 |
|---|---|---|---|
| G V-M2″ | generator today = 別名 datetime のローカル時計 | KILLED | 挙動テスト単独 |
| G V-M2b | generator today = time.localtime 経由 | KILLED | |
| G V-M14′ | generator today = 1 日前 | KILLED | |
| G V-M14b | generator today = 1 日後 | KILLED | |
| G V-CA | 完全性アラートに翌日を渡す | KILLED | |
| G V-CA2 | アラートに today を渡さない | KILLED | 記録 fixture が today=None を見る |
| G V-PS′ | base_date = today or date.today() | KILLED | |
| G V-PSb | base_date = JST 1 日前 | KILLED | |
| G V-PSc | publish_safety の jst import 削除 | KILLED | 作者主張の NameError 再現 |
| G **V-JU** | jst が UTC の日付を返す (generator テストだけ) | **SURVIVED** | 予定どおり。spec S で KILLED |
| X V-R1′ | 絶対パス検査を落とす | KILLED | 解決後の検査が層として残る |
| X **V-R2b** | .. 検査をスラッシュ区切りだけに | **SURVIVED** | 中に収まるバックスラッシュ .. のケース無し (低) |
| X V-R4′ | 解決後にコピーの中かを見ない | KILLED | ジャンクション越し |
| X V-R5′ | root 不在を空で返す | KILLED | |
| X V-R6′ | 監視対象から DB を外す | KILLED | |
| X V-R8 | 本番検査を変異なし実行の後へ | KILLED | |
| X **V-Xc′** | snapshot を rglob → glob | **SURVIVED** | 本番にサブディレクトリ無し (低) |
| X V-Xj′ | before を変異なし実行の後に取る | KILLED | |
| X V-E3′ | conftest 見張り autouse=False | KILLED | 自己テストが機能 |
| X V-E3b | 見張りから runtime を外す | KILLED | |
| X **V-E3c** | 見張りが mtime を見ない | **SURVIVED** | 同サイズ上書きのケース無し (低) |
| S V-U1′ | allow_open_bounds なら strptime を飛ばす | KILLED | |
| S V-U2′ | today の検査で開いた端を許す | KILLED | |
| S V-U5 | 実在チェックを月まで | KILLED | |
| S V-U6 | OPEN_WINDOW_BOUNDS に 20261332 | KILLED | |
| S **V-F7b** | SEALED_FROM 検査を today/now 指定時だけ | **SURVIVED** | 既定経路 (本番の artifact_drift) 未検査 (低〜中) |
| S V-Cm | 月単位比較 (別形) | KILLED | |
| S V-Fs | 検査を active ゲートの後ろへ | KILLED | |
| S V-JU | jst が UTC の日付を返す | KILLED | test_jst_midnight_is_the_boundary |
| S V-G1 | guard で to_date の検査を落とす | KILLED | |
| B V-A | dry-run 抑止を無効化 | KILLED | |
| B V-B | bat 最終 exit 0 | KILLED | |
| B V-B2 | 予想ビット 2→1 | KILLED | |
| B V-P | ps1 exit 0 | KILLED | |
| B V-E | ps1 が -LogDir 無視 | KILLED | |
| B V-D | fetch_mining import 順 | KILLED | |
| B V-R3 | bat cd をダミーへ (対照) | KILLED | 流れて撃墜 |
| B V-R1p | bat cd を本番 checkout へ | **REFUSED** | 枠の期待動作 |
| B V-B15 | 日付失敗を dry-run でも通知 | KILLED | |

作者の 74 種 (`jst_mut9_result.txt`): 73 撃墜 / F6 生存を読んだ。F6 (`today or ...`) は `_require_daystamp` が空文字を先に落とすので等価 — 作者主張は正しい (v3 と同じ判断、当方では再実行していない)。

## 項目別

- **検証設計の正しさ (証拠が持続するか): 4.7/5** (前回 4.5) — 挙動テストが「今日」を現実と離れた日付に固定して窓と基準日を直接見る / 見張り (conftest) と枠 (runtime・変異なし実行) に自己テスト / 対象パスは書く前に拒否 / 本番不在は fail-close。減点: 既定経路の SEALED_FROM 検査 (V-F7b) / バックスラッシュ区切り `..` (V-R2b) / 同サイズ上書き (V-E3c) の 3 つの網の目。
- **時間境界 (リーク分類学①の運用版): 4.5/5** (前回 4.5) — 固定時刻が UTC 境界をまたがず、generator 層では JST/UTC を区別しない (jst 層に委ねる)。naive `now` の非対称 (v3 提案 4) は未着手 (封印未定の今は到達しない)。
- **変異テスト (独立設計): 4.6/5** (前回 4.2) — 39 種 33/1/5、生存 5 はすべて網の粗さ。前回生存 7 件 (M2″/M14′/PS′/V-E3/V-Xc/V-Xj/V-F7) 全て閉鎖を確認。
- **A/B・再現性・merge 検証: 4.6/5** (前回 4.3) — suite 926/9/1 × 2 で作者と **一致** (v3 の 883 vs 887 の不一致は解消、+39 = 新規テストの collect 数と整合)。main は祖先で ff 可能、SEALED_FROM None 不動。
- **運用移行 / 統合判定 / 台帳: 4.3/5** (前回 4.0) — runbook 追加 (data-pipeline v3 条件を解消)、実経路 dry-run を当方でも再現。減点: v4 sibling 未提出 (提出後に FAIL / NOT_EVALUABLE があれば本判定もそれに従う)、`PRODUCTION_ROOT` と `register_auto_predict_task.ps1` の二重記述 (code-quality v3 (c)) 未着手、`docs/index.html` は監視対象外のまま (v3 提案 6)。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides / market_snapshot / factorial / bootstrap — **N/A** (type-B/C、backtest JSON 生成なし)
- [x] 比較設計 (期間 / code path / filter / fold) — N/A
- [x] 専門領域「証拠を生む仕組み」の欠陥 — **抵触なし** (時限テスト無し、変異は枠経由で本番不達、生存変異はすべて網の目)
- [x] 他 agent 判定との不整合 — v4 sibling 未提出。v3 sibling は PASS / PASS、data-pipeline の条件 1 件は解消
- [x] 前回宣言の執行 — (2) 解除条件成立 → PASS。(1)(3) 非該当、(4) 全件経由
- [x] SEALED_FROM = None のまま — `config.py:232`

## 反証の試み

- 「M2″/M14′/PS′ は挙動テストで撃墜」→ AST ガードを外した spec で 9/9 KILLED → **成立** (作者の結果では G1 が AST ガードで先に落ちていたため、この分離が必要だった)
- 「絶対パス / `..` は書く前に REFUSED」→ 12 種の対象パス、外のファイル bytes/mtime 不変 → **成立**
- 「本番不在なら開始しない」→ 3 通りで印ファイル無し → **成立**
- 「926 passed」→ 当方 926 × 2 → **一致**
- 「実経路 dry-run exit 0 / 24 races 24/24」→ 自分のコピーで再現 → **成立**
- 「F6 は等価」→ コードで確認 → **成立**
- 「挙動テストは JST を固定している」→ 固定時刻 10:00 JST は UTC と同日 → generator 層では JST/UTC を区別しない (V-JU@G 生存) → **部分的に成立** (jst 層のテストが補う)

## 改善提案 (採用条件ではない)

1. `tests/test_generator_today.py` の `FROZEN` を 2026-01-15 **08:00 JST** (= 1/14 23:00 UTC) にする。ローカル時計と UTC 日付の両方の変異を 1 本で区別できる。
2. `test_dotdot_is_refused_even_if_it_stays_inside` にバックスラッシュ区切り (sub＼..＼calc.py) を 1 件 (V-R2b)。
3. `test_a_malformed_sealed_from_is_rejected` に **引数なし** の経路を 1 件 (V-F7b、本番の `artifact_drift` が使う経路)。
4. `test_conftest_guard.py` に同サイズ上書き (`existing.log` を同じ長さで書き換える) を 1 件 (V-E3c)。
5. `test_a_leak_into_runtime_is_detected` の書込み先をサブディレクトリに (V-Xc′)。
6. (継続) naive `now` の tz 検査を active ゲートより前に / `docs/index.html` を snapshot に / `PRODUCTION_ROOT` の二重記述。

## 前回からの差分

- 前回 (20260926_0040、a9f3969): 4.3 / HOLD → 今回 (27a260e): 4.5 / **PASS** (+0.2)。
- 前回提案の消化: 1 (HOLD 解除 = generator / publish_safety 挙動テスト) ✓ / 2 (conftest 自己テスト) ✓ / 3 (runtime 漏れ・変異なし実行差分) ✓ / 5 (V-F7 today 経路) ✓ / 4 (naive now) ✗ / 6 (docs/index.html 監視) ✗。

## 終了時の記録

- worktree `git status --short` = **空** (開始時・suite 2 回後・終了時)、HEAD = `27a260e` 不動。
- 本番 `data/logs` + `data/runtime` + DB (3,172 エントリ、DB 20,092,399,616 B / WAL 0 B) の開始 / 終了 snapshot 差分 = **空** (suite 後・dry-run 後・終了時の 3 点とも)。worktree `data/logs` `data/runtime` の `ls --full-time` は開始時と **完全一致**。
- ジャンクションは `rmdir` で解除 (Test-Path False)、実 venv `python.exe` 健在 (site-packages 107)。隔離コピー (リンク無し) と spec / 結果 / probe は scratchpad `gate4_*` に残置。
- Task Scheduler 未操作 (状態読取のみ: Ready)、Discord 未送信、SEALED_FROM = None。
- 同時刻に別 agent が本番 checkout の venv で pytest を回していた (02:55〜、`-X utf8 ... --deselect tests/test_mutation_sandbox.py`)。当方の bat / ps1 テストの結果に異常は無かった。

## 次回宣言 (必ず執行する)

- (1) main への反映が **bat だけの cherry-pick** (jst.py 不在) なら **FAIL** (継続)。
- (2) `SEALED_FROM` に日付を入れる commit が時計・bat の変更と同居していたら **FAIL** (継続)。
- (3) 変異テストの結果が `scripts/mutation_sandbox.py` を経由せずに報告された (または隔離コピーが本番 checkout の中にある) 場合、その変異証拠は **不成立** (継続)。
- (4) **新規**: merge 後にこの系列を採点するとき、`docs/CLOCK_LEDGER.md` の runbook 表 (マージ後の最初の起動の 4 点) が **空のまま** か、`auto_predict_daily_DATE_FAILURE.log` が merge 後に新規生成されていたら **HOLD** (運用移行の証拠が無い状態で「移行完了」を主張させない)。
- (5) **新規**: 提案 3 (SEALED_FROM 検査の既定経路テスト) は、`config.py` の封印まわりを次に触る commit で同梱されていなければ、その回の「検証設計」項目を 4.0 上限にする (ゲートではない)。
