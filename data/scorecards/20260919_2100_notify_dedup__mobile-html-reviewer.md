# モバイル HTML レビュアー 採点 — b437db3 予想生成通知の同日重複抑止

## 判定: PASS (前回維持)

**改修タイプ: type-B** (`git show b437db3 --stat`: 5 files / +746 −4。`web/` `gui/` `predictor/` 変更 **0 行**。変更は `scripts/notify_dedup.py` (新規) / `scripts/auto_predict.py` / tests / docs のみ)。
**理由**: HTML 生成経路に到達しないことを実測 (generator プロセスの通知モジュール ロード 0 件、同日 HTML 連続 2 回生成の差分は「更新 時刻」1 行のみ)。抑止された日に iPhone 側で気付く手段 (sticky ヘッダの「更新 HH:MM:SS」チップ、白/#1a5fb4 = 6.3:1) は既存 HTML に備わっている。Discord 本文は最長ケースでも 617 字 < 2,000 字制限。
**根拠ファイル**: `scripts/notify_dedup.py:150-183` / `scripts/auto_predict.py:116-178,231-260` / `scripts/notify_discord.py:16-26` / `web/templates/index.html.j2:77-95,604-607` / `docs/OPERATION.md:93-131` / `web/dist/index.html` (本セッション 2 回再生成)
**次アクション**: 変更通知の差分行を機械キーから日本語ラベルへ (提案 1)。OPERATION.md にスマホだけで確認する手順を 1 行追加 (提案 3)。web 側の作業なし。

## 総合: 4.2 / 5 (前回 4.2、±0)

## 依頼 — 実測 (本セッション)

| # | 確認 | 結果 |
|---|---|---|
| 1 | `git show HEAD --stat` の `web/` 件数 | **0** |
| 2 | `import web.generator` 後の `sys.modules` に notify / auto_predict | **[]** (0 件)。`web/` 配下に `notify_dedup` `auto_predict` の文字列 0 件 |
| 3 | 同日 HTML 連続 2 回生成 (20:22:26 / 20:23:45、`--from 20260919 --to 20260919 --no-publish`) | 両方 **329,444 bytes**。`diff` 差分 **2 行 = 606 行目「更新 時刻」のみ**。依頼者の「生成時刻の 1 行を除いて一致」と整合 (前後コードの sha256 c0782ff493fc0eba 自体は再導出せず、同一コード連続 2 回で「1 行のみ差」の構造を確認) |
| 4 | 生成物の刻印 | `git: b437db3` に更新。DOM タグ **4,924** (前回 4,926、±2 はデータ由来)。外部 `<link>/<script>` **0**。viewport + theme-color ×2 = **3**。観察専用 notice 1 |
| 5 | HTML から「今日の予想が出たか」を読む手段 | `header` は `position: sticky` (`:80`)、`<h1>競馬予想 <span class="target-day">2026/09/19（土）</span>` + `<div class="updated">更新 2026-09-19 20:23:45</div>` が 375px で初期表示・折りたたみなし。auto_predict は通知の抑止と無関係に毎回 generator + publish を回す (`:266-311`) ので、抑止された 2・3 回目も HTML の 更新 時刻は進む |
| 6 | `.updated` コントラスト | 白 / `--accent-bg` #1a5fb4 (light) = **6.3:1**、白 / #1f5aa8 (dark) = **6.8:1**。13.6px 太字 600 → AA (4.5:1) 合格 |
| 7 | Discord 本文実レンダ (python で組み立て) | 初回 217 字。変更あり (push_ok True→False) 233 字。最悪ケース (drift 6 点 + 本文 400 字) **617 字** < 2,000。`notify_discord.py` に文字数ガードなし (既存) だが到達しない |
| 8 | gitignore | `data/runtime/*` は除外済 (`.gitignore:24-26`)。状態ファイルが Pages/iCloud 公開物に混入する経路なし (publish 対象は `index.html` + `static/` `assets/`) |
| 9 | テスト隔離 | `tests/conftest.py` autouse fixture が `NOTIFY_STATE_PATH` を tmp_path へ差し替え → テストが本番の抑止状態を汚す経路は閉じている |

## 改修特有の観点 (依頼 3 件)

**(1) 抑止された日に HTML 側だけで気付けるか — 可 (留保 1 件)**
Pages / iCloud の `index.html` を開けば、sticky ヘッダ 2 行目に「更新 <日時>」チップ (白/青 6.3:1、bold) と対象日 (h1 隣) が初期表示される。スクロール・タップ展開不要。留保: 同日中に ◎ や出走馬確定数が動いて HTML が再公開されても、payload `{n_races, version, push_ok}` が同じなら通知は出ない。改修前は同文 3 通が「再生成があった」ことを暗示していたが、この暗示は失われる。HTML を再度開けば 更新 時刻で分かるので誤読には直結しないが、`n_races` 以外に「◎ 集合のハッシュ」を payload に足せば「中身が変わった時だけ再通知」という本改修の設計意図とも整合する (提案 2)。

**(2) 変更通知本文の iPhone Discord 表示**
`🔁 **前回から変更あり**` + `  - push_ok: True -> False` + 空行 + 全文。絵文字は全て標準 Unicode (🔁 U+1F501 / 🏇 / 📱 / 🌐)、太字 `**` は Discord Markdown 標準で iPhone でも太字化する。先頭 2 スペース + `- ` は Discord ではインデント付き箇条書きとして描画され、読める。問題は差分行が **機械キーそのまま** (`push_ok: True -> False`、`n_races: 12 -> 24`、`drift: [] -> ['predictor/...']`) な点。単一運用者なので致命ではないが、通知だけ見て判断する設計 (`_completion_message` docstring `:162-163`) と釣り合わない。`⚠` (U+26A0、VS16 なし) が iOS でテキスト表示になりうるのは改修前からの既存事項で、本改修の減点対象外。

**(3) docs/OPERATION.md の手順がスマホだけで辿れるか — 辿れない**
「通知が来ないときの確認手順」1〜4 (`docs/OPERATION.md:110-116`) は コンソール/タスクログ・`data/runtime/notification_state.json`・`--force-notify`・状態ファイル削除 の 4 つで **全て PC 前提**。スマホしか手元にない場合の一次確認 (Pages の 更新 時刻を見る) が書かれていない。実装は手段を備えているのに手順書がそれを指していない。

## 項目別 (web 無変更のため前回値維持)

- **レスポンシブ: 4/5** — 不変
- **タップ領域: 5/5** — 不変
- **情報密度/誤読防止: 5/5** — 不変。留保据え置き: EV が P と同格 `conf-tag` 表示 / 鮮度がオッズ取得 HH:MM の `title` 属性依存 (今回生成物でも `オッズ取得 15:29">` の形で `title` 内、iOS タップで見えない)。次回 type-D で 4 へ下げる予告を継続
- **ダークモード/コントラスト: 3/5** — waku 4/6/7/8 白文字の AA 未達は **7 回目の持ち越し**。今回新規に `.updated` を実測 (6.3 / 6.8:1、合格)
- **iOS/file:// + 予算: 4/5** — 同日版 329,444 bytes、外部依存 0、公開物への状態ファイル混入なし。既定レンジ (±14 日) 2.05MB は未処置のまま

## 停止条件チェック

- [x] git_sha 刻印: 生成物 `git: b437db3`
- [x] baseline paired / market_snapshot counts / payout 欠損 — N/A (type-B)
- [x] 専門領域 Hard Fail (fresh/stale 表示・◎ 根拠・折りたたみ・横スクロール・1.5MB・AA 未達重要テキスト) — HTML 無変更につき **不抵触** (前回判定を実測値で維持)
- [x] 通知起因の誤読経路: 「観察専用」の一文は初回・変更あり の両本文に残る (実レンダで確認)

## 反証の試み

- 「通知層が generator に混入し HTML が変わる」→ sys.modules 0 件 + 連続 2 回生成の差分 1 行 + `web/` 内の参照 0 件。**不成立**
- 「変更通知が Discord 2,000 字を超え切り捨てで『観察専用』が落ちる」→ 最悪ケース (封印 6 点 drift + 400 字本文) 617 字。**不成立**
- 「抑止された日は iPhone から生成の有無が分からない」→ sticky ヘッダの 更新 チップが折りたたみ無しで初期表示。**不成立** (ただし手順書に未記載 = 提案 3)
- 「テストが本番の状態を汚し当日の中止通知が抑止される」→ conftest autouse で隔離。**不成立**

## 主な改善提案

1. **差分行を日本語ラベルに** — `scripts/notify_dedup.py:173-174` の `f"  - {k}: {o} -> {n}"` に `labels: dict[str,str] | None` 引数を足し、`auto_predict.py:314` から `{"n_races":"レース数","push_ok":"Web 版更新","version":"モデル"}` を渡す。`True/False` は `済/失敗` へ写像。スマホ通知だけで判断する運用に合わせる
2. **◎ 集合を payload に含める** — `scripts/auto_predict.py:146-153` `_completion_payload` に `top_picks_sha: str` (レース順に ◎ 馬番を連結した sha256 先頭 12 桁) を追加。同日再生成で ◎ が入れ替わった時だけ「変更あり」が届く。1 日最大 3 回起動なので通知回数は増えても +2 通で上限
3. **OPERATION.md にスマホだけの確認手順を 0 番目として追加** — `docs/OPERATION.md:110` の前に「スマホしか無いとき: Pages URL を開き、ヘッダ 2 行目『更新 <日時>』が当日朝の時刻なら生成済み (通知は重複抑止)。日付が前日なら未生成」の 1 行

## 参考所見 (スコープ外)

- `--force-notify` (`auto_predict.py:127-128`) は `record` を通らない。強制送信後の通常起動で状態が「初回」のままなら同文がもう 1 通届く。設計上「送る側に倒す」方針と整合しており実害は重複 1 通のみ。code-quality 側の判断に委ねる

## 前回からの差分

- 全 5 項目 ±0 (4.2 → 4.2)。判定 PASS 維持
- 持ち越し 3 件 (EV 同格表示 / `title` 依存鮮度 / waku 色 dark) は件数変わらず。`.updated` の AA 実測値 (6.3 / 6.8:1) を新規に記録
