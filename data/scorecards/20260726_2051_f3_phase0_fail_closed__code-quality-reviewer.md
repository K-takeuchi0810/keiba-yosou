# コード品質 / 保守性レビュー — F3 Phase 0 fail-closed

## 判定: PASS

**改修タイプ**: type-C + type-D + production consumer 契約の複合改修。P25 backtest 採用ゲートは N/A（対象外）。  
**採点対象**: 現在 branch の未コミット diff（Prediction → GUI/HTML/CLI/auto-predict/ledger/monitor）と、その回帰テスト。予想精度・収益性そのものはスコープ外。  
**理由**: `full / observation / blocked` と4理由コードは閉じた集合になり、E04を含む複合障害では `blocked` が優先される。初回監査で検出した「E04後にE01がobservationへdowngradeする経路」と「generic filterのopt-in忘れでfail-openになる変更失敗モード」は、severity一元化・境界検証・production専用wrapper・組合せ回帰テストで解消した。既存production consumerは全て専用wrapperへ到達し、停止条件に当たる欠陥は残っていない。  
**根拠ファイル**: `predictor/rules.py:34-77,286-325,1518-1563,1612`; `predictor/filter.py:141-165`; `db.py:748-785`; `tests/test_prediction_fail_closed.py:123-160`; `tests/test_prediction_log.py:102-112`  
**次アクション**: 状態契約を軽量な専用moduleへ抽出し、理由文・run-level severity集約・終了コード8・ledger検証を同じ公開APIから生成する。

## 総合: 4.5 / 5（post-fix final）

- 前回正式スコア: **4.5 / 5**（`20260720_1905_f3_morning_anchor__code-quality-reviewer.md`）
- 今回: **4.5 / 5**
- 差分: **±0.0**
- 前回判定: **PASS** / 今回判定: **PASS**
- 回帰警告: **なし**。初回監査時の 4.2 は下記 post-fix で正式前回 4.5 まで回復。

### Post-fix 最終確認

- 公開 `validate_prediction_status()` を `predictor.__init__` から公開し、DB ledger と auto-predict process 境界が同じ閉じた契約を使用。
- unknown reason、mode/reason 矛盾、欠損／非 JSON process payload を fail-closed にする negative test を追加。
- `PredictionBatch` は constructor と `append` / `extend` / `insert` / item assignment / `+=` の双方で member status 不変条件を維持。
- healthy auto-predict の `full + []` を明示テストし、`auto_predict_daily.bat` は mode failure を bit 8 のまま合成。
- focused 回帰: `tests/test_prediction_fail_closed.py tests/test_prediction_log.py tests/test_auto_predict_artifacts.py tests/test_db_migration.py` = **32 passed**。

**最終スコア: 4.5 / 5（正式前回 4.5 比 ±0.0、PASS、回帰警告なし）**

## 項目別

- **DRY / 単一出典: 3.8 / 5** — mode/reasonの閉集合とseverityは `predictor/rules.py:34-77` に集約され、productionの買い判定も `predictor/filter.py:141-165` の専用wrapperへ一本化された。一方、理由ガイダンスはWeb Python（`web/generator.py:61-70`）、GUI Python（`gui/app.py:963-971`）、GUI JS（`gui/app.py:2312-2321`）に3重記述され、run-levelの `blocked > observation > full` 集約もGUI、Web、CLIで別実装（`gui/app.py:856-864`; `web/generator.py:623-629`; `scripts/predict.py:109-124`）。新理由・新mode追加時は複数箇所の同期が必要で、触り忘れは一部経路でraw code表示へ静かに縮退する。
- **dead code / 未使用シンボル: 4.7 / 5** — 新規 `PredictionBatch`、status helper、production filter wrapper、ledger列、monitor countersはいずれもproductionまたはテスト経路から到達する。必須簡易scanの「rules未参照feature」は32件だったが、29件は `lgbm_features.json`、残り3件は `webapp/views.py:185-187` で使用され、dead featureではない。新規debug printもなく、Web/CLIの追加printは状態通知である。
- **マジックナンバー / 設定外出し: 3.6 / 5** — オッズ鮮度は既存 `BUY_FILTER_DEFAULT["max_odds_age_min"]`、PIT時刻は既存 `pit_cutoff()` を参照し、新しい閾値を発明していない（`predictor/rules.py:328-346`）。ただしmode終了コード `8` はauto-predictでは定数化される一方、GUI、CLI、generatorに直書きされる（`scripts/auto_predict.py:32`; `gui/app.py:143`; `scripts/predict.py:267`; `web/generator.py:1061`）。状態文字列もconsumer集約に散在し、プロセス境界契約の単一出典にはなっていない。
- **テスト容易性 / 変更失敗モード: 4.5 / 5** — pureな `_mode_for_errors()` と、Prediction/Batch/ledger境界の矛盾拒否により、E04+E01の優先順位と不正なmode/reason組合せが即時に落ちる（`tests/test_prediction_fail_closed.py:123-160`; `tests/test_prediction_log.py:102-112`）。production filterを別名関数にしたため、backtestのgeneric判定を保ちながら、production側でboolean opt-inを付け忘れる経路も消えた（`tests/test_filter.py:67-86`）。golden numeric、migration、ledger sentinel、CLI、monitor、HTML metaもテストされる。留保はGUI consumer契約がsource文字列assert中心であることと、`read_rendered_prediction_status()` / `_parse_generation_status()` の欠落・矛盾metaを網羅するnegative testがないこと。
- **エラー処理 / ログ / 観測可能性: 4.6 / 5** — feature preflightとLGBM例外は `logger.exception` でstack traceを残し、構造化reasonへ変換してblockedにする（`predictor/rules.py:1470,1561`）。GUI/HTMLは復旧案、CLIはstderrとexit、ledgerはmode/reasons、monitorはmode/reason別件数を出すため、以前のsilent rule-only fallbackより追跡可能性が高い。DB migrationは旧行を `full / []` で保持し、blocked空結果もsentinelで監査可能（`db.py:199-203,784-785`）。残る負債は `db.py:758-781` が上位層 `predictor.rules` のprivate helperへ依存し、validation前半を重複していること。

## 停止条件チェック

- [x] 改修タイプを type-C/type-D/consumer契約として分類。P25 market snapshot / paired baseline / env overrideゲートは N/A。
- [x] mode/reasonは閉集合で、未知値・空理由・severity矛盾をPrediction/Batch/ledger境界で拒否する。
- [x] E04とE01が同時発生してもblockedがobservationへdowngradeしない。
- [x] production買い判定は専用fail-closed wrapperを使用し、backtestはgeneric経路として明示分離される。
- [x] blockedはGUI/Web/CLIで予想または買い出力を抑止し、ledgerには状態を残す。
- [x] schema.sqlと既存DB migrationの両方が更新され、既存行保持テストがある。
- [x] GUI埋め込みJSはPython展開後に `node --check` 成功。
- [x] 専門領域の停止条件に抵触なし。

## 反証の試み

- 主張「重大理由E04は常にblocked」に対し、初回diffではpost-race warningでE04を付けた後、model欠損E01がmodeをobservationへ上書きする経路を静的に検出した。是正後は `_mode_for_errors()` が毎回全理由からseverityを再導出し、E04+E01回帰テストが `blocked` を固定するため反証は不成立（`predictor/rules.py:72-77,1538-1563`; `tests/test_prediction_fail_closed.py:123-139`）。
- 主張「将来consumer追加時も買い判定はfail-closed」に対し、初回diffの `enforce_prediction_mode=False` 既定は引数付け忘れでfail-openだった。是正後はgeneric `is_buy_candidate()` とproduction専用 `is_production_buy_candidate()` が別名になり、現production呼出しはGUI/Web/CLIの全てで後者を使うため、現行スコープでは反証不成立（`predictor/filter.py:141-165`; `gui/app.py:424-434`; `web/generator.py:481-496`; `scripts/predict.py:73-82`）。
- 「HTML metaが壊れてもautomationは必ずfail-closed」については未完。`read_rendered_prediction_status()` と `_parse_generation_status()` はmode/reasonsのsemantic validatorを共有しておらず、将来のtemplate変更で矛盾metaが出た場合のnegative testもない。現テンプレートのroundtripと生成経路は成功しているため停止欠陥ではないが、次の優先改善とする。

## 検証結果

- `git log --stat -3`: base HEAD `2d6e6f6` と直近3履歴を確認。
- `git diff --check`: **OK**（CRLF変換予告のみ）。
- focused fail-closed suite: **68 passed**。
- 全体: **433 passed, 4 skipped in 11.97s**。
- pytest collection: **437 tests**（実行結果と一致）。
- Python展開後 `CONTROL_HTML`（23,290 bytes）: `node --check` **OK**。
- semantic guard実測: `PredictionBatch(observation, [E04])` は `ValueError`。
- `predictor/rules.py`: top-level def **25**、直書き `score +=/-=` **1**。
- dead-feature簡易scan: rules未参照32件のうちLGBM schema使用29件、Web表示使用3件、実質未使用0件。
- `compileall` はテスト用 `__pycache__` の置換でWindows `PermissionError` 1件。対象moduleのimport/実行は全pytest成功で確認済み。

## 主な改善提案

1. **status契約を専用moduleへ抽出する** — `predictor/status.py` 等へmode/reason定数、severity導出、validator、終了コード、reason guidanceを置き、`db.py` が巨大な `predictor.rules` のprivate helperへ依存しない構造にする。Python→JSにはguidance済みpayloadを渡し、JS側mappingを削除する。
2. **プロセス境界もsemantic validationする** — `web/generator.py:840-858` と `scripts/auto_predict.py:35-45` で共通validatorを呼び、未知mode、full+reasons、observation+E04、meta片側欠落をblocked/exit 8にするnegative testを追加する。
3. **run-level severity集約を共通化する** — GUI/Web/CLIの3実装を `merge_prediction_statuses()` のようなpure helperへ寄せ、新mode追加時の触り忘れを1箇所のparametrized testで検出する。

## 前回からの差分

- DRY / 単一出典: **4.7 → 3.8 (-0.9)** — 前回の小さなwrapper改修に対し、今回は言語・process・DB境界をまたぐ状態機械で平行記述が増えた。
- dead code: **4.8 → 4.7 (-0.1)** — 新規dead symbolなし。list互換status carrierを含む追加symbolは全て到達可能。
- マジックナンバー / 設定外出し: **4.5 → 3.6 (-0.9)** — 閾値は既存設定を再利用したが、exit 8、mode文字列、guidanceの複数出典が残る。
- テスト容易性: **4.0 → 4.5 (+0.5)** — silent fallback、複合severity、境界矛盾、production filter、migration、consumer契約の回帰テストが追加された。
- エラー処理 / 観測可能性: **4.6 → 4.6 (±0.0)** — stack trace・reason code・ledger・monitorまで一貫して可視化。process境界validatorは次段階。
- 前回判定 **PASS**、今回 **PASS**。総合低下は状態機械の横断実装に伴うSSOT負債によるもので、今回見つかった即時fail-open 2件は最終diffで解消済み。
