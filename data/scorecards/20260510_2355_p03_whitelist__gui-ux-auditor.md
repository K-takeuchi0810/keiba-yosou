# GUI / UX 監査人 採点

**改修**: P0-3 — 重賞ホワイトリストモード (`config.BUY_FILTER_DEFAULT` に `whitelist_mode/whitelist_grades/whitelist_tracks`、`is_whitelisted_race(race)`、`gui/app.py:_is_buy_candidate(... race=)`、`web/generator.py:top_picks_by_race`、`scripts/backtest.py:whitelist_only_stats`)
**日時**: 2026-05-10 23:55
**対象**: gui/app.py (Api._is_buy_candidate のシグネチャ拡張のみ。HTML/JS 部分は未変更)

## 総合: 3.2 / 5

JS パース確認: `node --check` → CONTROL_HTML 内 JS 構文エラーなし (致命傷無し)。

P0-3 は買い候補生成ロジックの強い意味的変更 (= 中山 / 京都 / 重賞 以外は **すべて買い候補から除外**) だが、GUI 表面には何ひとつ反映されていない。`gui/app.py:236-238` で `race=race` を渡してサイレントに `False` を返すのみで、(a) ダッシュボードのフィルタ行に whitelist_mode のチェックボックスが無い、(b) `BUY_FILTER_DEFAULT` を JS 側 input value として撒いている既存規約 (config.py:36 のコメント) からも逸脱、(c) 「このレースは買い候補ゼロ」の理由が「フィルタが厳しい」なのか「ホワイトリスト除外」なのか判別不能。前回 (P1-3) と同様 **「バックエンドは健全になったが、ユーザの目に届いていない」**型の改修で、項目 2 はむしろ後退する。**総合 3.3 → 3.2 (-0.1)**。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — HTML/JS 未変更。Ⅰ/Ⅱ/Ⅲ/Ⅳ ステップは前回のまま。`whitelist_mode` という新しい運用モードが入ったのに UI からはその存在が一切わからず、本来は「重賞ホワイトリストモード [ON/OFF]」トグルがダッシュボード filter 行 (input value 群と同じ場所) に並ぶべき。可視化の機会損失で +0 据え置き、4/5。

- **エラー人間化 / 復旧支援: 3/5 (-0.5)** — 「3 番人気 ◎ で EV 1.20 なのに買い候補にならない」ケースが急増する (= 重賞以外はゼロになる) のに、ユーザに見える理由は無し。`_is_buy_candidate` が `False` を返す経路が 8 通り (rank/mark/odds/EV/value/age/confidence/whitelist) に増えたのに、UI 側は単に `buy=false` を表示するだけ。ホワイトリスト除外時は preview の馬カード or レース見出しに 「重賞外 (ホワイトリスト除外)」バッジを出すべき。前回 3.5 → 3 へ後退。

- **進捗表示 / ETA / キャンセル: 3/5** — 触り無し。±0。

- **二重実行防止 / ボタン状態管理: 3/5** — 触り無し。`_is_buy_candidate` の引数追加は呼出側 (gui/app.py:611) を 1 行で更新済みで `race=race` を渡しており TypeError リスクなし。±0。

- **レイアウト / タップ領域 / アクセシビリティ: 2/5** — 触り無し。サイドバー overflow / aria-label / helpBox 不在も継続。±0。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **ダッシュボード filter 行に whitelist トグルを追加** — `gui/app.py` の CONTROL_HTML 内 (filter input 群と同じ箇所) に `<label><input type="checkbox" id="whitelistMode" checked> 重賞 + 中山/京都のみ買う</label>` を追加。Api 側 `generate_predictions` の `bet_filter` JSON に `whitelist_mode` を流し込み、`_is_buy_candidate` で `filters.get("whitelist_mode", BUY_FILTER_DEFAULT["whitelist_mode"])` を尊重 (現状は config 直読みで GUI 上書き不可)。これだけで「設定の存在に気づける」「OFF にして確かめられる」が両立し、項目 1/2 を +0.5 ずつ改善できる。

2. **preview 側に「whitelist 除外」バッジ** — `web/generator.py` で各レースに `excluded_by_whitelist: bool` を埋め、PREVIEW_HTML 側 race ヘッダで `not race_whitelisted` のとき `<span class="badge muted">重賞外・買い候補対象外</span>` を表示。これで「なぜこのレースに ◎ が無いのか」がユーザに伝わる。

3. **(継続) サイドバー `overflow-y:auto` + `<details id="helpBox">`** — 前回・前々回からの最優先持ち越し。helpBox に「重賞ホワイトリストモードについて」の 3 行説明を入れれば本改修の意図 (1,164 戦 backtest で控除率 80% 超の領域のみに張る) もユーザへ伝えられる。

## 前回からの差分 (3.3 → 3.2)

- ボタン発見性: 4 → 4 (±0) — UI 露出ゼロなので評価据え置き
- エラー人間化: 3.5 → 3 (-0.5) — 候補ゼロの理由が 1 つ増えたのに GUI は無言、UX 上は後退
- 進捗 / ETA / キャンセル: 3 → 3 (±0) — 触り無し
- 二重実行防止: 3 → 3 (±0) — `race=` 引数追加は安全に伝播
- レイアウト / アクセシビリティ: 2 → 2 (±0) — 触り無し
- **総合: 3.3 → 3.2 (-0.1)** — バックエンド側のロジック強度は上がったが、ユーザに届く GUI 表面で逆に「沈黙」が増えた構図。提案 1+2 を入れれば次回 +0.4 (= 3.6) は射程内。
