# GUI / UX 監査人 採点

**改修**: P1-1 — `predictor/rules.py` リファクタ (dead feature 5 件削除、直書き定数 60→1、`_w()` 参照 48→121、backtest 数値完全一致)
**日時**: 2026-05-11 00:30
**対象**: gui/app.py (今回 **変更なし**。`predictor/rules.py` のみ)

## 総合: 3.2 / 5

GUI 担当範囲は完全に手付かず (CONTROL_HTML / PREVIEW_HTML / Api クラスとも diff ゼロ)。`predictor/rules.py` の内部リファクタは backtest 数値完全一致を保証している = ユーザの目に映るスコア・印・買い候補は 1 ティックも動かない。よって UX 観点での加点・減点要素は本質的に存在せず、前回 P0-3 (3.2/5) のスコアをそのまま維持する。**3.2 → 3.2 (±0)**。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — HTML 未変更。Ⅰ/Ⅱ/Ⅲ/Ⅳ 番号ステップ維持。±0。
- **エラー人間化 / 復旧支援: 3/5** — `_safe` / `_error_hint` も未変更。P0-3 で発生した「whitelist 除外で買い候補ゼロが無言」課題は持ち越し、±0。
- **進捗表示 / ETA / キャンセル: 3/5** — 触り無し。±0。
- **二重実行防止 / ボタン状態管理: 3/5** — 触り無し。`predictor/rules.py` の関数シグネチャは不変なので呼出側 (`gui/app.py:611` 周辺) も無傷で TypeError リスクゼロ。±0。
- **レイアウト / タップ領域 / アクセシビリティ: 2/5** — 触り無し。サイドバー overflow / aria-label / helpBox 不在の継続課題、±0。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **(継続) ダッシュボード filter 行に whitelist トグル** — P0-3 提案の持ち越し最優先。`gui/app.py` CONTROL_HTML の filter input 群に `<input type="checkbox" id="whitelistMode">` を追加し Api 側 `bet_filter` に流す。これだけで項目 1/2 が +0.5 ずつ動く。
2. **(継続) preview 側に「whitelist 除外」バッジ** — `web/generator.py` で各レースに `excluded_by_whitelist` を埋め PREVIEW_HTML race ヘッダに `<span class="badge muted">重賞外</span>` を出す。候補ゼロの理由がユーザに伝わる。
3. **(継続) サイドバー `overflow-y:auto` + `<details id="helpBox">`** — 3 改修連続持ち越し。helpBox に「重賞ホワイトリスト」「P1-1 リファクタで weight キー名が `_v2` 系に正規化された」等の運用注記を載せる。

## 前回からの差分 (3.2 → 3.2)

- ボタン発見性: 4 → 4 (±0) — gui/app.py 無変更
- エラー人間化: 3 → 3 (±0) — gui/app.py 無変更
- 進捗 / ETA / キャンセル: 3 → 3 (±0) — gui/app.py 無変更
- 二重実行防止: 3 → 3 (±0) — rules.py シグネチャ不変、呼出側影響なし
- レイアウト / アクセシビリティ: 2 → 2 (±0) — gui/app.py 無変更
- **総合: 3.2 → 3.2 (±0)** — 担当範囲未変更につきスコア維持。リファクタ自体は健全 (動作不変保証 + 直書き定数削減で将来の GUI 連携時に weight 値の trace がしやすくなる、間接的プラス) だが GUI 表面はゼロ差分のため数値には反映せず。
