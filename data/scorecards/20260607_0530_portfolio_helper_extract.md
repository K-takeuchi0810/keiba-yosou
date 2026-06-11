# 採点 2026-06-07 05:30

**改修内容**: 買い候補の日単位ポートフォリオ集計を predictor/portfolio.py の compute_day_portfolio() に単一出典化 (web/generator.py + gui/app.py の DRY 違反解消)。出力契約統一 + GUI JS フィールド名追随 + tests/ 新設 (pytest 12 ケース)
**対象ファイル**: predictor/portfolio.py (新規), tests/test_portfolio.py (新規), tests/conftest.py (新規), web/generator.py, gui/app.py

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|---|---|---|
| GUI / UX 監査人 | 4.1 | 4.1 | ±0 |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 |
| 予想ロジック分析官 | 4.4 | 4.35 | +0.05 |
| 収益性 / 投資判断 | 3.5 | 3.5 | ±0 |
| データパイプライン技術者 | 4.0 | 4.0 | ±0 |
| コード品質 / 保守性 | **4.6** | 4.2 | **+0.4** |
| 検証プロセス監査人 | 4.2 | 4.0 | +0.2 |

**全体平均 4.11 → 4.20 (+0.09)。後退項目なし。**

本改修は前回 scorecard (20260607_0441) の「横断的優先課題 1: buy_portfolio 集計を共通 helper に抽出」への直接対応。前回 code-quality の唯一の主減点 (DRY 小項目 4→3) を完全解消し、DRY 小項目は **3→5 (+2)**。

## 各専門家の所見 (要約)

### GUI / UX 監査人 — 4.1 / 5 (±0)
描画ロジックの helper 化のみで UX 表層は無介入、退行ゼロの「無害な内部改善」。JS フィールドリネーム (`over_cap`→`any_over_cap`, `day_total_pct`→`max_day_pct`) が参照側と完全整合し、`.over` 赤系警告・「⚠ 上限超過」ピル・空候補非描画 (count=0) の全分岐が生存。node --check PASS。ev 後方互換 fallback で gui item の `"ev"` キーから EV 加重が正しく機能 (exp_return_pct=125.6 確認)。天井固定要因は **input 既定値の config 乖離 (`value="1.05/0/10/20"` vs min_odds=8.0)、5 セッション連続未着手**。

### モバイル HTML レビュアー — 4.6 / 5 (±0)
index.html.j2 / CSS に diff なし。出力契約が portfolio-note (j2:366-371) の参照フィールドと完全一致を維持。再生成した web/dist/index.html で `06/07 21%（6件）` を正しく描画、無効データ混入ゼロ。`★ 上限張り` バッジが recommended_kelly 基準で実データ 5.00% 候補にマーキング (旧 full-Kelly 誤誘導是正済)。繰越減点: `details.buy-board > summary` 左右 padding 0 (3 セッション)。

### 予想ロジック分析官 — 4.4 / 5 (+0.05)
rules.py / features.py / weights.json 完全無編集。**依存方向が模範的**: portfolio.py は `__future__`/`collections.abc`/`config` のみ import し predictor.risk を引かない (循環回避を実機確認)。recommended_kelly は risk.recommended_fraction 由来 fraction を授受し helper 側で再縮小なし (二重縮小バグなし)。多日窓非合算・date 欠損 "?" バケット・ev 後方互換で運用乖離を構造的に抑制。デッドコード/整合性 4.5→5、本番乖離 4→4.5。

### 収益性 / 投資判断 — 3.5 / 5 (±0)
重点 5 観点すべて合格 (実測): (1) 多日窓 max=22.0% で全合算 32% にならない、(2) cap 超過 scale=0.625 で適用後 total=0.2500 に収束、(3) 推奨賭金加重 EV=1.25 が等加重より妥当、(4) ev/expected_value 後方互換で web/GUI 両出典取りこぼしなし (fallback 300.0% 確認)、(5) round(.,2) は web の `%.0f` 表示に無影響。ゼロ除算回避で 0% 誤表示防止。**総合 3.5 維持の理由は回収率本丸 (直近 62.7-85.4%、控除率 80% 跨ぎ) が未改善で天井を抑えるため** — 本改修の集計品質自体は減点なし。指摘: exp_return_pct の reliability gap 注記が表示層に未反映 (前回課題 #3 持ち越し、減点先は表示層)。

### データパイプライン技術者 — 4.0 / 5 (±0)
jvlink_client/ db.py data/schema.sql に diff ゼロ。helper は DB を一切 import せず (sqlite3/db なし)、in-memory dict list を O(n) 単一パス集計。鮮度ゲート (gui/app.py:703-707) は集計呼び出しの上流にあり迂回しない。idempotent=True / 入力 mutation なし / 副作用なしを inline 検証。提案: 入力契約を TypedDict に昇格すれば ingest→集計の契約乖離を静的検知可能。

### コード品質 / 保守性 — 4.6 / 5 (+0.4)
**DRY 3→5**: 両 call site が `compute_day_portfolio(buy_candidates)` の 1 行に、残骸ゼロ。dead import 削除が精密 (web は BET_PORTFOLIO_MAX_PCT のみ削除し recommended_fraction 用 2 定数は残置、gui は 3 定数削除)。magic number 4.5→5。tests/ 新設は **リポジトリ初の pytest 基盤**で高評価。減点要因: subagent 環境 (.venv32/system python) に pytest 未導入で「書いたが回せない」状態と判定 + ev/expected_value 二重契約が残る。

### 検証プロセス監査人 — 4.2 / 5 (+0.2)
backtest/calibrator に diff なし、前向き集計でリーク経路なし。リーク防止 4→4.5: 日単位区切りで多日窓過大化を構造的に防止しその境界を test 固定。境界網羅 (空/scale1.0/按分/多日 max/ev 優先/ゼロ除算 None/generator 入力) が良好。+0.5 を抑えた理由は subagent 環境で pytest 未導入。提案: pytest.ini で testpaths 固定、旧/新出力一致の diff 証跡をログ化。

## 横断的に見た優先課題

1. **pytest を依存・運用フックに正式化** (担当: code-quality + validation + prediction-logic、4 名が指摘) — **補足: 本セッションで `.venv64/Scripts/python.exe` に pytest を導入し 12 ケース全 PASS を確認済み**。ただし requirements-dev.txt / pytest.ini が未整備で、subagent が見た .venv32・system python には未導入。`requirements-dev.txt` に pytest 追記 + `[tool.pytest.ini_options] testpaths=["tests"]` を置き、weekly_monitor.bat 等に `pytest tests/ -q` を組み込んで初の test 基盤を「飾り」にしない。

2. **input 既定値の f-string 注入** (担当: gui-ux, **5 セッション連続**) — gui/app.py の `value="1.05/0/10/20"` を BUY_FILTER_DEFAULT 由来に。F5 初期表示が config (min_odds=8.0) と乖離し続け、既定値を「現在の買い目フィルタ」と誤読させる。発見性 3→4 の最安経路。

3. **exp_return_pct (想定回収) に reliability gap 注記** (担当: profitability, 前回課題 #3 持ち越し) — helper は正しい加重 EV を返すが、その EV 自体が中穴以上で市場 implied の 2-7 倍に過大 (config.py:152)。index.html.j2 と GUI 双方の想定回収表示に「未校正で楽観」注記を。MEMORY feedback_current_buy_candidates_warning と整合。

## 検証ログ
- `python -m py_compile gui/app.py web/generator.py predictor/portfolio.py` → PASS
- `.venv64 pytest tests/test_portfolio.py -q` → **12 passed** (cap 未満/超過按分/多日 max/空 list/ev 後方互換/加重 EV/欠損頑健/generator 入力)
- 埋め込み JS 抽出 (.venv32 import) → `node --check` CONTROL_HTML → PASS (ボタン生存)
- 合成コンテキストで index.html.j2 render → portfolio-note `06-07 40%（2件・⚠各点×0.62） / 06-08 3%（1件）` + 上限超過警告 + ★上限張りバッジを正しく出力
- compute_day_portfolio([]) → 既定契約 (count=0, days=[], exp_return_pct=None, cap_pct=25.0) 確認
