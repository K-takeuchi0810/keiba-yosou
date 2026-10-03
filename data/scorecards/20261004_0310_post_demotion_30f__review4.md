# post-demotion repaired 30-feature の学習・評価 — 4 名レビュー (2026-10-04)

- 対象: branch `post-demotion-30f-20261004`、SHA **da05c51** で固定 (61e2d14 学習前の執行事項 → d6bc38b 学習と評価の成果物 → da05c51 MANIFEST の blob 照合ハッシュ)、base main 4d8e940
- 担当: 外部の指示者の推奨 (validation / prediction-logic / data-pipeline) + code-quality (61e2d14 に未レビューのコード変更があったため)
- 運用: subagent CWD 限定運用 (ルール 1-bis (b))。学習・評価は再実行しない (窓の消費を増やさない)。変異は git archive da05c51 の隔離コピー。レビュー中 worktree 不変
- ai_builder_impact: none (data-pipeline が同意)

| 担当 | 判定 | 点 |
|---|---|---|
| data-pipeline-engineer | PASS | 4.4 |
| validation-process-auditor | PASS | 4.3 |
| code-quality-reviewer | PASS | 4.2 |
| prediction-logic-analyst | PASS | 4.0 |
| 平均 | | 4.23 |

## must-fix

- **prediction-logic M1 (docs のみ)**: 結果節の「補正の裾がやや広がったのは、打ち切りの明示の二値を外した分を他の特徴が希釈された形で拾った結果と整合する」は根拠のない機構の付与。外した特徴の 4B での gain は 0.20% (市場オフセット) / 0.30% (Fundamental)、評価行での発火は 0.86% で、ほぼ零摂動。裾の広がり・gain 配分の変化 (±2pt) は、木の本数 28→36 と列・行サンプリングの乱数の変化による再学習のばらつきと区別できない (seed sweep をしていないので判別不能)。(自分で確認: gain 0.0020 / 0.0030、木の本数 28→36 / 247→220)

## 確認されたこと (担当が独立に)

- 事前固定 (61e2d14 02:37:58) が学習 (02:41:47) より前、事前固定節は d6bc38b で 1 文字も変わっていない (結果節の追記のみ)。compare.py の mtime は評価 JSON より前
- 実行は fit 2 / 域外監査 1 / 評価 1 (run_index 1)。fundamental_eval は実行していない
- 受理判定を成果物から独立に再計算して一致。(b) は 4B と率が小数点以下まで同一 (max(new−old)=0.0、n_rows も一致 = 窓のデータ不変)。判定ロジックの変異 4 種で感応を確認
- 比較の数値は docs の表と全一致。区間はレース単位の再抽選 (別 seed で再計算してもほぼ同じ)
- data_version 46717:4ee66a39fb を本番 DB (mode=ro) から独立に再計算して一致。run_step.py の DB_PATH 差し替えは全経路に効き、worktree に空の DB を作っていない
- 626 レース / 8,279 頭が 4B と完全一致 (won / lead_min / p_t10 / odds / payout の差 0 行)
- MANIFEST 15/15 で sha256 と sha256_git_blob が一致。モデルは -text で CRLF のまま、LightGBM で読めて feature_name() == meta == FEATURES (30)
- 4B 凍結 15/15 不変、事前登録 docs 不変
- 本番 DB の本体 mtime と WAL は学習・評価の前後とレビュー時点で不変
- M-new (data_version) の是正と前回の Xa〜Xe を確認。公式変異 spec 29 体は 61e2d14 後も対象文字列が一致

## 重要な所見

- **馬別の相関 +0.54 は「この学習設定での補正の再現性の床」と読むべき** (prediction-logic): 外した特徴がほぼ零摂動なので、補正の分散の約 70% が再学習で再現しない (R² 0.29)。4A↔4B の +0.33 はデータ修復込みで同列比較できない
- 受理条件 (a) は弁別力が低い (区間の幅が ±1.1〜1.3 で、重なりはほぼ必ず成立)。(b) と同じく機械的な確認である旨を書く (validation / prediction-logic)
- 4B の評価時 data_version 35626 と今回 46717 の差は 4B 以降の取り込み。評価窓の T−10 市場と結果は paired で完全一致なので評価集合に影響なし (data-pipeline)

## nice-to-have

- in-sample ガードが meta に窓が無いと素通り (fail-open) → 両方欠けたら止める (validation)
- 評価窓の境界日のテスト (`<=` → `<` の変異が生存、validation / code-quality)
- ガードを build_dataset (重い) の前に (code-quality)
- 変異 spec に B30 (窓ガード) / B31 (snapshot の順序) を追加 (code-quality)
- `provenance.data_version` の `except sqlite3.Error` が閉じた接続の ProgrammingError も握る (根本。OperationalError に狭める候補、code-quality)
- `snapshot()` に db_path / size / mtime を入れる (data_version は取り込み台帳だけの指紋で、ai-builder の直接の書き込みを捉えない、data-pipeline)
- `_flag` の 2 つ目のメッセージを raw に揃える / model_schema の docstring「名前を持つモデル」を更新 (code-quality)
- run_step.py: config の既 import も弾く、assert → SystemExit、引数の usage (data-pipeline / code-quality)。**実行に使った版なので書き換えない** (次回のスクリプトで)
- compare.py の単体テスト、または scripts/ への昇格 (validation)
- 次回は db_state_before_fit も (validation)
- seed を変えて 2-3 本学習し、validation 2025 内で補正の seed 間相関を測れば「再現性の床」と M1 の判別不能が解消する (strategy_dev では走らせない、prediction-logic)
- gain 配分の表を成果物に残す (prediction-logic)
- 既存の未使用 import (fundamental_eval / market_offset_eval、base から) の掃除 (code-quality)
- da05c51 のコミットメッセージ「全 14 ファイル」は make_manifest.py を除いた数 (MANIFEST は 15 件)
