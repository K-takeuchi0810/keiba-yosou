# keiba-yosou — Claude Code 運用規約

このリポジトリで Claude Code が改修するときの全プロジェクト共通ルール。

## 必須ルール

### 1. 改修ごとに `expert-review` を必ず実行 (D1 モード)

`gui/` `predictor/` `jvlink_client/` `web/` `scripts/` 配下、または `weights.json` `calibrator.json` `schema.sql` のいずれかを編集して **タスク完了を宣言する直前** に、`expert-review` メタスキルを必ず通す。

詳細: `.claude/skills/expert-review/SKILL.md`

- 7 名の専門家 subagent を **並列** 起動
- `data/scorecards/<yyyymmdd>_<hhmm>_<topic>.md` に結果を保存
- 総合スコアが前回比 -0.3 以上下がった項目があれば警告
- ユーザの確認を待たない (D1 = auto-trigger)

ドキュメントだけの修正 (`*.md`) はスキップしてよい。

### 2. `gui/app.py` の HTML/JS を編集したら必ず `python-embedded-js` 検証

詳細: `.claude/skills/python-embedded-js/SKILL.md`

`CONTROL_HTML` / `PREVIEW_HTML` を触ったら **node で JS パース確認** が必須。Python の triple-quoted 文字列で `\n` が改行に展開される罠で過去 4 回以上ボタンが死んでいる。

### 3. 32bit Python 必須経路の遵守

JV-Link COM は 32bit。`.venv32/Scripts/python.exe` を使う。詳細は `.claude/skills/jvlink-com/SKILL.md`。

## 専門家 7 名

| ID | 担当 |
|---|---|
| `gui-ux-auditor` | pywebview コントロールパネル UX |
| `mobile-html-reviewer` | iPhone Safari + iCloud 経由の HTML |
| `prediction-logic-analyst` | rules.py / features.py / weights.json の構造 |
| `profitability-judge` | backtest 数値・EV・買い目フィルタ |
| `data-pipeline-engineer` | JV-Link → SQLite |
| `code-quality-reviewer` | DRY / dead code / 設定外出し |
| `validation-process-auditor` | backtest 設計・calibration |

## 関連スキル

- `.claude/skills/project-state/` ← **新セッション開始時に最初に読む** (現状サマリ + 次の優先課題)
- `.claude/skills/expert-review/` ← **改修の最後に必ず通す**
- `.claude/skills/python-embedded-js/` ← GUI HTML/JS 編集時
- `.claude/skills/jvlink-com/` ← JV-Link COM 周り
- `.claude/skills/jvdata-record/` ← レコード追加時
- `.claude/skills/keiba-feature/` ← 予想ロジック追加時
- `.claude/skills/keiba-backtest/` ← バックテスト設計時
- `.claude/skills/token-economy/` ← 大ファイル / 生成物の扱い

## 現在の状態 (2026-05 時点)

7 改修完了で全体平均 **3.06 → 4.09** (baseline 比 +1.03)。

詳細スナップショット (実 backtest 数値 / 次の優先 6 件 / 既知の軽微回帰 など) は `.claude/skills/project-state/SKILL.md` を参照。新セッションは **まずこれを読む** ことから始める。

scorecards は `data/scorecards/<日時>_<topic>.md` に時系列で保存済。最新の集約は `20260511_2345_ae_walkforward_sweep_review.md`。
