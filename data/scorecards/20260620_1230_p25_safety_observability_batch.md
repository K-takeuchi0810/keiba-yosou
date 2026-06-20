# 採点 2026-06-20 12:30

**改修内容**: 誤読防止 + 観測性向上 バッチ (commit `f825779`) — vb-sub フォント逆転是正 / nav-buy 実測コメント訂正 / VERIFICATION_BANNER_MARKER 定数化 (変更失敗モード fail-fast) / GUI publish StalePublishRefused 日本語案内化

**対象ファイル**: `gui/app.py`, `web/publish_safety.py`, `web/generator.py`, `web/templates/index.html.j2`, `tests/test_publish_safety.py`

## 総合スコア + 4 択判定 (rubric v3)

| 専門家 | 今回スコア | 今回判定 | 前回スコア | 差分 |
|---|---:|---|---:|---|
| GUI / UX 監査人 | **4.4** | **PASS** | 4.06 | +0.34 |
| モバイル HTML レビュアー | **4.38** | **HOLD** ⚠ | 4.5 | -0.12 |
| 予想ロジック分析 | **4.2** | **PASS** | 4.2 | ±0 |
| 収益性 / 投資判断 | **2.76** | **HOLD** | 2.2 | +0.06 |
| データパイプライン | **4.58** | **PASS (HOLD-pending-day2)** | 4.32 | +0.26 |
| コード品質 | **4.92** | **PASS** | 4.4 | +0.52 |
| 検証プロセス (最終ゲート) | **4.02** | **PASS (条件付き)** | 3.96 | +0.06 |

**7 役平均: 4.18 / 5** (前回 3.97 比 **+0.21**)。CLAUDE.md の -0.3 警告は不発火 (最大下げ幅 mobile -0.12)。

## 注目点

### Mobile HTML が HOLD (本 commit 起因ではない既知問題)

`web/dist/index.html` のサイズが **1,791,224 bytes (1.79MB)** で 1.5MB 警戒線を超過。data 窓拡大による DOM 肥大 (192 `<details>` / 2369 `<tr>` / 37,570 行) が支配的原因。本 commit の CSS 変更は誤差レベルで、サイズ問題は separable な配信物プルーニング案件。

mobile auditor の項目別スコアは:
- 情報密度 / 可読性 / 誤読防止: 4.0 → **4.7 (+0.7)** — vb-sub 階層逆転解消、最重要 safety message が weight 600 / 13.1px に昇格
- ダークモード / コントラスト: 4.5 → 4.7 (+0.2) — opacity 撤廃で実コントラスト +0.33 改善 (6.20→6.53:1)
- iOS / iCloud / パフォ予算: 4.5 → **3.5 (-1.0)** — 1.79MB サイズ警戒線超過

**サイズ問題は本 commit の責任外** だが現状の deliverable が予算を超えているため判定は HOLD。CSS 改善自体は純改善。

### Profitability は構造的 HOLD 継続

scoring 経路無変更 (`predictor/` 配下 0 行) のため、buy_only 65.77% / CI [47.95%, 83.19%] は不変。`calibration_in_sample=True` も継続。実弾投入は依然不可。本 commit による加点は誤運用予防経路 (StalePublishRefused 案内化 + vb-sub 強化 + MARKER 定数化) で +0.06 のみ。

### Code Quality が大幅前進 (+0.52)

エラー処理 / 観測可能性 が 4 → 5: GUI publish の StalePublishRefused 明示処理 + 戻り値構造化により `_safe` catch-all への依存度低下 + ユーザに「何をすべきか」が伝わる経路新設。前回提案 4 件 (#1 marker 定数化 / #2 GUI 案内化 / #3 preview_head 根拠 / #4 mobile) を **同一 commit で構造的に解消**。

## 各専門家の主な所見

### GUI / UX (PASS, 4.4)

- StalePublishRefused → 日本語案内化が Nielsen #9 三要件 (何が起きた / なぜ / 次にどうする) を完全充足
- 戻り値 `{ok: False, refused: True, refused_at, message}` 構造化で「単なる失敗」と「検証ガード発火」を JSON 上で区別可能、telemetry / log filter に使える観測性
- JS パース PASS、`run_all` 経路では assert_safe_to_publish が事前に publish=False に倒すため StalePublishRefused は独立 publish API のみで発生する経路差が綺麗
- 改善提案: 「次の一手ボタン」 (チェックを外す + 再生成) の直接設置で項目1 を 4→5

### モバイル HTML (HOLD, 4.38)

- vb-sub 実コントラスト再計算: 旧 6.20:1 (opacity 0.95) → 新 **6.53:1** (実測、commit message の 5.94:1 は約 0.6 過少)
- banner 高さ: 52px → **56.2px** (+4.2px、font-size up に伴う)。scroll-margin worst-case は前回 -18px → -6px に縮小
- nav-buy ダーク再計算: 私の再再計算で **7.34:1** (commit message の 6.40:1 は過剰補正の可能性、要再検証)
- **HTML サイズ 1.79MB > 1.5MB 警戒線** が HOLD の最大根拠。本 commit 起因ではない
- 改善提案 (優先): HTML サイズ削減 (開催絞り or lazy render) / scroll-margin 14rem / vb-sub 0.875rem (14px) へさらに引き上げ

### 予想ロジック (PASS, 4.2 横ばい)

- `predictor/` 配下は 1 byte も変更なし、退行リスクゼロ
- weights.json / RULES_VERSION / 3 層 docstring symbolic 参照 / 互換テーブル機構すべて無傷
- 持ち越し: bonus_subset_metrics 実証 / B 層 ablation env (PRED_DISABLE_BLEND) 実装 / Plan 追記

### 収益性 (HOLD, 2.76)

- backtest 数値不変 (20260615 から再導出なし)
- 観察用 / 紙運用 / 実弾候補の 3 段階で「実弾候補: NO」継続
- 加点 +0.06 は「危険物倉庫の扉ラベルを大きくして、鍵が壊れた時にアラームを増設した」改善。倉庫の中身 (戦略の収益性) は不変

### データパイプライン (PASS, 4.58)

- 鮮度管理 SLO 4.5 → **4.8** — calibrator compat 自動失効化 + 健全性チェーン自動 PASS/HOLD/FAIL 判定の完成
- 取得運用 (P25 重点) 3.5 → **4.6** — 前回「未稼働」、今回 eligible=fetched=ok=27 (100%)、汚染 False、post-start 0、Plan 期待値超過
- 1 開催日で機構達成、Plan 完了条件 (2-4 開催日で安定) 厳守のため最終認定は 2026-06-21 (日) 観測後

### コード品質 (PASS, 4.92)

- 変更失敗モード分析: 「template の class 名変更で publish ガードが沈黙する」事故を CI で fail-fast 化 (構造的価値最大)
- 前回提案 4 件すべて消化、21 passed
- 軽微減点: preview_head=8000 が **rendered 検証モード HTML** で十分かの直接実測未済 (生 template の marker offset は 17,934 bytes だが render 後は縮む見込み)

### 検証プロセス (PASS 条件付き, 4.02)

- 統合判定フロー (rubric v3): 全 6 agent に未解消 FAIL / NOT_EVALUABLE なし
- 過適合監視 / 統合判定 4.2 → **4.5** — marker integration test + health snapshot 機構 + StalePublishRefused 案内化が「機構が動くこと」の証拠を積み上げた
- **3 層 factorial 設計 (Plan Step 5)** が依然 C1/C5 の 2 セルのみ、C2/C3 欠落。前回降格宣言「次セッション執行」が本セッションも未実行 → 持ち越し 2 回目で **次セッション執行義務化**

## 横断的に見た優先課題 (3 件)

1. **HTML サイズ削減 (mobile HOLD の解消)** (担当: mobile-html-reviewer + data-pipeline)
   - 192 `<details>` / 2369 `<tr>` で 1.79MB → 1.5MB 以下へ
   - 案: 過去 N 開催を ZIP 化、HTML 本体は直近 4 週分のみ / details 単位の lazy unmount / 各日 section を別 HTML ファイル化
   - 本日 健全性 PASS 継続中で配信は止まっていないが、iOS Safari 初回パースで体感劣化リスク

2. **3 層 factorial の最低 4 セル paired run 完走** (持ち越し 2 回目、次セッション執行義務、担当: validation + prediction-logic + profitability)
   - C2 (A only = `_market_score` だけ ON) / C3 (B only = `_investment_probability` blend だけ ON) を走らせる
   - C3 を実現するには `PRED_DISABLE_BLEND` env を実装する必要あり (現在未実装)
   - 持ち越し 3 回目になると検証 process auditor の信頼性自体を毀損する

3. **out-of-sample backtest (`from=20260101`) で paired CI 再導出** (担当: profitability + validation)
   - calibrator `trained_to=20251231` 以降のみで buy_only CI を再導出
   - `calibration_in_sample=true` (リーク④) の構造的解消
   - HOLD 解除の前提条件

## 残リスク (前回比)

- ✓ **解消**: StalePublishRefused 型名露出 / VERIFICATION_BANNER_MARKER リテラル直書き / vb-sub フォント逆転 / nav-buy 実測コメント
- ✗ **継続**: 収益性 2.76 (実弾不可) / 3 層 factorial 未完 / out-of-sample 未実行 / bonus_subset_metrics 実証 0 件
- ⚠ **新規発見**: HTML サイズ 1.79MB (本 commit 起因ではないが現状 deliverable が予算超過)

## 関連 commit

- `f825779`: 本 commit (誤読防止 + 観測性向上 バッチ)
- `ac4a1ab`: Step 4 初日実測 + Plan 追記 (本セッション)
- `091e17b`: register PS1 schtasks /query 修正 (本セッション)
- `2546dd4`: fresh odds health check + 条件付き OOS 自動化 (本セッション)
- `20260620_1145_p25_step4_health_snapshot.md`: 本日の健全性スナップショット
