# 採点 2026-06-07 04:18

**改修内容**: gui/app.py CONTROL_HTML/PREVIEW_HTML の見た目改修 — 主要 CTA 濃色塗り化・card コントラスト/影強化・無音クリッピング(overflow/warnings/grid 行不一致)解消・フォント拡大・色トークン化(--buy/--primary系)・focus-visible 追加
**対象ファイル**: gui/app.py (CONTROL_HTML, PREVIEW_HTML, main background_color)

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|---|---|---|
| GUI / UX 監査人 | 4.0 | 3.6 | **+0.4** |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 (ドメイン未変更) |
| 予想ロジック分析官 | 4.35 | 4.35 | ±0 (ドメイン未変更) |
| 収益性 / 投資判断 | 3.5 | 3.5 | ±0 (ドメイン未変更) |
| データパイプライン技術者 | 4.0 | 4.0 | ±0 (ドメイン未変更) |
| コード品質 / 保守性 | 4.0 | 3.9 | +0.1 |
| 検証プロセス監査人 | 4.0 | 4.0 | ±0 (ドメイン未変更) |

**後退項目: なし。全項目維持または改善。**

CSS のみの改修のため、GUI/UX・コード品質の 2 軸のみが実評価対象。残り 5 軸は担当ドメイン (predictor / backtest / jvlink / web / scripts) に変更がなく前回値を維持。

## 各専門家の所見

### GUI / UX 監査人 — 4.0 / 5 (3.6 → 4.0, +0.4)
`node --check` PASS / Python ロジック不変でボタン全数生存。長期間 1/5 で総合を頭打ちにしていた「レイアウト/アクセシビリティ」を **1 → 4 (+3)** へ。3 件の無音データ欠落バグを実コードで解消:
(1) `#warnings .warn-item:nth-child(n+4){display:none}` 削除 → 4 件目以降の注意点が消えていたバグ修正、
(2) `.sidebar`/`.main` の `overflow:hidden` → `overflow-y:auto` で長コンテンツのクリッピング解消、
(3) `.dashboard-grid` の `grid-template-rows`(4定義) vs 実配置 5 行バンド不一致を `grid-auto-rows:min-content;align-content:start` 化し最下段プレビュー切れ解消。
加えて主要 CTA を「ほぼ白の灰文字」→「濃色塗り+白文字 weight600+shadow」化(disabled でも白文字濃色維持)、focus-visible 追加、card/ラベルのコントラスト・letter-spacing 適正化(card-title 9.1px→.69rem 等)。
満点に届かない 3 点: (a) 各ボタンの title ホバーヒント 0 個、(b) aria-label/role 不在、(c) **input 既定値乖離 (1464-1467 の value="1.05/0/10/20") が 3 セッション連続で温存**。

### モバイル HTML レビュアー — 4.6 / 5 (±0, ドメイン未変更)
本セッション diff は gui/app.py のみ。web/templates/ ・ web/generator.py は作業ツリー clean。pywebview デスクトップ GUI は iPhone 向け出力と別物のため再採点不要。
**要フラグ**: P20 (05c2724 等) で web/ 担当ソースが +185 行変更されたが mobile-html-reviewer の採点を一度も通っていない。4.6 は厳密には 2026-05-18 時点の評価で、P20 web/ 改修分は未評価据え置き。次に web/ を触る際に再採点が必要。
転用 learnings: GUI のコントラスト強化と同思想で `.strong-buy-badge` の dark 地色を CSS 変数明示すると屋外 iPhone で badge 沈み込み防止に有効。

### 予想ロジック分析官 — 4.35 / 5 (±0, ドメイン未変更)
predictor/rules.py / features.py / weights.json 無変更。CSS 改修はシグナル・重み・確率推定に一切関与せず。前回値 (20260518 phase_a1_to_s7) を維持。LGBM v5 高 p 帯の構造楽観は Phase B1 でのみ解消予定で本件と無関係。

### 収益性 / 投資判断 — 3.5 / 5 (±0, ドメイン未変更)
diff を収益性キーワード (`_investment_probability`/`_bet_metrics`/`_value_score`/`kelly`/`backtest` 等) で grep し加除ゼロ確認。回収率が控除率 80% 未到達なのは前回同様で、押し上げ経路は Phase B1 (LGBM v6) のみ。CSS 改修に収益性回帰なし。

### データパイプライン技術者 — 4.0 / 5 (±0, ドメイン未変更)
jvlink_client/ ・ db.py ・ schema.sql ・ data/raw/ 無変更。diff に Python/SQL/COM/ingest 行なし。ingest mtime カラム欠如・JVStatus timeout は 8 連続持ち越しだが本件と無関係。

### コード品質 / 保守性 — 4.0 / 5 (3.9 → 4.0, +0.1)
買い目色 (#9f1239/#fff1f2/#fecdd3) と CTA 濃色を `--buy*`/`--primary*` トークンに集約した DRY の正攻法を評価。根拠コメント付きで意図追跡可能。
**指摘 → 本セッション内で修正済**: `button.primary:hover` の gradient `#3a4656`/`#111827` 直書き漏れを指摘 → `--primary-soft`/`--primary-deep`/`--on-primary` を :root に追加し base/hover/disabled 全状態を単一出典化(magic number 項 3→4 相当)。
**残課題**: CONTROL_HTML と PREVIEW_HTML が別 triple-quoted 文字列で `:root` を二重定義(平行記述)。共通 token を Python 定数に切り出し f-string 注入すれば物理的に解消できる。

### 検証プロセス監査人 — 4.0 / 5 (±0, ドメイン未変更)
scripts/ ・ calibrator.json ・ weights.json 無変更。backtest/calibration/リーク防止/A-B 比較に触れるロジック行ゼロ。GUI 改修は backtest 数値・予想出力・校正データを変更せず回帰リスクゼロ。

## 横断的に見た優先課題

1. **input 既定値を `BUY_FILTER_DEFAULT` から f-string 注入** (担当: gui-ux-auditor)
   - `gui/app.py:1464-1467` の `value="1.05"/"0"/"10"/"20"` を config 由来に置換。F5 初期表示が config (`min_odds=8.0`) ではなく UI 既定値で絞った小集合になる **3 セッション連続の宿題**。見た目が整った今こそ「表示される数字自体の正しさ」を直すべき。これで GUI 総合 4.2 圏。

2. **共通 token を Python 定数に切り出し二重 `:root` 定義を解消** (担当: code-quality-reviewer)
   - CONTROL/PREVIEW の重複 token (`--bg`/`--surface`/`--border`/`--text` 等) を `BASE_TOKENS` 定数化し両 HTML へ注入。片方変更時の追随漏れリスク(P20 の risk↔config 二重定義と同質)を構造的に除去。

3. **各 data-action ボタンに title ホバーヒント + helpBox 追加** (担当: gui-ux-auditor)
   - 各 `<button>` に `title="..."` を付与し、sidebar 末尾に `<details id="helpBox">` で Ⅰ取得→Ⅲ予想→Ⅳ公開のフロー依存を明文化。低コストで発見性項目を底上げ。

## 検証ログ
- `python -m py_compile gui/app.py` → PASS
- 埋め込み JS を Python 解釈後に抽出し `node --check` → PASS (JS 不変、ボタン生存)
- primary hover の token 化を確認 (var(--primary-soft)/--primary-deep)
