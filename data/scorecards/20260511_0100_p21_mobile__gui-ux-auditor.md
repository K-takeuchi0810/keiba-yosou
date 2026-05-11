# GUI / UX 監査人 採点

**改修**: P2-1 — モバイル CSS (`web/templates/index.html.j2`) 主体だが、実際は `gui/app.py` にも +55 / -17 の差分あり (whitelist 統合・BUY_FILTER 単一出典化)
**日時**: 2026-05-11 01:00
**対象**: gui/app.py (CONTROL_HTML JS / Api クラス)。`node --check` パスOK。

## 総合: 3.6 / 5

ユーザ申告は「gui/app.py 変更なし」だが `git diff HEAD -- gui/app.py` 実測で **+55 / -17**、しかも内容が前回 P1-1 scorecard の最優先継続提案 2 件 (① whitelist トグル相当の `_is_buy_candidate(race=race)` 統合 ② フィルタ初期値の Python 単一出典化) を直接潰す改修。CONTROL_HTML 側にも `applyBuyFilter()` ヘルパと `get_buy_filter_default` API 経路が新設され、ハードコード `value="1.05"` と Python 側 `BET_MIN_*` のズレ事故が構造的に消える。**3.2 → 3.6 (+0.4)**。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — Ⅰ/Ⅱ/Ⅲ/Ⅳ 番号フロー継続。±0。
- **エラー人間化 / 復旧支援: 4/5** — `gui/app.py:644` の鮮度警告が `>{max_age}分` を埋め込み、ユーザが現行閾値を視認可能に。+1。
- **進捗表示 / ETA / キャンセル: 3/5** — 触り無し。±0。
- **二重実行防止 / ボタン状態管理: 3/5** — 触り無し。`_is_buy_candidate` シグネチャに `race=` 追加だが既存呼出 (`gui/app.py:611`) を同コミットで更新済、TypeError リスク無し。±0。
- **レイアウト / タップ領域 / アクセシビリティ: 2/5** — `gui/app.py` 側のレイアウト改修ゼロ (モバイル CSS は `web/templates/` 担当範囲外)。サイドバー overflow / aria-label / helpBox 不在は 4 改修連続持ち越し。±0。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **(継続) サイドバー `overflow-y:auto` + `<details id="helpBox">`** — 4 改修連続持ち越し最優先。CONTROL_HTML の `.sidebar` に `max-height: 100vh; overflow-y:auto;` + 末尾に helpBox を 1 ブロック追加するだけ。helpBox に「BET_WHITELIST=1 で重賞のみ買い」「フィルタ初期値は config.BUY_FILTER_DEFAULT 単一出典 (P2-1 で統一)」を載せる。
2. **whitelist 状態の UI 可視化** — `_is_buy_candidate` で sily に whitelist 除外しても CONTROL 側に表示が無い。`get_buy_filter_default` 応答に `whitelist_enabled: bool` を足し、フィルタ行末に `<span class="badge">重賞のみ</span>` を出すと「買い候補ゼロ」の理由が明示される。
3. **フィルタ input に `aria-describedby`** — 4 つの number input (`filter_ev` / `filter_value` / `filter_min_odds` / `filter_max_odds`) に `<small id="filter_ev_hint">期待値 ≥ N を買い候補に</small>` + `aria-describedby` を付与。タップ領域 / 視覚障碍対応で項目 5 を 2→3 に押し上げ可能。

## 前回からの差分 (3.2 → 3.6)

- ボタン発見性: 4 → 4 (±0) — フロー UI 不変
- エラー人間化: 3 → 4 (+1) — 鮮度警告に閾値埋込 + フィルタ単一出典で「数値が UI と内部でズレる」系の暗黙バグが構造的に消えた
- 進捗 / ETA / キャンセル: 3 → 3 (±0)
- 二重実行防止: 3 → 3 (±0) — シグネチャ変更だが呼出側同期済
- レイアウト / アクセシビリティ: 2 → 2 (±0) — `gui/app.py` 担当範囲ではモバイル CSS 改修の恩恵ゼロ
- **総合: 3.2 → 3.6 (+0.4)** — 前回最優先提案の whitelist 統合 + 初期値単一出典化が両方落ちたため加点。ユーザ申告「変更なし」は実体と齟齬あり、要確認。
