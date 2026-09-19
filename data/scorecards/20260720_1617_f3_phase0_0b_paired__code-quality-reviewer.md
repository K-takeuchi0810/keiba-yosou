# コード品質 / 保守性レビュアー 採点 — F3 Phase 0-0b paired OOS

## 判定: PASS

**改修タイプ**: type-B（検証・診断ツール）。P25 採用固有ゲートは N/A。対象は
`scripts/f3_phase0_0_eval.py`、`tests/test_f3_phase0_0_eval.py` と生成 artifact/report の
保守性のみ。統計的な採用判断自体は専門外。

**理由**: paired 計算契約と保存 artifact の旧 evaluator provenance は成立している。最終 HEAD
`fa1d491` で paired JSON を canonical な `data/f3_phase0_0/paired_oos.json`、report を固定 docs path に
限定し、`config.py`、`data/keiba.db`、evaluator source を出力先にする反例をすべて拒否した。
bootstrap entry-point fail-fast、reference/historical calibrator 保護、atomic write、evaluator commit
記録も揃い、停止条件となるコード欠陥は解消した。

**根拠ファイル**: `scripts/f3_phase0_0_eval.py:291`, `scripts/f3_phase0_0_eval.py:510`,
`scripts/f3_phase0_0_eval.py:686`, `tests/test_f3_phase0_0_eval.py:71`,
`data/f3_phase0_0/paired_oos.json`

**次アクション**: 非停止課題として、長時間 treatment/control run の checkpoint/resume と、
dirty status/effective env を含む provenance manifest を追加する。

## 総合: 4.3 / 5（最終 HEAD `fa1d491`）

- 前回: **4.1 / 5**（HEAD `5b4d43d` 再レビュー）
- 今回: **4.3 / 5**
- 差分: **+0.2**
- 参考: Phase 0-0 前回 scorecard **4.0 / 5**

既存 OOS 経路の再利用、pure な paired bootstrap、保存済みモデルの再現検査、2 unit test の追加を
加点した。最終差分では atomic write、固定出力 allowlist、evaluator commit、entry fail-fast、
境界 test を追加した。対象 module は約1,150行・29関数となり、最大関数は `run_paired_oos()` 約155行、
`_evaluate_oos()` 146行、`run()` 141行で、前回の orchestration 集中は解消していない。

## 項目別

- **DRY / 重複コード: 4.5 / 5** — control/treatment は同じ `_evaluate_oos()` を
  `include_ledger=True` で呼び、window/filter/calibrator/rules のコードパスを共有する
  (`scripts/f3_phase0_0_eval.py:716-744`)。bootstrap も1つの `indices` を両系列に適用する
  (`:574-585`)。減点は3種類の basis 名が validation・計算・report に平行記述される点と、
  149行の `run_paired_oos()` に検査・2 run・join・判断・書込が集中する点。

- **dead code / 未使用シンボル: 4.5 / 5** — AST 検査で対象 script の未使用 import 候補は0。
  追加した `_saved_pair_validation_check`、`_paired_roi_bootstrap`、`run_paired_oos` は実行経路または
  tests から到達し、`include_ledger` もpaired runで使用される。repo必須簡易 scan の rules 未参照
  feature候補は32件だが、多くは LGBM schema 消費であり今回追加の dead code ではない。

- **マジックナンバー / 設定外出し: 3.5 / 5** — seed、B、期間、artifact path は module 定数化。
  一方、frozen再現条件 `425/65` とエラー文 `62.09%` (`:724-735`)、stake 100円、CI
  2.5/97.5、AUC tolerance `1e-5`、進捗200 race は spec 化・根拠コメントがない。
  `BLOCKED_FEATURES` と `LIVE_VALUES` の二重キー管理も前回から残る。

- **テスト容易性 / 副作用分離: 4.5 / 5** — paired計算は pure helper で、同一 ledger の差0と
  shared-resample 決定性を検証 (`tests/test_f3_phase0_0_eval.py:71-89`)。保存モデルのAUC再現も
  integration test 化。対象実測 **11 passed in 3.90s**、全体は報告値 **377 passed / 4 skipped**。
  `samples=0` の public orchestration 処理前拒否、reference/calibrator 衝突、`config.py` / DB /
  evaluator source の拒否 test を追加。非同一ledger、3 basis、
  missing payout、片側0 bet、ledger key/day不一致も残る。artifact依存 test は clean checkoutで
  必要ファイルが無い場合に単体で完結しない。

- **エラー処理 / ログ / 長時間実行安全性: 4.5 / 5** — read-only DB、sealed guard、実行前後の
  production SHA、treatment-first fail-closed、validation再現失敗時のcontrol未実行は妥当
  (`scripts/f3_phase0_0_eval.py:720-770,820-822`)。`_evaluate_oos()` の monkeypatch は
  `finally` 復元される。JSON/report の atomic replace と evaluator commit 追加も前進。一方、
  `run_paired_oos()` は `samples <= 0` を DB/model 読込前に拒否し、reference/calibrator も protected
  入力へ追加。JSON/report は canonical な固定出力だけを許すため既存 project file を上書きできない。
  減点は、重い OOS を直列実行して
  最後にだけ JSON を書くため、後半失敗時に前半成果を再利用できない。checkpoint/resume、構造化
  logger、途中 manifest はなく、進捗 `print` は `i % 200 == 0` と bet race が偶然一致した時しか
  到達しない (`:389-391`)。post-hash も例外終了時には確認・記録されない。

## 停止条件チェック

- [x] **コード・モデル provenance** — `rules_sha`、evaluator SHA、model/feature SHAを記録。
  保存済み artifact の evaluator commit `af13474` と SHA は当該 historical source に一致する。
  現 HEAD は安全性のみを変更した `5b4d43d` で artifact 自体の再計算は不要だが、将来実行では
  `evaluator_commit` と現 evaluator SHA を自動記録する。
- [x] **baseline paired 比較** — control/treatment の race-id集合を一致検査し、同一 day index を共有
  (`scripts/f3_phase0_0_eval.py:745-762`)。50日・10,000/10,000 valid samplesをartifactから再導出。
- [x] **payout欠損** — ledgerに `payout_present` を持ち、固定race basisでは欠損を除外・計数
  (`:542-550,594`)。今回 artifact は各 basis に `excluded_missing_payout` を保存。
- [x] **production/封印安全性** — production 4 artifact の前後 hash 一致、
  `production_artifacts_unchanged=true`、sealed access falseをartifactで確認。
- [x] **出力先安全性** — paired JSON/report を固定 canonical path に限定。production/cache/
  reference/calibrator/既知artifactに加え、`config.py`、DB、evaluator source の反例を全拒否。
- [x] **引数 fail-fast** — `run_paired_oos()` 冒頭で `samples <= 0` を即拒否し、entry-point
  regression test で DB/model に到達しないことを確認。
- [ ] **paired artifact の実行時 dirty/env snapshot** — evaluator content hashで実行コードは同定可能だが、
  `git_status_short` と `_evaluate_oos()` の effective env/calibrator/reference 要約はpaired JSONへ未転記。
  監査性の優先改善事項。今回のコード品質判定を覆す実行不一致は実測されなかった。
- [x] **P25 market snapshot / factorial / fresh odds** — type-Bのため N/A。

## 反証の試み

- 主張「paired bootstrap が同じ day-block 標本を使う」に対し、実装で乱数 index が一度だけ生成され、
  control/treatment双方が同じ `indices` を参照することを確認 (`:574-585`)。さらに同一ledger testは
  point/CIとも厳密に0で **成立** (`tests/test_f3_phase0_0_eval.py:71-89`)。
- 主張「保存済み treatment を再利用して同じ OOS を再現する」に対し、validation AUCの実artifact
  再推論 test成功、paired artifact の `treatment_oos_reproduced=true`、425 bets/65 hits一致を確認。
- 反例候補「race集合は同じでもdayがモデル間でずれる」は join 時に treatment dayだけを採用し、
  day一致をassertしていない (`scripts/f3_phase0_0_eval.py:749-755`)。現 harness ではrace_id由来日付のため
  不一致は起きにくいが、境界 invariant として未検証。

## 検証結果

- `git log --stat -3`: 最終 HEAD `fa1d491`。任意 output_dir を含む固定出力先 guard と回帰 test を含む。
- `pytest tests/test_f3_phase0_0_eval.py -q`: **11 passed in 3.90s**。
- 全体 test（親実行報告）: **377 passed / 4 skipped**、paired contract OK。
- AST parse: script/testとも成功。対象 scriptの未使用 import候補0。
- 最終 code/test は commit `fa1d491`。`git diff --check` はエラーなし。
- 必須 scan: `predictor/rules.py` は def **20件**、直書き `score +=/-=` **1件**。
- print scan: gui/predictor/jvlink_client/web は9件。今回 script の2件はCLI進捗/最終JSONでdebug残骸なし。
- `paired_oos.json`: self-selectedは50日/471 races、10,000 valid samples、差
  `+0.010190899`、CI `[-0.046736630, 0.064105634]`。artifact の evaluator SHA は記録 commit
  `af13474` の historical source と一致し、その後の差分は出力安全性・provenanceのみ。

## 主な改善提案

1. **atomic temp を並行実行対応にする** — 固定 `.tmp` でなく同一dirの unique tempfileを使い、
   同時実行時の一時ファイル衝突を避ける。
2. **長時間runを再開可能にする** — treatment ledgerをhash付き中間artifactへatomic writeし、
   model/rules/filter/calibrator hash一致時だけcontrol再開に利用する。
3. **paired provenanceを自己完結させる** — dirty status、effective env、
   reference/filter/calibrator hash、各run elapsed/race countsをpayloadへ転記する。`:788-827`。
4. **paired invariantを固定する** — joined非空、control/treatment day一致を
   明示検証し、非同一ledger・3 basis・欠損・片側0 betのparametrized testsを追加する。`:510-616`。

## 前回からの差分

- DRY: 4.0 → 4.5（+0.5）— 既存 OOS harnessを両モデルで再利用し、paired resampleを1 helper化。
- dead code: 4.0 → 4.5（+0.5）— 新規経路は到達可能、未使用 import 0件を維持。
- マジックナンバー: 3.5 → 3.5（±0.0）— 定数化は維持したがfrozen件数/tolerance等が追加。
- テスト容易性: 4.0 → 4.5（+0.5）— entry fail-fast と危険な project path の回帰を固定。
- エラー/ログ/安全性: 4.0 → 4.5（+0.5）— canonical fixed outputs で destructive path を閉塞。
- 前回判定: **HOLD**。今回判定: **PASS**。総合は4.1→4.3（+0.2）。
