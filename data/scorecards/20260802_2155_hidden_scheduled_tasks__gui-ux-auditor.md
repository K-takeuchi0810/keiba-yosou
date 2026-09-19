# GUI / UX 監査人 採点

## 判定: HOLD

**理由**: 今回は GUI/HTML を変更しない type-B/C 境界の運用改修であり、GUI 回帰はなく前回評価を維持する。定期実行の画面フラッシュは抑止できる一方、非表示化された失敗をユーザーへ能動通知する経路は追加されていない。
**根拠ファイル**: `scripts/fetch_fresh_odds.bat:1-6`、`C:/Users/kizun/AppData/Local/ScheduledTaskRunner/run-scheduled-task-hidden.vbs:3-47`、`C:/Users/kizun/Documents/Codex/2026-08-02/new-chat/outputs/scheduled-task-backup_20260802_214740/manifest.json:1-115`
**次アクション**: 今回改修の採用を妨げない継続改善として、非ゼロ終了時だけタスク名・対象・終了コード・時刻を集約ログまたは Windows 通知へ記録し、画面を常時出さずに失敗を発見できるようにする。

**改修タイプ**: type-B/C 境界（Windows Task Scheduler の実行方式と batch 互換性の運用改修。type-D の GUI/HTML 差分なし）
**採点対象**: `scripts/fetch_fresh_odds.bat` の ASCII コメント / CRLF 化、共通 VBS runner、8タスクの Action 非表示化がデスクトップ利用体験へ与える影響
**スコープ外**: 予測・収益性・P25 採用判断、各バッチ内部の業務ロジック。既存 `gui/app.py` / `web/templates/` の絶対評価は前回値を維持する。
**GUI 非影響確認**: `git status --short` / `git diff --stat` で追跡対象の差分は `scripts/fetch_fresh_odds.bat` のみで、`gui/app.py`、`web/templates/`、`web/generator.py` に差分なし。したがって CONTROL_HTML の JS パース再検証と P25 固有 GUI ゲートは N/A。

## 総合: 3.6 / 5（参考スコア、前回維持）

今回の非表示実行 UX 単体は **4/5**。画面フラッシュ除去は達成しているが、失敗の能動通知がないため一流の無人運用水準である 5 には届かない。GUI 本体の5軸は差分がないため、直近監査 `20260720_1905_f3_morning_anchor__gui-ux-auditor.md` の 3.6 / HOLD を維持する。

## 項目別

- **タスクフロー / 発見性: 4/5** — 8タスクの Action は `wscript.exe //B //NoLogo` と共通 runner に統一され、対象スクリプトと既存引数は変更前 manifest の `Target` / `TaskArgs` と一致する（`manifest.json:3-14,17-28,31-42,45-56,59-70,73-85,88-99,102-113`）。定期処理が作業中の画面へ割り込まないため、ユーザーの主タスクを中断しない。
- **エラーの人間化 / 回復支援: 3/5** — runner は引数不足・対象不在・不正 mode を終了コード 87 / 2 で返し、子プロセスの終了コードも Task Scheduler へ返す（runner `:9-19,22-35`）。ただし `//B` と `WINDOW_HIDDEN=0` により画面上のエラーは全て消え、runner 自身には時刻・対象・説明を残すログや通知がない。監査時点の8タスク中5件は直近結果が非ゼロだったが、うち7件は変更後未実行であり今回改修起因とは判断しない。Nielsen 9（エラーの認識・診断・回復支援）の観点では、Task Scheduler の数値コードだけでは発見性が不足する。
- **システム状態の可視性: 3/5** — `WshShell.Run(command, 0, True)` によって処理完了まで runner が待機し、終了状態は Scheduler に残る（runner `:34-35`）。一方、通常利用中の進捗・成功・失敗は意図的に非表示であり、バックグラウンド処理として妥当でも、異常時だけの控えめな可視化は未実装。
- **状態整合性 / 誤読防止: 4/5** — 変更前の8 XMLと現在の `Export-ScheduledTask` を Action ノード除外で比較し、8/8件で XML が完全一致した。現在の Action は8/8件が同じ runner を参照し、CMD / PS1 fixture で終了コード 7 / 9、不正 mode 87、対象不在 2 を再実測した。`fetch_fresh_odds.bat` は 290 bytes、CRLF 6、単独 LF 0、BOMなしで、問題を起こした日本語コメントは ASCII に置換済み（batch `:1-6`）。
- **レイアウト / 入力効率 / アクセシビリティ: 4/5** — GUIレイアウト自体は変更なし。定期的なコンソールの瞬間表示と残留ウィンドウを除去する設計は、フォーカス奪取・視覚的ちらつき・誤クリックの機会を減らす。反面、支援技術を含む全利用者に対して異常状態も不可視になるため、通知または集約ログへの導線が必要。

## 停止条件チェック

- [x] GUI / HTML 差分なし（前回スコア維持）
- [x] 8タスクの Action 以外は変更前 XML と 8/8 件完全一致
- [x] 非表示実行、完了待ち、終了コード伝播を runner と fixture で確認
- [x] `fetch_fresh_odds.bat` の ASCII コメント / CRLF を実測
- [x] 今回差分に適用される専門領域の Hard Fail なし
- P25 固有の paired baseline / market_snapshot / payout / CONTROL_HTML 表示ゲート: N/A（予測採用・GUI表示を変更しない運用改修）

## 反証の試み

- **仮説**: 画面を隠すために Task Scheduler のトリガー、実行制限、重複実行方針なども変わり、既存システムへ影響した可能性。
- **確認**: 変更前バックアップ8 XMLと現在の8タスクを Action ノード除外で比較し、8/8件で完全一致。runner の CMD fixture は空白入り引数を保持して終了コード7、PS1 fixtureは9を返した。変更後に実行された `MAIBuilder Live JRA Data` は 22:05 に結果0で完了した。
- **結論**: 設定ドリフトと共通実行経路の引数・終了コード破損は不成立。ただし残り7タスクの変更後定刻実走と、画面が一度も描画されないことの視覚観察は未検証。後者は `wscript.exe //B` と `WINDOW_HIDDEN=0` のコード確認で補完した。

## 主な改善提案

1. **異常時だけ発見可能にする** — runner の `exitCode <> 0` 時に、対象パス・終了コード・時刻をユーザー領域の集約ログへ追記する。常時ウィンドウは出さず、Nielsen 9 の診断・回復手掛かりを残す（runner `:34-35`）。
2. **復旧導線を残す** — バックアップ `README_restore.txt` と8 XMLの場所を運用メモから参照可能にし、runner 欠損時に元 Action へ戻せるようにする。

## 前回からの差分

- タスクフロー / 発見性: 4 → 4（GUI差分なし。定期実行の割込みは減少）
- エラー人間化 / 復旧支援: 4 → 4（GUI本体は不変。今回の運用経路単体は通知不足により3）
- 進捗表示 / ETA / キャンセル: 3 → 3（GUI差分なし）
- 二重実行防止 / ボタン状態管理: 4 → 4（Action以外の task settings は同値）
- レイアウト / アクセシビリティ: 3 → 3（GUI差分なし。コンソールちらつきのみ改善）
- 前回判定: HOLD。今回も HOLD。総合 3.6 → 3.6（差分 0.0）。今回の運用改修自体に採用を止める GUI/UX 欠陥はない。
