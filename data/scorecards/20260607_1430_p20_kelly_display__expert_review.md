# 採点 2026-06-07 14:30 — P20 予想 HTML Kelly 表示是正

**改修内容**: 予想 HTML の買い候補 Kelly 表示を full Kelly (過大、合計 115%) から recommended_fraction (quarter + per-bet cap) に是正 + ポートフォリオ上限警告 + over-confidence caveat
**対象ファイル**: predictor/risk.py, config.py, web/generator.py, web/templates/index.html.j2

**診断起点**: 2026-06-06 dist の買い候補 8 件が全件 4〜14 人気 (オッズ 8〜48 倍)、モデル P が市場 implied の 2〜7 倍 (系統的 over-confidence)、full Kelly 合計 115.6%。reliability gap 補正後は Kelly 合計 27.5% / ★強い買い 6→0 件。

---

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|--:|--:|--:|
| GUI / UX 監査人 | 3.8 | 3.8 | ±0 |
| モバイル HTML レビュアー | 4.4 | 4.6 | -0.2 |
| 予測ロジック分析家 | 4.2 | 4.1 | +0.1 |
| 収益性判定家 | 3.4 | 3.5 | -0.1 |
| データパイプライン技術者 | 4.0 | 4.2 | -0.2 |
| コード品質レビュアー | 3.9 | 4.3 | **-0.4 ⚠ 後退** |
| 検証プロセス監査人 | 3.4 | 4.6 | **-1.2 ⚠ 後退** |

**平均**: 3.87 / 5

**注記**: 上記は **follow-up fix 適用前** の版に対する採点。後退 2 件 (検証 -1.2 / コード品質 -0.4) の指摘は下記 follow-up fix で直接対応済。

---

## 各専門家の所見 (要点)

### 収益性判定家 (3.4, -0.1)
quarter+5%cap+25% portfolio cap の三層は実弾防御として妥当。full Kelly 副次表示の判断も是。ただし **P20 は回収率を 1 円も動かさない表示層 fix で、根本の over-confidence (P が市場の 2-7 倍) は Phase B1 まで残存**。「推奨 4.68%」表示がユーザーに安心感を与え楽観を見えにくくする副作用を懸念。改善提案: ① kelly_weighted_return_rate を backtest に追加、② 縮小後の各点推奨額も表示、③ **HTML に over-confidence 警告バナー追加**。

### モバイル HTML レビュアー (4.4, -0.2)
CSS 変数流用・ダークモード対応は正しい。減点は情報密度: buy-metrics が P/EV/推奨/full Kelly の **4 値併記**で 320px 狭画面で折り返し増、portfolio-note 警告文 50 字が 3 行折り返し。改善提案: ① 480px 以下で buy-metrics を 2 段組、② portfolio-note の padding 圧縮。

### コード品質レビュアー (3.9, -0.4) ⚠
recommended_fraction 切り出し + 純粋関数化は +。ただし **config 定数が risk.py のデフォルト引数と二重定義、「単一出典」が看板倒れ** (最大指摘)。理想は risk.py が `from config import BET_KELLY_*` してデフォルトに使う。+ generator.py に無関係な icloud sync 診断コードが混在、commit 分離推奨。

### 検証プロセス監査人 (3.4, -1.2) ⚠⚠
**最大の後退**。診断で測った reliability gap (P 0.2-0.3 帯→真値 12.3% 等) が **HTML にもコメントにも開示されず、backtest アーティファクトにも残っていない**。fix が終始「sizing/variance 問題」として説明され **calibration 問題であることを構造的に隠蔽**、「表示が直った=直った」誤認リスク。改善提案: ① **over-confidence の限界を HTML とコメントに明示**、② 診断数値を再現可能アーティファクト化、③ P20 単独コミット化。

### 予測ロジック分析家 (4.2, +0.1)
predictor 本体は P20 で未編集 (rules.py の jump-surface guard は別 topic の先行変更)。recommended_fraction 単一出典化は運用安全に寄与。診断露呈の課題を次候補として指摘: ① rank ベース印に確率フロア導入 (P=0.3% 馬に ▲ が付く問題)、② pick-reason に確率駆動シグナル明示。

### データパイプライン技術者 (4.0, -0.2)
ingest/parser/schema 無編集、新規 DB アクセスなし。減点は診断で表面化した **odds_fetched_at が DB にあるのに HTML 非露出 + win_odds が前夜暫定値** の鮮度欠陥 (P3 候補)。

### GUI / UX 監査人 (3.8, ±0)
gui/app.py 無編集で維持。node --check PASS。新指摘: config.BET_KELLY_* を GUI から確認/変更する導線が皆無 (次回 GUI 改修候補)。

---

## follow-up fix (採点後・後退 2 件への直接対応)

検証 -1.2 + コード品質 -0.4 の指摘が正当なので即対応:

### fix-A: over-confidence の常時開示 (検証 #1 + 収益性 #3)
- `web/templates/index.html.j2`: 買い候補ボードに `.calib-caveat` を常設 — 「⚠ 表示の P/EV/Kelly は**未校正の予想確率**に基づく。中穴〜大穴の勝率を市場想定の 2〜7 倍に過大評価する傾向があり実際の期待値は低い。再訓練 (Phase B1) まではロジック観察用、実弾投入は非推奨」
- `config.py` / `predictor/risk.py`: コメントに「quarter+cap は variance 抑制であって calibration ではない、over-confidence の矯正は Phase B1 領域」を明記
- MEMORY「実弾運用を控える」方針と整合

### fix-B: config 単一出典化 (コード品質 #2)
- `predictor/risk.py`: `from config import BET_KELLY_MAX_PCT, BET_KELLY_MODE` し、`recommended_fraction` / `kelly_size` のデフォルトを `None`→config fallback に変更。二重定義を解消 (risk→config 一方向依存、循環なし)。検証: rec(0.187)=0.0467 / rec(0.30)=0.05 / size 不変

### fix-C: 狭画面情報密度 (モバイル #1+#2)
- `@media (max-width:480px)`: `.full-kelly-note` を block 改行配置、`.portfolio-note` padding 圧縮

**再検証 (2026-06-06 再render)**: caveat 表示 OK / 推奨 4.68% (full Kelly 18.7%) / portfolio 28.9% + ×0.87 警告 / DRY 単一出典動作 OK。

---

## 横断的に見た優先課題 (P20 後の残課題)

1. **【根本・Phase B1】over-confidence そのものの矯正** (検証 + 収益性 + 予測ロジックが共通指摘) — P20 は誠実な開示まで。LGBM v6 再訓練 + 再校正でモデル P を市場整合へ。fix-A の caveat はそれまでの暫定開示
2. **【P3 候補】odds 鮮度の HTML 露出** (データパイプライン) — odds_fetched_at を買い候補カードに「○分前」表示 + BET_MAX_ODDS_AGE_MIN 超過警告。前夜暫定オッズで算出した EV を確定値と誤認する事故を防ぐ
3. **【P4 候補】rank ベース印に確率フロア** (予測ロジック) — P<3% の馬に ◎○▲ が付かないよう mark 確定前にガード。over-confidence 根治はしないが表示暴走の応急弁

## commit 衛生 (複数 reviewer 指摘)

現 working tree は P20 (config/risk/generator/template) と **本セッション開始前から存在する無関係変更** (predictor/rules.py jump guard, scripts/backtest.py 距離バケット, web/generator.py icloud sync 診断, scripts/q1_root_cause.py + season_brier_test.py の _stats_helper 化) が混在。P20 単独コミットには generator.py の icloud 部分と P20 部分を分離する必要があり、ユーザー判断待ち。
