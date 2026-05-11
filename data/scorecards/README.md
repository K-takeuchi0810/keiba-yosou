# scorecards/

`expert-review` メタスキルが書き出す **改修ごとの採点履歴**。

## ファイル構造

```
YYYYMMDD_HHMM_<topic-slug>.md          ← 集約 (本体)
YYYYMMDD_HHMM_<topic-slug>__<agent>.md ← 個別 (差分追跡用、任意)
```

## 専門家 7 名

| ID | 役割 |
|---|---|
| `gui-ux-auditor` | GUI / UX (pywebview) |
| `mobile-html-reviewer` | モバイル HTML 出力 |
| `prediction-logic-analyst` | 予想ロジック設計 |
| `profitability-judge` | 収益性 / 投資判断 |
| `data-pipeline-engineer` | データパイプライン |
| `code-quality-reviewer` | コード品質 / 保守性 |
| `validation-process-auditor` | 検証プロセス |

各専門家の詳細は `.claude/agents/<name>.md` を参照。

## 5 段階ルーブリック

| 点 | レベル |
|---|---|
| 5 | 模範的 |
| 4 | 良好 |
| 3 | 標準的 |
| 2 | 改善必要 |
| 1 | 致命的 |

総合スコアは項目平均 (小数 1 桁)。詳細は `.claude/agents/_rubric.md`。

## 運用 (D1 モード)

- 改修ごとに **自動** で 7 名並列実行 → ここに保存
- 総合が前回比 -0.3 以上下がった専門家は警告
- 優先課題は次の改修で扱う
