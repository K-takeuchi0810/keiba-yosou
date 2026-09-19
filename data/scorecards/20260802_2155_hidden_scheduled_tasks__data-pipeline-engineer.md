# データパイプライン技術者 採点 — hidden scheduled tasks

## 判定: PASS

**理由**: `type-C（取得運用／スケジューラ）` の限定改修として、8タスクの対象・引数・作業ディレクトリ・多重実行ポリシー・実効タイムアウトが維持され、runner は子プロセスを待って終了コードを返す。8分制限案は撤回され、強制終了による stale lock の新規回帰も残っていない。

**根拠ファイル**: `scripts/fetch_fresh_odds.bat:1-6`、`C:\Users\kizun\AppData\Local\ScheduledTaskRunner\run-scheduled-task-hidden.vbs:6-42`、`C:\Users\kizun\Documents\Codex\2026-08-02\new-chat\outputs\scheduled-task-backup_20260802_214740\manifest.json`、同ディレクトリの8タスクXML、2026-08-02 セッション内の `Export-ScheduledTask` / `Get-ScheduledTaskInfo` 実測

**次アクション**: 次回の各タスク定刻実行後に `LastTaskResult` と既存ログを確認する。runner はリポジトリ外配置なので、再構築手順またはハッシュ付きmanifestを運用資料に残す。

## 対象・スコープ

- 対象: `scripts/fetch_fresh_odds.bat` のASCIIコメント化・CRLF化、外部VBS runner、8個のユーザータスクの非表示起動設定。
- スコープ外: JV-Link取得ロジック、raw/SQLite ingest、予測ロジック、既存データの品質改善。これらは今回変更されていないため、変更差分としては採点しない。
- 改修タイプ: **type-C（取得運用）**。P25収益性・paired backtestゲートは N/A。

## 総合: 4.0 / 5（参考スコア）

## 項目別

- **JV-Linkエラー回復／終了コード伝播: 4/5** — runner は `WScript.Arguments` からmode・target・残余引数を組み立て、`WshShell.Run(..., 0, True)` で非表示かつ完了待ちし、その戻り値を `WScript.Quit` へ渡す（runner `:6-30`）。読み取り専用の反証試験で子PowerShellの `exit 37` がrunner終了コード37として返った。`MAIBuilder Live JRA Data` はrunner登録後の2026-08-02 21:55実行が結果0で完了した。
- **ingest経路の同値性: 4/5** — 8/8タスクで変更前manifestのtargetが現Actionのrunner第2引数に一致した。引数あり2タスクも `--no-pause`、`--skip-if-no-race-today` を保持し、受け側は `%~1` で解釈する（`C:\Users\kizun\dev\傾向収集\sync_jvlink_then_collect.bat:17-31`、`run_weekly_validation_summary.bat:11`）。取得・ingestのPython引数自体は変更されていない。
- **データ鮮度／スケジュール維持: 4/5** — 変更前後XML比較で8/8のTriggers、Principals、Conditionsが一致。`keiba-fresh-odds` は毎回の対象・10分周期・`MultipleInstancesPolicy=IgnoreNew`を維持し、実効 `ExecutionTimeLimit=PT72H` も変更前CIM既定値と一致した。既存coverageを再集計し、2026-08-02は31起動・eligible 72・fetched/ok 72（100%）、直近14日合計は410/416（98.6%）を確認したが、これは変更前の稼働証拠であり非表示化後全タスクの実走証明ではない。
- **作業ディレクトリ／復旧性: 4/5** — WorkingDirectory指定があった2/8タスクは変更前後で同値、空だった6/8も空のまま。各バッチは `%~dp0` または絶対パスで自ら作業場所を確定する（`scripts/fetch_fresh_odds.bat:4`、`scripts/auto_predict_daily.bat:3`、`weekly_monitor.bat:3`）。8件の変更前XMLとmanifestが `scheduled-task-backup_20260802_214740` にあり、手動ロールバック材料は揃う。
- **fresh odds取得運用／可観測性: 4/5** — `fetch_fresh_odds.bat` は290 bytes、BOMなし、LF 6件すべてCRLFで、日本語cmd誤解釈の原因を除去しつつPythonコマンド・リダイレクトを不変にした（`:1-6`）。`//B //NoLogo` とwindow style 0により画面表示を抑止する。一方、非表示化は既存のJV-Linkハング自体を直さず、現存する14:00由来lockも変更していないため、異常検知は既存healthcheck／ログに依存する。

## 停止条件チェック

- [x] スケジューラ登録あり: 8/8がEnabled・Ready、`keiba-fresh-odds` も登録済み。
- [x] 対象・引数・WorkingDirectory・Triggers・Principals・Conditions・MultipleInstancesの変更前後同値を確認。
- [x] 子終了コードの伝播を実測（37→37）。runnerの異常modeも87を返した。
- [x] 強制終了による新規のlock/partial raw経路なし: `PT8M` は撤回され、変更前実効値 `PT72H` を維持。
- [x] coverage JSONLに直近開催日の起動・取得・ingest結果・`failed_reason`・`lock_skipped`が存在。
- [ ] git_sha / rule_version / paired baseline / market_snapshot / payout欠損: **N/A**（予測採用判断ではなくスケジューラ起動方法だけの変更）。

## 反証の試み

- 主張「非表示化しても終了コードが失われない」に対し、runner経由で子プロセスを終了37にして確認 → **反証不成立**（runnerも37）。
- 主張「タイムアウト変更で取得挙動を変えない」に対し、当初のPT8Mでは `scripts/fetch_fresh_odds.py:40,49-52,65-68` の30分stale lockと不整合になり、8分強制終了後の後続runがskipするシナリオが成立した → **当初案は反証成立**。最終設定はPT72Hに戻され、回帰を除去済み。
- 主張「全タスクの実稼働同値」に対し、変更後に実走済みなのは確認時点で `MAIBuilder Live JRA Data` のみ → 他7件は静的同値性まで確認、次回定刻の実走結果は未確認。ただしrunner構築・引数・cwd・終了コードに停止条件となる欠陥は見つからない。

## 主な改善提案

1. **runnerの復旧可能性を明文化** — リポジトリ外の `C:\Users\kizun\AppData\Local\ScheduledTaskRunner\run-scheduled-task-hidden.vbs` を再生成できるスクリプトまたはSHA-256付きmanifestを管理し、PC移行・誤削除時の8タスク一括復旧を可能にする。
2. **変更後スモーク確認を自動化** — 各タスクの次回実行後にAction、LastTaskResult、ログ更新時刻を照合するread-onlyチェックを追加する。特にhealthcheckの非0（0/1/2/3/4の意味あり）を単純なrunner障害と誤認しない。
3. **既存ハングの別途対策** — 今回の非表示化とは分離し、JV-Link COM呼出しを安全に隔離した上で、stale lock回収とpartial/0-byte raw清掃を含むタイムアウト設計を行う。Task Schedulerの短い強制終了だけを再導入しない。

## 前回からの差分

- 直近の同担当scorecardは別改修（F3 Phase 0.0）で対象が異なるため、数値比較はしない。
- 今回はスケジューラ起動方法の限定レビューとして **PASS / 4.0**。当初PT8M案はlock回収時間との不整合でPASS不可だったが、PT72Hへの復元を実測して判定を更新した。
