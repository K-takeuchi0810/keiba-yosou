# 採点 2026-05-10 23:00 — P0-1: buy_filter を config 一元化

**改修内容**: `config.BUY_FILTER_DEFAULT` を新設し、`web/generator.py` BET_MIN_* / `gui/app.py:_is_buy_candidate` / `scripts/backtest.py` / GUI dashboard JS input すべてが同じ値 (1.05/0/10/20) を参照するよう統一。新 API `Api.get_buy_filter_default()` で JS 起動時に Python 側 default をロード。
**主な編集**: `config.py`, `web/generator.py`, `gui/app.py`

## 総合スコア (項目平均) の推移

| # | 専門家 | 今回 | 前回 | 差分 | 状態 |
|---|---|---|---|---|---|
| 1 | GUI / UX 監査人 | 3.2 | 3.2 | ±0 | 裏方リファクタで UX 不変 |
| 2 | モバイル HTML レビュアー | 3.4 | 3.4 | ±0 | テンプレ未変更 |
| 3 | 予想ロジック分析官 | 3.4 | 3.4 | ±0 | predictor/ 未変更 |
| 4 | 収益性 / 投資判断専門家 | **2.0** | 1.8 | **+0.2** | フィルタ実用性 1→3 |
| 5 | データパイプライン技術者 | 3.8 | 3.8 | ±0 | 担当範囲未変更 |
| 6 | コード品質 / 保守性レビュアー | **2.8** | 2.6 | **+0.2** | DRY 3→4 / 設定外出し 2→3 |
| 7 | 検証プロセス監査人 | **3.4** | 3.2 | **+0.2** | A/B 管理 3→4 |

**全体平均: 3.06 → 3.14 (+0.08)**
**後退ゼロ** (-0.3 以上下がった専門家なし)。

## 改善できた点

- **🟢 収益性 / 買い目フィルタの実用性 (1 → 3)**: 生成 / 検証 / GUI 表示の 3 経路で同じフィルタ値を参照する構造に。「フィルタを掛ければ勝てるか」が原理的に測定可能になった。
- **🟢 コード品質 / DRY (3 → 4)**: buy_filter の二重定義が完全消滅。
- **🟢 コード品質 / 設定外出し (2 → 3)**: 4 値 + max_odds_age_min が config 化。
- **🟢 検証プロセス / A/B 管理 (3 → 4)**: `BUY_FILTER_DEFAULT × weights.json × calibrator.json × --rule-version` の 4 軸で実験を切れるように。

## 残課題 (P0-1 延長で片付けたい指摘)

### 🟡 続漏れ: `gui/app.py:634` に `odds_age > 30` の直書き 30 が残存
- 指摘元: コード品質
- config の `max_odds_age_min` を変えても warnings の閾値は追従しない不整合
- 修正コスト: 10 分。`max_odds_age_min` への置換 1 行

### 🟡 構造改善: `scripts/backtest.py` を直接 config 参照に
- 指摘元: 検証プロセス
- 現状 `from web.generator import BET_MIN_*` 経由 → 間接参照で動くが意図不明瞭
- 修正コスト: 10 分。`from config import BUY_FILTER_DEFAULT` に切替

### 🟡 P0-1 後 backtest が未実行
- 指摘元: 検証プロセス
- `--rule-version p01-buy-filter-unified` で記録しないと差分検証ができない
- 修正コスト: 25 秒 (短期) 〜 8 分 (長期 3,180 戦)

## 横断的な次の優先課題

P0-1 の延長 (上の 3 件) を片付けつつ、ベースラインで挙がった次の P0 へ:

### 🔴 P0-2. calibrator の少数 bin 過学習対策
- 指摘元: 収益性 + 検証プロセス + 予想ロジック
- bin 0.15-0.20 が count=27 で `calibrated 0.3333` (raw の約 2 倍) → 偽の高 EV 候補を量産
- 修正: `min_count=20→50`、未達 bin は隣接統合 or `calibrated = avg_probability` 恒等寄せ

### 🟠 P1-1. `_score_one` 491 行 + 直書き 60 箇所 + dead feature 削除
### 🟠 P1-2. `_investment_probability` の三段がけを 2 段に減らす
### 🟠 P1-3. 観測性 (`logging` 導入 + `except: pass` 9 箇所置換)

## 個別 scorecards

- `20260510_2300_p01_buy_filter_unified__gui-ux-auditor.md`
- `20260510_2300_p01_buy_filter_unified__mobile-html-reviewer.md`
- `20260510_2300_p01_buy_filter_unified__prediction-logic-analyst.md`
- `20260510_2300_p01_buy_filter_unified__profitability-judge.md`
- `20260510_2300_p01_buy_filter_unified__data-pipeline-engineer.md`
- `20260510_2300_p01_buy_filter_unified__code-quality-reviewer.md`
- `20260510_2300_p01_buy_filter_unified__validation-process-auditor.md`
