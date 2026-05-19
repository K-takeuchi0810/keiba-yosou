# GUI / UX 監査人 採点 — Phase A1+A2+S5+S6+S7

**改修対象**: `bad4e9c..d5c76ce` (Phase A1+A2+S5+S6+S7)
**評価日**: 2026-05-18
**評価軸**: Phase B1 前のインフラ整備フェーズとして GUI/HTML UX の表現力 + バグ予防構造

## 総合: 3.8 / 5 (前回 P06 3.6 → +0.2)

S7 三連改修 (predictor/filter.py 集約 / HTML UX 5 項目 / pick-reason トリミング) で **HTML 出力側の UX が大幅改善**。一方 CONTROL_HTML 側の `min_kelly` / `max_predicted_p` 入力欄欠落は P05 から 3 期連続温存。

## 項目別

### 1. 情報設計: 4 / 5
- HTML 側で大幅改善。`P / EV / K` 3 メトリクス 1 行表示、Kelly 降順、`★ 強い買い` バッジ、フィルタ条件 header、version snapshot footer
- CONTROL_HTML 側ダッシュボード (`gui/app.py:1438-1441`) は Kelly フィルタ入力欄欠落 = config の主絞り条件が UI に露出していない

### 2. レスポンシブ: 4 / 5 (±0)
- 既存 breakpoint 維持、S7-β 新規 CSS は狭画面で溢れない
- `.conf-tag` ヒット領域は前回繰越し残課題

### 3. ダークモード対応: 4 / 5 (±0)
- 全変数を 2 系統管理、S7 新規 CSS も var() 経由で自動追随
- `--bg-mute` が `:root` 未定義で fallback 固定 (改善余地)

### 4. 認知負荷: 4 / 5 (+1)
- S7-γ で 9 種の無情報プレフィックス除外 + 先頭 4 + 信頼度行末尾保持
- 元の 10-15 シグナルが 4-5 シグナルに圧縮

### 5. バグ予防構造: 5 / 5 (+2、P06 比)
- S7-α が決定打。`predictor/filter.py:is_buy_candidate` 1 関数に集約
- 4 経路 (predict / backtest / gui / generator) が import 経由で参照する形に統一
- `web/generator.py:257-260` の二重防御ガード (`kelly_fraction >= 0.0001`)
- 過去 1 ヶ月で 2 度 (S5-3, S7-α) 同種の漏れが発生したことへの学習が織り込まれた

## 改善提案 (優先 3 件)

1. **CONTROL_HTML の filter input を `min_kelly` / `max_predicted_p` 主体に再構成** (3 期連続温存中の最優先課題) — `gui/app.py:1438-1441` を更新
2. **HTML buy-board の `★ 強い買い` 閾値 (0.10) を `config.BUY_FILTER_STRONG_KELLY` で外出し** — Phase B1 後の閾値 tuning コストを 1 箇所に集約
3. **`_trim_rationale` の除外プレフィックスを per-signal metadata に移行** — `predictor/rules.py` の rationale 生成側で `(signal_text, importance: int)` タプル化、Phase B1 と同期させる long-term 案件

## 関連ファイル
- `predictor/filter.py` (新設、唯一の判定関数)
- `gui/app.py:271-295` (delegate 化)、`gui/app.py:1438-1441` (未着手の input 既定値)
- `web/generator.py:294-296, 315-340, 343-370, 73-96` (Kelly sort / filter_summary / version_snapshot / _trim_rationale)
- `web/templates/index.html.j2:106-150, 321-348, 417-427` (CSS / buy-board / footer)
