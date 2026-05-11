# GUI / UX 監査人 採点

**改修**: a (walk-forward 検証) + e (sweep + filter 更新)
**日時**: 2026-05-11 23:45
**対象**: `gui/app.py` (Api._is_buy_candidate / CONTROL_HTML JS) + `config.BUY_FILTER_DEFAULT`
**JS 検証**: `node --check` PASS (JS len 12824)

## 総合: 3.6 / 5

`config.BUY_FILTER_DEFAULT` に `min_popularity` / `max_popularity` / `exclude_confidence` を追加し、`_is_buy_candidate` が `race=` を受け取って whitelist + 人気帯 + 信頼度除外を横断適用する形に整流化。`min_ev` / `min_value` の `None` を「制約なし」として扱うよう書き直しており、sweep 結果 (wl_ex_unsure_pop_1_4 / eval 89.0%) を Python 単一出典で再現可能。一方 CONTROL_HTML 側は 4 つの input (EV / Value / Odds min / max) のみで、**人気帯 / 信頼度除外を UI から弄れない継続課題**が残る。前回 3.6 → 3.6 (±0)。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — Ⅰ→Ⅳ フロー不変。helpBox 不在は 5 改修連続持ち越し。±0。
- **エラー人間化 / 復旧支援: 4/5** — `>{max_age}分` 鮮度警告は P2-1 から継続。`exclude_confidence` リスト化で「なぜ買い候補から外れたか」の根拠が config 一箇所で説明可能に。±0。
- **進捗表示 / ETA / キャンセル: 3/5** — 触り無し。±0。
- **二重実行防止 / ボタン状態管理: 3/5** — `_is_buy_candidate` シグネチャに `race=` 追加、呼出側 (`gui/app.py:627`) 同期済。TypeError リスク無し。±0。
- **レイアウト / タップ領域 / アクセシビリティ: 2/5** — `min_popularity` / `max_popularity` / `exclude_confidence` の **dashboard input が未追加**。sweep の主絞り条件 (1-4 人気) が GUI から見えないため、ユーザは「なぜ買い候補が前より減った/増えたか」を config.py を直読するまで把握不能。±0 だが −1 圏内。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **継続課題: 人気帯 / 信頼度 input を dashboard に露出** — `gui/app.py:1401-1404` の filter 行に `<label>人気<input id="filter_min_pop" type="number" min="1" max="18" value="1"> 〜 <input id="filter_max_pop" type="number" min="1" max="18" value="4"></label>` を追加し、`buildFilter()` (line 1472-1477) と `applyBuyFilter()` (1661-1666) に `min_popularity` / `max_popularity` を通す。sweep で採用した主絞り条件 (1-4 人気) が UI で可視・調整可能になる。
2. **信頼度除外をチェックボックス化** — `exclude_confidence: ["暫定","混戦","接戦"]` を 3 つのチェックボックスとして CONTROL_HTML に出す。リストが構造データなので number input より checkbox 群が自然。サーバ側で `filters.get("exclude_confidence", default)` は既に対応済なので JS 側追加だけで済む。
3. **(継続) サイドバー `overflow-y:auto` + `<details id="helpBox">`** — 5 改修連続持ち越し最優先。新 helpBox には「P0-4 sweep で wl_ex_unsure_pop_1_4 (1-4人気+重賞/中山京都+信頼度除外) を採用、eval 期 89.0%」と書けば、フィルタ既定値の根拠が UI で完結する。

## 前回からの差分 (3.6 → 3.6)

- ボタン発見性: 4 → 4 (±0)
- エラー人間化: 4 → 4 (±0) — 鮮度警告は前回完了、今回は除外理由の構造化のみ
- 進捗 / ETA / キャンセル: 3 → 3 (±0)
- 二重実行防止: 3 → 3 (±0)
- レイアウト / アクセシビリティ: 2 → 2 (±0) — 新 filter キー (人気帯 / 信頼度) が **GUI dashboard input に露出していない** 継続課題
- **総合: 3.6 → 3.6 (±0)** — 内部出典統一は P2-1 で既に加点済。今回は config 拡張 + Python 側適用に留まり UI 露出ゼロのため横ばい。
