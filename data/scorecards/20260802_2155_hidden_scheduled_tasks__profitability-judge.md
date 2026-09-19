# 収益性 / 投資判断専門家 採点 — hidden scheduled tasks

## 判定: PASS

**改修タイプ**: type-C（データ取得・運用）。予測確率、買い目フィルタ、EV、Kelly、売買戦略の変更はない。P25 固有の ROI / CI / paired baseline / bonus candidate ゲートは **N/A（対象外）**。

**理由**: 非表示 runner は対象スクリプト、引数、作業ディレクトリ、完了待ち、子終了コードを維持しており、8タスクの Action 以外は変更前XMLと 8/8 件で完全一致した。データ取得欠落リスクを増やす停止条件は確認されない。

**根拠ファイル**: `scripts/fetch_fresh_odds.bat:1-6`、`C:\Users\kizun\AppData\Local\ScheduledTaskRunner\run-scheduled-task-hidden.vbs:3-35`、`C:\Users\kizun\Documents\Codex\2026-08-02\new-chat\outputs\scheduled-task-backup_20260802_214740\manifest.json:1-115`、同ディレクトリの変更前8タスクXML。

**次アクション**: 次回定刻後に `keiba-fresh-odds` と `keiba-fresh-odds-healthcheck` の `LastTaskResult` および各ログ更新を確認する。これは継続監視であり、採用停止条件ではない。

## 総合: 4.4 / 5（参考スコア）

## 項目別

- **回収機会・データ取得継続性: 4/5** — runner は `WshShell.Run(command, 0, True)` で非表示実行し、完了まで待って子終了コードを返す（runner `:34-35`）。CMD fixture は空白入り引数を保持して終了コード7、PS1 fixtureは9、不正modeは87を返した。8タスクの非Action XMLは変更前後で 8/8 件完全一致。全8件の次回定刻実走は未到来のため5点にはしない。
- **EV入力・オッズ鮮度への影響: 4/5** — `fetch_fresh_odds.bat` の実行行は変更されず（`:6`）、差分はコメントのASCII化とCRLF化だけ（`:1-6`）。取得頻度、対象Python、出力ログ、タスクのトリガー・`PT72H`制限・`IgnoreNew`は維持され、オッズ欠落を増やす挙動差は確認されない。
- **Kelly / 資金管理: 5/5** — 対象外変更。資金配分・賭け金上限・購入処理には差分がなく、本改修による破産確率の増加はない（`git diff --stat` は `scripts/fetch_fresh_odds.bat` のコメント2行のみ）。
- **買い目フィルタ・表示集合の同一性: 5/5** — 対象外変更。予測・フィルタ・候補生成コードは無変更であり、タスクは変更前と同じ8ターゲットと引数を起動する（manifest `:3-114` と現行Actionの実測比較）。
- **鮮度監視・復旧可能性: 4/5** — healthcheck はスケジューラ結果、coverage、DB fresh rowsをJSON/ログへ記録する既存経路を保持し、runnerも終了コードをTask Schedulerへ返す。一方、runner 1ファイルが8タスク共通の依存点になったため、削除時の影響範囲は広い。変更前XML、manifest、runnerコピーは復旧用に保存済みだが、次回定刻ログ確認を留保とする。

## 停止条件チェック

- P25再現性メタ / paired baseline / market_snapshot / payout欠損: **N/A（type-Cで収益性・採用主張なし）**
- [x] Action以外のタスク設定が変更前と同値（8/8件、XMLをActionノード除外で完全比較）
- [x] 取得ターゲットと引数が変更前と同値（8/8件、manifestと現行Actionを比較）
- [x] 完了待ち・終了コード伝播あり（CMD=7、PS1=9をこのセッションで再実測）
- [x] `fetch_fresh_odds.bat` の処理本体・ログ経路は不変、全行CRLF・BOMなしを実測
- [x] 専門領域の停止条件に抵触なし

## 反証の試み

- 主張「非表示化で子処理の引数または失敗コードが失われ、データ欠落が見逃される」に対し、空白入り引数を含むCMD fixtureとPS1 fixtureをrunner経由で実行した。CMDは期待どおり終了コード7、PS1は9を呼出元へ返したため反証シナリオは不成立。
- 主張「非表示化の際にトリガー・タイムアウト・多重起動設定まで変わった」に対し、変更前XMLと現行ExportをActionノード除外で比較し、8/8件で完全一致したため不成立。
- 未検証: 変更後の本番実走は確認時点で `MAIBuilder Live JRA Data`（2026-08-02 22:05、結果0）のみ。他7件は静的同値性と共通runnerの合成試験まで。

## 主な改善提案

1. **共通runnerの存在監視** — `C:\Users\kizun\AppData\Local\ScheduledTaskRunner\run-scheduled-task-hidden.vbs` の存在とSHA-256をhealthcheck対象へ追加し、8タスク共通依存点の消失を実行前に検知する。

## 前回からの差分

- 同一テーマの前回収益性採点はなし。直近のF3収益性スコアは戦略/OOS評価であり、本type-C運用変更とは比較しない。

## 運用段階

本改修はデータ取得基盤の運用変更であり、戦略を「観察用」「紙運用」「実弾候補」の次段階へ昇格させる根拠ではない。既存戦略の運用段階は不変。
