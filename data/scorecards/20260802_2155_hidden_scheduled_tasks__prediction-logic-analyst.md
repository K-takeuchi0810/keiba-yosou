# 予想ロジック分析官 採点

## 判定: PASS

**改修タイプ**: type-C（データ取得・運用起動経路）。`predictor/`、重み、calibrator、backtest、予測入力の計算は変更されていないため、type-A の P25 固有ゲート（C1/C2/C3/C5、market_snapshot、bonus subset、calibrator refit）は **N/A（対象外）**。

**理由**: fresh odds バッチはコメントの ASCII 化と CRLF 化だけで、32-bit Python による取得コマンドは不変。8タスクは起動 Action のみ非表示 runner に置換され、トリガー・実行主体・多重起動・タイムアウト等は変更前 XML と同値であり、予測ロジックおよび train-serve 入力契約に変更はない。

**根拠ファイル**: `scripts/fetch_fresh_odds.bat:1`、`scripts/fetch_fresh_odds.bat:6`、`C:/Users/kizun/AppData/Local/ScheduledTaskRunner/run-scheduled-task-hidden.vbs:22`、`C:/Users/kizun/AppData/Local/ScheduledTaskRunner/run-scheduled-task-hidden.vbs:34`、`C:/Users/kizun/Documents/Codex/2026-08-02/new-chat/outputs/scheduled-task-backup_20260802_214740/manifest.json`

**次アクション**: 次回の自然スケジュール実行後、各タスクの終了コードと既存ログ更新を確認する。影響回避のため本レビューでは実運用タスクを手動起動していない。

## 総合: 4.8 / 5（参考スコア）

## 項目別

- **シグナル網羅性と市場残差性: 5/5** — 予測シグナルの追加・削除・変更なし。Git 差分は `scripts/fetch_fresh_odds.bat:2-3` のコメントのみ。
- **重み妥当性 / 過適合リスク: 5/5** — `predictor/weights.json` および重み消費経路に差分なし。P25 ablation は N/A。
- **信頼度判定 / 確率推定の構造: 5/5** — calibrator、確率変換、race 内正規化に差分なし。確率分布を変えるコードは対象変更に含まれない。
- **デッドコード / 設計の整合性: 4.5/5** — runner は CMD/PowerShell を明示分岐し、対象存在確認、引数引用、同期実行、終了コード伝播を実装（runner:18-35）。汎用テストで CMD=7、PowerShell=9 の期待終了コードを実測した。
- **本番運用との乖離リスク（train-serve skew）: 4.5/5** — 変更前バックアップ XML と現行 XMLを比較し、8/8 タスクで Action 以外が完全一致。Action も元の対象ファイルと引数を保持する。`fetch_fresh_odds.bat:6` の実取得コマンドは不変で、入力鮮度・取得内容を変える差分はない。自然実行の観測前である点だけを留保する。

## 停止条件チェック

- P25 再現性メタ / paired baseline / market_snapshot / payout 欠損: **N/A（type-A ではない）**
- 専門領域別 P25 停止条件: **N/A（予測ロジック変更・採用主張なし）**
- type-C 汎用停止条件: **不抵触**。8/8 タスクで Action 以外の設定同値、runner の引数・終了コード伝播を確認。

## 反証の試み

- 主張「画面を非表示にしても処理契約は変わらない」に対し、(1) 引数に空白がある CMD、(2) PowerShell、(3) 非ゼロ終了コード、(4) タスク設定の意図しない変更を反証候補とした。汎用 runner テストは CMD 7 / PowerShell 9 をそのまま返し、8タスクの非 Action XML は全件同値だったため、反証は不成立。

## 主な改善提案

1. **自然実行の事後確認** — 次回予定時刻後に Task Scheduler の結果と既存ログの更新時刻を確認し、実ターゲットでも終了コード伝播と成果物更新を閉じる。運用タスクの手動起動はデータ影響回避のため不要。

## 前回からの差分

- 前回は F3 予測ロジック検証（4.0/5）で対象が異なるため、数値比較は N/A。今回は予測ロジック不変の運用変更として独立採点。
