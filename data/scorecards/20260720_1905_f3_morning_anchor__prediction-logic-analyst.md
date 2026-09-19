# 予想ロジック分析官 採点

## 判定: HOLD

**理由**: 朝アンカー取得基盤は F3 drift 特徴の train/serve 前提を改善する設計になっているが、実測 smoke は対象レース 0 件で、`lead >= 60分` と `wide_drift > 0` の数値受入はまだ成立していない。
**根拠ファイル**: `scripts/fetch_morning_odds.bat:14-49`, `scripts/register_morning_odds_task.ps1:9-49`, `docs/F3_morning_anchor_result.md:5-10`, `data/f3_phase1_readiness/dev_odds_coverage.json`
**次アクション**: branch を main に統合した後の最初の JRA 開催日に 08:45 run を実測し、全レースの `lead >= 60分` coverage、09:00 以降の T-10 点との `wide_drift > 0`、実 COM/DB 競合、欠測パターンを再採点する。

## 総合: 4.3 / 5（前回 4.2 → 今回 4.3、+0.1）

> 改修タイプ: **type-C（市場データ取得・運用基盤）**。採点開始時の指定 HEAD は `1163c83`。レビュー中に lock 待機秒の定数連動だけを追加した `e5eaf34` が同 branch に積まれたため、最終確認は `e5eaf34` まで含む。`main...HEAD` の変更は morning batch、Task 登録 PS1、専用 test の3ファイルだけで、`predictor/rules.py` / `features.py` / `weights.json` / `calibrator.json` は無変更。P25/type-A の paired A/B/C、calibrator refit、market snapshot 採用ゲートは N/A。

## 項目別

- **シグナル網羅性: 4.5/5** — 新シグナルの追加・削除はない。朝アンカーは市場 drift 候補を新たに採用せず、将来の PIT 2時点比較に必要な入力を収集するだけであり、前回のシグナル構造評価を維持する。固定 `--window 600 --min-lead 0` は wrapper 内に閉じ、呼び出し側の `%*` で変えられない (`scripts/fetch_morning_odds.bat:23`, `tests/test_f3_morning_anchor.py:13-26`)。
- **重み妥当性 / 過適合リスク: 4.0/5** — `weights.json` は無変更で、朝データを見て重み・閾値を事後調整していない。必須確認では top-level 24 keys、直書き `score +=/-=` は既存の異常馬マーカー `predictor/rules.py:580 score -= 1000` の1件だけ。数値受入前に drift 重みへ進まない HOLD は過適合防止として整合する。
- **信頼度判定 / 確率推定: 4.0/5** — `_confidence`、`_score_probabilities`、calibrator、shrink、温度、EV 経路は無変更。今回の 0件 smoke を確率品質・ranking・ROI の改善証拠へ読み替えていない (`docs/F3_morning_anchor_result.md:8-10`, `:21-24`)。
- **デッドコード / 設計整合性: 4.8/5** — morning/live が同じ `scripts.fetch_fresh_odds` と atomic `single_run_lock` を通り、競合検出後は最大6回待機して残存競合を rc=4 で fail-closed にする (`scripts/fetch_morning_odds.bat:21-36`)。有効窓 marker 不在も rc=2 (`:39-45`)。Task 更新は delete gap のない `Register-ScheduledTask -Force` (`scripts/register_morning_odds_task.ps1:35-47`)。predictor 無変更のため dead feature / V2 flag / warning 伝搬の既存状態に回帰はない。
- **本番運用との乖離リスク: 4.0/5** — 実 Task は `Ready`、08:45 daily、action は専用 batch、上限1時間、`IgnoreNew`、次回 2026-07-21 08:45、直近 result 0 と read-only で実測した。固定600分窓は first post 09:50 に対して65分 leadを作れる設計。一方、直近 smoke は `total_races=0 / upcoming=0` で、JV-Link/DB ingestも早期 snapshotも未実行。既存 readiness は自分で再集計して 225 total / 71 usable / 19 drift / 0 wide、earliest lead中央値19.95分のままであり、train/serve skew低減はまだ将来効果に留まる。

## 停止条件チェック

- [x] 採点対象 HEAD と変更範囲を確認: 指定 `1163c83`、追補 `e5eaf34`。predictor差分なし。
- [x] `git_sha / rule_version / env_overrides`: 予測 artifact を生成しない type-C のため rule/env は N/A。scorecardに対象 SHA を記録。
- [x] baseline paired比較、market_snapshot counts、payout欠損: 予測採用判断ではないため N/A。
- [x] モデル・feature・weights・calibrator・production予想経路は無変更。
- [ ] F3数値受入: **未完**。`lead >= 60分` の実レース snapshot 0、再計測 `wide_drift > 0` 未確認。
- [ ] 実競合受入: **未完**。同時起動日は対象レース0で COM/DB 区間に入らず、nested-lock testだけが成立 (`docs/F3_morning_anchor_result.md:47-50`)。

## F3 drift readiness への効果

- **構造上の効果: PASS** — 08:45の固定朝点と既存の発走前 live 点が揃えば、`earliest >= 60分` かつ `latest <= 25分` の wide drift 定義を満たせる。朝 wrapper は有効窓をログで検証し、no-op と競合を成功扱いしない。
- **数値受入: HOLD** — 2026-07-20 19:03の smoke はレース0件。従来 artifact の `wide_drift=0` を更新する情報はなく、Phase 1 の7モデル比較開始条件には未到達。
- **運用前提: HOLD** — 実 Task action は repo の main 作業ディレクトリを指す一方、read-only `git cat-file` では main に batch がまだ存在しない。merge 前は scheduled run が成功不能であり、result 文書もその coupling を明記している (`docs/F3_morning_anchor_result.md:41-43`)。

## 反証の試み

- 改修の主張「朝 Task 登録だけで wide drift 母集団が増える」に対し、Task実状態、morning log、readiness JSONを確認した。Task設定と `window=0-600min` marker は成立したが、対象レース0のため DB増分0、早期点0、wide0。よって**基盤成立の主張は支持、数値改善済みという主張は不成立**。
- 「共有 lock が競合を静かに成功扱いして朝点を欠落させる」反証に対し、wrapper は競合文字列を検出して再試行し、6回残存で rc=4を返す。nested acquisition testも second=False を確認し、この静かな成功経路はコード上不成立。ただし実 COM/DB 競合は未検証。

## 主な改善提案

1. **最初の JRA 開催日を受入 gate にする** — `docs/F3_morning_anchor_result.md:62-68` の4項目を実測し、`lead >= 60分` coverage、wide件数、欠測帯、row/raw増分、09:00競合結果を同一 artifact に保存する。
2. **Task 成功とアンカー成功を分離監視する** — rc=0でも `eligible=0` / `fetched=0` なら開催日だけ警告する監視を追加し、Schedulerの成功表示をデータ到着成功と誤認しないようにする。
3. **merge 後に action 実体を再確認する** — main に batch が存在することを確認してから Task を再 queryし、最初の開催日前に手動 no-race smokeを1回通す。

## 前回からの差分

- シグナル網羅性 4.5 → 4.5、重み 4.0 → 4.0、確率構造 4.0 → 4.0: predictor非変更。
- 設計整合性 4.7 → 4.8 (+0.1): 固定窓 marker、共有 lock retry、残存競合 rc=4、Task `-Force` 更新が取得契約を fail-closed にした。
- 本番乖離 3.8 → 4.0 (+0.2): 08:45 Taskが実登録され、前回指摘の早期アンカー欠如に対する具体的運用経路ができた。ただし実開催日データがないため4.0止まり。
- 前回判定 HOLD → 今回 HOLD: 保留理由は「基盤未実装」から「初開催日の数値受入待ち」へ進んだ。

## 検証メモ

- `git log --stat -4`: `3ce4810` → `6d512ba` → `1163c83` → `e5eaf34`。予想ロジック/モデル差分なし。
- `.venv32/Scripts/python.exe -m pytest tests/test_f3_morning_anchor.py -q`: **4 passed in 0.39s**。
- Task read-only実測: Ready / 08:45 daily / PT1H / IgnoreNew / LastTaskResult 0 / NextRun 2026-07-21 08:45。
- morning log: `window=0-600min` と `CHECK: effective window=600 confirmed`、ただし `total_races=0 / upcoming=0`。
- このレビューで編集したのは本scorecardのみ。他agent・ユーザの未追跡ファイルは変更していない。
