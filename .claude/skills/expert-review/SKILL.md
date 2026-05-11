---
name: expert-review
description: keiba-yosou のあらゆるコード改修が完了した直後に必ず呼ぶ。7 名の専門家 subagent (gui-ux-auditor / mobile-html-reviewer / prediction-logic-analyst / profitability-judge / data-pipeline-engineer / code-quality-reviewer / validation-process-auditor) を並列起動して 5 段階採点を取り、`data/scorecards/` に保存。「採点」「scorecard」「expert review」「専門家レビュー」要求にも対応。改修ごとに必ず通過させることでアプリ品質を時系列で追跡する。
---

# 専門家による採点ワークフロー (D1 = 改修ごと自動)

## いつ呼ぶか (= 必須トリガー)

このプロジェクトでは **コードを 1 行でも編集して改修が完了したと宣言する直前** に、このスキルを必ず通す。
ユーザの確認を待たない (D1 モード)。

具体的なトリガー:
1. `gui/app.py` `predictor/*` `jvlink_client/*` `web/*` `scripts/*` のいずれかを Edit / Write した
2. `weights.json` `calibrator.json` `schema.sql` を変更した
3. ユーザが「採点して」「scorecard 出して」「expert review」と発話した

軽微なドキュメント更新 (`README.md` `*.md` のみ) はスキップしてよい。

## 何をするか (実行手順)

### 1. 改修サマリを 1 行で書く

直前のコミット or 編集差分を `git diff --stat` 等で確認し、改修内容を 1 行 (40〜80 字) に要約。
例: `2026-05-09 GUI fetch_results を 0B14 から RACE 差分に切替 + 馬番00行を全層フィルタ`

### 2. 7 専門家を **並列** 起動

`Agent` ツールで 7 つの subagent をすべて同じメッセージ内で並列発火する (1 つずつ直列に呼ぶと体感的に倍以上遅い)。

各 agent への共通プロンプト雛形:
```
改修内容: <summary>
直前の編集ファイル: <list>

`.claude/agents/_rubric.md` の 5 段階ルーブリックに従い、自分の専門範囲を採点せよ。
`data/scorecards/*_<your-agent-name>.md` に過去スコアがあれば必ず読み、差分を出すこと。
出力は 200 行以内。
```

呼ぶ subagent:
- gui-ux-auditor
- mobile-html-reviewer
- prediction-logic-analyst
- profitability-judge
- data-pipeline-engineer
- code-quality-reviewer
- validation-process-auditor

### 3. 結果を 1 ファイルに集約 → 保存

ファイル名: `data/scorecards/YYYYMMDD_HHMM_<topic-slug>.md`

- `<topic-slug>` は改修内容の英語短縮 (例: `fetch_results_race`, `mobile_horse_zero_fix`)
- 同じトピックで複数回採点が走るときは末尾に連番 `_2` `_3`

ファイル構造:
```markdown
# 採点 YYYY-MM-DD HH:MM

**改修内容**: <1 行サマリ>
**対象ファイル**: <主要なもの 5 つまで>

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|---|---|---|
| GUI / UX 監査人 | 4.0 | 3.4 | +0.6 |
| ... |

## 各専門家の所見

### GUI / UX 監査人
<subagent から返ってきた内容をそのまま貼る>

### モバイル HTML レビュアー
...

(全 7 名分)

## 横断的に見た優先課題

<7 名の改善提案を Claude (=自分) が並べ替え、優先度の高い順に 3 件出す>

1. **<タイトル>** (担当: gui-ux-auditor + mobile-html-reviewer)
   - 内容
2. ...
```

### 4. スコア低下を検知

総合 (項目平均) が **前回より 0.3 以上下がった** 専門家がいたら警告:
- 差分テーブルの該当セルを **太字 + 「⚠ 後退」** マーキング
- 「横断的に見た優先課題」の冒頭に明示

### 5. ユーザに簡潔報告

最終応答に貼るのは下記 3 点だけ (full scorecard は data/scorecards/ にあるから):
1. 総合スコア推移の表 (上記 1 つ)
2. 後退した観点があればそれ (なければ「全項目維持または改善」)
3. 優先改善 1 件

## 並列起動のコード例 (Claude Code 用)

```python
# Agent ツールを 1 メッセージ内で 7 回呼ぶ (= 並列実行)
# subagent_type に各 agent の name を指定
```

実装上の注意:
- 各 subagent は対象範囲外を読まない (トークン浪費防止)
- `git log --stat -3` で直前差分を必ず確認するよう agent プロンプトに含める
- scorecard 保存先 `data/scorecards/` は git 管理対象 (履歴を残す)

## scorecard ファイル名規則

```
data/scorecards/<yyyymmdd>_<hhmm>_<topic-slug>.md
data/scorecards/<yyyymmdd>_<hhmm>_<topic-slug>__<agent-name>.md   (個別)
```

集約ファイルが本体。個別ファイルは agent ごとの差分追跡用にも残す。

## やってはいけないこと

- 7 人を直列で呼ぶ (4-7 倍遅い)
- 「採点をスキップしてコミット」 (D1 = 必須)
- ユーザの確認を待つ (D1 は自動)
- 採点結果を改ざんする (低い点が出たら受け入れて改修案として扱う)
- 全 agent に対象範囲外まで読ませる (トークン爆発)

## 関連スキル

- `python-embedded-js`: 採点前に必ず JS パース確認 (壊れていたら GUI 監査人が即 1 確定)
