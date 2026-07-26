# 検証プロセス監査人 採点 — F3 Phase 0 fail-closed

## 判定: PASS

**理由**: type-C（ledger / migration）+ type-D（production consumer）を主対象とする非採用改修。初回監査の停止条件だった healthy `full + []` の誤拒否と、日次 pipeline での mode bit 8 消失は修正され、監査者の直接反証と全 suite で green。Batch/member status 矛盾も constructor で拒否する。DB migration、core、web / GUI / CLI / auto-predict / ledger / monitor の構造化契約に停止条件は残らない。  
**対象HEAD**: `2d6e6f60c4f82b4d7dd163a7a2f61d29fdb4348c` 上の未コミット差分（branch `codex/phase0-fail-closed`、監査時 `git status` dirty）  
**スコープ外**: P25 の利益戦略採用、market snapshot factorial C1-C5、fresh odds 収益寄与は N/A。今回、予想数値の改善・採用は主張されていない。  
**次アクション**: 非停止課題として mixed-mode GUI と feature preflight 例外時の backtest 意味を integration test で固定し、結果文書の G1/G3/G5 記述を最新実装へ同期する。

## 総合: 4.2 / 5（参考スコア）

- 初回監査: **3.6 / 5・FAIL**
- 再監査: **4.2 / 5・PASS**（+0.6）。停止条件2件の red→green、Batch/member整合検証、focused / full suite の再実測による。
- 時系列上の前トピック（`20260720_1905_f3_morning_anchor`）: **3.4 / 5・HOLD**

## 項目別

| 採点軸 | 今回 | 根拠 |
|---|---:|---|
| バックテスト設計の正しさ | 4/5 | `scripts/backtest.py` 自体に diff はなく、production-only の `is_production_buy_candidate` と従来の `is_buy_candidate` を分離。通常データは G3 golden と G4 exact validation で非破壊を確認した。ただし `predictor/rules.py:1466-1479` は従来 raise していた feature preflight 例外を blocked rule-only batch に変え、`scripts/backtest.py:815` は mode を確認せず集計するため、異常データ時の旧停止意味は integration test 未固定。 |
| 時系列リーク防止 | 5/5 | `predictor/features.py:134,332,357,716` 等は当該日を `< before_date` で除外し、同日 bias は `predictor/features.py:386,429,485` の `start_time < ?` を維持。監査者が `f3_phase0_0_eval --skip-oos` を一時出力先で再実行し、control AUC **0.7913195088860858** / treatment AUC **0.7887806982333265**、production artifacts unchanged=true を再導出した。OOS 非実行と凍結済み 425 bets / 62.0941% の参照は `docs/F3_phase0_fail_closed_result.md:43` に明記され、G4 の許容条件どおり。 |
| calibration / reliability 計測 | 4/5 | exact validation は Brier / LogLoss も再出力し、control **0.06152239057336797 / 0.22251022597610776**、treatment **0.06166960895115952 / 0.22329900811964803** を実測。`scripts/monitor.py:88-128` は observation / blocked を暗黙除外せず mode / reason 内訳を併記する。`predictor/calibrator.json` は isotonic、47,884件、2025-01-01〜12-31 fit を記録し、2026 OOS と分離。今回新規の reliability bin / clustered CI はないため満点ではない。 |
| A/B比較 / バージョン管理・受入証拠 | 4/5 | 再監査で full suite **440 passed / 4 skipped**、focused **96 passed**。healthy `full + []`、bit 8 分岐、Batch/member矛盾拒否を直接再実行した。G1 の旧assertは現行コードに対し blocked / observation となるため red を独立再構成でき、現行 structured assert は green。G3 は rule-only の全既存fieldと full/LGBM の主要numeric goldenを固定。ただし作業ツリーは未コミットで、結果文書は test数・G1詳細・G3範囲・bat変更有無が最新状態へ未同期。 |
| 過適合監視 / 期間分割評価 | 4/5 | 本改修は採用判断を行わず、train/validation、2026 OOS、2026-10-01以降 sealed の既存分割を変更していない。exact validation のみ再実行し、OOS skip を明記して凍結値を参考扱いに限定したため自己参照はない。OOS を今回独立再実行していない分だけ 5 点は付けないが、設計上許容された省略であり HOLD 要因ではない。 |

## 初回重大指摘の是正確認

### RESOLVED — healthy auto-predict

`scripts/auto_predict.py:42-45` は key欠落 / `None` のみ E04 default とし、空 list を保持する。監査者が `_parse_generation_status(SimpleNamespace(returncode=0, stdout='{"prediction_mode":"full","error_reasons":[]}'))` を再実行し、**`("full", [])`** を確認。`tests/test_auto_predict_artifacts.py:88-95` に正常系回帰テストが追加された。

### RESOLVED — production 日次 pipeline の mode bit 8

`scripts/auto_predict_daily.bat:31-40` は `PREDICTCODE == 8` を `EXITCODE += 8`、その他の非ゼロを bit 2へ分岐する。静的contract testに加えて監査者が ASCII source を直接照合し、bit 8 mapping を確認した。

### RESOLVED — Batch/member status 不一致

`predictor/rules.py:296-302` は Batch status と全member status/reasonsを比較し、矛盾を `ValueError` で拒否。監査者の直接probeと `tests/test_prediction_fail_closed.py:162-177` が green。

## 残存課題（非停止）

- GUI は run-level mode を blocked 優先で集約しつつ、full race の `buy_candidates` は保持する（`gui/app.py:856-922,1008-1020`）。一方 banner は一律「買い候補は作成しません」（`:2323`）と表示する。web は mixed-mode 文言を分けているが、GUI test は source 文字列 assert のみ（`tests/test_gui_js_contract.py:68-75`）で、mixed-mode dashboard の整合を実行検証していない。
- feature preflight 失敗時、core は blocked の内部予想を返す一方、backtest は status を見ず集計する。LGBM欠損時の旧 rule-only 数値維持には必要だが、feature計算例外まで従来と同じかを固定したテストがない。
- `docs/F3_phase0_fail_closed_result.md:40-45` は 429 tests、G3「全field」、G5「bat/ps1変更なし」の旧記述のまま。現状は440 tests、G3は rule-only全field + LGBM主要numeric、batはbit 8保持のため変更あり。監査証跡として同期が必要。

## G1〜G5 監査

| Gate | 判定 | 監査結果 |
|---|---|---|
| G1 red→green | **PASS（独立再構成）** | 旧silent assert（LGBM例外 / model欠損でも full）は現行実装に対し blocked / observation となるため red、structured mode assert はgreen。結果文書は「2件red」とするが具体的失敗内容は監査時ファイルに見当たらず、文書同期は残る。 |
| G2 full suite | **PASS** | `.venv64/Scripts/python.exe -m pytest -q tests/` → **440 passed, 4 skipped in 15.81s**。focused consumer / migration / backtest → **96 passed**。 |
| G3 rule-only + full/LGBM golden | **PASS（範囲明記）** | rule-only は全既存field、full/LGBM は主要7 numeric fieldを固定。さらに G4 が実モデル/validation stack の exact数値を固定するため、本改修の正常数値非破壊を支持。 |
| G4 exact val / OOS skip | **PASS** | 監査者再実行で AUC 2値が exact match、Brier/LogLossも保存、production SHA不変。OOS skip と凍結値参照を明記。 |
| G5 artifacts / 非対象不変 | **PASS** | 一時評価の `production_artifacts_unchanged=true`。`scripts/backtest.py`、production model/features/meta/calibrator/weights、ps1 に対象diffなし。batは ASCII のまま bit 8保持の必要最小変更。 |

## migration / ledger / monitor

- `data/schema.sql:642-646` と `db.py:199-203` の両方に DEFAULT `full` / `[]` があり、旧schema 1行を作って `init_db` 後も既存主キー・行を維持する migration test が green。
- observation の各馬行、blocked 空結果の sentinel、自由文字列 / severity 矛盾拒否を `tests/test_prediction_log.py:48-115` で固定。focused 96 tests に含めて実測 green。
- monitor は非fullを Brier から勝手に除外せず mode / reason count を返す consumer test が green。これは指定契約と一致する。

## 停止条件チェック

- [x] 過去 backtest 複数件と rule_version 履歴あり（直近 filtered に p26 / p25 baseline を確認）
- [x] exact validation の期間・split・cache SHA・git SHA・production SHA を確認
- [x] OOS skip と参照元を明記、sealed holdout 非使用
- [x] full test suite と focused migration / consumer tests を監査者が再実行
- [x] G1旧assert red / structured assert greenを独立再構成
- [x] healthy `full + []` を含む auto-predict contract
- [x] rule-only全既存field + full/LGBM主要numeric golden
- [x] mode bit 8 が日次bat終端まで保持される
- [x] Batch/member status矛盾を拒否
- [x] P25固有 market snapshot / paired収益ゲートは改修タイプ上 N/A

## 反証の試み

初回に主張を崩した2反証を再実行した。健康 payload `full + []` は今回は `("full", [])`、日次batは rc=8 を bit 8へ保持し、どちらも成立しなかった。さらに full memberを observation Batchへ混入する反証は `ValueError: prediction batch status conflicts with member status` となった。全体440 testsもgreenで、初回停止条件は解消。

## 主な改善提案

1. **結果文書を実装へ同期** — `docs/F3_phase0_fail_closed_result.md:40-45` に G1 の具体的旧assert失敗、440/4、G3の正確な範囲、bat bit 8変更を記録する。
2. **異常系 backtest integration** — LGBM欠損は旧rule-only数値一致、feature preflight例外は採用する停止/除外/集計方針を明示し、mode別race countを artifactへ残す。
3. **mixed-mode GUI実行テスト** — full + blocked raceを同一dashboardへ渡し、候補数とbanner文言が矛盾しないことを Python API出力とJS renderの双方で固定する。
