# 採点 2026-06-07 04:41

**改修内容**: GUI ダッシュボード情報設計改善 — 誤ラベル「上位予想プレビュー」削除 / 買い候補ポートフォリオ集計バー追加 (N点・推奨投資率・想定回収) / 買い候補ピルをフル Kelly → recommended_kelly 表示に是正
**対象ファイル**: gui/app.py (get_dashboard, CONTROL_HTML/JS/CSS)

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|---|---|---|
| GUI / UX 監査人 | 4.1 | 4.0 | +0.1 |
| コード品質 / 保守性 | 4.2 | 3.9 | **+0.3** |
| 収益性 / 投資判断 | 3.5 | 3.5 | ±0 |
| 予想ロジック分析官 | 4.35 | 4.35 | ±0 (ドメイン未変更) |
| データパイプライン技術者 | 4.0 | 4.0 | ±0 (ドメイン未変更) |
| 検証プロセス監査人 | 4.0 | 4.0 | ±0 (ドメイン未変更) |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 (ドメイン未変更) |

**後退項目: なし。** (code-quality の DRY 小項目は 4.0→3.0 だが、dead code +1.0 / magic -number +1.5 が上回り総合は +0.3)

## 各専門家の所見 (要約)

### GUI / UX 監査人 — 4.1 / 5 (4.0 → +0.1)
誤ラベルの死にゾーン「上位予想プレビュー」(実体は list_races 開催順で最初の4レース本命) を section/JS/dead CSS ごと撤去。新設 `.buy-portfolio` バーが「N点 / 推奨投資 X% / 想定回収 Y%」を1行集約し手動 Kelly 合算を解消、over_cap 時 `.over` 赤系警告。レイアウト/アクセシビリティ 4→4.5。発見性 (3) が天井を抑える: ボタン title / helpBox / **input 既定値乖離 (1513-1516, 3 セッション連続)** が未着手。node --check PASS。

### コード品質 / 保守性 — 4.2 / 5 (3.9 → +0.3)
dead code 一括撤去で残骸ゼロ (項目2: 4→5)。前回壁だった config↔risk.py 単一出典化が完成 (magic: 3→4.5)。**唯一の DRY 減点 (4→3)**: buy_portfolio 日次集計が web/generator.py:344-378 の by_day_total と同型再実装。共通 helper 抽出を強く推奨 (→ 別タスク化済)。

### 収益性 / 投資判断 — 3.5 / 5 (±0)
集計ロジック検証で 4 点すべて合格: (1) recommended_fraction (quarter+cap) が web と整合、(2) 日単位集計で多日窓過大化なし、(3) exp_return の推奨賭金加重 EV は等加重より優れる、(4) フル Kelly 廃止は破綻ベット防止に直結。Kelly/投資割合 3.5→4.5。回収率本丸は未変更で総合 3.5 維持。
**指摘 → 本セッションで修正済**: recommended_kelly の格納スケールが web(fraction) と GUI(%) で乖離 → GUI も **fraction 格納に統一**、表示直前に pct2() で ×100。同名異スケール footgun を解消。

### 予想ロジック / データパイプライン / 検証プロセス / モバイル HTML — いずれも ±0 (ドメイン未変更)
predictor/ ・ jvlink_client/ ・ scripts/ ・ web/ に diff なし。recommended_fraction は import して表示に使ったのみ。get_dashboard の SQL クエリ本体も不変。前向き集計のためリーク経路なし (検証監査人)。モバイル: web 側 portfolio_info が GUI より進んだ日別集計を既に持つため移植不要、想定回収% のみ控えめ表示なら検討余地 (MEMORY の実弾警告と整合必須)。

## 横断的に見た優先課題

1. **buy_portfolio 集計を共通 helper に抽出** (担当: code-quality + profitability) — `predictor/portfolio.py` に `compute_day_portfolio()` を切り出し web/generator.py:344-378 と gui/app.py の重複を解消。CLAUDE.md が警告する「単一出典乖離クラス」。DB 不要の純粋関数なので tests/ 新設の第一歩にもなる。**別タスク化済 (web パイプライン検証を伴うため)**。

2. **input 既定値の f-string 注入** (担当: gui-ux, 3 セッション連続) — gui/app.py:1513-1516 の `value="1.05/0/10/20"` を `BUY_FILTER_DEFAULT` 由来に。F5 初期表示が config (min_odds=8.0) と乖離。

3. **想定回収 (exp_return_pct) に reliability gap 注記** (担当: profitability) — 校正後 EV は中穴以上で楽観側。「賭けてよい」誤読を防ぐ注記を。MEMORY feedback_current_buy_candidates_warning と整合。

## 検証ログ
- `python -m py_compile gui/app.py` → PASS
- 埋め込み JS 抽出 → `node --check` → PASS (ボタン生存)
- recommended_fraction(0.20)=0.05 (cap), (0.08)=0.02 を venv で確認
- モック描画で「推奨 1.55%/0.88%」(fraction 0.0155/0.0088 から)・portfolio バー・preview 撤去を DOM eval 確認
- scale 統一後の再描画で pct2() 表示正常を確認
