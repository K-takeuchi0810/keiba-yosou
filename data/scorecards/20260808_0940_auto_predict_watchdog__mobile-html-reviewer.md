# モバイル HTML レビュアー 採点

## 判定: PASS

**理由**: コミット `cb970a0` は日次取得・予想タスクの watchdog、起動時刻、ログ出力、回帰テストを変更する **type-C 相当（取得・運用基盤）**。`web/` の変更は0件であり、今回差分によるモバイルHTML回帰はない。type-D/P25表示固有ゲートは N/A（対象外）として前回評価を維持する。  
**採点対象**: 今回差分によるモバイルHTML回帰の有無。watchdog・Windowsタスク・JV-Link取得処理そのものの運用品質は専門外。  
**根拠ファイル**: `scripts/auto_predict_daily.bat:12-16`、`scripts/register_auto_predict_task.ps1:8-9,28-43`、`scripts/run_auto_predict_daily.ps1:28-45`、`tests/test_auto_predict_task_runner.py:14-84`。`git diff cb970a0^ cb970a0 -- web` は本セッション実測0件。  
**次アクション**: 今回変更へのモバイルHTML修正要求なし。別改修で既存の枠番色コントラストをAA適合させる。

## 総合: 4.0 / 5（参考スコア）

前回 4.0 → 今回 4.0（±0）。HTML/CSS/view model/生成物に変更がないため据え置き（`data/scorecards/20260802_2155_hidden_scheduled_tasks__mobile-html-reviewer.md:10-20`）。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `web/` 差分0件。前回4/5を維持（前回scorecard:16）。
- **タップ領域 / 操作性: 5/5** — インタラクティブ要素のCSS差分0件。前回5/5を維持（同:17）。
- **情報密度 / 可読性 / 誤読防止: 4/5** — 鮮度・推奨・購入判断の表示契約に差分なし。前回4/5を維持（同:18）。
- **ダークモード / コントラスト: 3/5** — 色指定の変更0件。既存のAA留保を含め前回3/5を維持（同:19、現行色定義 `web/templates/index.html.j2:584-591`）。
- **iOS / iCloud互換 + パフォーマンス予算: 4/5** — HTML/CSS/DOM差分0件。前回4/5を維持（同:20）。参考実測として現存する `web/dist/index.html` は506,410 bytesだが、今回コミットの生成物ではないため採点根拠には用いない。

## 停止条件チェック

- [x] 改修タイプを type-C 相当と分類。type-D HTML改修ゲートは **N/A（対象外）**。
- [x] `git show cb970a0 --stat` の変更は scripts 3件・tests 1件で、`web/` は0件。
- [x] `git diff cb970a0^ cb970a0 -- web` は0件、`git status --short -- web` も0件を本セッションで確認。
- [x] `web/dist/index.html` 再生成・375px再監査・P25 market snapshot照合は type-D改修時のみ必須のため **N/A**。
- [x] 今回差分によるモバイルHTML専門停止条件への新規抵触なし。

## 反証の試み

- 主張「watchdog改修はHTMLに影響しない」に対し、コミット差分だけでなく作業ツリーの同時 `web/` 変更も確認した。コミット差分・作業ツリーとも0件で、反証は不成立。
- 将来スマホ画面にwatchdog状態を出す場合は、タイムアウトを単なる「処理中」にせず「取得失敗・既存DB利用」と明示する必要がある。現コミットはHTML出力を追加していないため参考所見に留める。

## 主な改善提案（優先1件）

1. **既存の枠番4/6/7/8色をWCAG AAへ調整** — `web/templates/index.html.j2:587,589-591` の白文字背景色を暗くするか文字色を変更する。前回実測は4枠4.06:1、6枠2.50:1、7枠2.92:1、8枠2.91:1で、通常文字4.5:1未達（`data/scorecards/20260720_1204_f3_phase0_0__mobile-html-reviewer.md:25`）。これは今回差分の回帰ではない。

## 前回からの差分

- 5項目すべて据え置き。前回判定 PASS → 今回 **PASS**。
- 前回と同じ type-C相当の非HTML改修であり、HTML側への新規変更要求はない。
