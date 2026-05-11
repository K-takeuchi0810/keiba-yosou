# GUI / UX 監査人 採点

**改修**: P0-1 — buy_filter を `config.BUY_FILTER_DEFAULT` に一元化、新 API `Api.get_buy_filter_default()` を追加し JS 起動時に input 初期値を Python 側から取得
**日時**: 2026-05-10 23:00
**対象**: gui/app.py (config.py / web/generator.py は連携確認のみ)

## 総合: 3.2 / 5

JS パース確認: `node --check` → CONTROL_HTML 内 JS (12,824 byte、ベースライン比 +486 byte) は構文エラーなし。新 API `get_buy_filter_default` を呼ぶ Promise チェーン (`gui/app.py:1640-1660`) も妥当。総合 1 確定の致命傷は無し。

UX 観点で言うと、本改修は**ユーザに見える挙動が変わらない裏方リファクタ**。input の初期値 (1.05/0/10/20) は HTML 静的値・JS フォールバック・Python 配信値のどれを引いても同じ数値が出るので、画面体験は完全に同じ。よって UX スコアの動意は基本的にゼロで、前回弱点 (ヘルプ無し / hint 不足 / overflow / aria) はすべて未着手。前回 3.2 → 今回 3.2 (±0)。「config を弄ったときに input にも反映される」という潜在的可用性は上がっているが、ユーザは config.py を触らないので体感差分は無い。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — `data-action` 駆動 + Ⅰ/Ⅱ/Ⅲ/Ⅳ ステップ表示は前回どおり良。`<details id="helpBox">` 不在、Ⅱ→Ⅲ の依存表記不在も前回どおり。本改修ではこの軸の触り方なし。±0。

- **エラー人間化 / 復旧支援: 3/5** — `_error_hint` の網羅 5 ケースのまま。新 API `get_buy_filter_default` は `_safe` デコレータ経由なので失敗時は `{ok:false}` を返すが、JS 側 `restoreOptions()` (gui/app.py:1640-1660) は `res.filter` が無いケースを単にスルーするだけで、ユーザに「フィルタ初期値の取得に失敗した。HTML 既定値で続行」のような通知が無い。サイレント縮退でも実害は無いが「人間化」観点では加点要素にもならない。±0。

- **進捗表示 / ETA / キャンセル: 3/5** — 本改修は進捗系を一切触っていない。ETA 序盤ジャンプ・`render()`/`publish_to_icloud()` 中の cancel 不通も前回どおり。±0。

- **二重実行防止 / ボタン状態管理: 3/5** — `inFlight` フラグ未導入のまま。`_run_lock` も未導入。本改修では触っていない。なお新 API `get_buy_filter_default` は `_status` を更新せず軽量で、ポーリング経路に追加負荷もないので、二重実行リスクは増えていない。±0。

- **レイアウト / タップ領域 / アクセシビリティ: 2/5** — `.sidebar { overflow: hidden }` のまま。input には `title=` も `aria-label` も付与なし。本改修ではこの軸の触り方ゼロ。±0。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **HTML 静的 `value="1.05"/0/10/20` と JS `inputNumber(..., 1.05)` フォールバックを Python 側 default で置換し、本当の意味で「単一出典」にする** — 現状 `gui/app.py:1374-1377` の input には依然 `value="1.05"` 等が直書きされ、`gui/app.py:1446-1449` の `inputNumber('filter_ev', 1.05)` フォールバックにも同値が残る。`config.BUY_FILTER_DEFAULT` を変えても、API 取得失敗時 (例: pywebview ready 前のレース) には旧値が表示される。HTML 側は `value=""` に空にし、JS 起動時に `applyBuyFilter` で必ず埋める / `inputNumber` の第二引数も `window.__defaults?.min_ev ?? 1.05` のような形にする、もしくは Python が文字列置換でテンプレ生成時に埋め込む方が真の一元化。

2. **`get_buy_filter_default` 失敗時のサイレント縮退をやめ、`detailsBox` に薄い注意を出す** — `gui/app.py:1644-1646` で `res.filter` が falsy のケースは何もせずに通過する。ここで `setDetails('警告', '買い目フィルタ初期値の取得に失敗。HTML 既定値で続行します')` を出せば、config を変えたのに反映されない事故にユーザが気づける。コスト数行。

3. **(継続) サイドバー overflow と helpBox 追加** — 前回の最優先提案がそのまま残っている。今回は別軸の改修なので持ち越しだが、項目 5 が 2/5 のままだと総合が 3 台から動かない。次回以降の P0 候補。

## 前回からの差分 (前回スコアがあれば)

- ボタン発見性: 4 → 4 (±0) 触り無し
- エラー人間化: 3 → 3 (±0) 新 API のサイレント縮退のみ追加、hint 拡充は無し
- 進捗 / ETA / キャンセル: 3 → 3 (±0) 触り無し
- 二重実行防止: 3 → 3 (±0) 新 API は軽量で無害、本筋は未着手
- レイアウト / アクセシビリティ: 2 → 2 (±0) 触り無し
- **総合: 3.2 → 3.2 (±0)** UX に直接効く改修ではないため点は動かない。ただし config 変更時の input 自動追従という保守性向上は記録に値する。
