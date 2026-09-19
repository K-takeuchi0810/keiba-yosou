# GUI / UX 監査人 採点

## 判定: HOLD

**理由**: F3 Phase 0-0b は type-B（paired OOS 評価）で GUI 変更はなく、現行操作系への回帰はない。一方、既存 GUI は全長時間ステージでの確実なキャンセルと基本 ARIA がプロ承認水準に未達。
**根拠ファイル**: `gui/app.py:197`, `gui/app.py:275`, `gui/app.py:1000`, `gui/app.py:1936`, `gui/app.py:2413`
**次アクション**: `ingest_all` / `publish_to_icloud` 中にも協調キャンセルを通し、進捗要素へ `role="progressbar"` と `aria-valuenow` を付与する。

**改修タイプ**: type-B（paired OOS の検証・分析。`scripts/f3_phase0_0_eval.py` と結果文書が対象、GUI 差分なし）
**採点対象**: `gui/app.py` の Api / CONTROL_HTML と、今回変更による GUI 影響
**スコープ外**: paired OOS の統計設計・実測値・採用判断そのもの
**GUI 非影響確認**: 最終 HEAD `fa1d491` に対する `git diff af13474^ fa1d491 -- gui/app.py` および `git status --short -- gui/app.py` はともに空。
**JS 検証**: PASS — 最終 HEAD で Python 解釈後の CONTROL_HTML から 22,086 bytes を抽出し `node --check` 成功。onclick 8 種の呼出先は全て関数定義あり（missing=[]）。

## 総合: 3.6 / 5（項目平均）

| 項目 | 今回 | 前回 | 差分 |
|---|---:|---:|---:|
| ボタン発見性 / フロー明示性 | 4 | 4 | 0 |
| エラー人間化 / 復旧支援 | 4 | 4 | 0 |
| 進捗表示 / ETA / キャンセル | 3 | 3 | 0 |
| 二重実行防止 / ボタン状態管理 | 4 | 4 | 0 |
| レイアウト / タップ領域 / アクセシビリティ | 3 | 3 | 0 |
| **総合（項目平均）** | **3.6** | **3.6** | **0.0** |

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — 主要 CTA に「取得 → 予想 → 公開」、個別操作に Ⅰ→Ⅱ→Ⅲ→Ⅳ と依存順序が明示され、各主要 action に具体的な `title` がある（`gui/app.py:1943-1964`）。ただし必須観点の `<details id="helpBox">` はなく、詳細設定と出力詳細だけで初回フローをまとめたヘルプはない（`gui/app.py:1967-1979`）。
- **エラー人間化 / 復旧支援: 4/5** — `_safe` は型名・メッセージ・hint・trace を分離し（`gui/app.py:215-242`）、JS はサマリ + hint と JSON 詳細を折り畳みへ表示する（`gui/app.py:2470-2475`）。公開拒否も再生成手順まで日本語で案内する（`gui/app.py:1103-1124`）。一方 `_error_hint` は主要 6 系統に限られ（`gui/app.py:197-212`）、進捗取得・dashboard の Promise 失敗は raw `e` 表示（`gui/app.py:2378-2383`, `gui/app.py:2440-2445`）。
- **進捗表示 / ETA / キャンセル: 3/5** — progress bar、百分率、ETA、実行中のみ見える中止ボタン、1 秒ポーリングを備える（`gui/app.py:1936-1940`, `gui/app.py:2413-2469`）。取得 callback と予想 subprocess は中止を検査する（`gui/app.py:294-315`, `gui/app.py:1085-1092`）。ただし `ingest_all` と `publish_to_icloud` 内部には `_check_cancel` が渡らず、押下直後に止まらない区間がある（`gui/app.py:1000-1009`, `gui/app.py:1100-1127`）。予想生成中は経過秒のみで ETA がない。
- **二重実行防止 / ボタン状態管理: 4/5** — JS は status に応じ全 `data-action` を disable（`gui/app.py:2108-2111`, `gui/app.py:2414-2438`）。`inFlight` は未採用だが、Python 側 `_begin_run` が lock 内で running を原子的に check-and-set し、TOCTOU で二操作が滑り込んでも片方を BusyError にするため JV-Link COM の二重 Open は防ぐ（`gui/app.py:275-286`）。一方、通信失敗時に `refreshStatus()` が false を返しボタンを再有効化し得る余地は残る（`gui/app.py:2440-2445`, `gui/app.py:2489-2493`）。
- **レイアウト / タップ領域 / アクセシビリティ: 3/5** — sidebar と dashboard は `overflow-y:auto`（`gui/app.py:1249-1258`, `gui/app.py:1322-1326`）、focus-visible がある（`gui/app.py:1810-1814`）。主要アクションには title がある。反面、tab に title / `aria-selected` がなく、日付 label は input と関連付けられず、progress bar に ARIA role/value がない（`gui/app.py:1908-1914`, `gui/app.py:1936-1940`, `gui/app.py:1984-1987`）。通常ボタンには 44px 相当の `min-height` がない（`gui/app.py:1777-1793`）。`display:none` は中止・プレビュー等の状態切替用途で、恒久的死にゾーンとは認めない。

## 停止条件チェック

- [x] JS パース成功、onclick 呼出先欠落なし
- [x] F3 Phase 0-0b による `gui/app.py` 差分なし
- [x] Ⅰ→Ⅱ→Ⅲ→Ⅳ の操作順序と主要 action title あり
- [x] Python 側原子ガードにより JV-Link COM 二重 Open 防止
- [ ] 専門領域のプロ承認条件: 全長時間ステージの確実なキャンセルと基本 ARIA が未達
- P25 固有の backtest / market_snapshot / profitability ゲート: N/A（type-B の GUI 影響監査）

## 反証の試み

- **仮説**: paired OOS 評価追加が共通 import や GUI テンプレを間接変更し、ボタンを壊した可能性。
- **確認**: 対象コミットの `gui/app.py` 差分と現在の同ファイル status は空。さらに Python import 後の実 JS を `node --check` し、onclick target 8 種を静的照合して missing=[]。
- **結論**: 今回改修による GUI 回帰は不成立。留保は前回からの既存課題で、Phase 0-0b の後退ではない。

## 主な改善提案

1. **キャンセルを ingest / publish の内部まで伝播** — `ingest_all(..., cancel_check=self._check_cancel)` 相当と、公開コピー前後の `_check_cancel()` を追加し、「中止」表示と実際の停止を一致させる。
2. **進捗とフォームの ARIA を補完** — `#progressWrap` に `role="progressbar"`、JS で `aria-valuenow/min/max` 更新、日付 label に `for`、タブに `aria-selected` を付ける。
3. **操作ヘルプを追加** — sidebar に `<details id="helpBox">` を置き、初回フロー、検証モード禁止事項、エラー時の復旧順を短く記載する。

## 前回からの差分

- ボタン発見性: 4 → 4（GUI 差分なし。番号順と title は維持）
- エラー人間化: 4 → 4（GUI 差分なし。hint 網羅性と raw Promise error の留保も不変）
- 進捗 / ETA / キャンセル: 3 → 3（GUI 差分なし。ingest / publish の中止保証が残る）
- 二重実行防止: 4 → 4（GUI 差分なし。Python 原子ガードを維持）
- レイアウト / アクセシビリティ: 3 → 3（GUI 差分なし。overflow / focus は維持、ARIA 課題も不変）
- 前回判定: HOLD。今回も HOLD。総合 3.6 → 3.6（差分 0.0）。
