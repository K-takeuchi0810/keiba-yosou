# 予想ロジック分析官 採点 — 「今日」の決定を jst.py に集約 (commit `37eaf61`, branch `jst-date-unify-20260920`)

## 判定: PASS

**改修タイプ**: type-B/D 混成 (運用層 + `web/generator.py` の非予測行 1 箇所)。`git diff main..HEAD --stat` は
`jst.py` (新規) / `scripts/auto_predict.py` / `scripts/auto_predict_daily.bat` / `scripts/notify_dedup.py` /
`tests/test_jst_date.py` / `web/generator.py` の 6 件。`predictor/` `config.py` への差分は **0 行**
(`git diff main..HEAD --stat -- predictor config.py` が空)。P25 固有ゲート (A/B/C 層 factorial /
bonus_subset_metrics / calibrator refit / market_snapshot) は **N/A (対象外)**。

**理由**: 予測そのもの (特徴量・モデル・calibrator・PIT) に触れる経路は 0。封印 6 成果物は `SEALED_ARTIFACTS`
を直接 sha256 して **6/6 一致** (`artifact_drift()` は `SEALED_FROM=None` で短絡するので使っていない)。
`jst.py` は stdlib のみ import し、`predictor.rules/features/filter` の import 閉包に `jst` は入らない
(実測 False)。停止条件抵触なし。ただし依頼者の前提「generator の today は本番経路で使われない」は
**不成立** (下記反証 1) で、コミット内コメントも同じ誤りを含む。値は JST ホストでは不変なので実害なし。

**根拠ファイル**: `web/generator.py:20,315-317,603`、`scripts/auto_predict.py:270-287,339`、
`config.py:250-297,309-344`、`predictor/rules.py:64-86,122-125,999-1012`、`scripts/predict_t10.py:120,249`、
`scripts/predict_t10.bat:10`、`tests/test_jst_date.py:114-133`

**次アクション**: (1) `web/generator.py:312-314` のコメントを「publish 完全性判定 (:603) の対象日にも使う」に訂正。
(2) `scripts/predict_t10.py` の対象日既定 (:249) を `current_jst_daystamp()` に寄せ、guard の対象に加える
(PIT の `now` (:120) は naive `start_time` と比較するため aware 化は別途設計)。(3) guard 正規表現に
`datetime\.now\([^)]*\)\.strftime` を追加。

## 総合: 4.7 / 5 (参考スコア)

## 依頼 5 点への回答 (主張を鵜呑みにせず再導出)

| # | 依頼 | 検証 (本セッション実行) | 結果 |
|---|---|---|---|
| 1 | `generator.py:315` の today は本番経路で未使用か | `auto_predict.py:339` は `--from day --to day` を必ず渡す → 既定窓 (:316-317) は未使用。**しかし** 同じ `today` 変数が `:603 assess_race_completeness(rendered_days, today=today)` に渡り、publish 完全性 alert の対象日になる (grep `\btoday\b` で 4 箇所) | **部分的に不成立**。既定窓は未使用だが publish alert が消費。旧: local date、新: JST date。JST ホストでは同値、非 JST ホストでは `day` (JST) と一致するようになり**整合は改善** |
| 2 | import 順・循環・副作用 | `jst.py` は `datetime` のみ import。`generator.py:20` は `sys.path.insert` 後・`config` import 前。`import web.generator` 後の `sys.modules` に notify/auto_predict は 0 件、`jst` はあり。predictor 3 モジュールだけの閉包に `jst` は **無い** | 循環なし・副作用なし |
| 3 | 予測に効く経路 / 封印ハッシュ | `predictor/` 差分 0 行。6 件 sha256 直接比較 | **6/6 一致**。予測経路への影響 0 |
| 4 | `predictor/` に残る「今日」 | `predictor/rules.py:124` (`datetime.now()` local) のみ。calibrator 互換の `expires_on=2026-09-30` 判定に使うが、現行は `expected_rules_version == RULES_VERSION == p26-lgbm-v6-2026-07-03` で `:1000` の分岐に入らず **到達不能**。到達しても `:1008-1012` の log 出力のみで確率は変えない。`predictor/risk.py:170,194` は台帳の時刻刻印 | PIT 判定・特徴量には効かない |
| 5 | backtest / 学習窓 / 封印窓の境界解釈 | `scripts/backtest.py:1298-1299` は `--from/--to` required。`guard_analysis_window` (`config.py:309-348`) は時計を読まない。`DATA_SPLIT` は静的定数。`sealed_window_started` (`config.py:270`) は `date.today()` local で **未統合**だが `SEALED_FROM=None` で現在は短絡 | 境界解釈の変化なし。封印開始後の drift 検査開始日だけ local 時計依存が残る (JST ホストでは同値) |

## 項目別

- **シグナル網羅性と市場残差性: 5/5** — 予測シグナルの追加・削除なし (predictor 差分 0 行)。
- **重み妥当性 / 過適合リスク: 5/5** — `weights.json` `calibrator.json` `lgbm_*` `second_blend.json` の 6 件 sha256 が `SEALED_ARTIFACTS` と一致 (独立再計算)。paired ablation は N/A。
- **信頼度判定 / 確率推定の構造: 5/5** — raw→blend→calibrate→normalize 経路に差分なし。predictor 閉包に `jst` 不在を実測。calibrator 互換状態は `match` (今日 / 2026-10-01 注入とも)。
- **デッドコード / 設計の整合性: 4/5** — 留保 4 件。(i) `generator.py:312-314` のコメント「通常運用では使われない」は `:603` の消費と矛盾 (誤解を招く記述)。(ii) `jst.py` docstring「『今日』を決める唯一の場所」に対し、`scripts/predict_t10.py:249` (対象日既定) / `config.py:270` (`sealed_window_started`) / `gui/app.py:405` (`_date_range`) が独自に日付を作ったまま。(iii) `tests/test_jst_date.py:128-129` の guard は `date.today()` `datetime.now().date()` `datetime.today()` のみ検出し、`datetime.now().strftime("%Y%m%d")` 形 (repo 内で最も多い書き方: `predict_t10.py:249` `gui/app.py:405` `fetch_mining.py:20`) を**素通し**する。auto_predict にこの形で戻しても落ちない。(iv) `jst` は aware datetime を返すが、`odds_age_minutes` / `due_races` は naive `fetched_at` / `start_time` と比較する。将来 `current_jst_datetime()` をそのまま `now=` に流すと `TypeError` (aware vs naive) になる。設計上の注意書きが `jst.py` に無い。
- **本番運用との乖離リスク (train-serve skew): 4.5/5** — 予測経路の入力・コードパスに変化なし。留保: F3 正本を書く T-10 経路 (`register_predict_t10_task.ps1` → `predict_t10.bat` → `scripts.predict_t10`、5 分毎) の対象日 (`:249`) と PIT 時計 (`:120 now = datetime.now()`、`actionable = mins > 0` を決める) が **今回の統合の外**にあり、`predict_t10.bat:10` のログ日付も PowerShell `Get-Date` (local) で auto_predict 側と別出典。JST ホストでは同値なので現時点の skew は 0 だが、「今日を 1 箇所で決める」という改修の目的に対して、最も金銭・判定に直結する時計が残った。

## 停止条件チェック

- [x] 改修タイプを type-B/D と分類し、predictor/config 差分 0 行を確認
- [x] 封印成果物 6 件のハッシュを直接 sha256 で独立再計算して一致
- [x] import 閉包を実測 (generator→jst あり・jst→project 0、predictor→jst 無し)
- [x] `tests/test_jst_date.py` 12 passed、関連 (generator/auto_predict/notify/sealed/guard/publish) 128 passed / 1 skipped
- [x] backtest 窓 (`--from/--to` required) / `guard_analysis_window` / `DATA_SPLIT` に時計依存なし
- P25 再現性メタ / paired baseline / market_snapshot / payout 欠損 / calibrator refit: **N/A (type-A でない)**

## 反証の試み

1. 「generator の today は本番経路で使われない」(依頼者・コミットコメント双方) → `\btoday\b` を grep し `:603` で `assess_race_completeness(today=today)` に渡ることを確認 → **不成立**。publish 完全性 alert の対象日が local→JST に変わる。auto_predict の `day` も JST なので両者は一致 (旧も両者 local で一致)。整合は保たれ、値も JST ホストで同一。
2. 「予測に効く経路は無い」→ `predictor/` 内の時計 (`rules.py:124`) の到達性を追跡。`_load_calibrator` は `expected != RULES_VERSION` のときだけ `evaluate_calibrator_compat` を呼ぶが、現行は `match`。到達しても log のみ → **成立**。
3. 「境界のテストが実行時刻に依存しない」→ `test_dedup_and_the_target_day_agree` (:93-99) は `now` 注入なしの 2 回呼び出しを比較しており、JST 00:00 を跨いだ瞬間だけ偶発失敗しうる。実害は無視できる (再実行で通る) が、テスト自身の趣旨とは食い違う。
4. 「OS が UTC でも正しい」→ `TZ=UTC` 下で `.venv64` python: `jst=20260920`、`datetime.now()`=14:56 (UTC 時刻を読んでいる) で `date.today()`=20260920。23:56 JST 時点なので両者一致、UTC 15:00 以降に分岐するのは注入テスト (:27-36) で確認済 → **成立**。

## 主な改善提案

1. **`scripts/predict_t10.py:249` の対象日既定を `current_jst_daystamp()` に寄せ、`tests/test_jst_date.py:114` の parametrize に追加** — T-10 経路が F3 正本を書く以上、対象日の出典を auto_predict と揃えるべき。PIT 用 `now` (`:120`) は naive `start_time` と比較するので、揃える場合は `current_jst_datetime().replace(tzinfo=None)` 相当のヘルパを `jst.py` に置き、aware/naive 混在の `TypeError` を防ぐ。
2. **guard の正規表現に `r"datetime\.now\([^)]*\)\.strftime\("` を追加** (`tests/test_jst_date.py:128-129`) — repo で最多の「今日」の作り方を検出できていない。現状は変異 7 種に対して落ちるが、8 種目 (`datetime.now().strftime("%Y%m%d")`) は素通し。
3. **`web/generator.py:312-314` のコメント訂正 + `config.sealed_window_started` に `now` 注入** — 前者は `:603` の消費を明記。後者は `today or current_jst_daystamp()` に寄せ、封印開始日の判定と生成対象日の時計を一致させる (現在は `SEALED_FROM=None` で無害だが 10/01 自動開始の候補日が近い)。

## 前回からの差分

- 前回 (`20260919_2100_notify_dedup`): PASS 4.7。項目別: 網羅性 5 → 5 / 重み 5 → 5 / 確率構造 5 → 5 / 設計整合性 4 → 4 (留保の内容が入替: 前回の「時計混在 (auto_predict の `date.today()` vs dedup JST)」は**本改修で解消**、代わりにコメント誤記・guard の検出漏れ・唯一の場所の未達 3 箇所・aware/naive 注意) / skew 4.5 → 4.5 (前回留保の `artifact_drift()` 短絡罠は依頼者側が既に認識、今回は T-10 時計の未統合)。総合 4.7 → 4.7。1 点を超える変動なし。
- 判定 PASS 継続。マージ時期をコミット文が「9/21 の 3 起動終了後」と自制している点は、生成対象日を決める基盤の変更として妥当 (予測側の追加検証は不要)。
