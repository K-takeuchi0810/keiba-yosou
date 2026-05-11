# 採点 2026-05-10 23:10 — P0-2: calibrator 過学習対策 + P0-1 延長

**改修内容**:
- **P0-2**: `_apply_calibrator` に **「count < min_count なら raw 寄せ (恒等)」** ロジックを追加。`min_count` を 20 → 50 に引き上げ。環境変数 `PRED_CALIBRATOR_MIN_COUNT` で上書き可。
- **P0-1 延長 (a)**: `gui/app.py:634` の `odds_age > 30` 直書きを `BUY_FILTER_DEFAULT["max_odds_age_min"]` に置換。警告文言も `(>{max_age}分)` で動的化。
- **P0-1 延長 (b)**: `scripts/backtest.py:buy_filter_from_generator()` を `web.generator` 経由から **直接 config 参照** に変更。

## 総合スコア (項目平均) の推移

| # | 専門家 | 今回 | 前回 | ベースライン | 差分 (前回比) |
|---|---|---|---|---|---|
| 1 | GUI / UX 監査人 | **3.3** | 3.2 | 3.2 | **+0.1** |
| 2 | モバイル HTML レビュアー | 3.4 | 3.4 | 3.4 | ±0 |
| 3 | 予想ロジック分析官 | **3.6** | 3.4 | 3.4 | **+0.2** |
| 4 | 収益性 / 投資判断専門家 | **2.4** | 2.0 | 1.8 | **+0.4** |
| 5 | データパイプライン技術者 | 3.8 | 3.8 | 3.8 | ±0 |
| 6 | コード品質 / 保守性レビュアー | **3.0** | 2.8 | 2.6 | **+0.2** |
| 7 | 検証プロセス監査人 | **3.6** | 3.4 | 3.2 | **+0.2** |

**全体平均: 3.06 (baseline) → 3.14 (P0-1) → 3.30 (P0-2)** = ベースライン比 **+0.24**
**後退ゼロ**。**5 名が改善** (1, 3, 4, 6, 7) / 維持 2 名 (2, 5)。

## 改善できた点

- 🟢 **収益性 / 校正済み確率の信頼性 (2 → 4)**: `count<50` の bin が恒等寄せ → `bin 0.15-0.20 (count=27, calibrated 0.33)` の偽高 EV 量産経路を構造的に遮断。`bin 0.10-0.15 (count=52)` も shrinkage で raw に 36% 寄り、`bin 0.0-0.05 (count=317)` だけが完全な校正適用、という階段ができた。
- 🟢 **収益性 / EV 整合性 (2 → 3)**: `PRED_CALIBRATOR_MIN_COUNT` `PRED_CALIBRATOR_ALPHA` で旧挙動再現 + A/B が可能に。
- 🟢 **予想ロジック / 重み妥当性 (2 → 3)**: 過適合経路の構造的遮断。
- 🟢 **予想ロジック / 確率推定 (4 → 4.5)**: 2 段ガード設計 (恒等 + Bayesian shrinkage) で count に応じた連続的信用度。
- 🟢 **コード品質 / 設定外出し (3 → 4)**: 直書き 30 解消、`min_count` `shrinkage_alpha` も設定経由に。
- 🟢 **検証プロセス / calibration 計測 (3 → 4)**: 二段防御で「ノイズ bin が EV を暴走させる」リスクを封じた。
- 🟢 **GUI / エラー人間化 (3 → 3.5)**: 警告文言が config 連動。

## 警告 (連続指摘 = 即対処必要)

### 🔴 P0-1/P0-2 後 backtest が 1 件も保存されていない (2 連続警告)
- 指摘元: 検証プロセス監査人 (2 連続)
- 「改修と backtest 保存をペアで運用ルール化」を要求
- 数値根拠ゼロのため過適合監視 2/5 が固定
- **次のアクション**: `scripts/backtest.py --rule-version p02-calibrator-minbin --save` を即実行

### 🟠 jvlink_client/client.py の except: pass 9 箇所 (3 連続未着手)
- 指摘元: コード品質レビュアー (3 連続)
- 単発で総合 3.0 → 3.3 まで上がる最大効果
- 観測性 2/5 が固定の主因

### 🟠 モバイル ダークモード変数化 (3 連続未着手)
- 指摘元: モバイル HTML レビュアー (3 連続)
- ダークモード 2/5 が固定の主因

## 横断的な次の優先課題

### 🔴 P0-3 (新規). 改修後 backtest を即実行 → rule_version 付きで保存
- コスト 25 秒〜8 分。**ここで止めて即実行が最も効果的**
- `scripts/backtest.py --from 20260101 --to 20260430 --rule-version p02-calibrator-minbin --bet tan --save`

### 🟠 P1-3. 観測性 (`logging` 導入 + `except: pass` 9 箇所置換)
- 連続 3 回未着手の重要課題
- 同時に `_apply_calibrator` の calibrator 破損時 warn 1 行も追加

### 🟠 P1-1. `_score_one` 491 行を 5〜7 関数に分割 + 直書き 60 箇所を weights.json 移送 + dead feature 6 件削除
- 予想ロジック分析官 + コード品質の共通優先

### 🟡 P2-1. ダークモード CSS 変数化
- モバイル HTML レビュアー 3 連続未着手

## 個別 scorecards

- `20260510_2310_p02_calibrator_minbin__gui-ux-auditor.md`
- `20260510_2310_p02_calibrator_minbin__mobile-html-reviewer.md`
- `20260510_2310_p02_calibrator_minbin__prediction-logic-analyst.md`
- `20260510_2310_p02_calibrator_minbin__profitability-judge.md`
- `20260510_2310_p02_calibrator_minbin__data-pipeline-engineer.md`
- `20260510_2310_p02_calibrator_minbin__code-quality-reviewer.md`
- `20260510_2310_p02_calibrator_minbin__validation-process-auditor.md`
