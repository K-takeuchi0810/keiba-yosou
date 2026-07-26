# モバイル HTML レビュアー 採点

## 判定: PASS

**改修内容**: F3 Phase 0 fail-closed を Prediction から GUI / HTML / CLI / ledger / monitor まで構造化実装。  
**採点対象**: `web/templates/index.html.j2`、`web/generator.py`、再生成した `web/dist/index.html` 先頭200行。  
**根拠**: 未コミットdiff、`git log --stat -3`、関連25テスト成功、必須 `render()` 成功、生成物 2,038,233 bytes、修正前の本scorecard。  
**判定理由**: レース単位のblocked表示・本命/買い候補抑止と機械可読metaが成立。指摘した混在modeの矛盾と英語/内部コードのみの警告は、日本語の状態・影響・復旧手順とcode併記へ修正された。

## 総合: 4.0 / 5

修正前 3.6 → 今回 4.0（+0.4）。F3着手前の直近スコア4.0にも復帰。サイズ予算超過は残るが、今回表示修正に起因する回帰ではない。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `viewport` は `device-width, initial-scale=1, viewport-fit=cover`。`main` は `max-width:720px`。481–600pxで調教師、480px以下で調教師・性齢・斤量を畳み、320/375/414pxでも表は横スクロール可能。新警告は固定幅を持たず折返すため横幅回帰なし（template:5,147,488,514-537）。
- **タップ領域 / 操作性: 5/5** — 日付ナビ、買い候補カード、480px以下のレース`summary`は44px以上。`summary::after`の矢印とopen時回転も維持。blocked警告は操作要素でなく、タップ領域の新規欠陥なし（template:119-135,357-378,421-442,523-525）。
- **情報密度 / 可読性: 4/5** — blocked時は本命プレビューと予想表を隠し、状態・影響・復旧手順を日本語表示する。混在時は「該当レースの買い候補は作成しない／fullレースは通常判定」と明示し、全体停止との誤読を解消。内部codeは追跡用に併記される（generator:58-68,620-640,712-715; template:643-659,761-766）。
- **ダークモード / コントラスト: 3/5** — 新バナー文字は実測で light 5.19:1、dark 7.13:1とAA適合。既存の白文字/枠番4・6・7・8は前回実測 4.06/2.50/2.92/2.91:1で通常文字AA未達のため据え置き（template:17-68,96-104）。
- **iOS / iCloud互換: 4/5** — Apple web-app meta、sticky、横スクロール、外部リソース非依存を維持。生成物2,038,233 bytesは1.5MB予算超過だが、現行テンプレート全体のfail-closed追加はHEAD比1,730 bytes（生成物の約0.085%）のみ。修正前生成物2,559,017 bytesとの差はmode/対象データが異なり、今回コードの肥大化回帰とは判定しない。safe-area未実装と既存サイズ問題は留保。

## 指摘反映確認

1. **混在modeの矛盾（解消）**
   - `prediction_mode_counts`でfull混在を判定し、停止対象と通常判定対象を明記。回帰テスト成功。

2. **利用者向け警告不足（解消）**
   - 既知4codeを日本語の状態・影響・復旧手順へ対応付け、codeも保守用に併記。

3. **HTMLサイズ（既存留保、今回回帰ではない）**
   - post-fix実測2,038,233 bytes。1.5MB予算超過は残る。
   - fail-closedテンプレート追加全体は+1,730 bytesに留まり、2MB級サイズの原因ではない。対象開催短縮またはサイズ上限テストは別課題。

## 必須確認

- [x] `git log --stat -3` と未コミット `web/` diffを確認。
- [x] `.venv32/Scripts/python.exe` で最新HTMLを再生成し、`rendered`を確認。
- [x] 関連テスト `test_template_render.py` / `test_prediction_consumers.py`: 25 passed。
- [x] `web/dist/index.html` 先頭200行を確認。mode=`blocked`、既知4codeをmetaへ保持。
- [x] viewport、320/375/414/600/720+px、44px、dark、iOS/offline互換を確認。
- [x] 実装ファイルは編集せず、本scorecardだけを追加。

## 前回からの差分

- レスポンシブ: 4 → 4（±0）
- タップ領域: 5 → 5（±0）
- 情報密度: 3 → 4（+1、指摘解消）
- ダークモード: 3 → 3（±0）
- iOS互換: 3 → 4（+1、サイズをコード帰属で再評価）
- 総合: 3.6 → **4.0（+0.4、PASS）**
