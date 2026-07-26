# F3 Phase 0 fail-closed 実装結果

- 実装日: 2026-07-26
- branch: `codex/phase0-fail-closed`
- base: `2d6e6f60c4f82b4d7dd163a7a2f61d29fdb4348c`
- 対象: `docs/F3_MARKET_RESIDUAL_DESIGN.md` §4.4（正本文書自体は不変）

## 実装契約

| mode | core の返却 | production の表示 | 買い候補 |
|---|---|---|---:|
| `full` | 通常予想 | 通常表示 | 既存条件 |
| `observation` | 予想 + 閉じた理由コード | 予想表 + mode/reason banner | 0 |
| `blocked` | 内部比較用予想 + 閉じた理由コード | 予想表を抑止し reason 行のみ | 0 |

`PredictionBatch` は list 互換のまま、空結果でも race 単位の状態を保持する。backtest・分析は
mode を強制せず従来の数値計算を継続し、web / GUI / CLI / auto-predict の production
consumer だけが mode を強制する。理由は `E01_MODEL_MISSING` / `E02_STALE_ODDS` /
`E03_PIT_VIOLATION` / `E04_FEATURES_INCOMPLETE` の4値に限定した。

## 消費者

- Web: observation は買い候補なし、blocked は予想表なし。HTML meta と可視 banner/reason 行を追加。
- GUI: dashboard mode bannerを追加し、blocked の予想項目を抑止。venv64 の mode exit 8を正常な状態返却として解釈。
- CLI: observation はstderr通知 + exit 0、blocked は出力抑止 + exit 8。
- auto-predict: 通常の生成失敗 bit 2と分離して mode failure bit 8を追加し、日次batでも
  bit 8を保持して通知文へmode/reasonを含めた。
- Ledger: `prediction_mode TEXT NOT NULL DEFAULT 'full'` と
  `error_reasons TEXT NOT NULL DEFAULT '[]'` を追加。blocked 空結果は空馬番sentinel 1行で記録する。
- Monitor: observation/blockedをBrier対象から暗黙除外せず、mode/reason別件数を併記する。

## Migration

`data/schema.sql` の新規DB定義と `db.init_db()` の `_ensure_column` の両方を更新した。
旧行はSQLiteの列DEFAULTにより `full` / `[]` となり、既存の予想・主キー・答え合わせ行は保持される。

## 受入ゲート

| Gate | 結果 |
|---|---|
| G1 | 実装直後、旧「LGBM例外/特徴計算例外でも通常予想」characterization 2件が `PredictionBatch` の `blocked / E04` 返却との差でred。その後structured mode assertへ更新してgreen |
| G2 | `.venv64/Scripts/python.exe -m pytest tests -q`: **441 passed, 4 skipped** |
| G3 | rule-onlyは改修前固定goldenの既存Prediction全フィールド、変更対象full/LGBM経路は score/rank/probability/EV/Kelly/raw blend がbit一致 |
| G4 | `--skip-oos` 実測: control AUC **0.7913195088860858** / treatment AUC **0.7887806982333265**。OOSは今回再実行せず、凍結済み `docs/F3_phase0_0b_result.md` の **425 bets / 62.0941%** を参照 |
| G5 | production model/features/meta/calibrator/weightsおよび正本文書のSHA-256が着手前後一致。ps1変更なし |

GUI埋め込みJSはPython展開後の `CONTROL_HTML` から抽出して `node --check` を通過した。
DB内容、Discord、封印期間、傾向収集、他branch、production artifactへの変更・送信は行っていない。

7分野expert reviewは平均 **3.91 / 5**、実装判定 **PASS_WITH_FINDINGS**。
前回比 -0.3以上の後退はなく、状態文言・集約・exit codeの単一出典化を次課題とした。
