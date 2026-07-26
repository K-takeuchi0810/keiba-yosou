# 予想ロジック分析官 採点 — post-fix 再監査

## 判定: PASS

**理由**: 初回HOLDの3指摘は解消した。`post_race:*` warning は E04/blocked に接続され、E04＋E01等の複合理由もseverity helperによりblockedを維持する。full/LGBM経路の既存数値golden、mode/reasonの型・ledger整合性検証、production専用buy wrapperが追加され、backtest/evaluatorの非強制も維持された。

## 総合: 4.4 / 5（初回監査 4.2 → post-fix 4.4、+0.2）

> 直前の別改修 scorecard は 4.3 のため、時系列比較では 4.3 → 4.4（+0.1）。以下の「初回監査」節は修正前の証跡として保持し、本節が最終判定を supersede する。

| 採点軸 | post-fix | 初回 | 差分 | 再監査結果 |
|---|---:|---:|---:|---|
| シグナル網羅性 | 4.5 | 4.5 | ±0.0 | シグナル・weightsは不変。既存の明示的な `post_race:*` 可用性シグナルだけをE04へ接続した。 |
| 重み妥当性 / 過適合リスク | 4.0 | 4.0 | ±0.0 | 重み・閾値・calibratorは不変。warning比率の新しいmagic thresholdを発明せず、既存のcritical markerを使用。 |
| 信頼度判定 / 確率推定 | 4.2 | 4.0 | +0.2 | full/LGBM経路で score/rank/win probability/EV/Kelly/raw blend の固定goldenを追加。正常数値不変を変更経路で直接検証した。 |
| デッドコード / 設計整合性 | 4.9 | 4.4 | +0.5 | `prediction_mode_for_errors` と `validate_prediction_status` を単一出典化。E04優先、未知reason、空reason、mode不一致を型とledgerで拒否。generic/production filterも責務分離した。 |
| 本番運用との乖離リスク | 4.6 | 4.2 | +0.4 | Web/GUI/CLIは専用 `is_production_buy_candidate` を使用し、generic filterを使うのはbacktest/evaluatorだけ。post-race依存を含む内部予想が本番買いへ漏れない。 |

## post-fix 指摘収束

- **E04 warning接続: RESOLVED** — `_has_blocking_feature_warnings` が既存 `post_race:*` markerを検出し、`prediction_mode_for_errors` がE04をblockedへ写像 (`predictor/rules.py:352-364, 1528-1533`)。availability warning単独は朝に期待されるため、新しいcoverage thresholdを作らず診断のまま維持する設計も妥当。
- **severity合成: RESOLVED** — E04が含まれれば他reasonに関係なくblocked、E01/E02/E03だけならobservation。反証実行で `[E04, E01] → blocked` を確認 (`predictor/rules.py:55-77`)。
- **mode/reason整合性: RESOLVED** — `Prediction`、`PredictionBatch`、ledgerが共通validatorを通り、full＋reason、non-full＋空reason、observation＋E04、未知reasonを拒否。`prediction_status` も矛盾入力をblocked/E04へ安全側補正する。
- **normal bit identity: RESOLVED** — rule-only goldenに加え、`conn + race + working LGBM + clean live status` のfull経路goldenを追加 (`tests/test_prediction_fail_closed.py:208-251`)。
- **production wrapper: RESOLVED** — Web/GUI/CLIの全3直接買い経路は専用wrapper。`scripts/backtest.py:715` と `scripts/f3_phase0_0_eval.py:364` はgeneric filterのままで、凍結評価を強制停止しない。

## post-fix 検証

- `.venv64/Scripts/python.exe -m pytest tests/ -q`: **437 passed, 4 skipped**。
- 関連8 testファイル: **72 passed**。
- 反証: 全馬 `post_race:leg_quality_code` ＋ model missing → **blocked / [E04, E01]**。
- production wrapper参照: `web/generator.py`、`gui/app.py`、`scripts/predict.py`。generic参照: backtest/evaluator。
- weights top-level 24 keys、magic-number検出は既存 `score -= 1000` の1件、`git diff --check` errorなし。
- 新たな重大指摘なし。OOS 425 bets / 62.0941% の重い再計算は今回も未実行だが、backtest非強制の呼び出し構造とfull数値goldenで本修正の対象経路を確認した。

---

## 初回監査（修正前・履歴）

## 判定: HOLD

**理由**: E01/E02/E03 と例外起因 E04 の構造化、現行 production consumer の買い抑止、backtest 非強制は成立している。一方、仕様で E04 の入力とされた `feature_warnings` の集計が mode 遷移に接続されておらず、全馬で必須データ欠損警告が出ても `full` のままになる。正常系 bit 一致も、変更の入った full/LGBM 経路では直接固定されていない。

**次アクション**: (1) 必須 warning の定義と既存集計に基づく race-level E04 閾値を実装・テストする、(2) `conn + race + working LGBM + PIT適格odds` の正常 full 経路で改修前全フィールド bit 一致を固定する。

## 総合: 4.2 / 5（前回 4.3 → 今回 4.2、-0.1）

> 評価対象: branch `codex/phase0-fail-closed`、base/HEAD `2d6e6f60c4f82b4d7dd163a7a2f61d29fdb4348c` の未コミット差分。`.Codex/agents/_rubric.md` は現 CWD に存在しないため、過去 scorecard の5軸と本role定義を継承した。前回は `20260720_1905_f3_morning_anchor__prediction-logic-analyst.md` の 4.3。

## 項目別

| 採点軸 | 今回 | 前回 | 差分 | 評価 |
|---|---:|---:|---:|---|
| シグナル網羅性 | 4.5 | 4.5 | ±0.0 | `features.py` / `weights.json` は無変更。E02/E03 が既存鮮度・PITシグナルを production status に接続したが、新シグナルや場面別重みは増減していない。 |
| 重み妥当性 / 過適合リスク | 4.0 | 4.0 | ±0.0 | weights/calibrator/閾値は不変。weights top-level 24 keys、直書き `score +=/-=` は既存の `score -= 1000` だけ。本変更で短期成績に追随した重み調整はない。 |
| 信頼度判定 / 確率推定 | 4.0 | 4.0 | ±0.0 | `_confidence`、temperature、shrink、calibrator、EV は不変。blocked 内部では従来比較用の確率を計算するが、現行 production 出力は抑止する。full/LGBM 正常経路の bit identity を直接固定するテストがないため加点しない。 |
| デッドコード / 設計整合性 | 4.4 | 4.8 | -0.4 | `PredictionBatch` の list 互換、閉じた reason enum、race/run status 集約、ledger sentinel は整合的。backtest は `enforce_prediction_mode=False` の既定で従来挙動を維持。ただし E04 が warning 集計に未接続で、production 強制も caller opt-in の fail-open default に依存する。 |
| 本番運用との乖離リスク | 4.2 | 4.0 | +0.2 | Web/GUI/CLI/auto-predict/ledger/monitor まで mode/reason が伝搬し、現行買い経路は非fullをゼロ化する。E04欠損警告の取り逃しと、将来 consumer が opt-in を忘れる余地が残るため 4.2 止まり。 |

## 重大な指摘

### 1. [高] E04 が `feature_warnings` 集計に接続されず、広範な欠損を `full` で通す

- 仕様は `E04_FEATURES_INCOMPLETE` を「必須特徴の計算失敗が閾値を超えた」とし、既存 `feature_warnings` 集計を使うよう明記している (`docs/codex_f3_phase0_fail_closed.md:70-77`)。
- 実装は warning を各馬へ付けるだけ (`predictor/rules.py:1459-1469`) で、mode 決定は preflight の例外または LGBM例外だけ (`:1485-1494`, `:1521-1525`)。
- 反証実行: 全2頭に `leg_quality_unavailable`、`same_day_bias_unavailable`、`post_race:leg_quality_code`、`post_race:same_day_bias` を付けても `prediction_status == ('full', [])`。
- これは「必須特徴欠損で full を返さない」という正本 §4.4 の一部を未実装にする。少なくとも必須warning集合、race-level比率、閾値の単一出典と境界テストが必要。

### 2. [中] G3 の bit 一致テストが、変更された正常 full/LGBM 経路を通らない

- `test_normal_rule_only_existing_fields_golden` は `predict_race(horses)` で `conn/race` を渡さず、`use_features=False`。新しい feature preflight、live odds、model coverage check をすべて迂回する (`tests/test_prediction_fail_closed.py:116-155`)。
- 報告の G4 は `--skip-oos` で val AUC のみ。val再現は保存モデルの品質確認であり、`predict_race` の正常 full 出力全フィールド bit 一致の代替にならない。OOS 425 bets / 62.0941% は今回未再実行。
- 実コード比較上、正常時の数式変更は見当たらないが、受入証拠としては不足。full経路の改修前goldenを追加すべき。

### 3. [中] production 抑止 API が opt-in default で、将来 caller は fail-open

- `is_buy_candidate(..., enforce_prediction_mode=False)` は後方互換と backtest非破壊には有効 (`predictor/filter.py:38-79`)。
- 現行 Web/GUI/CLI はすべて `True` を渡し、scope内では買い抑止できている。反証でも blocked 内部値が買い条件を満たすケースで default=True相当は通過、production opt-in は拒否した。
- ただし fail-closed の安全性が全 production caller の記憶に依存する。将来経路向けに production wrapper、consumer種別の必須引数、または明示 evaluation API へ分離すると再発耐性が上がる。

## 指定観点の監査

- **normal bit identity: PARTIAL** — rule-only既存フィールドgoldenは bit一致。full/LGBM経路は未固定。
- **backtest非強制: PASS** — `scripts/backtest.py:715` と `scripts/f3_phase0_0_eval.py:364-366` は新フラグを渡さず、statusを無視して従来計算を続ける。フィルタ単体testも default非強制 / production強制を固定。
- **E01: PASS** — model不在は observation + structured reason。rule-only値は観察表示に限定。
- **E02: PASS** — 既存 `max_odds_age_min` と `odds_age_minutes` を再利用し observation。
- **E03: PASS** — `pit_cutoff` を再利用し、NULL/欠損/T-10超過を observation。backtestのオッズ選択は変更していない。
- **E04: PARTIAL** — feature/LGBM例外とmodel出力馬集合不一致は blocked。ただし warning集計による広範欠損は未実装。
- **blocked内部計算: PASS（条件付き）** — core は比較・monitor/backtest用に2頭分の確率/EV/Kellyを保持する。Webは表を隠し、GUI/CLIはraceをskip、ledgerは空馬番sentinel、production filterはfalse。内部値の存在自体は意図された層分離と整合するが、前記opt-in依存は残る。
- **monitor: PASS** — observation/blockedをBrierから勝手に除外せず、mode/reason件数を併記する契約どおり。
- **reason closure: PASS** — `Prediction` / `PredictionBatch` / ledger が未知 reason/mode を拒否する。

## シグナル・確率・dead feature 必須確認

- `.venv32/Scripts/python.exe` で `weights.json` を読出し: 24 top-level keys。今回差分なし。
- magic number検出: `predictor/rules.py:667 score -= 1000` の既存1件。今回追加なし。
- `features.py` の `feat["X"]` は98 key、`rules.py` の直接 `feat.get("X")` は75 key。未直接参照keyはLGBM artifact等の消費もあるため単純差分だけでdead認定しない。features/rulesのシグナル削除差分はない。
- calibrator/temperature/shrinkは差分なし。既存 `min_count` 恒等寄せ + Bayesian alpha shrinkを維持。

## 検証

- `git log --stat -3` / 対象全 `git diff` / `git diff --check`: 確認済み。whitespace errorなし。
- `.venv64/Scripts/python.exe -m pytest tests/ -q`: **429 passed, 4 skipped**。
- fail-closed関連8ファイルの絞込み: **64 passed**。
- full-warning反証: 全馬に4 warningでも **mode=full / reasons=[]**。
- blocked反証: preflight例外で **mode=blocked / len=2**、内部EV/Kellyあり。filter defaultは通過、production強制は拒否。
- `predictor/features.py` / `weights.json` / `calibrator.json` と production artifact は本差分で無変更。
- 本レビューで編集したのはこの個別scorecardのみ。

## 前回からの差分

- シグナル 4.5、重み 4.0、確率 4.0 は据え置き。
- 設計整合性 4.8 → 4.4: status構造は良いが、E04 warning契約漏れとcaller opt-in依存を減点。
- 本番乖離 4.0 → 4.2: 朝アンカーの将来受入待ちとは別に、今回の現行consumer伝搬・表示・買い停止・ledger記録は具体的改善。
- 総合 4.3 → 4.2。E04接続とfull経路golden完了後は再評価可能。
