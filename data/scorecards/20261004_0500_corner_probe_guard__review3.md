# 通過順位の probe の緑化と検証フラグのコード強制 — 3 名レビュー (2026-10-04)

- 対象: branch `corner-probe-20261004`、SHA **d4d87fc** (base main 432689b)。コードは 382130f (probe の判定) と
  d4d87fc (config / predictor/features.py / scripts/analyze_misses.py / tests)
- 担当 (外部の指示者の指定): code-quality / data-pipeline / validation。subagent CWD 限定運用、変異は隔離コピー

| 担当 | 判定 | 点 |
|---|---|---|
| data-pipeline-engineer | PASS | 4.3 |
| validation-process-auditor | PASS | 4.3 |
| code-quality-reviewer | PASS | 4.1 |

## 確認されたこと
- 順序: 対象 d651842 → 期待値 e7e59b9 → 1 回目 1b51e73 → 判定の修正 382130f → 再実行 9ceceea → verified d4d87fc。
  対象と期待値の blob は全コミットで同一。1 回目と 2 回目は値の一覧と 296 行の照合行が完全一致 (同じ raw の強い証拠)
- 382130f は「結果を見て条件を変えた」ではない (golden 突合の実装は不変、範囲・全 0 の不合格は残る、変えたのは JRA 公式に
  反証された経験則の終了コードへの影響だけ)
- data-pipeline が probe を自分で再実行して 5/5・74/74・296/296・rc 0 を再現。2026-07 以降の DB の値は同じ parser で SESW を
  parse した値と一致 (179/179、地方 422/422)
- ガード: 通過順位の数値を使う経路で、フラグを通らないものは無い (code-quality が全列挙)。変異 12 件中 11 件を検出
- ai-builder は通過順位を RA から自前で復元しており horse_races.corner_order_* に依存しない。compute_features は表示・特徴で
  読むだけ → ai_builder_impact: tested は妥当

## 指摘と対応 (このブランチで反映)
- validation must-fix: 期待値ファイルの取得時刻「04:3x」はファイルのコミット時刻 (04:25) と矛盾 → RESULT.md の正誤表で訂正
  (ファイル本体は sha の同一性を保つため触らない)
- validation must-fix / data-pipeline must-fix: backfill の契約 (入口でガード、False なら 1 行も書かないテスト、
  upsert_horse_race / ingest_all を使わず corner 4 列だけを UPDATE、1 トランザクションで検収不合格なら rollback、
  開催日の拒否、承認フラグなしは dry-run) → backfill を書くときに実装する (Scratch B の前)
- data-pipeline: SE の再 upsert は odds_fetched_at の刻印が残ったまま win_odds を確定値で上書きし、PIT の汚染行を作る
  (2026-05/06 の 2,582 行) → parser のコメントと事前登録に記録、backfill は UPDATE 専用
- data-pipeline: parser の「暫定確定」「緑化まで禁止」のコメントを現状に → 更新
- code-quality (強く推奨): 通過順位を読むファイルの許可リストのテスト → tests/test_corner_gate.py に追加
- code-quality: 期待値の該当レコードが無いときの変異が生存 → テスト追加
- code-quality / validation / data-pipeline: probe の docstring が旧仕様、config の説明が実態より強い、webapp の import 時の
  スナップショット → いずれも修正
- 互換確認のログに失敗した試行の Traceback が混ざっていた → スクリプトを保存し取り直し (元のログは _first_attempt として残す)
- 事前登録 §8-3 に進捗と地方の行の注記を追記
- probe の `--expect` 時に範囲・全 0 の逸脱を無視する点 (code-quality nice-to-have 1) は、外部の指示者の決定
  (golden の結果で終了コードを決める) のまま据え置き、docstring に「照合する馬を広く与えること」と明記
- 既存の別件: test_model_artifacts_are_unchanged_during_the_seal が worktree で落ちる (second_blend.json の改行)。封印の状態の
  認識 (sealed_window_started) も含めて別途確認する
