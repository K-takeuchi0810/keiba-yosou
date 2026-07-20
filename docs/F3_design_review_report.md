# F3 事前登録文書と既存実装の整合レビュー

## 1. レビュー範囲

- 対象文書: 「競馬予想システム F3 事前登録・設計凍結ドキュメント」v1.0-draft（2026-07-20）
- 対象コード: commit `068efb0cce3d2b369942cced2d4601d04135f264` (`main`)
- 対象artifact: `predictor/lgbm_features.json`（112特徴）、`predictor/lgbm_meta.json`（`lgbm-v6-rel-draw-clean-tuned-fixed`）
- 実施方法: 静的コードレビューと既存テストの対応確認。コード、モデル、設定、DBデータは変更していない。
- 判定語:
  - **準拠**: 文書仕様を現行コードとテストで確認できる。
  - **不一致**: 現行挙動が文書仕様と異なる。
  - **未実装**: 対応する本番経路または出力が存在しない。
  - **部分実装**: 部品は存在するが本番経路への強制接続、時刻条件、テストのいずれかが不足する。

## 2. 結論

**現行実装は v1.0-draft を凍結できる状態ではない。Phase 0 と市場offsetモデルは新規実装に近い変更が必要である。**

主要な理由は次の5点。

1. 現行LGBMは馬単位のbinary classifierであり、レース単位categorical cross-entropyでも `log(q)` 固定offsetでもない（`scripts/train_lgbm.py:1-14, 262-300`）。
2. 推論後に各馬のbinary出力を合計1へ正規化しているが、これはレース単位softmax offset学習の代替にならない（`predictor/ml_model.py:114-165`）。
3. モデル欠損・特徴計算失敗時にrule-onlyへ縮退でき、`prediction_mode` / `error_reasons` によるfail-closedがない（`predictor/ml_model.py:35-75`, `predictor/rules.py:1391-1408`）。
4. PIT用 `odds_snapshots` と選択関数は存在するが、設定はT-10であり、予測・backtest経路はこの関数を呼ばず `horse_races.win_odds` を直接使う（`config.py:88-92`, `predictor/pit_gate.py:35-65`, `predictor/rules.py:1141-1149`, `scripts/backtest.py:136-156`）。
5. 112特徴artifactはG-MINを6個、G-POPを2個含む。さらにartifact外のrule scorerも人気、マイニング、当該レースの `leg_quality_code` を使うため、主challengerのG-OWN限定条件を満たさない（`scripts/train_lgbm.py:42-117`, `predictor/rules.py:543-581, 772-820`）。

なお、リポジトリ内の既存文書 `docs/F3_MARKET_RESIDUAL_DESIGN.md:56-61` はT-10、dev期間2026-07-04〜09-30、封印開始2026-10-01、800レース到達時判定を「確定」としている。今回のv1.0-draftはT-15かつ判定日未定であり、**凍結前に旧文書を廃止・superseded指定するか、どちらを正本とするか決定が必要**である。

## 3. 本文仕様との整合

### 3.1 第2節: レース単位multinomial softmax + 固定市場offset

| 仕様 | 判定 | 現行実装 | 差分 |
|---|---|---|---|
| レース単位categorical cross-entropy | **不一致** | 学習ラベルは馬単位0/1、LightGBM `objective=binary` / `binary_logloss`（`scripts/train_lgbm.py:9-14, 178-202, 278-300`） | レースgroupは保持するがbinary学習では損失に使っていない。 |
| `eta_i = log(q_i) + f(x_i)` | **未実装** | `init_score`、固定offset、同等のcustom objectiveはない。 | 市場確率は学習後の投資確率blendで初めて入る。 |
| `log(q)` 係数を1に固定 | **未実装** | offset自体がない。 | 固定を検査するテストもない。 |
| レース内softmax | **不一致** | rule側はscoreの指数正規化、LGBM側はbinary確率を単純に総和除算（`predictor/rules.py:941-971`, `predictor/ml_model.py:159-165`）。 | 推論時正規化だけで、学習損失はmultinomialではない。 |
| qを控除除去・レース内正規化 | **部分実装** | `1 / win_odds` をレース内合計で割る（`predictor/rules.py:1141-1149`）。 | no-vig正規化自体は同形だが、T-15 snapshotの保証がない。除外馬集合も明示固定されていない。 |
| 主f(x)はG-OWNのみ | **不一致** | 112特徴にG-MIN 6、G-POP 2。rule側にも人気・マイニングが入る。 | G-OWN allowlistと機械検査がない。 |
| binary logistic offsetを使わない | **形式上は未採用** | 現行はoffsetなしのbinary classifier。 | 禁止形式ではないが、要求形式にも準拠しない。 |

### 3.2 第4節: fail-closedと出力スキーマ

| 仕様 | 判定 | 現行実装 | 差分 |
|---|---|---|---|
| モデル欠損時に観察/買い停止 | **不一致** | artifact欠損・LightGBM未導入時は空dictとなり、rule-onlyへ縮退（`predictor/ml_model.py:45-65`, `predictor/ml_model.py:168-176`）。 | `full` 相当の予測を返せる。 |
| stale odds / PIT違反時に停止 | **未実装** | backtestには独自の鮮度除外があるが、NULL時刻を「歴史的確定オッズとして信頼」する（`scripts/backtest.py:136-156, 807-813`）。live `predict_race` は停止しない。 | 文書の `fetched_at IS NOT NULL` と逆。 |
| 必須特徴欠損時に停止 | **不一致** | 特徴計算失敗馬はLGBM入力からskip、モデル全体失敗時はrule-only。`feature_warnings` は警告のみ（`predictor/ml_model.py:140-165`, `predictor/rules.py:1365-1375`）。 | 欠損理由コード、レース単位停止がない。 |
| 理由をUIとログへ表示 | **未実装** | `prediction_mode` / `error_reasons` / E01〜E04が存在しない。 | `feature_warnings` は要求スキーマ・強制遷移の代替ではない。 |
| `p_market_no_vig` | **未実装（内部値のみ）** | `_market_probabilities` のローカルdictだけ。 | Prediction、ログ、HTML/CLI出力に保持されない。 |
| `p_rule_raw` | **未実装（内部値のみ）** | `raw_rule_prob` のローカルdictだけ。 | 出力されない。 |
| `p_lgbm_raw` | **未実装（内部値のみ）** | `raw_lgbm_prob` のローカルdictだけ。 | 出力されない。 |
| `p_model_calibrated` | **未実装（内部値のみ）** | `probability_by_num` は校正後だがPredictionへ保存しない。 | `win_probability` には別の投資blend後値を入れる。 |
| `alpha_vs_market` | **未実装** | 対応フィールド・計算なし。 | — |
| `expected_value = p * odds - 1` | **不一致** | 現行は `p * odds`（gross return multiple）で、1を引かない（`predictor/rules.py:1260-1276`）。 | 名前が同じでも意味が1.0ずれる。 |
| `odds_snapshot` | **未実装** | `Prediction` / `prediction_log` にsnapshot ID・fetched_atなし。 | ログには発行時オッズだけを保存。 |
| `prediction_mode` | **未実装** | フィールドなし。 | — |
| `error_reasons` | **未実装** | フィールドなし。 | — |
| p26 monitor baseline再凍結 | **未実装** | calibratorに期間・rule versionはあるが、本文のbaseline定義・hash・凍結日を一体で記録したartifactは確認できない。 | 付録Cの記入が必要。 |

現行 `Prediction.win_probability` は、コードコメント自身が「calibrator + market blend + odds discount後でレース内非正規化、確率として解釈不能」と明記している（`predictor/rules.py:228-234`）。この値をGUI、HTML、filter、prediction logが「勝率」として使用している（`predictor/rules.py:1411-1448`, `gui/app.py:870-875`, `web/generator.py:336-380`, `db.py:738-772`）。第4節の分割は表示上の改名ではなく、内部契約の是正が必要である。

### 3.3 第5節: fetched_at / T-15データ適格条件

| 仕様 | 判定 | 現行実装 | 差分 |
|---|---|---|---|
| `fetched_at IS NOT NULL` | **部分実装** | `odds_snapshots.fetched_at` はNOT NULL、`usable_snapshots` もNULL除外（`data/schema.sql:596-614`, `predictor/pit_gate.py:53-65`）。 | 本番予測・backtestがこの入口を使用していない。 |
| T-15以前 | **不一致** | `PIT_GATE_MINUTES=10`（`config.py:88-92`）。既存テストもT-10を検証（`tests/test_pit_gate.py:30-49`）。 | 文書はT-15。 |
| backtestとliveで同一snapshot選択 | **未実装** | `usable_snapshots` の参照は同モジュールとunit testのみ。 | 実経路の強制接続テストがない。 |
| 上書きレコード除外 | **部分実装** | `odds_snapshots` は時系列appendだが、現行予測はUPDATEされる `horse_races.win_odds` を読む。 | 使用snapshotのIDと選択規則が出力されない。 |
| 発走後・時刻矛盾除外 | **部分実装** | `usable_snapshots` はcutoff後をSQL除外。backtest独自ゲートはpost-startを除外可能。 | NULL時刻を信頼し、T-15ではなく、live停止へ接続しない。 |
| 97%汚染期間の機械除外 | **未実装** | 汚染期間を一意に定義したmanifest / evaluator gateを確認できない。 | 凍結前に期間と学習可否を確定する必要がある。 |

## 4. 付録Aチェックリストの現状

| # | チェック項目 | 現状判定 | 検証可能性 / テスト状況 |
|---:|---|---|---|
| A1 | レース単位categorical cross-entropy | **不一致** | コードでbinaryと確認可能。要求損失のテストなし。 |
| A2 | 全出走馬へのレース内softmax | **不一致** | ruleの指数正規化とLGBM総和除算は確認可能だが、学習softmaxではない。要求を保証するテストなし。 |
| A3 | `log(q)` が学習不可offset、係数1固定 | **未実装** | `init_score` / custom objective / fixed tensorなし。テストなし。 |
| A4 | qが控除除去後Σ=1（許容誤差1e-6） | **部分実装** | `_market_probabilities` は総和正規化するが、T-15入力・全適格馬集合・Σ誤差の専用テストなし。 |
| A5 | T-15以外のオッズ混入なし | **不一致** | T-10設定、PIT入口未接続、rule・market blendが `horse_races` を直接参照。`test_pit_gate` は孤立unit test。 |
| A6 | binary logistic offset形式を不採用 | **要再実装後検査** | 現行はoffsetなしbinary。禁止形式ではないが要求モデルではない。将来の回帰防止テストなし。 |
| A7 | f(x)にG-MKT/G-POP/G-MINなし | **不一致** | artifactはG-MIN 6、G-POP 2。rule側にはさらに人気・マイニングがある。allowlist testなし。 |
| A8 | 取消・除外後の再正規化がtrain/eval同一 | **部分実装 / 未保証** | 異常馬はrule scoreを-1000としてrule確率を0にするが、LGBM推論入力と学習datasetには残り得る（`predictor/rules.py:575-581, 941-959`; `scripts/backtest.py:572-593`; `scripts/train_lgbm.py:175-202`）。JG取込テストはあるが、モデル母集団の一致テストはない。 |

既存テストで近いものは次のとおりだが、付録Aの適合を保証しない。

- `tests/test_pit_gate.py`: cutoff・NULL/late snapshot除外・時系列insertを検証。ただしT-10で、本番経路接続は未検証。
- `tests/test_features_f1_f2.py`: train/serveのfeature vector parityを検証。特徴群allowlistやavailable_atは未検証。
- `tests/test_market_popularity_scoring.py`: 現行の人気補正・blend ablationを検証。市場offsetモデルのテストではない。
- `tests/test_scratches_win5.py`: JG parse/DB保存を検証。softmax母集団の除外・再正規化は未検証。

## 5. 112特徴の仮分類

### 5.1 分類方針と集計

- G-MKT: 現在レースのオッズ、市場確率、人気順位、オッズ由来量。
- G-POP: 過去を含む人気・支持率由来量。
- G-MIN: JRA-VAN DM/TM mining由来量とそのレース内変換。
- G-OWN: 上記以外のレース条件、過去成績、関係者・血統・コース適性、派生量。ここでの「OWN」は独自性・知財性を証明するものではなく、本レビュー用の排他的な仮分類。

artifact 112個の集計は **G-MKT 0 / G-POP 2 / G-MIN 6 / G-OWN 104**。ただしartifact外で `predictor.rules` が `win_popularity`（G-MKT/G-POP）、`win_odds`（G-MKT）、`mining_predicted_order`（G-MIN）、現行 `leg_quality_code`（post-race疑い）を使用するため、この集計だけで主challengerの純度は保証できない。

リスク欄:

- **POST-HIGH**: 当該レース終了後に確定する値がhistorical replayへ混入する強い疑い。
- **PIT-UNPROVEN**: 発走前情報ではあり得るが、T-15以前の取得・確定を示すtimestamp/版管理がない。
- `—`: コード上は日付 `< current_race_date` の過去データまたは静的な事前情報。正式な付録B（available_at、pit_condition、レビュー署名）は別途必要。

| # | feature_id | 仮分類 | リスク / 根拠 |
|---:|---|---|---|
| 1 | `past_count` | G-OWN | — |
| 2 | `recent_avg_finish` | G-OWN | — |
| 3 | `recent_avg_finish_rate` | G-OWN | — |
| 4 | `recent_best_finish` | G-OWN | — |
| 5 | `recent_top3_count` | G-OWN | — |
| 6 | `recent_win_count` | G-OWN | — |
| 7 | `last_finish` | G-OWN | — |
| 8 | `days_since_last` | G-OWN | — |
| 9 | `burden_delta` | G-OWN | — |
| 10 | `current_starter_count` | G-OWN | **PIT-UNPROVEN**: T-15時点の取消反映後頭数をsnapshot化していない。 |
| 11 | `current_race_level` | G-OWN | — |
| 12 | `current_distance` | G-OWN | — |
| 13 | `best_top3_race_level` | G-OWN | — |
| 14 | `same_bucket_runs` | G-OWN | — |
| 15 | `same_bucket_top3` | G-OWN | — |
| 16 | `same_bucket_wins` | G-OWN | — |
| 17 | `estimated_leg_samples` | G-OWN | —（過去走のみ） |
| 18 | `class_level_runs` | G-OWN | — |
| 19 | `class_level_wins` | G-OWN | — |
| 20 | `class_level_top3` | G-OWN | — |
| 21 | `class_condition_top3` | G-OWN | — |
| 22 | `class_rise_points` | G-OWN | — |
| 23 | `class_drop_points` | G-OWN | — |
| 24 | `high_grade_close_loss` | G-OWN | — |
| 25 | `high_grade_midfield_close` | G-OWN | — |
| 26 | `recent_trend_delta` | G-OWN | — |
| 27 | `same_track_type_runs` | G-OWN | — |
| 28 | `same_track_type_wins` | G-OWN | — |
| 29 | `same_track_type_top3` | G-OWN | — |
| 30 | `same_distance_runs` | G-OWN | — |
| 31 | `same_distance_top3` | G-OWN | — |
| 32 | `same_course_runs` | G-OWN | — |
| 33 | `same_course_wins` | G-OWN | — |
| 34 | `same_course_top3` | G-OWN | — |
| 35 | `same_course_distance_runs` | G-OWN | — |
| 36 | `same_course_distance_top3` | G-OWN | — |
| 37 | `same_going_runs` | G-OWN | — |
| 38 | `same_going_top3` | G-OWN | — |
| 39 | `best_final_3f` | G-OWN | —（過去走のみ） |
| 40 | `avg_final_3f` | G-OWN | —（過去走のみ） |
| 41 | `best_time_per_100m` | G-OWN | —（過去走のみ） |
| 42 | `best_relative_time_diff` | G-OWN | —（過去走のみ） |
| 43 | `best_final_3f_rank` | G-OWN | —（過去走のみ） |
| 44 | `jockey_win_rate` | G-OWN | — |
| 45 | `jockey_rides` | G-OWN | — |
| 46 | `trainer_win_rate` | G-OWN | — |
| 47 | `trainer_runs` | G-OWN | — |
| 48 | `same_day_bias_score` | G-OWN | **POST-HIGH**: current horseの `leg_quality_code` を参照し、過去backtestでは当該レース後値が見える（`predictor/features.py:370-453`）。 |
| 49 | `same_day_gate_bias_score` | G-OWN | **PIT-UNPROVEN**: 先行レース結果を `start_time < current` で使うが、結果確定時刻を検査しない。 |
| 50 | `sire_surface_top3_rate` | G-OWN | — |
| 51 | `sire_surface_samples` | G-OWN | — |
| 52 | `sire_distance_top3_rate` | G-OWN | — |
| 53 | `sire_distance_samples` | G-OWN | — |
| 54 | `dam_sire_surface_top3_rate` | G-OWN | — |
| 55 | `dam_sire_surface_samples` | G-OWN | — |
| 56 | `dam_sire_distance_top3_rate` | G-OWN | — |
| 57 | `dam_sire_distance_samples` | G-OWN | — |
| 58 | `sire_going_top3_rate` | G-OWN | — |
| 59 | `sire_going_samples` | G-OWN | — |
| 60 | `dam_sire_going_top3_rate` | G-OWN | — |
| 61 | `dam_sire_going_samples` | G-OWN | — |
| 62 | `mining_dm_rank` | G-MIN | **PIT-UNPROVEN**: `mining_predictions` にfetched_atがなくT-15適格を証明できない。 |
| 63 | `mining_dm_time` | G-MIN | **PIT-UNPROVEN**: 同上。 |
| 64 | `mining_tm_rank` | G-MIN | **PIT-UNPROVEN**: 同上。 |
| 65 | `mining_tm_score` | G-MIN | **PIT-UNPROVEN**: 同上。 |
| 66 | `jockey_track_top3_rate` | G-OWN | — |
| 67 | `jockey_track_samples` | G-OWN | — |
| 68 | `trainer_track_top3_rate` | G-OWN | — |
| 69 | `trainer_track_samples` | G-OWN | — |
| 70 | `horse_track_top3_rate` | G-OWN | — |
| 71 | `horse_track_samples` | G-OWN | — |
| 72 | `sire_track_top3_rate` | G-OWN | — |
| 73 | `sire_track_samples` | G-OWN | — |
| 74 | `race_month` | G-OWN | — |
| 75 | `track_recent_30d_top3_rate` | G-OWN | — |
| 76 | `track_recent_30d_samples` | G-OWN | — |
| 77 | `track_recent_30d_avg_winning_pop` | G-POP | 過去勝ち馬の人気由来。日付は過去に限定。 |
| 78 | `track_recent_90d_top3_rate` | G-OWN | — |
| 79 | `track_recent_90d_samples` | G-OWN | — |
| 80 | `track_recent_90d_avg_winning_pop` | G-POP | 過去勝ち馬の人気由来。日付は過去に限定。 |
| 81 | `jockey_recent_30d_top3_rate` | G-OWN | — |
| 82 | `jockey_recent_30d_samples` | G-OWN | — |
| 83 | `jockey_recent_90d_top3_rate` | G-OWN | — |
| 84 | `jockey_recent_90d_samples` | G-OWN | — |
| 85 | `trainer_recent_30d_top3_rate` | G-OWN | — |
| 86 | `trainer_recent_30d_samples` | G-OWN | — |
| 87 | `horse_recent_90d_top3_rate` | G-OWN | — |
| 88 | `horse_recent_90d_samples` | G-OWN | — |
| 89 | `jockey_win_rate_rank_in_race` | G-OWN | — |
| 90 | `jockey_win_rate_z` | G-OWN | — |
| 91 | `recent_avg_finish_rate_rank_in_race` | G-OWN | — |
| 92 | `recent_avg_finish_rate_z` | G-OWN | — |
| 93 | `best_time_per_100m_rank_in_race` | G-OWN | — |
| 94 | `best_time_per_100m_z` | G-OWN | — |
| 95 | `sire_distance_top3_rate_rank_in_race` | G-OWN | — |
| 96 | `sire_distance_top3_rate_z` | G-OWN | — |
| 97 | `horse_track_top3_rate_rank_in_race` | G-OWN | — |
| 98 | `horse_track_top3_rate_z` | G-OWN | — |
| 99 | `mining_dm_time_rank_in_race` | G-MIN | **PIT-UNPROVEN**: mining元値にfetched_atがない。 |
| 100 | `mining_dm_time_z` | G-MIN | **PIT-UNPROVEN**: mining元値にfetched_atがない。 |
| 101 | `draw_position` | G-OWN | **PIT-UNPROVEN**: starter_countに依存し、T-15時点の取消反映版を固定していない。 |
| 102 | `leg_quality_available` | G-OWN | **POST-HIGH**: current `horse.leg_quality_code` の有無そのもの。raw leg_codeを除外しても欠損パターンで結果時点を識別し得る（`predictor/features.py:1031-1039`）。 |
| 103 | `same_day_bias_available` | G-OWN | **POST-HIGH / PIT-UNPROVEN**: current legの有無と先行レース結果の利用可否に影響される。 |
| 104 | `had_grade_run` | G-OWN | — |
| 105 | `bloodline_data_available` | G-OWN | —（coverage missingnessの期間ドリフトは別途監視推奨） |
| 106 | `is_wide_draw` | G-OWN | **PIT-UNPROVEN**: starter_count依存。 |
| 107 | `current_bucket` | G-OWN | — |
| 108 | `current_track_code` | G-OWN | — |
| 109 | `current_surface_family` | G-OWN | — |
| 110 | `current_going` | G-OWN | **PIT-UNPROVEN**: 馬場状態の取得・更新時刻を保存していない。 |
| 111 | `estimated_leg_code` | G-OWN | —（過去走のlegから推定。当該レースraw legとは分離） |
| 112 | `gate_zone` | G-OWN | **PIT-UNPROVEN**: starter_count依存。 |

### 5.2 artifact外の入力（主challenger純度に影響）

| 入力 | 仮分類 | 使用箇所 | 問題 |
|---|---|---|---|
| `horse.win_odds` | G-MKT | no-vig市場確率、投資blend、EV | T-15 snapshot IDを経由しない。 |
| `horse.win_popularity` | G-MKT / G-POP | rule score | fresh判定は「発走30分以内」でありT-15固定ではない。 |
| `horse.mining_predicted_order` | G-MIN | rule score・stability | main predictionへ直接混入。取得時刻を検査しない。 |
| current `horse.leg_quality_code` | G-OWN扱い不能（post-race疑い） | pace、same-day bias、availability | コメント上もpost-race値。historical replayとliveで可用性が異なる。 |
| rule probability | 複合 | LGBMとの既定50/50 blend | G-OWN-only LGBMを作っても、ruleを混ぜる限り主challengerはG-OWN-onlyにならない。 |

`predictor/lgbm_meta.json` のfeature importanceでも `mining_tm_rank` が最大、`mining_tm_score` が2位、`mining_dm_rank` が3位である。現行モデルは独自特徴の残差エッジを測るモデルではなく、mining依存モデルとして扱うべきである。

## 6. 凍結前に文書側で解消すべき点（数値は決定しない）

1. 新v1.0-draftと既存 `F3_MARKET_RESIDUAL_DESIGN.md` の正本関係を明記する。T-10/T-15とforward期間が同時に有効な状態を残さない。
2. 「控除除去」の具体式を明記する。現行の単純 `1/odds` 正規化を採用するなら、その式と除外馬処理を凍結する。
3. `expected_value` をnet edge（`p*odds-1`）とgross return multiple（`p*odds`）のどちらで保存・表示するか、フィールド名を含めて固定する。
4. 主challengerがG-OWN-onlyである範囲を、LGBM入力だけでなくrule blend・calibrator・second blendまで含むend-to-end pipelineとして定義する。
5. 同日先行レース結果をG-OWNとして許可する場合、結果確定時刻がcurrent raceのT-15以前であることを機械検証できる条件を付録Bへ追加する。
6. 取消・除外の母集団を「T-15時点の有効出走馬」に固定し、q算出、softmax、label、評価で同じ集合を使う規則を明記する。

## 7. Phase 0実装に進む際の優先順（提案のみ）

1. `Prediction` と永続ログを付録Cの明示フィールドへ分割し、既存 `win_probability` の曖昧な契約を廃止する。
2. レース単位のpreflightを1か所に集約し、モデル・snapshot・PIT・特徴allowlistのいずれかが失敗したら `full` を返せないようにする。
3. `odds_snapshots` からT-15の採用snapshotを決定し、live/backtestの両方へ同じ関数を強制する。snapshot ID/fetched_atを出力に保存する。
4. 112特徴を正式な付録B catalogへ変換し、まずPOST-HIGH 3件とG-MIN 6件を主モデルallowlistから遮断するテストを作る。
5. その後にレース単位offsetモデルと付録Aの数学的契約テストを実装する。現行binary artifactはbaseline/challenger比較用に残し、要求モデルと同一視しない。

プレースホルダ数値（CLV閾値、最低件数、EVマージン、ROI付帯条件、判定日、bootstrap block）は本レビューでは決定していない。
