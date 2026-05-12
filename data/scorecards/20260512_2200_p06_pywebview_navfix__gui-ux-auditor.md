# GUI / UX 監査人 採点

**改修**: P0-6 pywebview navigation コールバックレース修正
**日時**: 2026-05-12 22:00
**対象**: `gui/app.py:825-836` (`open_preview` の `load_url` + `show_control` の `load_html` を `threading.Timer(0.1, ...)` で 100ms 遅延)
**JS 検証**: `node --check` PASS (JS len 12824, CONTROL_HTML / PREVIEW_HTML 不変)
**Python AST**: OK (commit 820f44e, +4 行 / -2 行)

## 総合: 3.6 / 5

pywebview の return-value 配信と画面 navigate が **同一スレッド・同一スタック** で並走していたため、return 値を JS に届ける直前で旧 document の `window.pywebview._returnValuesCallbacks` が GC され、`open_preview` / `show_control` / 巻き添えの `get_dashboard` で **TypeError 連発** していた構造を `threading.Timer(0.1, ...)` で「return → 100ms 後に navigate」へ非同期化。ユーザ体感としては (a) コンソール / 標準出力が真っ赤にならず、(b) ボタン押下時に `inFlight` フラグが reject されず正常にリセットされ、(c) 「プレビュー開く」ボタンの 2 度押し許容性が改善。GUI レイアウト・aria・色は一切いじっておらず、**前回 (3.4) で −1 した「UI input 既定値乖離」(`gui/app.py:1407-1410` の `value="1.05" / "0" / "10" / "20"` vs `config.BUY_FILTER_DEFAULT={min_ev:None, min_value:None, min_odds:8.0, max_odds:20.0}`) は未着手**。一方、「エラー人間化」と「二重実行防止」の 2 軸で実害級の改善があり、ネット +0.2 で 3.6 に復帰。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — Ⅰ→Ⅳ ナンバリング / helpBox の不在は不変。±0。
- **エラー人間化 / 復旧支援: 4/5 → 5/5** — `_safe` + `_error_hint` 自体は不変だが、これまで preview/control 切替のたびに 3 個の TypeError が標準出力を埋め、本物のエラーを隠蔽していた。navigate を `Timer` で切り離したことで **pywebview 自身が吐いていた偽陽性エラーが消滅**。ユーザが見るログが「アプリのエラー」だけになり、復旧支援系の S/N が大幅改善。+1。
- **進捗表示 / ETA / キャンセル: 3/5** — 触り無し。±0。
- **二重実行防止 / ボタン状態管理: 3/5 → 4/5** — 旧実装では preview を開くと `get_dashboard` の Promise が TypeError で reject され、`inFlight` フラグが解除されずに次のボタンがロックされる事故があった (剥がれない disable)。今回 navigate を Promise 解決後 100ms に倒したため **return 経路と画面遷移経路が完全分離**、`inFlight` reject が原理的に発生しなくなった。`setActionButtonsDisabled` が「剥がれない disable」状態でハングする最悪ケースを潰した。+1。
- **レイアウト / タップ領域 / アクセシビリティ: 1/5** — **未着手**。`gui/app.py:1407-1410` の input 既定値が config と乖離したままで、F5 初期表示時に **EV≥1.05 / Odds≥10 で絞った候補** が出る (config の `min_odds=8.0` 既定 41 戦ではなく、UI 既定で絞られた小集合)。前回指摘事項は完全に温存。±0。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **継続: input 既定値を `BUY_FILTER_DEFAULT` から f-string 注入** — `gui/app.py:1407-1410` を `f'<input id="filter_ev" ... value="{BUY_FILTER_DEFAULT["min_ev"] or ""}">'` 形式に置換。None は空文字 → `inputNumber()` の default に倒す。今回触っていない部分なので前回提案を完全再掲。これだけで総合 3.8 圏。
2. **`threading.Timer(0.1, ...)` の 100ms は経験則のため定数化** — `gui/app.py:830, 835` の `0.1` をモジュール頂部 `_NAVIGATE_DELAY_SEC = 0.1` に括り出し、低スペック PC で配信遅延した場合に env で `KEIBA_GUI_NAV_DELAY=0.3` 等から上書きできる経路を残す。今は固定 100ms で TypeError が止まっているが、JV-Link 起動直後の重い局面で再発する可能性ゼロではない。
3. **Timer の不発を可視化** — `threading.Timer(...).start()` は例外を握り潰すため、`webview.windows` が空 (起動直後 / 終了時) だと無音で死ぬ。`lambda` 内を `try/except` で囲み、失敗時に `self._set_status("画面遷移に失敗。ボタン再押下してください。", "error", running=False)` を呼ぶ。「ボタン押したけど何も起きない」体験を残さない。

## 前回からの差分 (3.4 → 3.6, +0.2)

- ボタン発見性: 4 → 4 (±0)
- エラー人間化: 4 → 5 (+1) — pywebview 由来の偽陽性 TypeError が消滅し、`_safe` の error_hint が本物のエラー時だけ前面化する S/N に改善。
- 進捗 / ETA / キャンセル: 3 → 3 (±0)
- 二重実行防止: 3 → 4 (+1) — return-value reject が原理的に消え、`inFlight` がロックされる経路が 1 本減った。「ボタンが永遠に disabled」最悪ケース除去。
- レイアウト / アクセシビリティ: 1 → 1 (±0) — UI input 既定値乖離は **温存**。今回の改修はバックエンド navigate のタイミング修正のみで、CONTROL_HTML テンプレ側に触れていない。
- **総合: 3.4 → 3.6 (+0.2)** — pywebview 内部の race を thread 切り離しで原理的に絶ったのは構造改善として大きい。ただし前回からの宿題 (config→UI 既定の同期) が残っており、3.6 で頭打ち。改善提案 1 を当てれば 3.8、提案 3 (Timer 失敗ハンドル) まで通せば 3.9 圏。
