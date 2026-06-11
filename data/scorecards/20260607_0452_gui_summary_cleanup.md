# 採点 2026-06-07 04:52

**改修内容**: 「不要表示の整理」フェーズ — summary の冗長メトリクス (オッズ N/M・Race最新) 撤去で 4 タイル化 + 死にコード (race_meta クエリ・last_fetched_race payload) 除去 + レビュー指摘の orphan CSS (.preview-*) 撤去
**対象ファイル**: gui/app.py (get_dashboard, CONTROL_HTML JS/CSS)

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|---|---|---|
| GUI / UX 監査人 | 4.1 | 4.1 | ±0 |
| コード品質 / 保守性 | 4.3 | 4.2 | +0.1 |
| 収益性 / 投資判断 | 3.5 | 3.5 | ±0 (ドメイン未変更、0441 から carry forward) |
| 予想ロジック分析官 | 4.35 | 4.35 | ±0 (ドメイン未変更) |
| データパイプライン技術者 | 4.0 | 4.0 | ±0 (ドメイン未変更) |
| 検証プロセス監査人 | 4.0 | 4.0 | ±0 (ドメイン未変更) |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 (ドメイン未変更) |

**後退項目: なし。**
注: code-quality の dead-code 小項目は一時 5→4 (orphan CSS 残存) と評価されたが、**その指摘 (.preview-item/.preview-item strong/.preview-sub) を本セッション内で撤去済**。残課題は解消。

レビューは GUI/UX + code-quality の 2 名のみ実行。残り 5 ドメイン (predictor/jvlink/scripts/web/mobile) は本セッション 0441 full run から diff ゼロのため値を carry forward (skill のトークン経済・対象外精読禁止方針に従う)。

## 各専門家の所見 (要約)

### GUI / UX 監査人 — 4.1 / 5 (±0)
summary を 6→4 タイル (レース / 出走頭数 / 買い候補 / Odds最新) に整理、4 カラム行に過不足なく収まる。冗長な「オッズ N/M」(出走頭数と重複) と低アクション性「Race最新」を撤去、オッズ取得率は取得不完全時のみ「オッズ未取得: N頭」warning で温存しノイズ削減。レイアウト 4.5 維持 (前回 buy-portfolio で到達済の天井)。node --check PASS。
発見性 (3) の天井要因は **4 連続宿題**: ボタン title ほぼ無し / helpBox 不在 / input 既定値 (value="1.05/0/10/20") の config 乖離。
※ gui-ux は「odds_count SQL も dead」と指摘したが、code-quality が正しく反証 — odds_count は warning ロジック (`odds_count < horse_count`) で現役のため残置が正。

### コード品質 / 保守性 — 4.3 / 5 (4.2 → +0.1)
Python 側撤去は模範的 clean: race_meta クエリ・last_fetched_race payload・対応 JS metric 2 つが orphan ゼロで消滅 (git grep 一致)。`s.odds` payload を warning ロジックで単一クエリ共用し JS 表示のみ落とす判断は正しい DRY。撤去で SQL クエリ 1 本減・副作用面積縮小。`/10.0` 直書きも純減。
**指摘 → 本セッションで修正済**: orphan CSS 3 セレクタ (.preview-item / .preview-item strong / .preview-sub) が top_preview 描画撤去で死にクラス化していた (タスクの orphan 検査が CSS セレクタを grep し漏れた) → 撤去し .buy-main に統合。dead-code 純度を回復。

## 横断的に見た優先課題 (継続)

1. **input 既定値の f-string 注入** (gui-ux, **4 セッション連続**) — gui/app.py の `value="1.05/0/10/20"` を `BUY_FILTER_DEFAULT` 由来に。F5 初期表示が config と乖離し続け、発見性 3 点を固定。情報整理が一段落した今が着手の好機。
2. **各ボタンに title + helpBox 新設** (gui-ux) — Ⅰ→Ⅳ の依存を UI 内に明文化。発見性 3→4 の最安経路。
3. **撤去 PR の orphan 検査を CSS セレクタまで拡張** (code-quality, 運用) — JS 描画ブロックを消したら対応 class 名も git grep する手順を撤去チェックリストに追加 (今回 .preview-* を漏らした再発防止)。
4. **buy_portfolio 共通 helper の web 側反映** (継続) — 別タスク (task_dfd85328) で web/generator.py の call-site 置換待ち。

## 検証ログ
- `python -m py_compile gui/app.py` → PASS
- `grep preview-item|preview-sub|preview-compact|previewList|top_preview gui/app.py` → NONE (orphan ゼロ)
- 埋め込み JS 抽出 → `node --check` → PASS
- モック描画で summary 4 タイル (レース/出走頭数/買い候補/Odds最新) + 「オッズ未取得: 14頭」warning + preview パネル消滅を DOM eval / screenshot 確認
