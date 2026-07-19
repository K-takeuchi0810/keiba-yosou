# Codex 作業指示: 定期実行バッチの修理 (完走型・全 5 ステージ)

前提: 2026-07-19 の定期タスク監査で以下を確定済み (実測ログ・argparse 照合済み):

1. **`scripts/auto_predict_daily.bat` の `fetch_full --since-last` は存在しない引数**
   (`error: unrecognized arguments` exit 2)。導入 commit `2a49bdd` 以来、毎日の
   fetch_full ステップが**静かに失敗**し続けている (次行の WARN で握り潰し)。
   夜 20:00 の外部バッチ (傾向収集) が正しい `--dataspecs` で DB を更新していたため
   実害が隠れていた。
2. **`keiba-yosou-weekly-monitor` が今朝 pytest 途中で強制終了** (LastResult
   `0xC000013A` = STATUS_CONTROL_C_EXIT)。ログは `--- pytest tests/ ---` の dots 54 個で
   `^C` 打ち切り。**monitor 本体 (Brier drift / mining / placeholder = CLAUDE.md ルール 4 の
   週次安全網) まで到達せず未実行**。
3. **`register_auto_predict_task.ps1` の 09:30+11:30 の 2 トリガー化が実機未反映**
   (実タスクは 09:30 単発のまま。ps1 は main に入っているが再実行されていない)。
4. `keiba-oos-backtest-auto` タスクが Disabled・一度も未実行 (`0x41303`) — 要否調査のみ。

外部バッチ (`C:\Users\kizun\dev\傾向収集\`) は監査済みで問題なし — **触らない**。

起動前:
```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッション
codex> /model    # reasoning effort = medium
# ステージ間で /compact
```

---

## ここから Codex へのプロンプト本文

競馬予想パイプラインの定期実行バッチに確定済みの故障が 3 件あります。**途中で人間に確認を
求めず、ステージ 1→5 を順に完走**してください。受入ゲート未達は自力で最大 3 回再試行、
それでも駄目ならスキップ理由を最終報告に記し残ステージ続行。説明は最小限、実ファイルに書く。

### 全体ルール

- 最初に `git status --short` を確認。tracked に未コミット変更があれば**着手せず報告して終了**。
  `git checkout -b codex/scheduler-repair main` で新ブランチ。push しない
- **作業完了後、最終ステージで必ず `git checkout main` に戻す** (明朝 09:30/11:30 の
  スケジュール実行が feature ブランチ上で走ると、未レビュー commit が main へ push される
  ハザードがあるため。main の auto_predict.py にはまだ branch guard が無い)
- コミットは最終ステージのみ `git add <個別パス>` 明示 (git add -A/-u 禁止)
- **触ってはいけない**: `C:\Users\kizun\dev\傾向収集\` 配下すべて / branch
  `codex/output-defects` (PR #9、別ストリーム) / `predictor/` / `data/keiba.db` の中身
- 専門家レビュー / scorecard の作成禁止。**Discord 実送信禁止** (data/discord_webhook.txt は
  本物の secret。bat の通知行は実行せずレビューのみ、テストは mock)
- bat / ps1 は **ASCII のみ** (cp932 parse 事故の既知クラス)。編集後は
  `python -c "print(all(b<128 for b in open(r'<file>','rb').read()))"` で確認
- Task Scheduler の操作 (Get-ScheduledTask / Register-ScheduledTask) は PowerShell で可。
  ただし**タスクの削除は再登録とセットでのみ** (消しっぱなし禁止)

### ステージ 1: `--since-last` バグ修正 + fetch_full 失敗の可視化

対象: `scripts/auto_predict_daily.bat` / `scripts/register_auto_predict_task.ps1` (コメント) / tests

1-1. **13 行目の修正**: `.venv32\Scripts\python.exe -m scripts.fetch_full --since-last`
   → `--since-last` を除去。fetch_full の既定 (dataspecs=RACE HOSE / option=1 = JVOpen 通常差分)
   が本来意図した「前回以降の差分取得」。冒頭の REM コメント (`fetch_full --since-last` 言及)
   も実態に合わせ更新。
1-2. **失敗の可視化**: fetch_full 失敗を握り潰さず exit bit に載せる。
   現行 bits は 1=gap / 2=predict。**4=fetch_full failure** を追加:
   `set FETCHCODE=%errorlevel%` で捕捉 → 従来どおり続行 (既存 DB で予想は出す) しつつ、
   最後の EXITCODE 合成に `if %FETCHCODE% NEQ 0 set /a EXITCODE+=4` を追加。
   あわせて FETCHCODE 非ゼロ時に `scripts.notify_discord --message
   "WARN: fetch_full failed (exit N); predictions used existing DB (see <log>)"` を
   best-effort 呼び出し (weekly_monitor.bat の既存パターンを踏襲)。
   fetch_mining の失敗は従来どおり WARN のみ (mining は補助素材) で変更しない。
1-3. `register_auto_predict_task.ps1` の chain 説明コメントに bit 4 を追記 (ASCII)。
1-4. **テスト**: bat は直接テストできないので、(a) `scripts.fetch_full --help` 相当の
   argparse に `--since-last` が無いことを前提とした「bat が渡す引数が argparse で
   受理されること」の検証テストを追加 — bat をパースして `-m scripts.<name>` の引数列を
   抽出し、各スクリプトの ArgumentParser で `parse_known_args` でなく本物の parser に
   通す (SystemExit しない) ことを確認する軽量テスト (`tests/test_scheduled_bat_args.py`
   新規)。auto_predict_daily.bat と weekly_monitor.bat の python 呼び出し行を対象にする。
   ※ COM 実行はしない — parser 構築だけを import して検証 (fetch_full 等は main() 内で
   parser を組んでいるため、bat から抽出した引数を argparse に渡す形が難しければ、
   「bat 内の `-m scripts.X` 呼び出しに現れるフラグ集合 ⊆ X の add_argument 定義集合」を
   ソース正規表現で照合する方式でもよい。どちらか実装が堅い方を選ぶ)

**受入ゲート 1**: bat から `--since-last` が消えている / bits 4 の合成がある /
新テストが「今回のバグを過去に戻したら FAIL する」ことを確認 (一時的に --since-last を
戻して red になるのを確認してから green に戻す) / ASCII 維持。

### ステージ 2: weekly_monitor の強制終了対策 (安全網の順序是正 + pytest 隔離)

対象: `weekly_monitor.bat` / tests (可能な範囲)

背景: 今朝の強制終了で「pytest が先・monitor が後」の順序のため、週次の Brier drift 監視
(ルール 4) が丸ごと未実行になった。原因 (^C の由来) は特定できていないが、構造対策として
**安全網を先に完了させ、pytest を隔離**する。

2-1. **実行順序の変更**: `:run` 内を「① scripts.monitor → ② fresh_odds_coverage
   --check-gaps → ③ pytest」の順に並べ替える。①② が完了すれば、pytest がどこで
   死んでも安全網は機能する。exit bits (1=monitor / 2=pytest / 4=gap) は不変。
2-2. **pytest のタイムアウト隔離**: pytest 呼び出しを PowerShell の
   `Start-Process -PassThru` + `WaitForExit(600*1000)` パターン (見本:
   `C:\Users\kizun\dev\傾向収集\sync_jvlink_then_collect.bat` の RACE fetch 部) で包み、
   600 秒超過で kill + TESTCODE=124 とする。ハング/強制終了がバッチ全体を巻き込まない。
2-3. **タスク設定の調査 (変更はしない、報告のみ)**: PowerShell で
   `(Get-ScheduledTask keiba-yosou-weekly-monitor).Settings` の ExecutionTimeLimit /
   MultipleInstances を取得し、0xC000013A の原因候補 (時間制限 / 多重起動停止 / 手動停止)
   の切り分け材料として最終報告に記載。
2-4. bat の ASCII 維持と errorlevel 伝播 (call :run リダイレクト → exit /b) の非破壊を確認。

**受入ゲート 2**: 並べ替え後の weekly_monitor.bat を**手動実行** (`cmd /c weekly_monitor.bat`)
し、ログに monitor → coverage → pytest の順で出力され、exit code が bit 合成どおりで
あること (Discord 通知行は webhook 実送信になるため、**実行前に通知行を一時 REM アウト
して実行→実行後に戻す**か、EXITCODE=0 で通知が発火しないことを確認する — 今日は
placeholder 72 行が過渡状態で monitor exit 0 見込みなので後者でよい)。

### ステージ 3: スケジュールタスクの実機反映

対象: Task Scheduler (コード変更なし)

3-1. `powershell -ExecutionPolicy Bypass -File scripts\register_auto_predict_task.ps1` を実行し、
   `keiba-auto-predict` を 09:30 + 11:30 の 2 トリガーで再登録。
3-2. 検証: `Get-ScheduledTask keiba-auto-predict | Select -Expand Triggers` で
   トリガー 2 件 (09:30 / 11:30) を確認し、`Get-ScheduledTaskInfo` の NextRunTime を
   最終報告に記載。
3-3. 注意: 再登録した action が指す bat は **main の内容で実行される** (checkout 依存)。
   本作業のブランチがマージされるまで、bat は旧内容 (--since-last) のまま実行される旨を
   最終報告に明記 (マージを待たずタスクだけ直る、という誤解の防止)。

**受入ゲート 3**: トリガー 2 件の実機確認。

### ステージ 4: keiba-oos-backtest-auto の調査 (報告のみ・変更禁止)

4-1. `Get-ScheduledTask keiba-oos-backtest-auto` の定義 (action / trigger / State) と、
   実行対象 `scripts/run_oos_backtest_if_fresh_ok.ps1` の中身・依存
   (`scripts/rerun_oos_backtest.ps1` 等) を読み、以下を最終報告に整理:
   - このタスクが何をするものか (1-2 行)
   - Disabled になっている経緯の手がかり (git log / コメント)
   - 有効化した場合に今動くか (依存スクリプト・引数の妥当性を静的確認。実行はしない)
   - 有効化/削除の推奨と理由 (判断はユーザに委ねる)

### ステージ 5: 最終検証 + コミット + checkout 復帰

5-1. `pytest tests/ -q` 全 green (378 passed / 4 skipped + 新規分)。
5-2. **コミット (1 回)**: `scripts/auto_predict_daily.bat` / `weekly_monitor.bat` /
   `scripts/register_auto_predict_task.ps1` / `tests/test_scheduled_bat_args.py` /
   `docs/codex_fix_20260719_scheduler_repair.md` を明示 add。英語 1 行 + 本文数行。
5-3. **`git checkout main` に戻す** (必須 — 全体ルール参照)。`git branch --show-current` が
   main であることを確認。
5-4. `git status --porcelain --untracked-files=no` が空、push なし、DB 不変、
   傾向収集 配下に変更なしを確認。

**受入ゲート 5**: 1 コミット、全テスト green、**checkout = main**。

### 最終報告 (15 行以内)

1. ステージごとの完了/スキップ
2. bat 引数検証テストの red→green 確認結果
3. weekly_monitor 手動実行の順序・exit code / タスク設定 (ExecutionTimeLimit 等) の調査値
4. keiba-auto-predict のトリガー 2 件と NextRunTime / 「マージまで bat は旧内容」の注意
5. oos-backtest-auto の調査結果と推奨 (有効化 or 削除、理由 1 行)
6. コミット sha / checkout=main / push なし / 傾向収集 不変

---

## (Claude Code 側メモ — Codex には渡さない)

- Codex 完了後、**正規 expert-review (D1)** — scripts/ の bat 変更につき必須。重点:
  ①bat 引数検証テストの検知力 (同型バグの再発防止として十分か)、②weekly_monitor の
  順序変更が exit bits の意味を変えていないか、③pytest タイムアウト wrapper の
  errorlevel 伝播
- レビュー PASS 後に PR 作成。**PR #9 (output-defects) と本 PR (scheduler-repair) の
  マージ順は任意** (ファイル重複なし: PR #9 は auto_predict.py/j2/generator、本 PR は
  bat/ps1/tests)
- マージ後の運用: 次の土曜 (7/25) の 11:30 トリガーで日曜分が埋まること、翌週日曜の
  weekly_monitor が完走することを検収
- 0xC000013A の真因が「本セッションの並行作業との衝突」の可能性もある (今朝 10:00 の
  pytest 実行中に私がこの checkout でテスト/レビューを回していた)。順序是正+隔離で
  実害は防げるが、根治には weekly_monitor の専用 clean worktree 化が次の一手
- 残課題: fetch_mining 失敗の可視化 (今回は意図的に WARN のまま) / oos-backtest-auto の
  要否はユーザ判断待ち
