# 検証プロセス監査人 (最終ゲート) 採点 — JST 統一 v2 (1baab6c, branch jst-date-unify-20260920)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `1baab6c` 固定、worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\jst-unify`。git は全て `git -C <wt>`、Read/Grep は worktree 絶対パス。変異・dry-run は `git archive 1baab6c` の隔離コピー 3 つ (scratchpad `gate_jst_validation{,_b,_c}` + `.venv64` ジャンクション、`_c` には worktree の dry-run 用小 DB を複製) で実施。worktree・本番 checkout のファイルは未編集、SHA 不動、Task Scheduler 未操作、Discord 未送信、本番 bat は未起動。全テストは worktree 上で実行 (書込みは `.gitignore` 対象の `data/logs` のみ)。開始時・全テスト後・終了時の worktree `git status --short` = **空** (3 回確認)。ジャンクションは reparse point として解除、実 venv の `python.exe` 健在 (site-packages 107) を確認。

## 判定: PASS (最終ゲート — 他 agent 判定統合済み。条件 2 件を merge 時に執行)

**理由**: 指示元 (CHAT) の完了条件 7 件は **全件成立** (下表)。前回 FAIL (20260921_0040、37eaf61、2.4) の停止事由「翌日に赤くなる時限テスト」は注入方式へ書き換え済み (`tests/test_notify_dedup.py:263-279`)、既定経路テストは want=False/True の両極を持ち **実時刻に依存しない** ことを確認。本番 checkout は `main` (d134b3b) に戻っており、scheduler `keiba-auto-predict` は main の `run_auto_predict_daily.ps1` を引数なしで起動 (next 09/26 08:00)。独立変異 34 種 (今回分) で **26 撃墜 / 8 生存**、生存はすべて「正しさ」ではなく「テストの網の粗さ」(下表、うち等価 3)。停止条件 (汎用・専門) への抵触なし。
**改修タイプ**: type-B/C (運用基盤: 時計・bat・ps1。predictor / backtest / GUI 非接触)。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN) は **N/A (対象外)**。6 agent 統合は type-B のため形式上 N/A だが、本ラウンドで揃っている sibling 判定 (code-quality **PASS 4.0** / data-pipeline **PASS 4.2 条件 3 件**) を統合: FAIL / NOT_EVALUABLE / HOLD なし → 本 agent 単独の検証設計欠陥も無し → PASS。
**根拠ファイル**: `config.py:260-277,306-312` / `jst.py:47-72` / `scripts/auto_predict_daily.bat:9-38,73-77` / `scripts/run_auto_predict_daily.ps1:11,15,54-61` / `tests/test_sealed_clock.py:38-52,72-84,101-124,129-147,153-202` / `tests/test_daily_bat_rundate.py:53-69,75-80,103-196` / `tests/test_auto_predict_task_runner.py:330-397` / `tests/test_today_single_source.py:56-62` / `tests/test_jst_date.py:97-107,186-199` / `tests/test_notify_dedup.py:263-279` / `docs/CLOCK_LEDGER.md:39-40,44-50,68-81` / merge `67e365d` (両親 `aa0396f` / `d134b3b`、merge-base `fe9c6a5`) / scratchpad `mutate.py` `mutate2.py` `dryrun_c.ps1` `full_suite_wt.txt` `mutation_bat.log`
**次アクション (merge 時に執行する条件)**: (1) **ff merge か merge commit で `jst.py` と新 bat を同時に main へ入れる**。bat だけの cherry-pick は不可 — main の bat は旧版 (`date.today()` 直読み) で `jst.py` が無く、新 bat 単独なら全トリガで exit 8 + Discord ERROR になる (data-pipeline 条件 (1) と一致)。(2) merge 後の最初の起動で `auto_predict_daily_<JST日付>.log` が生成され `DATE_FAILURE.log` が無いことを確認 (23:00 時点、main `data/logs` に DATE_FAILURE.log は存在せず、22:03 以降の新規ファイルも無し — data-pipeline が報告した 22:29-22:34 の痕跡は現存しない)。

## 総合: 4.1 / 5 (前回 2.4 / FAIL → +1.7)

1 点超の上昇の根拠 (列挙): 時限 fail の解消を無改変 HEAD で確認 (827 passed / 9 skipped / 1 deselected、rc 0、40.8 s) / 前回の生存変異 M2・M4・M6 が撃墜 (M5 は `jst_today` 廃止で対象消滅) / 実経路 dry-run を自分で再現 (3 シナリオ) / 本番 checkout が main。

## 完了条件 (CHAT) の成立表

| # | 条件 | 判定 | 一次証拠 |
|---|---|---|---|
| 1 | `sealed_window_started` が JST 単一出典だけを使う | **成立** | `config.py:273-277`: `from jst import current_jst_daystamp` のみ、`datetime`/`date` の import 無し (diff 67e365d..1baab6c で `from datetime import date` 削除を確認)。変異 S-b (date.today 復活) 8 fail / S-c (自前 UTC 時計を別名 `stamp` に代入 = AST ガード回避) 7 fail で撃墜 |
| 2 | now 注入と now=None 既定経路の両方をテスト | **成立** | `test_sealed_clock.py:101-124` 既定経路 (want=False と True の両極 → 実時刻に依存しない) + `:117-124` 既定=注入の一致。変異 S-d (now 無視) 5 fail |
| 3 | 境界 / UTC 15:00 / None は開始しない / 10/01 は境界で開始 / fixture 分離 | **成立** | `:72-84` 8 instant (9/30 00:00・23:59:59・23:59:59.999999、10/01 00:00:00・00:00:01、UTC 14:59:59・15:00:00、JST 10/01 08:59:59)。`sealed_from_1001` と `sealed_unset` は別 fixture (`:38-52`)、None は `:129-138` で注入・既定の両経路。変異 S-a (>=→>) 7 fail。**留意**: 開始日が常に「月初」なので月粒度比較 (S-f) が生存 — 中旬開始 (例 20261015) のケースが無い |
| 4 | OS の TZ を変えても同じ判定 (TZ が子に効くかも) | **成立** | `:153-202` subprocess で UTC0 / JST-9 / PST8PDT、`time.timezone` が 3 値で異なることを先に assert。独立確認: 同 venv で `TZ=UTC0/JST-9/PST8PDT` → naive now = 13:51 / 22:51 / 06:51、UTC は不変 → TZ は本当に効いている。変異 S-h (naive local を返す) 3 fail |
| 5 | .bat → wscript → Python 実経路 dry-run (正常 / 異常) | **成立 (限定 1 点)** | 隔離コピー `_c` で `wscript //B //NoLogo <vbs> ps1 <c>\scripts\run_auto_predict_daily.ps1 -DryRun` を自分で 3 回実行: **V1** exit 0、`auto_predict_daily_20260925_dryrun.log`、`run date 20260925 (JST)`、fetch/notify 不呼出。**V2** `jst.py` の時計を UTC 09-25 15:30 (= JST 09-26 00:30) に固定 → bat のログ名 `…20260926_dryrun.log` と Python の対象日 `generate: 20260926 (24 races)` / `entry coverage scheduled=24 … covered=24` が **同じ出典から一致**、exit 0。**V3** `jst.py` を ImportError に → exit 8、`DATE_FAILURE.log` に Traceback、`auto_predict_daily_.log` も日付入りログも生成されず、stderr は `rundate_stderr.txt` (451 B) に保存、通知なし。watchdog は exit=8 をそのまま伝搬。**限定**: `auto_predict --dry-run` は `web.generator` 起動前に return (`auto_predict.py:401-402`) するので、生成・Pages staging・通知分岐は dry-run 経路に **乗らない**。bat ヘッダの "Everything else is the same path" は対象日決定までに読み替えること |
| 6 | mutation (作者 25/25 撃墜) | **成立 (独立設計で確認)** | 下表。今回分 34 種: 26 撃墜 / 8 生存 (等価 3、網の粗さ 5)。作者の 25 種そのものは再現していないが、同クラスで独立に設計した変異が同等の撃墜率 |
| 7 | 全テスト 827 / 9 / 1 | **成立** | worktree で `-m pytest -q tests/ --deselect …frozen_validation_auc`: **827 passed, 9 skipped, 1 deselected in 40.79s**, rc=0。前後で `git status --short` 空 |

## 変異表 (独立設計、隔離コピーで実行、byte 復元を毎回 assert)

判定に使ったテスト: 封印 = `test_sealed_clock + test_today_single_source + test_jst_date + test_sealed_holdout` (baseline 59 passed) / bat = `test_daily_bat_rundate + test_jst_date` (26) / ps1 = `test_auto_predict_task_runner -k "watchdog or dry_run"` (9) / 前回生存の再植 = `test_today_single_source + test_jst_date + test_notify_dedup + test_notify_e2e + test_publish_safety + test_auto_predict_artifacts` (90)。

| ID | 変異 | 結果 | 備考 |
|---|---|---|---|
| S-a | `day >= SEALED_FROM` → `>` | KILLED 7 | 境界 |
| S-b | `date.today()` 復活 (OS ローカル) | KILLED 8 | 既定経路 + AST ガード |
| S-c | 自前 UTC 時計を `stamp` に代入 (AST ガードの TARGET_NAMES 回避) | KILLED 7 | 既定経路テストが捕まえる (ガード非依存) |
| S-d | 注入 `now` を無視 | KILLED 5 | |
| S-e | `today` より時計を優先 | KILLED 2 | |
| **S-f** | `day[:6] >= SEALED_FROM[:6]` (月粒度) | **SURVIVED** | fixture の開始日が常に月初 (20261001) のため等価。中旬開始で壊れる |
| S-g | jst 既定 now を `datetime.now().astimezone()` (ローカル aware) | KILLED 1 | `test_jst_date.py:97-107` のソース文字列 assert のみが検出 (挙動は等価) |
| S-h | jst 既定 now を naive local | KILLED 3 | OS TZ テストが検出 |
| S-i | `astimezone(JST)` → `replace(tzinfo=JST)` | KILLED 8 | |
| S-j | `sealed_window_active()` ゲート削除 | KILLED 1 | test_sealed_holdout |
| **S-k** | `today` と `now` 併用時に `now` 優先 | **SURVIVED** | 併用ケース未定義 (等価扱い、API の曖昧さ) |
| S-l | `utcoffset() is None` 判定を削除 | KILLED 1 | 前回指摘 (b) の閉鎖を確認 |
| S-m | JST を +8 に | KILLED 10 | |
| B-1 | `goto :date_failure` 削除 (無音 fallthrough) | KILLED 13 | |
| B-2 | stderr を捕捉しない | KILLED 1 | Traceback 保存テスト |
| B-3 | dry-run でも fetch 実行 | KILLED 1 | |
| B-4 | 日付失敗を exit 0 | KILLED 11 | |
| B-5 | `cd /d "%~dp0"` (scripts へ) | KILLED 14 | |
| B-6 | `set "RUNDATE="` 初期化削除 (環境の古い値を再利用) | KILLED 1 | |
| B-7 | `--dry-run` の綴り違い | KILLED 2 | |
| **B-8** | 正規表現を任意 8 桁に緩める | **SURVIVED** | 低: Python は日付しか出さない |
| **B-9** | `/x` を外し部分一致に | **SURVIVED** | 低: 同上 |
| **B-10** | `set FINALCODE=%errorlevel%` → `0` (後段の終了コード不伝搬) | **SURVIVED** | **中**: スタブが全て exit 0 なので「正常系 exit 0」は伝搬の証拠にならない。既存行だが、今回の bat テストで失敗スタブ (例 auto_predict exit 2 → bat exit 2) が 1 本欲しい |
| B-11 | dry-run の coverage に `--notify` | KILLED 1 | |
| B-12 | 日付失敗通知を dry-run でも送る | KILLED 1 | |
| B-13 | `DATE_FAILURE.log` を書かない | KILLED 11 | |
| **B-14** | DATEERR を追記モードに (古い stderr が蓄積) | **SURVIVED** | 低 (成功時 0 B は維持されない程度) |
| B-15 | ログ先頭行を `%date%` に (RUNDATE と不一致) | KILLED 1 | |
| P-1 | /c 文字列の二重引用を外す | KILLED 1 | `a&b` パスのみで検出 (作者主張どおり) |
| P-2 | `--dry-run` を常時付与 | KILLED 3 | |
| P-3 | `--dry-run` を付けない | KILLED 4 | |
| **P-4** | `DryRun → SkipNotification` の連動を削除 | **SURVIVED** | **中**: dry-run で timeout / kill 失敗すると `Send-WatchdogAlert` が Discord へ POST する。「dry-run は Discord 無効」の主張はこの経路で未固定 |
| P-5 | `--dry-run` 前の空白欠落 | KILLED 4 | |
| **P-6** | `-WorkingDirectory $PSScriptRoot` | **SURVIVED** | 等価 (bat が自分で cd) |
| M2' | generator `today = datetime.now().date()` | KILLED 1 | 前回生存 M2 → 閉鎖 (AST ガード) |
| **M2''** | generator `_t = datetime.now(); today = _t.date()` | **SURVIVED** | AST ガードは代入先名でしか見ない + generator 既定 `today` の意味テストが無い (前回提案 1 の後半は未執行) |
| **M14'** | generator `today − 1 日` | **SURVIVED** | 同上。`assess_race_completeness(today=)` の基準日が 1 日ずれても検出されない |
| M3' | auto_predict `today` = UTC 日付 | KILLED 1 | 前回生存 → 閉鎖 |
| M4' | auto_predict `today` = `date.fromtimestamp(time.time())` | KILLED 1 | 前回生存 M4 → 閉鎖 |
| M6' | notify_dedup `decide` の today を自前ローカル時計に | KILLED 1 | 前回生存 M6 → 閉鎖 |
| M12' | `_is_final_attempt` が now 無視 | KILLED 1 | |
| **PS'** | publish_safety `base_date = today or date.today()` | **SURVIVED** | `base_date` は TARGET_NAMES 外 + 注入テスト無し。JST 機では等価 |

集計: 今回分 (S/B/P) 34 種 → 26 撃墜 (76%)、生存 8 (等価 3: S-k / P-6 / B-14、網の粗さ 5: S-f / B-8 / B-9 / B-10 / P-4)。前回生存の再植 8 種 → 5 撃墜、生存 3 (M2'' / M14' / PS')。前回宣言「M2/M4/M5/M6 のいずれかが依然素通りなら HOLD 上限」は、書かれた綴りの M2・M4・M6 が撃墜、M5 は対象消滅 → **HOLD 上限は適用しない**。ただし同クラスの M2''/M14' は残る (次回宣言へ)。

## 項目別

- **検証設計の正しさ (証拠が持続するか): 4.3/5** — 既定経路テストは両極を持ち、実時刻に依存しない (前回の時限 fail の再発防止として妥当)。`test_the_real_setting_is_still_unset` (`:141-148`) が「時計の修正と設定変更を混ぜない」を固定しており、SEALED_FROM=None を確認。dry-run の実証は対象日決定まで (生成は乗らない)。B-10: 正常系スタブが全て exit 0 で終了コード伝搬が未検証。
- **時間境界 (リーク分類学①の運用版): 4.2/5** — 8 instant + None 3 instant + TZ 3 zone。`utcoffset() is None` (前回 (b)) 閉鎖。S-f: fixture が月初固定で月粒度の取り違えが不可視。同一起動内の独立時計読取 (auto_predict:222,267,301 / notify_dedup:202,244 = 4-5 回) は前回のまま — 提案止まりで台帳にも項目が無い。
- **変異テスト (独立設計): 3.8/5** — 撃墜 76%。作者の「25 種全撃墜」は再現対象にしていないが、同クラス独立変異で bat/ps1 は 15/19、封印は 11/13。生存の実害は P-4 (dry-run の timeout 経路で Discord POST) と B-10 (終了コード)。
- **A/B・再現性・merge 検証: 4.3/5** — 全 suite を自分で再現 (数値一致)。merge 67e365d: 両側で触れた 3 ファイル (`scripts/auto_predict.py` / `web/generator.py` / `tests/test_notify_e2e.py`) の解決は「db の中止述語 + jst の単一出典を併記」「仮 DB に data_div 列追加」で、main 側の `_entry_coverage` 4 値・全中止分岐・`_final_confirmation` 追加が欠落なく残っていることを両親 diff で確認。`test_sealed_holdout.py` の data_div 列 / `payout_finality_monitor` 免除も main 由来で妥当。
- **運用移行 / 統合判定 / 台帳: 4.0/5** — 本番 checkout `main`、scheduler は main の ps1 を引数なしで起動 (= 本番は `""bat""` 経路、テストは `-SkipNotification` 起動で `[]` 到達を確認)。台帳: 集約済み表に A3 と bat 失敗時を移動、A1/A2 (predict_t10 の naive `datetime.now()` :120,:249) は F3 再開前必須で別フェーズ、A4/A5 (fresh odds :186 / health :516、**毎日 09:00/09:15 に scheduler で動いている PIT 隣接の時計**) も別フェーズ、A6 GUI は最後、B 群は main 反映後、C 群は急がない — 各行の参照行は 1baab6c で現存を確認。JST 機で実害が無い前提での順序は妥当だが、A4/A5 は「ホスト / TZ を変える前に必須」を台帳に明記すべき。docs の「10/01 自動開始」誤記の訂正 (996f0eb / 7dc7250) は config の実値 (None) と一致。sibling: code-quality PASS 4.0 / data-pipeline PASS 4.2 (条件 3) → 不整合なし。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides / market_snapshot / factorial / bootstrap — **N/A** (type-B/C、backtest JSON 生成なし)
- [x] 比較設計 (期間 / code path / filter / fold) — N/A
- [x] 専門領域「証拠を生む仕組み」の欠陥 — **抵触なし** (時限テスト解消、既定経路は両極)
- [x] 他 agent 判定との不整合 — FAIL / NOT_EVALUABLE / HOLD なし (2 名 PASS、他 4 名は本ラウンド未提出 → type-B のため統合必須ではない)
- [x] 前回宣言の執行 — 「時限テストが残っていれば再 FAIL」→ 解消を確認 / 「M2/M4/M5/M6 素通りなら HOLD 上限」→ 4 件とも閉鎖 or 対象消滅 → 適用せず
- [x] SEALED_FROM = None のまま (時計の修正と設定変更の分離) — `config.py:243` + テストで固定

## 反証の試み

- 「827 passed」→ worktree で同数を再現、rc 0 → **成立**
- 「dry-run 正常 exit 0 / 壊した jst で exit 8 + Traceback」→ 隔離コピーで実経路 (wscript→vbs→ps1→bat) 3 シナリオを再現 → **成立** (生成は経路外という限定つき)
- 「25 種全撃墜」→ 独立 34 種で 8 生存 (等価 3) → **主張の一般化は部分的に不成立** (網の粗さ 5 件)
- 「JST 単一出典」→ S-c (別名代入で AST 回避) も既定経路テストが撃墜 → **成立**
- 「OS の TZ を変えても同じ」→ TZ が Python に効くことを独立確認、S-h 撃墜 → **成立**
- 「main 取り込み merge は import 2 箇所のみ競合」→ 両側変更 3 ファイル、解決内容を両親 diff で確認 → **成立**

## 主な改善提案 (merge 前後の小 commit)

1. **P-4**: `run_auto_predict_daily.ps1` の `-DryRun` 時に `Send-WatchdogAlert` が呼ばれないことをテストで固定 (timeout fixture + `-DryRun` で `notify_discord` 未起動を assert)。
2. **B-10**: `test_daily_bat_rundate.py` に失敗スタブ 1 本 (`auto_predict` が exit 2 → bat exit 2、`fresh_odds_coverage` exit 1 → bat exit 1、両方 → 3) を追加。
3. **S-f**: `test_sealed_clock.py` に中旬開始 (例 `SEALED_FROM=20261015`) の境界 1 組を追加。
4. **M2''/M14'**: generator 既定 `today` の意味テスト (`build_view_model(from_date=None,…)` の窓と `assess_race_completeness(today=)` の基準日が `current_jst_date(now)` と一致) を追加。AST ガードの TARGET_NAMES に `base_date` を加える。
5. 台帳に「同一起動内の独立時計読取 (auto_predict 3 箇所 / notify_dedup 2 箇所)」を 1 行追加し、A4/A5 に「ホスト / TZ 変更前に必須」を明記。

## 前回からの差分

- 前回 (20260921_0040、37eaf61): 2.4 / FAIL → 今回 4.1 / PASS (+1.7)。根拠は上記「総合」に列挙。
- 前回提案の消化: 1 (時限テスト修正) ✓ / 2 (checkout 復帰) ✓ / 3 前半 (AST ガード + utcoffset) ✓、3 後半 (generator 意味テスト、単一 now の貫通) ✗ → 提案 4・5 として持ち越し。

## 次回宣言 (必ず執行する)

- (1) main への反映が **bat だけの cherry-pick** (jst.py 不在) で行われていたら **FAIL** (全トリガ exit 8 + Discord ERROR になるため)。
- (2) 次にこの系列を採点するとき、M2''/M14' (generator 既定 today の意味テスト) が依然素通りなら **HOLD 上限**。
- (3) `SEALED_FROM` に日付を入れる commit が時計・bat の変更と同居していたら **FAIL** (設定変更は別コミットの合意)。
- (4) P-4 (dry-run timeout 経路の Discord POST) を放置したまま「dry-run は Discord 無効」を再主張したら、その主張を **不成立** と記録する。
