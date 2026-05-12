# GUI / UX 監査人 採点

**改修**: P0-5 BUY_FILTER_DEFAULT 切替 (wl_ex_unsure_pop_1_4 → wl_odds_8_20)
**日時**: 2026-05-12 21:00
**対象**: `config.BUY_FILTER_DEFAULT` + `gui/app.py:_is_buy_candidate` (None ガード) + `web/generator.py:152-157`
**JS 検証**: `node --check` PASS (JS len 12824, CONTROL_HTML 不変)

## 総合: 3.4 / 5

walk-forward の控除率比較 (eval 116.1% vs 旧 89.0%) で +27pt 改善する `wl_odds_8_20` に切替。`min_popularity` / `max_popularity` / `exclude_confidence` が `None` / `[]` を取れるよう `gui/app.py:239-246, 263-268` にガードを追加し、`int(None) TypeError` を回避。`web/generator.py:152-157` も同じ None→1/99 フォールバックで揃えた。バックエンドの堅牢性は上がったが **CONTROL_HTML の filter input 既定値が config と乖離** (UI `filter_min_odds=10` だが config `min_odds=8.0`、`filter_ev=1.05` だが config `min_ev=None`、`filter_value=0` だが config `min_value=None`)。dashboard 開いた瞬間に「config と違う条件で絞った買い候補」が表示されるため、単一出典の前提が UI で崩れる。前回 3.6 → 3.4 (−0.2)。

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — Ⅰ→Ⅳ フロー / helpBox 不在は不変。±0。
- **エラー人間化 / 復旧支援: 4/5** — None ガード追加で「filter_sweep の新 hybrid 候補 (popularity=None) を試した際に GUI が落ちる」事故を予防。`_safe` + `_error_hint` は不変。+0 維持。
- **進捗表示 / ETA / キャンセル: 3/5** — 触り無し。±0。
- **二重実行防止 / ボタン状態管理: 3/5** — シグネチャ変更なし、`_is_buy_candidate(race=…)` 同期済。±0。
- **レイアウト / タップ領域 / アクセシビリティ: 2/5 → 1/5** — **UI input 既定値が config から乖離**。`gui/app.py:1405` `value="1.05"`, `:1406` `value="0"`, `:1407` `value="10"` が config (`min_ev=None`, `min_value=None`, `min_odds=8.0`) と矛盾。dashboard を一度も触らずに F5 すると **config 既定 (41戦/116.1%) ではなく旧 UI 既定 (EV≥1.05 / Odds≥10)** で絞った候補が出る。ユーザが「sweep で採用したフィルタ」を見るには 4 input を手動で書き換える必要があり、単一出典の主張が破れている。−1。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **CONTROL_HTML の input 既定値を `config.BUY_FILTER_DEFAULT` から流し込む** — `gui/app.py:1405-1408` の `value="1.05" / "0" / "10" / "20"` を Python f-string で `{BUY_FILTER_DEFAULT['min_ev'] or ''}` / `{BUY_FILTER_DEFAULT['min_odds']}` 等に置換。None なら `value=""` (空) として `inputNumber()` の default に倒す。これで config 変更だけで GUI 既定が追随し、再ビルド/再起動 1 回で sweep 採用フィルタが UI 既定に反映される。
2. **`inputNumber()` の default 引数も config 注入** — `gui/app.py:1477-1480` の `inputNumber('filter_ev', 1.05)` 等のハードコード default を、テンプレ展開時に `BUY_FILTER_DEFAULT` から差し込む (例: `inputNumber('filter_min_odds', {BUY_FILTER_DEFAULT['min_odds']})`)。空欄時の挙動も config 出典に統一。
3. **(継続) `min_popularity` / `max_popularity` / `exclude_confidence` の UI 露出** — wl_odds_8_20 では `None` のため表示不要だが、`scripts/filter_sweep.py` に追加した hybrid 候補 (`wl_odds_8_20_pop_4_8` 等) を試すには UI から弄れないと不便。`<details class="filter-panel">` 内に折り畳みで人気帯 input を追加し、空欄 = None = 制約なし、と扱う。

## 前回からの差分 (3.6 → 3.4, −0.2)

- ボタン発見性: 4 → 4 (±0)
- エラー人間化: 4 → 4 (±0) — None ガード追加は堅牢性 +、ユーザ体感 ±0
- 進捗 / ETA / キャンセル: 3 → 3 (±0)
- 二重実行防止: 3 → 3 (±0)
- レイアウト / アクセシビリティ: 2 → 1 (−1) — **UI 既定値が config と乖離**。前回までは「UI に露出していない」継続課題で済んでいたが、今回 config 主絞り条件 (min_odds) が変わったのに UI 既定 (10) は据え置きで、**初期表示が 2 種類の異なるフィルタで矛盾** する状態に悪化。−1 確定。
- **総合: 3.6 → 3.4 (−0.2)** — バックエンド None ガードは正しいが、UI 既定値の同期漏れが致命的。改善提案 1 (config→input value テンプレ流し込み) を当てれば 3.6 復帰、人気帯 input 追加で 3.8 圏。
