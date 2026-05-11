# GUI / UX 監査人 採点

**改修**: ベースライン (初回)
**日時**: 2026-05-10 22:49
**対象**: gui/app.py

## 総合: 3.2 / 5

JS パース確認: `node --check` → CONTROL_HTML 内 JS (12,338 byte) は構文エラーなし。PREVIEW_HTML には JS ブロックなし (iframe + 戻るボタンのみ)。`onclick="window.pywebview.api.show_control()"` 等は到達可能。よって総合 1 確定の致命傷は無し。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — `data-action` 駆動 + `<span class="step">Ⅰ/Ⅱ/Ⅲ/Ⅳ</span>` で順序が一目で分かる。最上段 `.primary` の「取得→予想→公開」一括ボタンは Hick の法則的に良設計。マイナス: 操作ヘルプ (`<details id="helpBox">`) が存在せず、初見ユーザは血統取得 fromtime の書式 (例 20260501000000) ヒントしか手がかりがない。`Ⅱ オッズ` と `Ⅲ 予想` の「Ⅱ→Ⅲ の間に DB 取り込みが走る」のような依存関係も書かれていない。

- **エラー人間化 / 復旧支援: 3/5** — `run()` 内で `[res.error, res.hint]` を 1 行サマリ化し、その下に JSON 全文を `<details>` で畳む構造は良。`_error_hint` は JVInit / 32bit / SQLite lock / iCloud / Permission の 5 ケースをカバー。ただし `network`, `timeout`, `BSTR`, `rc=-202/-402/-502` (JVOpen 系コード) のような JV-Link 固有エラーが網羅されていない。`render()` / `publish_to_icloud()` の典型失敗 (テンプレ欠落、iCloud 未マウント以外の WinError) も hint なし。`refreshDashboard()` の catch は `summary` セルに生 Error 文字列を詰めるだけで復旧手順なし。

- **進捗表示 / ETA / キャンセル: 3/5** — `progress-wrap` バー + `progressText` で `xx.x% / 残り 約 N分` を表示。1 秒ポーリング (`setInterval(refreshStatus, 1000)`) は妥当。マイナス: ETA 算出の `_progress_detail` は直近 5 サンプルで線形外挿のみで、序盤に進捗 0 → 5% でジャンプすると残り時間が異常値になりやすい。`_stage_progress` が知っているのは RACE/HOSE/DIFN/BLOD/0B31 のみで、他 dataspec (UM/CH/WH/HR…) は `progress=null` でバーが消える。`_check_cancel` は `_progress` コールバックと odds ループ各反復に入っており効きは確実、ただし `render()` (HTML 生成) と `publish_to_icloud()` の中には入っていないので「予想生成中の中止」「公開中の中止」は実質効かない。

- **二重実行防止 / ボタン状態管理: 3/5** — `setActionButtonsDisabled(true)` を `run()` 開始時に立て、`refreshStatus()` が返した `st.running` で再評価する流れは正しい。`_set_status(..., running=True)` がステージ間で常に True を維持しているのも良い。マイナス: JS 側に独立した `inFlight` フラグがなく、ポーリング遅延 (1 秒) の隙にユーザが連打すると、最初のクリックの `setDetails(...実行中...)` 表示は出るが Promise レース次第で `running=false` の status を読み込み 2 つ目の `[method]` が走る理論窓がある。`fetch_data` と `fetch_odds` を連打すると `JVLinkClient()` が二重 Open される可能性 (Python 側に Lock なし)。`cancelBtn` は cancel 連打時に自分を disable する処置あり (○)。

- **レイアウト / タップ領域 / アクセシビリティ: 2/5** — サイドバー `.sidebar { height: 100vh; overflow: hidden }` (gui/app.py:872-881) で `overflow-y: auto` ではない。780px 縦の既定ウィンドウで Ⅰ〜Ⅳ + 確認 2 ボタン + `#detailsBox` を全部入れた状態で、ユーザがウィンドウ高を縮めると下端の `Explorer で開く` や詳細ボックスが見切れる。ボタンに `title=` ホバーヒントがゼロ、`aria-label` ゼロ、`focus-visible` 専用スタイルなし (キーボード操作が黒枠デフォルトに依存)。コントラスト: `--text-mute: #7d8591` on `--bg: #eef0f3` は WCAG AA ぎりぎり (3.6:1) で `.subtitle` `.hint` `.section-label` が薄い。タップ領域は `padding: .48rem .72rem` で本文 14px 換算 ≒ 7px 上下、最低 44×44 を満たさない (.primary でも約 36px 高)。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **サイドバーをスクロール可能にし、操作ヘルプ `<details id="helpBox">` を追加** — `gui/app.py:872-881` の `.sidebar { overflow: hidden }` を `overflow-y: auto` に変更し、最下部に `<details id="helpBox"><summary>操作ガイド</summary>...</details>` で「Ⅰ→Ⅱ→Ⅲ→Ⅳ の依存」「血統 fromtime 書式」「中止が効かない場面 (HTML 生成中)」を明記する。狭いウィンドウでの見切れ解消 + 初見ユーザの自走力向上。

2. **`_error_hint` を JV-Link rc / network / 生成系まで拡充** — `gui/app.py:44-56` の if 連鎖に `"rc=-202"` (認証切れ) → 「JV-Link の利用キーを確認」、`"rc=-402"` → 「fromtime が古すぎ」、`"rc=-502"` → 「サーバ接続失敗、時間を置いて再試行」、`"timed out"` / `"WinError 10060"` → ネットワーク確認、`"FileNotFoundError" and ("templates" in text)` → テンプレ破損、を追加。生 JSON しか出ないケースを 5 → 10 ケースまで広げると体感の「壊れたら詰む感」が大きく減る。

3. **二重実行防止に明示的 `inFlight` フラグを導入し、JV-Link 二重 Open を Python 側でも Lock** — JS 側 `gui/app.py:1586-1619` の `run()` 冒頭で `if (window.__inFlight) return;` と `window.__inFlight = true;` を立て、最終 `.then()` で false に戻す。Python 側 `Api` に `self._run_lock = threading.Lock()` を持たせ、`fetch_data` `fetch_odds` `fetch_bloodline` `run_all` の冒頭で `acquire(blocking=False)` を試み、失敗時は `{"ok": False, "error": "別処理が実行中"}` を返す。1 秒ポーリング窓のレース問題と JVLinkClient 二重 Open を両側で塞げる。

## 前回からの差分 (前回スコアがあれば)

初回採点のため差分なし (`data/scorecards/` には `README.md` のみ存在)。
