# 収益性 / 投資判断専門家 採点 — F3 morning anchor

## 判定: HOLD（取得基盤 PASS / Phase 1 収益判定 HOLD）

**理由**: 朝アンカー取得基盤は固定600分窓、08:45日次実行、競合時fail-closedまで実装・登録され、Phase 1収益検証の前提を前進させた。しかし実測はレース終了後の0 race / 0 fetchで、60分以上のアンカー、`wide_drift > 0`、ROI、EV、校正の数値受入がすべて未完である。  
**根拠ファイル**: `scripts/fetch_morning_odds.bat:9-41`、`scripts/register_morning_odds_task.ps1:3-44`、`docs/F3_morning_anchor_result.md:6-10,43-49,63-68`  
**次アクション**: branchをmainへ統合後、最初のJRA開催日に08:45 runと09:00 live runの実競合を確認し、lead >= 60分のrace coverage、欠損パターン、行/RAW増分、`wide_drift > 0`を実測する。到達後も同一race/day-blockのpaired ROI/CIが80%を超えるまで実弾投入しない。

## 総合: 2.0 / 5（参考スコア）

前回 **2.0 / HOLD**、差分 **±0.0**。取得基盤の追加は収益検証を可能にする前提改善だが、新しい収益・確率品質の証拠ではない。直近の有効backtestも全体68.9%、buy-only 54.1%で控除率目安80%未満のため、規約上3以上にはできない。

## 改修タイプとスコープ

- **type-C（データ取得基盤）を主、type-B（readiness計測の前提）を従**: 最終HEAD `e5eaf34`。直近3 commitは `scripts/fetch_morning_odds.bat`、登録PS1、専用テストの競合・ログ・登録更新を変更した。
- **採点対象**: 朝アンカーがPhase 1のPIT市場残差検証を開始できる観測点を作る設計か、数値受入の未完を誤って収益改善と扱っていないか。
- **対象外**: 予測モデル、`_investment_probability`、`_bet_metrics`、`_value_score`、買い目filter、calibratorの良否。今回変更されていない。

## 項目別

- **回収率: 1/5** — 今回はbacktestも払戻評価もなく、新ROIは0件。直近3 artifactを再確認すると、最新p26はbuy 0件、`baseline_brier.json`はROI schema外、直近の有効p25は1,568戦・全体ROI 68.9%、buy-only 194件・54.1%で80%未満。朝アンカーの導入だけでは不合格状態は変わらない。
- **EV計算の整合性: 2/5** — 確率・EV経路は未変更。固定 `--window 600 --min-lead 0` と実効窓marker検査により、将来のmarket drift入力をPITで作る入口は明確になった（`scripts/fetch_morning_odds.bat:23-41`）。ただし取得0件のため、朝アンカーを使った校正後確率×実オッズ、discount有無、EV差は未評価。
- **Kelly fraction / 投資割合: 3/5** — 現行のKelly表示・日次capに変更はなく、今回も賭金、最大DD、同日相関、複数候補配分を評価していない。基盤変更による加点・減点はない。
- **買い目フィルタの実用性: 2/5** — morning smokeはeligible/fetched 0/0で、買い候補数、信頼度別採用率、relaxation、オッズ帯別ROIを一切追加していない（`docs/F3_morning_anchor_result.md:10-24`）。既存buy-only 54.1%を覆す証拠はない。
- **校正済み確率の信頼性: 2/5** — calibratorは不変。60分以上の観測点と`wide_drift > 0`がまだ0件なので、将来のdriftモデルについてbin count、shrinkage、reliabilityを評価できない（`docs/F3_morning_anchor_result.md:6-10,24`）。

## Phase 1 収益検証の前提

| 前提 | 現在の証拠 | 判定 |
|---|---|---|
| 朝窓を上書き不能 | 固定 `--window 600 --min-lead 0`、`%*`転送なし | PASS |
| 60分以上を狙える時刻 | Taskは08:45、最初の発走09:50想定で65分lead | 設計PASS・実測待ち |
| live取得との排他 | 共通lock、6回×30秒retry、残存競合はrc=4 | 実装PASS・実COM競合待ち |
| Task稼働 | `Ready`、NextRun 2026-07-21 08:45、直近result 0 | PASS |
| race-day取得 | 19:03 smokeは0 race / 0 fetch | HOLD |
| lead >= 60分 coverage | 未取得 | HOLD |
| `wide_drift > 0` | prior 0、未再計算 | HOLD |
| ROI / EV / calibration受入 | 新規結果なし | HOLD |

専用テストは `.venv32/Scripts/python.exe -m pytest tests/test_f3_morning_anchor.py -q` で **4 passed**。実Taskはこのレビュー時点で `Ready`、`LastTaskResult=0`、`NextRunTime=2026-07-21 08:45`をread-only実測した。

## 停止条件チェック

- [x] 改修HEAD・対象差分を特定: `e5eaf34`、`git log --stat -3`を確認。
- [x] baseline paired比較: **N/A**。type-C/B基盤改修で収益改善やモデル採用を主張していない。
- [x] `market_snapshot` / payout欠損: **N/A**。今回の成果物はbacktest採用判断ではなく、朝PIT snapshot取得基盤。
- [x] production予測・filter・calibrator不変: 対象差分に該当ファイルなし。
- [x] 数値受入未達を明示: go-live、60分coverage、`wide_drift > 0`をpendingとしている。
- [x] 収益性停止条件: ROI 80%超の新証拠なし。実弾投入やPhase 1採用を主張せずHOLDしている。

## 反証の試み

- 主張候補「Task登録と成功rcにより朝アンカー取得は受入済み」に対し、19:03 smokeの対象が0 raceで、JV-Link COMにもDB ingestにも入っていないことを確認した（`docs/F3_morning_anchor_result.md:10,49`）。したがって成功rcは引数伝播/no-race経路の証拠に限られ、実取得・実競合・wide driftの数値受入にはならない。
- 主張候補「08:45なら全raceでlead >= 60分」に対し、時刻設計は最初の発走に対して65分leadを持つが、朝オッズ配信の有無と全race coverageは未実測である。設計PASSとデータ受入HOLDを分離した。

## 主な改善提案

1. **最初のrace-day runを受入artifact化** — `docs/F3_morning_anchor_result.md:63-68` の4項目をrace別coverage表、欠損理由、Task結果、row/RAW delta、再計算後wide_driftとともに固定し、実測前はPhase 1学習をfail-closedにする。
2. **収益ゲートを事前固定** — 朝アンカー観測期間の最低開催日数・最低race数・wide-drift最低件数を人間が先に定め、到達後に同一race/day-blockのpaired ROI/CI、最大DD、採用件数を評価する。
3. **merge couplingを先に解消** — Task actionはmain作業ディレクトリを指し、branch未統合中はbatが存在しない（`docs/F3_morning_anchor_result.md:43`）。次回08:45より前にmainへ統合されなければgo-liveは成立しない。

## 前回からの差分

- 総合: **2.0 → 2.0（±0.0）**。
- 判定: **HOLD → HOLD**。前回の`wide_drift=0`に対し、今回はそれを解消する朝取得基盤が実装・登録されたが、初回race-day実測前なので収益証拠は増えていない。
- 前進: 固定600分窓、08:45 Task、競合retry/fail-closed、引数上書き防止、専用テスト4件。
- 未完: 60分coverage、朝オッズ欠損パターン、実COM/DB競合、日次増分、`wide_drift > 0`、モデル別paired ROI/CI。
