# 予想ロジック分析官 採点

## 総合: 4.0 / 5（前回 4.1 → 今回 4.0、-0.1）

> 評価対象: F3 Phase 0-0 の3リークチャネル定量化。指定の `.Codex/agents/_rubric.md` は現 CWD に存在しなかったため、過去 prediction-logic scorecard の5軸フォーマットと依頼文の必須観点を適用した。

## 項目別

- **シグナル網羅性: 4.5/5** — 現行 LGBM は112特徴で、距離・コース・馬場・血統・脚質推定・上がり・騎手/厩舎・枠・相対特徴まで広く保持する。F3 treatment は control の112列から `same_day_bias_score` / `leg_quality_available` / `same_day_bias_available` の登録3列だけを除いた109列で、追加0・残存列順序維持を成果物から確認した。ただし同日確定結果由来の `same_day_gate_bias_score` は treatment に残る（control gain 0.0855%、treatment gain 0.0930%）ため、「全発走後リーク除去」ではなく登録3チャネルの ablation に限定される。
- **重み妥当性 / 過適合リスク: 4.0/5** — `rules.py` の `score +=/-= 数値` は意図的な異常馬マーカー `score -= 1000` 1件のみで、主要ルール重みは `weights.json` に外出し済み。M2 control/treatment は同一 cache、時系列末尾20% split（train 8,294 races / val 2,074 races）、781 rounds、seed/bagging_seed/feature_fraction_seed/data_random_seed=`20260720`、`deterministic=True` で揃っている。反面、`feature_fraction=0.7662` かつ列数が112対109なので、同じ seed でも各木の特徴サンプリング集合は完全な paired intervention にならない。単一 seed の差を「純寄与」と断定せず、複数 seed 分布または feature_fraction=1 の感度分析が必要。
- **信頼度判定 / 確率推定: 4.0/5** — AUC/Brier/LogLoss/top-1 の算出と差分方向は正しい。M0/M1 は同一 public v6・同一 val に対して入力3列だけを live 値0へ置換するため live skew の測定として妥当。M2 は同一条件再学習の control/treatment であり、登録3列の学習時寄与を見る設計も良い。結果は M0−M1 AUC `+0.001974`、M2 control−treatment AUC `+0.002539`、top-1 は後者 `0.0` で、効果は小さい。「純リーク寄与」「真のvalidation baseline」という文言は、残存する同日枠バイアスと再学習によるモデル経路差を考えると強すぎるため、「登録3特徴 ablation 差」「3特徴除外 baseline」へ弱めるべき。
- **デッドコード / 設計の整合性: 4.5/5** — `BLOCKED_FEATURES` と `LIVE_VALUES` は同じ3列で、M1 は入力をコピーして対象列だけゼロ化、M2 treatment は同じ3列だけ削除する。control/treatment のモデル実体も各112/109特徴、同一 rounds/主要 params/seed を確認。production model/features/meta/calibrator の前後 SHA-256 は全て一致し、実験成果物は別ディレクトリに隔離されている。5件の unit test は通過。ただしテストは同一 split/seed/params、成果物の「3列だけ削除」、production hash 不変を直接回帰テストしておらず、主要契約が実行後の手確認に依存する。
- **本番運用との乖離リスク: 3.0/5** — `_guard_unsealed` は `2026-10-01` 以降を拒否し、固定 OOS は `2026-01-01..06-14`、DB は read-only、production SHA は不変で sealed/本番不変の基本契約を満たす。一方 OOS の「M2-treatment」は treatment booster だけを差し替え、50% blend の rule 側では `same_day_bias_score`、`same_day_gate_bias_score`、raw `leg_quality_code` 経路が残る。したがって62.09%はリーク除去済み全スタックの OOS ではない。また metrics の `git_sha=068efb0...` は未追跡の evaluator 本体を含まず、実験モデル/feature JSON/calibrator.bak の SHA も保存していないため再現性 provenance が弱い。

## 主要契約の検査結果

- **M0/M1:** PASS — 同一 public booster・同一val、3列だけを0へ置換。入力配列を破壊しないテストもPASS。
- **M2 control/treatment:** PASS（留保あり）— 同一split/seed/rounds/params。control 112列、treatment 109列、除外は登録3列だけで順序維持。単一seedかつ feature subsampling のため差を厳密な causal/pure 寄与とは呼ばない。
- **sealed禁止:** PASS — 境界テストと実績期間を確認。`to_date=20261001` は拒否。
- **本番不変:** PASS — production 4成果物の前後SHAが一致。ただし evaluator 自身が未追跡で、記録commitはコード同定子になっていない。
- **指標解釈:** PARTIAL — 差分符号と数値は正しいが、「純リーク」「真のbaseline」「M2-treatment OOS」は過大表現。

## 主な改善提案（優先順）

1. **結論を登録3特徴の ablation に限定** — `純リーク寄与`→`登録3特徴の再学習ablation差`、`真のvalidation baseline`→`3特徴除外baseline`。OOSは「treatment booster + 現行rule blend」でありリーク除去済み全スタックではない、と表/table名にも明記する。
2. **OOSのrule側も同じ契約で遮断するか、OOSを参考値へ降格** — 少なくとも rule score の `same_day_bias_score` / `same_day_gate_bias_score` / raw `leg_quality_code` 経路を実験コンテキスト内だけ live-safe に固定し、production本体は変更せず再評価する。登録外の `same_day_gate_bias_score` を残すなら、残存リークとして明記する。
3. **再現性契約を機械化** — metrics に evaluator/test/cache/control/treatment/features/calibrator のSHA、dirty/untracked status、LightGBM versionを保存。テストに同一split/seed/params、exact-3 feature diff、production hash不変を追加し、可能なら複数seedまたは `feature_fraction=1` 感度分析を添える。

## 前回からの差分

- シグナル網羅性: 4.0 → 4.5（+0.5）— 現行112特徴と exact-3 ablation 成果物を確認。ただし残存同日枠バイアスあり。
- 重み妥当性 / 過適合リスク: 4.0 → 4.0（±0）— 外出し状態維持。固定seed/splitは良いが単一seed差の断定は不可。
- 信頼度判定 / 確率推定: 4.0 → 4.0（±0）— 指標実装は妥当、表現の因果的過大解釈が減点。
- デッドコード / 設計の整合性: 4.5 → 4.5（±0）— exact-3除外と成果物隔離は良好。主要契約テスト不足。
- 本番運用との乖離リスク: 3.0 → 3.0（±0）— sealed/本番不変は確認したが、OOS rule側の残存リークと provenance が未解消。

## 検証メモ

- `git log --stat -3`: 直近3commitはいずれも予想HTML公開で、F3 evaluator/結果は未追跡。記録SHAは今回コードを含まない。
- 必須確認: `weights.json` は24 top-level keys。magic-number grep は異常馬マーカー1件のみ。
- `pytest tests/test_f3_phase0_0_eval.py -q`: **5 passed**。
- 前回比は **-0.1** で、-0.3以上の回帰警告条件には非該当。
