# 時計の台帳 (2026-09-22)

「いま」「今日」をどこで作っているかの一覧。JST 統一の残作業範囲を確定するために作る。

## なぜ要るか

2026-09-20 まで、日付は 7 箇所がそれぞれ独自に作っていた。JST を明示していたのは
通知の重複判定だけで、残りはシステムのローカル時刻任せだった。同じ 1 回の起動の中で
「今日」が 2 通り存在しうる状態で、境界をまたいだ瞬間に「対象日は 9/20 なのに通知の
記録は 9/21」のような食い違いが起きる。**予想を出す日そのものを決める値**なので、
ずれたら 1 日ぶんの予想を落とす。

`jst.py` に `current_jst_date` / `current_jst_daystamp` / `current_jst_datetime` を
置き、`now` を注入できる形で集約を始めた (branch `jst-date-unify-20260920`、main 未マージ)。
この台帳は **まだ寄せていない箇所**を、直す順番を決められる形で残すもの。

現機は JST なので、いずれも **いまは実害が出ていない**。効くのは
(1) OS のタイムゾーンが変わったとき (2) 日付境界をまたぐ実行 (3) UTC のホストへ
移したとき。優先度はその 3 つで壊れたときの被害で付ける。

- **A** = 金銭・判定 (PIT / オッズ / 封印) に直結。ずれると数字が嘘になる
- **B** = 対象日を決める。ずれるとその日の処理が丸ごとずれる
- **C** = 刻印・ログ・表示。ずれても読み手が混乱するだけ

## 集約済み (単一出典 = `jst.py`)

branch `jst-date-unify-20260920` で対応済。main には未反映。

| file / function | 用途 |
|---|---|
| `scripts/auto_predict.py` `main()` | 生成対象日 |
| `scripts/notify_dedup.py` `jst_today` (廃止) → `current_jst_daystamp` | 重複判定の対象日 / 保持期間 |
| `scripts/auto_predict.py` `_is_final_attempt` | 最終起動の判定 (11 時) |
| `web/generator.py` `build_view_model` | 既定の生成窓 + 完全性アラートの基準日 |
| `scripts/auto_predict_daily.bat` | ログのファイル名 |
| `gui/app.py` `_date_range` | ダッシュボードの「今日開催あり」判定 |
| `scripts/fetch_mining.py` `normalize_date` | `--date today` の解決 |
| `web/publish_safety.py` `assess_race_completeness` | 完全性アラートの基準日 |
| `config.py` `sealed_window_started` (旧 A3、2026-09-25) | 封印窓の開始日判定。`now` 注入可。境界・既定経路・OS の TZ 変更をテストで固定 (`tests/test_sealed_clock.py`) |
| `scripts/auto_predict_daily.bat` の失敗時 (2026-09-25) | 日付が取れなければ空日付のログへ逃げず exit 8。stderr を保存 (`tests/test_daily_bat_rundate.py`) |

## 未対応 — 優先度 A (PIT / 判定に直結)

| # | file / function | いまの取得方法 | 用途 | PIT 影響 | 対象日決定への影響 | 優先 | 修正前に必要なテスト |
|---|---|---|---|---|---|---|---|
| A1 | `scripts/predict_t10.py` `run()` :120 | `now = now or datetime.now()` (naive local) | T−10 ゲートの基準時刻。`actionable = mins > 0` を決める | **直撃**。F3 の正本を書く時計そのもの。ずれると発走前/後の判定が反転する | なし (日付は別引数) | **A** | `now` 注入で境界 (T−10 ちょうど / 発走時刻ちょうど) を直接検証。DB の `start_time` が naive なので **aware をそのまま渡すと TypeError**。`jst_now_naive()` のような明示ヘルパを先に用意し、比較の両辺が同じ意味であることをテストで固定する |
| A2 | `scripts/predict_t10.py` `main()` :249 | `args.date or datetime.now().strftime("%Y%m%d")` | T−10 正本の対象日 | 間接 (日がずれれば別日のレースを処理) | **直撃** | **A** | OS=UTC で JST 日付になること / JST 00:00 境界 / `run()` と同じ日を指すこと |
| A4 | `scripts/fetch_fresh_odds.py` :186 | `now = datetime.now()` → `target_date` にも使用 | fresh odds 取得の基準時刻と対象日 | **直撃**。発走何分前かの判断に使う | **直撃** (同じ `now` から対象日も作る) | **A** | 対象日と基準時刻が同じ `now` から出ること / 日跨ぎ実行で両者が食い違わないこと |
| A5 | `scripts/check_fresh_odds_health.py` :516 | `now = datetime.now()` → `date_str` にも使用 | 鮮度の健全性チェックの基準時刻・対象日 | 間接 (警告の要否) | **直撃** | **A** | 同上。`--check-after-time` との比較が JST で行われること |
| A6 | `gui/app.py` `presetToday()` :2214 (JS `new Date()`) | ブラウザのローカル時刻 | 日付入力欄のプリセット。「今日」ボタン | なし | **直撃**。`setDates` が `from_date` / `to_date` を埋め、その値が `_run_render_in_venv64(from_date, to_date, ...)` にそのまま渡って生成窓になる | **A** | 「表示だけか、処理対象日を決めているか」で優先度が変わると指示されたので**実際に追跡して確認した**結果、後者だった。ただし値は入力欄に見えており利用者が直せるので、黙って決まる A1-A5 よりは弱い。修正案はサーバ応答に `today_jst` を載せて JS はそれを使う。テスト: UTC ホストを模したブラウザ時刻でプリセットが JST 日付になること |

## 未対応 — 優先度 B (対象日を決める)

| # | file / function | いまの取得方法 | 用途 | PIT 影響 | 対象日決定への影響 | 優先 | 修正前に必要なテスト |
|---|---|---|---|---|---|---|---|
| B1 | `scripts/fetch_results.py` `normalize_date` :24,26 | `datetime.now()` / `- 1 日` | `--date today` / `yesterday` の解決 | なし (結果取得) | **直撃**。`yesterday` は境界で 2 日ずれうる | **B** | `today` / `yesterday` の両方を注入で。JST 00:00 直後に `yesterday` が一昨日にならないこと |
| B2 | `scripts/fresh_odds_coverage.py` :80, :150 | `datetime.now() - timedelta(days=n)` | `--last N` の窓の下限 | なし | 窓の端が 1 日ずれる | **B** | 注入で窓の下限を検証。`--last 1` が「今日」を含むこと |
| B3 | `scripts/cleanup_placeholder_horse_rows.py` :44 | `today or date.today().strftime("%Y%m%d")` | 掃除対象日の既定 | なし | 直撃 (誤った日を掃除しうる) | **B** | 注入テスト。既に `today` 引数があるので容易 |
| B4 | `scripts/f3_phase1_readiness.py` :362 | `min(date.today()..., "20260930")` | 集計窓の上限 | なし | 直撃 | **B** | 注入テスト |

## 未対応 — 優先度 C (刻印 / 表示のみ)

| # | file / function | いまの取得方法 | 用途 | 優先 | 備考 |
|---|---|---|---|---|---|
| C1 | `predictor/rules.py` :124 | `today or datetime.now().strftime("%Y-%m-%d")` | calibrator 互換表の `expires_on` 判定 | **C** | 現行は `expected_rules_version == RULES_VERSION` で一致するため **到達しない**。到達してもログのみ。`today` 引数あり |
| C2 | 各 `analyze_*.py` / `backtest.py` / `monitor.py` の `generated_at` 等 | `datetime.now()` | 生成時刻の刻印 | **C** | 対象日ではないので統一の対象外。ただし「日付は JST / 時刻はローカル」の混在は読み手を混乱させるので、いずれ揃える |

## 進め方 (2026-09-22 時点の合意)

1. `jst-date-unify-20260920` を **次の非開催日**にマージ (dry-run + 再レビュー後)
2. A3 (`sealed_window_started`) は 2026-09-25 に対応済み (上の「集約済み」へ移した)。
   ※ 当初「10/01 に封印が自動開始する」と書いていたが誤り。封印開始は 2026-09-17 に
   延期済み (commit `d52f417`、`SEALED_FROM = None`)。A3 の欠陥は SEALED_FROM に
   日付を入れた瞬間から効くので、開始前に直す必要があった (期限の話ではない)
3. A1 / A2 (`predict_t10`) は **別フェーズ**。F3 再開前に必須だが Group A の開始条件にはしない。
   DB 全体を aware 化する大改修ではなく、`jst_now_naive()` のような明示ヘルパで
   比較境界を揃える
4. A6 (GUI の「今日」ボタン) は A1-A5 より弱い (値が入力欄に見えており
   利用者が直せる) ので、A 群の中では最後でよい
5. B 群は JST 基盤が main に入ってからまとめて
6. C 群は急がない

## この台帳の使い方

新しく「今日」を作るコードを書くときは、まず `jst.current_jst_date` /
`current_jst_daystamp` を使う。使えない事情があるならこの表に行を足す。
`tests/test_today_single_source.py` (branch `jst-date-unify-20260920`) の AST ガードが
主要モジュールを見張っているので、対象を広げるときは同時に台帳も更新する。
