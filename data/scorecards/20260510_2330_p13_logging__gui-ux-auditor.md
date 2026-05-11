# GUI / UX 監査人 採点

**改修**: P1-3 (`jvlink_client/client.py` の `except: pass` 9 箇所 → `logger.warning(..., exc_info=True)`、`jvlink_client/ingest.py` 運用 `print` → `logger.error`、`predictor/rules.py:_apply_calibrator` calibrator 型不正時に `logger.warning` 1 行)
**日時**: 2026-05-10 23:30
**対象**: gui/app.py (本 PR では未変更。間接影響のみ評価)

## 総合: 3.3 / 5

JS パース確認: `node --check` → CONTROL_HTML 内 JS (12,824 byte、前回比 ±0) は構文エラーなし。総合 1 確定の致命傷は無し。

P1-3 は純粋なバックエンド (Python logger) 化で、`gui/app.py` の Api / CONTROL_HTML / PREVIEW_HTML には 1 文字も触れていない。GUI 上の見え方は前回 (P0-2) から変化なし。**理屈上**は JV-Link 取得失敗時に `logger.warning(exc_info=True)` でスタックトレースが残るので、ユーザがバグ報告する際の再現性は上がる — が、Python の `logging` は既定で stderr 出力のままで、pywebview のデスクトップ画面からは一切見えない。GUI 側 (`_safe` の JSON エラーレスポンス → `detailsBox`) には改善の経路が存在しない。`logger` の出力先を `data/logs/*.log` へファイル化 + GUI から「ログを開く」ボタンで導線を貼って初めて UX に効くが、本 PR ではそこまで来ていない。よって項目 2 は据え置き、**総合 3.3 → 3.3 (±0)**。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — 本改修は HTML / JS に未着手。Ⅰ/Ⅱ/Ⅲ/Ⅳ ステップ + `data-action` 駆動は前回のまま。`<details id="helpBox">` 不在も継続。±0。

- **エラー人間化 / 復旧支援: 3.5/5** — `client.py` の沈黙バグ (`except: pass` 9 箇所) が `logger.warning` で可視化されたのは品質工学的には大進歩。ただし出力先が stderr 限定 → GUI 利用時には `pythonw.exe` 起動でそもそも捨てられている可能性が高い。`_error_hint(e)` も未拡張、`detailsBox` の表示内容も同一。GUI 表面でユーザが得られる情報量はゼロ増。±0 据え置き。

- **進捗表示 / ETA / キャンセル: 3/5** — 触り無し。±0。

- **二重実行防止 / ボタン状態管理: 3/5** — 触り無し。`logger` 化で例外を握り潰さなくなった分 (= 例外が呼出元へ伝播するパスが増えた可能性)、`inFlight` リセット動線で未検証だが、当該 9 箇所はいずれも `except Exception: logger.warning(...)` で再 raise しないので呼出側の制御フローは不変。±0。

- **レイアウト / タップ領域 / アクセシビリティ: 2/5** — `.sidebar { overflow: hidden }`、`title=` / `aria-label` 不在も継続。±0。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`logger` の出力をファイル + GUI から閲覧可能に** — `gui/app.py` の `if __name__ == "__main__":` ブロック直前に `logging.basicConfig(filename="data/logs/app.log", level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")` を追加。さらに Api クラスに `def open_log(self): os.startfile("data/logs/app.log")` を生やし、サイドバー末尾に `<button data-action="open_log">ログを開く</button>` を追加。これで P1-3 の `logger.warning` がエンドユーザに到達する経路が初めて完成し、項目 2 を 4/5 へ持ち上げられる。

2. **エラーカード内に「最後の警告 N 件」を表示** — Api 側で `MemoryHandler` (容量 50) を仕込み、`get_recent_warnings()` を Api メソッド化。`detailsBox` のエラーレンダリング (gui/app.py:1478 付近) で警告履歴を折り畳み表示すれば、`client.py` のリトライ揺らぎ (`exc_info=True`) がユーザに見える形になる。

3. **(継続) サイドバー `overflow-y: auto` + helpBox** — 前回・前々回からの最優先持ち越し。項目 5 が 2/5 のままだと総合が 3 台前半に張り付く構造問題。

## 前回からの差分

- ボタン発見性: 4 → 4 (±0) GUI 未変更
- エラー人間化: 3.5 → 3.5 (±0) Python 内部の可視化は進んだが GUI 表面に届いていない
- 進捗 / ETA / キャンセル: 3 → 3 (±0) 触り無し
- 二重実行防止: 3 → 3 (±0) 触り無し
- レイアウト / アクセシビリティ: 2 → 2 (±0) 触り無し
- **総合: 3.3 → 3.3 (±0)** 改修自体は健全 (沈黙バグ撲滅は GUI 安定性に長期で効く) だが、**ユーザが見える GUI** に届いていないので採点には寄与しない。提案 1 を入れれば次回 +0.2 は確実。
