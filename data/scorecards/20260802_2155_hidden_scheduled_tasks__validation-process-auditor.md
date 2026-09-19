# 検証プロセス監査人 採点

## 判定: PASS

**理由**: 変更前 XML 8 件、現在の 8 Action、対象ファイル、合成 CMD/PS1、変更後の実タスク正常終了を一次確認でき、当初の `PT8M` は撤回され fresh-odds の非 Action XML も変更前と一致したため、採用を止める欠陥はない。
**根拠ファイル**: `scripts/fetch_fresh_odds.bat:1-6`、`C:/Users/kizun/AppData/Local/ScheduledTaskRunner/run-scheduled-task-hidden.vbs:1-43`、`C:/Users/kizun/Documents/Codex/2026-08-02/new-chat/outputs/scheduled-task-backup_20260802_214740/manifest.json:1`、同ディレクトリの 8 XML
**次アクション**: 次回の各タスク実行後に `LastTaskResult` と業務ログを突合する。異常があれば、保存済み XML を同名タスクへ再登録してロールバックする。

### 採点対象と改修タイプ

- 対象: `scripts/fetch_fresh_odds.bat` の ASCII コメント化・CRLF 化、外部 VBS ラッパー、8 個のユーザータスクの Action、変更前バックアップ。当初追加された `ExecutionTimeLimit=PT8M` は最終状態では撤回済み。
- 改修タイプ: 予測・backtest 採用判断ではない運用基盤改修（type-B/C 相当）。P25 固有の factorial、market snapshot、収益性ゲート、他 6 agent 統合は N/A（対象外）。

## 総合: 4.0 / 5 (参考スコア)

## 項目別

- **変更スコープと設定等価性: 4/5** — 現在の 8 Action はすべて `wscript.exe //B //NoLogo <runner> <mode> <target> [args]` で manifest の target/mode/args と完全一致した。最終状態の非 Action XML は 8 件とも変更前と一致した。fresh-odds の XML には `ExecutionTimeLimit` 要素がなく、CIM 表示は既定値 `PT72H` であり、変更前 XML と同じ（`PT0S` が明示登録された状態ではない）。トリガー（09:00 開始、10 分間隔、10 時間）、`IgnoreNew`、principal、Unified Scheduling Engine は保持された。実測 2026-08-02 22 時台。
- **バックアップとロールバック可能性: 4/5** — 変更前 XML 8 件をすべて XML として再パースでき、各 URI が対象タスク名に一致した。`manifest.json` には元の Execute/Arguments/Target/TaskArgs が 8 件分ある（例: `manifest.json:3-12`, `31-40`, `45-54`, `73-82`）。XML の再登録で Action を含む旧定義へ戻せる。ただし復元コマンドの手順書・復元ドライラン・XML 個別ハッシュ一覧は同梱されていない。
- **ラッパーの合成検証: 4/5** — 配置先 VBS と work コピーの SHA-256 はともに `A7420BAB7F23797AAC3F0707C36AAAC9891E10C5536AB65779C7C6D8AA5A1F5D`。CMD fixture は `--no-pause` と空白入り引数を保持して終了コード 7、PS1 fixture は終了コード 9、不正 mode は 87 を呼出元へ返した。`WINDOW_HIDDEN=0`、同期待機、子終了コード返却は `run-scheduled-task-hidden.vbs:3-4,17-30` に実装されている。
- **成果物の再現性・耐久性: 4/5** — 現用 VBS と work コピーのハッシュ一致、変更前 XML 8 件、manifest により現時点の再構築・復元材料は揃う。軽微な留保として、現用 VBS はリポジトリ外の `%LOCALAPPDATA%` にあり、版管理された導入・検証・復元スクリプトはない。また旧定義の `/d /c call` を VBS の直接 BAT 起動へ統一しており、現在は HKCU/HKLM の CMD AutoRun が空なので実害を反証できたものの、元の `/d` 契約を明示的には保存していない（元定義: `manifest.json:59-62,73-76` ほか）。
- **実環境での事後検証: 4/5** — 変更後 21:55 に `MAIBuilder Live JRA Data` が新 Action で実行され `LastTaskResult=0` を記録した。他 7 件の LastRunTime/LastTaskResult はバックアップ時点と同一で、変更後の本番実行証拠ではない。この不足は共通コードパスの合成 CMD/PS1 テストで補完したが、次回定期実行後のログ突合は継続観察事項。

## 停止条件チェック

- [x] 変更前の 8 タスク XML と manifest が存在し、全 XML を再パース可能
- [x] 現在の 8 Action の mode/target/args が manifest と完全一致
- [x] 非 Action 設定は 8 件とも変更前 XML と一致（fresh-odds の `PT8M` は撤回済み）
- [x] BAT は BOM なし、CRLF 6、bare LF 0、日本語 REM なし（`scripts/fetch_fresh_odds.bat:1-6`）
- [x] CMD/PS1 の引数および終了コード伝播を合成テストで確認
- [ ] 全 8 タスクの変更後実行証拠（変更後の実タスク正常終了は現時点で 1/8。合成 CMD/PS1 でコードパスを補完）
- [ ] P25 固有 Required Evidence — N/A（対象外）

## 反証の試み

- 主張「VBS 化しても引数と終了コードを保持する」に対し、空白入り引数を要求して終了 7 を返す CMD fixture と、終了 9 の PS1 fixture を配置済み本体で実行した。結果は 7 / 9 で成立。不正 mode も 87 で fail-closed。
- 主張「タスクの副次設定に影響しない」に対し、バックアップ XML と最終状態の `Export-ScheduledTask` を Action 除外で比較した。8 件とも一致。fresh-odds の `PT8M` 追加は撤回され、変更前・現在とも `ExecutionTimeLimit` 要素なし。
- 主張「8 件すべて実運用で問題ない」に対し、バックアップ時点と現在の LastRunTime を比較した。変更後に走ったのは MAIBuilder 1 件のみで、残り 7 件は未成立（未検証）。

## 主な改善提案

1. **実行後監査を完了する** — 次回実行後に各タスクの `LastTaskResult` と対象ログを保存する。これは PASS 後の観察事項であり、合成テストと変更後 1 件の正常終了で本改修のコードパスは確認済み。
2. **runner を再現可能な成果物にする** — VBS、8 タスクの期待 Action、バックアップ/復元/検証コマンド、SHA-256 を版管理された運用スクリプトまたは永続 outputs にまとめる。
3. **CMD 契約を明示する** — `cmd` mode は `%ComSpec% /d /s /c call ...` 等で旧タスクの `/d`（AutoRun 無効）を維持し、直接 BAT 起動への暗黙依存をなくす。

## 前回からの差分

- 同一改修の前回 scorecard なし。
