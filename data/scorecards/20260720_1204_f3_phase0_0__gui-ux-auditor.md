# GUI / UX 監査人 採点

## 判定: HOLD

**理由**: F3 Phase 0.0 は type-B（検証・診断）で GUI 変更はなく回帰なし。一方、現行 GUI は操作可能だが、全ステージで確実に効くキャンセルとアクセシビリティがプロ承認水準に未達。
**根拠ファイル**: `gui/app.py:197`, `gui/app.py:275`, `gui/app.py:1188`, `gui/app.py:1936`, `gui/app.py:2413`
**次アクション**: `ingest_all` / `publish_to_icloud` 中にも協調キャンセルを通し、進捗要素へ `role="progressbar"` と `aria-valuenow` を付与する。

**改修タイプ**: type-B（固定 split / seed によるリーク診断。`gui/app.py` は変更なし）
**採点対象**: `gui/app.py` の Api / CONTROL_HTML と、今回変更による GUI 影響
**スコープ外**: F3 の統計設計・指標値・本番不変性そのもの
**JS 検証**: PASS — Python 解釈後の CONTROL_HTML から 22,086 bytes を抽出し `node --check` 成功。`onclick` 8 種の呼出先は全て関数定義あり（missing=[]）。

## 総合: 3.6 / 5（項目平均）

| 項目 | 今回 | 前回 | 差分 |
|---|---:|---:|---:|
| ボタン発見性 / フロー明示性 | 4 | 4 | 0 |
| エラー人間化 / 復旧支援 | 4 | 5 | -1 |
| 進捗表示 / ETA / キャンセル | 3 | 3 | 0 |
| 二重実行防止 / ボタン状態管理 | 4 | 4 | 0 |
| レイアウト / タップ領域 / アクセシビリティ | 3 | 1 | +2 |
| **総合（項目平均）** | **3.6** | **3.6（公表値）** | **0.0** |

注: 前回 `20260512_2200_p06_pywebview_navfix__gui-ux-auditor.md` の公表総合は 3.6 だが、記載された項目点 4/5/3/4/1 の算術平均は 3.4。比較表は履歴互換のため公表総合 3.6 を使用した。今回値は 18÷5=3.6。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — 主要 CTA に「取得 → 予想 → 公開」、個別操作に Ⅰ→Ⅱ→Ⅲ→Ⅳ と依存順序が明示され、各アクションに具体的な `title` がある（`gui/app.py:1943-1964`）。ただし必須観点の `<details id="helpBox">` は存在せず、初回利用者向けのまとまった操作説明はない。
- **エラー人間化 / 復旧支援: 4/5** — `_safe` は型名・メッセージ・hint・trace を分離し（`gui/app.py:215-242`）、JS は 1 行サマリ + hint の後に詳細 JSON を折り畳み表示する（`gui/app.py:2470-2475`）。公開拒否も再生成手順まで日本語で案内する（`gui/app.py:1103-1124`）。一方 `_error_hint` は主要 6 系統のみ（`gui/app.py:197-212`）で、進捗取得・dashboard の Promise 失敗は raw `e` 表示（`gui/app.py:2378-2383`, `2440-2445`）。世界水準の 5 には届かないため、前回 5 から絶対基準で是正。
- **進捗表示 / ETA / キャンセル: 3/5** — progress bar、百分率、ETA、実行中のみ見える中止ボタン、1 秒ポーリングを備える（`gui/app.py:1936-1940`, `2413-2469`）。取得 callback と予想 subprocess は 0.5 秒周期で中止を検査する（`gui/app.py:123-139`, `314-355`）。ただし `ingest_all` と `publish_to_icloud` の内部は `_check_cancel` を受けず、押下直後に止まらない区間がある（`gui/app.py:1000-1009`, `1100-1127`）。予想生成中は経過秒のみで ETA がない。
- **二重実行防止 / ボタン状態管理: 4/5** — JS は status に応じ全 `data-action` を disable（`gui/app.py:2108-2111`, `2414-2438`）。`inFlight` は未採用だが、Python 側 `_begin_run` が lock 内で running を原子的に check-and-set し、TOCTOU で二操作が滑り込んでも片方を BusyError にするため JV-Link COM の二重 Open は防ぐ（`gui/app.py:275-286`）。一括実行でも最初の `with JVLinkClient()` 終了後にオッズ用 client を開く（`gui/app.py:1143-1154`）。通信失敗時に `refreshStatus()` が false を返しボタンを再有効化し得る軽微な余地が残る。
- **レイアウト / タップ領域 / アクセシビリティ: 3/5** — sidebar と dashboard は `overflow-y:auto`（`gui/app.py:1249-1258`, `1322-1326`）、focus-visible があり（`gui/app.py:1810-1814`）、機能テキスト色は AA 比を満たす値へ更新済み（`gui/app.py:1201-1206`）。主要アクションには title がある。反面、tab / filter reset に title がなく、日付 label は input と関連付けられず、progress bar に ARIA role/value がない。通常ボタンの高さも約 34px で 44px タップ目安に届かない（`gui/app.py:1777-1793`）。`display:none` は中止・プレビュー等の状態切替用途で、恒久的死にゾーンとは認めない。

## 停止条件チェック

- [x] JS パース成功、onclick 呼出先欠落なし
- [x] F3 変更による `gui/app.py` 差分なし
- [x] Ⅰ→Ⅱ→Ⅲ→Ⅳ の操作順序と主要 action title あり
- [x] Python 側原子ガードにより JV-Link COM 二重 Open 防止
- [ ] 専門領域のプロ承認条件: 全長時間ステージの確実なキャンセルと基本 ARIA が未達
- P25 固有の backtest / market_snapshot / profitability ゲート: N/A（type-B の GUI 影響監査）

## 反証の試み

- **仮説**: F3 診断追加が共通 import や GUI テンプレを間接変更し、ボタンを壊した可能性。
- **確認**: `git diff -- gui/app.py` と `git status --short gui/app.py` は空。さらに Python import 後の実 JS を `node --check` し、全 onclick target を静的照合して missing=[]。
- **結論**: F3 による GUI 回帰は不成立。今回スコアの留保は既存 GUI の残課題であり、F3 のリーク定量化改修による後退ではない。

## 主な改善提案

1. **キャンセルを ingest / publish の内部まで伝播** — `ingest_all(..., cancel_check=self._check_cancel)` 相当と、公開コピー前後の `_check_cancel()` を追加し、「中止」表示と実際の停止を一致させる。
2. **進捗とフォームの ARIA を補完** — `#progressWrap` に `role="progressbar"`、JS で `aria-valuenow/min/max` 更新、日付 label に `for`、タブに `aria-selected` を付ける。
3. **操作ヘルプを追加** — sidebar に `<details id="helpBox">` を置き、初回フロー、検証モード禁止事項、エラー時の復旧順を短く記載する。

## 前回からの差分

- ボタン発見性: 4 → 4（F3 影響なし。番号順と title は維持）
- エラー人間化: 5 → 4（F3 回帰ではなく、現行 v2 絶対基準で raw Promise error と hint 網羅性を再評価）
- 進捗 / ETA / キャンセル: 3 → 3（F3 影響なし。ingest / publish の中止保証が残る）
- 二重実行防止: 4 → 4（F3 影響なし。Python 原子ガードを確認）
- レイアウト / アクセシビリティ: 1 → 3（前回後に入った overflow / focus / contrast 改善を現行コードで再確認。F3 の寄与ではない）
- 前回判定: 記載なし。今回 HOLD は現行 GUI の絶対評価であり、F3 Phase 0.0 の採用判断を妨げる GUI 停止条件はない。
