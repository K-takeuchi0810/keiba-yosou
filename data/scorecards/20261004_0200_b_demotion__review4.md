# B: h_history_truncated の降格 (監査列化) — 4 名レビュー (2026-10-04)

- 対象: branch `b-demote-h-history-truncated-20261004`、SHA **84b2376** (base `00460f0` = main) で固定
- 運用: subagent CWD 限定運用 (ルール 1-bis (b): git はすべて `git -C <worktree>`、Read/Grep は worktree 絶対パス)。レビュー中は worktree 不変 (終了後 `git status --short` 空、HEAD 84b2376 を確認)
- レビュー担当 (外部の指示者の指定で 4 名): code-quality / validation / data-pipeline / prediction-logic
- ai_builder_impact: none (data-pipeline が docs/EXTERNAL_DEPENDENTS.md の import 一覧と照合して確認)

| 担当 | 判定 | 点 |
|---|---|---|
| data-pipeline-engineer | PASS | 4.4 |
| code-quality-reviewer | PASS | 4.2 |
| prediction-logic-analyst | PASS | 4.1 (前回 0.5-4B 3.6) |
| validation-process-auditor | PASS (条件付き) | 3.8 |
| 平均 | | 4.13 |

## must-fix (validation、次の post-demotion 30 特徴の学習コミットまでに執行。未執行で `predictor/*_model.*` を上書きしたらその回は FAIL に降格)

- **M1** collect() の配線テストが値を検証していない。`test_collect_builds_the_input_from_the_model_schema` は全特徴を 0.5 で作るので、評価時に列を反転する変異 (X2 fundamental_eval / X3 market_offset_eval) が生存。collect() が書く margin / p_raw と `booster.predict(feature_matrix(rows, feats))` の一致を、値の異なる行で assert する
- **M2** Fundamental モデルは名前無し (`Column_*`) で、meta sidecar だけが契約。meta の features を反転する変異 (X1) が生存 (`resolve_feature_schema` は本数しか照合できない)。`model.fit(..., feature_name=list(FEATURES))` を付ける。凍結 4B は遡及不可なので「meta と学習時 FEATURES (99eec68) の一致を監査で確認済み」と記録
- (自分で確認: `scripts/fundamental_model.py` の `model.fit` に feature_name なし / テストの行は `_row(feats, value=0.5)`)

## nice-to-have (担当横断で整理)

1. 評価 JSON の `model_feature_schema` にモデルファイルの sha256 と、モデル meta の git_sha / code_version / train / validation / best_iteration を同梱 (data-pipeline 1・validation N1・prediction-logic b)。`predictor/*_model.txt` は同名で上書きされるため、ファイル名だけでは世代を辿れない
2. 監査率の定義の単一出典: `feature_domain_audit.run` の `np.mean(arr == 1.0)` が `fundamental_model.audit_rates` の再実装 (code-quality 2・data-pipeline 4)。NaN の扱いも明示
3. 監査率の年別内訳 (validation N2)。時間の代理かどうかは単調減少で判定するので、窓ごとに 1 値では不足 (4B で見つけたのは年別 40.9→22.3→9.7→3.9%)
4. テストの穴: `only_in_current` が空でないケース (X9 code-quality)、collect 内の `assert_no_market_features(model_features)` (X1 code-quality / X6 validation)、`feature_matrix` の欠落検査が全行に効くこと (X2 code-quality)、`fit()` の meta 組み立てを純粋関数に切り出してテスト可能に (X3 code-quality)
5. 世代ラベルと schema の結合 (prediction-logic a): `--label` と `n_features` の照合、fit meta に `n_features` / `generation`、表示ヘッダの固定文字列「Phase 0.5-4A」を label に
6. 監査率の母集団に主分析の fresh_t10 部分集合も (prediction-logic c)
7. FREEZE_MANIFEST の注記: `fundamental_model.meta.git_sha = af42382` は dirty な SHA で、その commit の FEATURES は 4A の 30 本 (実効コードは 99eec68、validation が照合) (validation N3、自分でも確認)。`hash_note` の「CRLF→LF」は、LightGBM 自身が書く `\r\n` を含むモデル txt では素朴な置換と一致しない (各ファイルの `line_endings: verbatim` が正) (data-pipeline 2、自分でも確認)
8. 過渡期: 現在の `predictor/*_model.txt` は 4B (31) のまま、FEATURES は 30。再学習までの audit JSON (n_features 30) と eval JSON (31) は数字が食い違って見える (data-pipeline 3)
9. fundamental_eval にも学習窓と評価窓の disjoint assert (validation N5、既存の穴)
10. docs/PHASE05_5_PREREG.md に「打ち切りフラグも特徴にしない」を反映 (prediction-logic d)
11. 微小: 21.3% / 36.7% の記述がファイル内 2 箇所、`load_model_schema` の戻り値型注釈、`print_report` の「(監査列)」ラベルが幅超過

## 重要な所見

- **降格は時間の代理を「消す」のではなく「薄める」** (prediction-logic): (age, h_starts, h_days_since の NaN) の組み合わせから打ち切りは部分的に復元できる。研究目的では明示の二値の方が有害なので方向は正しいが、「時間の代理は消えた」とは書かない。30 特徴で β₂ が動いても、それは希釈の効果であって新しい情報ではない
- 残り 30 本のうち累積系 (`h_starts` / `hd_starts` / `ht_starts`、`h_days_since` の上限、`s_winrate` の分母) は上裾が時間とともに伸びるが、域外率は軽微 (所見、must-fix ではない)

## 次の学習 (post-demotion repaired 30-feature) への設計上の注意 (validation)

1. 目的は衛生の変更であって改善の主張ではない。実行前に事前固定: 「β₂ の CI が 4B (0.4997 [−0.828, 1.726]) と重なり、域外率が悪化しなければ受理。β₂ が良くなっても信号とは見なさない」
2. strategy_dev (2026-05-09〜08-31) は消費済み (CONSUMED_WINDOWS)。同じ 626 レースの paired 再評価として扱い、台帳に追記。新しい validation と呼ばない
3. 2025 (validation 窓) は 4A / 4B の early stopping と選択に使用済み。2025 の LogLoss を out-of-sample の証拠として報告しない
4. CONFIRM_FROM = 20260914 以降に触れない
5. モデル meta と評価 JSON の label に世代名と凍結 4B への参照
6. 封印: SEALED_FROM=None、SEALED_ARTIFACTS に fundamental / market_offset は含まれない (確認済み)

## 担当が独自に行った検証

- 公式の変異 12 体を、validation / prediction-logic / code-quality がそれぞれ隔離コピーで再実行 → 12/12 KILLED
- 追加の変異: code-quality 7 体 (X1 / X2 / X3 / X9 が生存)、validation 9 体 (X1 / X2 / X3 / X6 / X9 が生存)。生存は上の must-fix と nice-to-have 4 に対応
- 凍結 4B: 15 ファイルの raw sha256 が一致、LightGBM で読めて 31 列に解決、現行の `predictor/*_model.*` 4 ファイルも凍結物と sha 一致 (再学習はしていない)
- 全テスト (worktree): 1037 passed / 12 skipped / 1 failed (`test_model_artifacts_are_unchanged_during_the_seal`: worktree の checkout で `predictor/second_blend.json` が CRLF になる。main では単独実行で passed。B とは無関係)
- `collect(` の呼び出し元で壊れたものはない。eval 2 本以外に、今の FEATURES で保存済みモデルの入力を組む箇所はない
