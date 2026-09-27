# モバイル HTML レビュアー 採点 — 37eaf61 「今日」の決定を jst.py 1 箇所に集約

## 判定: PASS (条件 1 件、9/21 08:00 より前に確認)

**改修タイプ: type-D (最小)** — `git show HEAD --stat`: 6 files / +242 −11。`web/generator.py` +6 −1 (import 1 行 + `today = current_jst_date()` 1 行 + コメント 3 行)。`web/templates/index.html.j2` は main と **差分 0**。
**理由**: 同日 HTML を main → branch → main の順に連続 3 回生成 (00:00:18 / 00:03:32 / 00:06:05 JST) し、main と branch の差は「更新 時刻」1 行 + 「git: sha」1 行の **2 行のみ** (対照の main→main も更新 1 行のみ)。本文・◎・オッズ・観察専用表示は byte 一致。ヘッダ「更新 <日時>」は壁時計 (JST) と一致。HEAD の `jst.py` は JST 0 時境界を正しく跨ぐことを **実時刻 00:08:30 JST で実測**。
**条件 (専門領域外だが誤読経路に直結)**: 本セッション中 00:07:03〜00:11:20 JST、共有 checkout の作業ツリー `jst.py` に **未コミットの `- timedelta(days=1)` 変異** が置かれていた (` M jst.py` を実測、00:11:20 に HEAD へ戻った = 並行の変異テストと推定)。Task Scheduler はこの checkout (`register_auto_predict_task.ps1:19`、`auto_predict_daily.bat:3,7`) で動くため、変異が残った状態で 9/21 08:00 を迎えると **iPhone ヘッダは「更新 09/21 08:xx」なのに対象日「2026/09/20」** となる = 「今日の予想が出た」誤読の実物。コミット文の「9/21 は main で運用」とも checkout 実態 (branch) が食い違う。**08:00 前に `git status --short jst.py` が空であること、および 9/21 に動かす branch の明示的確認** を条件とする (現時点 00:11 では clean)。
**根拠ファイル**: `web/generator.py:21,312-317,672` / `jst.py:47-69` / `tests/test_jst_date.py:97-99` / `docs/OPERATION.md:131-137` / `scripts/auto_predict.py:40,222` / `web/templates/index.html.j2:89-95,606` / 生成物 3 本 (scratchpad `run1_main.html` `run2_branch.html` `run3_main.html`)
**次アクション**: 上記条件の処置 → `generated_at` (`generator.py:672`) と鮮度 filter の `now` (`:473`) も `jst` 経由に揃える (OS が UTC の機械でヘッダだけ UTC になる残り 2 箇所) → `tests/test_jst_date.py:97-99` の自己参照比較を外部基準 (UTC now + 9h) との比較に変える。

## 総合: 4.0 / 5 (前回 4.2、−0.2)

内訳: レスポンシブ 4 / タップ 5 / 情報密度・誤読防止 **4 (5→4、前回予告どおり)** / ダーク・コントラスト 3 / iOS・予算 4。
−0.2 は本改修起因ではなく、前回・前々回に「次回 type-D で下げる」と予告していた持ち越し (鮮度が `title`/`aria-label` 依存で iOS では視認不可) を type-D 該当の本回で適用したもの。警告閾値 (−0.3) 未満。

## 依頼 4 点 — 実測

| # | 依頼 | 結果 |
|---|---|---|
| 1 | 同日 HTML を main / branch で連続生成し一致するか | main を `git archive` で scratchpad に展開 + `data/` を junction (共有 checkout の branch 切替なし)。`--from 20260920 --to 20260920 --no-publish` を **main→branch→main** の順で連続実行。サイズ 363,906 / **363,912** / 363,906 bytes。`diff` main vs branch = 更新 時刻 1 行 + `git: ?` → `git: 37eaf61` 1 行 (+6 bytes はこれ。archive 展開には .git が無いため)。対照 main vs main = 更新 1 行のみ。**本文差 0**。所要 各 ~2.5-3 分、間隔 ≤ 3 分 (前回の 14 分・432 ハンク問題は再現せず) |
| 2 | 引数なしの既定窓 (today±14) が変わっていないか | 式は `today ∓ 14 日` のまま (`generator.py:316-317`)。HEAD の `current_jst_date()` を 00:08:30 JST で実測 → 2026-09-21 = `datetime.now().date()` と一致、窓 20260907〜20261005 で main と同一。**注意**: 00:07:05 の 1 回目実測では branch 側が 2026-09-20 を返した。原因は作業ツリーの未コミット変異 (上記条件) で、HEAD 版を別 path から import し直して正値を確認。境界注入 14:59:59Z→20260920 / 15:00:00Z→20260921 も HEAD 版で確認。OS=UTC 想定 (22:30Z) では main の `datetime.now().date()` が前日を返し branch は翌日を返す = 改修意図どおり |
| 3 | ヘッダ「更新 <日時>」が JST のままか | branch 生成物 `<div class="updated">更新 2026-09-21 00:03:32</div>`、bash `date +%T` の終了時刻 00:03:32 と一致 → **JST**。ただし出所は `generator.py:672 datetime.now()` (ローカル時計) で、本改修の `today` (UTC→JST 変換) とは **別の時計**。JST 機では同値、UTC 機では 9 時間ずれる。`.updated` は白/#1a5fb4 = **6.3:1** (light)、白/#1f5aa8 = **6.8:1** (dark)、13.6px 太字 600、sticky ヘッダ内で初期表示 (前回値、テンプレ差分 0 で維持) |
| 4 | OPERATION.md がスマホだけで辿れるか | `docs/OPERATION.md:133-137` に 0 番「スマホしか手元にない場合はここだけ: Pages を開いてヘッダの `更新 <日時>` を見る…」が追加済 (main `1548ca0` 由来)。Pages URL は文書に無いが Discord 本文 (`auto_predict.py:222` `🌐 Web版: https://k-takeuchi0810.github.io/keiba-yosou/`) に毎回入るので、前日以前の通知からタップで到達可。**辿れる**。留保: `push_ok=False` の日は Pages が古く iCloud だけ新しいので、0 番に「Pages か iCloud の index.html」と併記すべき (1 語) |

## 停止条件チェック (type-D)

- [x] git_sha 刻印: branch 生成物 `git: 37eaf61`
- [x] fresh/stale 区分・◎ 根拠・折りたたみ・横スクロール: テンプレ差分 0、生成物 byte 一致 → 前回判定 (不抵触) を実測値で維持。`<details>` 24 個は前回同様 買い判断情報の外
- [x] HTML サイズ: 同日版 363,912 bytes (< 1MB)。既定 ±14 日版 (前回 2.05MB) は本回未再測 (パス指定運用では到達しない)
- [x] 外部 `<link>/<script src>/http(s)://`: **0**。viewport + theme-color ×2 = 3。verification-banner/mode 7、観察専用 1
- [x] 公開物への混入: `web/dist` 復元済 (md5 7d03f8cf… 一致、363,585 bytes、`git: 93046ba`)。scratchpad の main-tree は junction を `rmdir` で切離し後に残置 (実 data には触れていない)
- [x] **作業ツリー汚染** (上記条件): HEAD には無い。00:11:20 に解消を実測。08:00 前の再確認のみ残る

## 項目別

- **レスポンシブ 4/5** — 不変 (テンプレ差分 0)
- **タップ領域 5/5** — 不変
- **情報密度 / 誤読防止 4/5 (↓)** — 生成物で再確認: オッズ鮮度は `title="取得 09:59" aria-label="オッズ取得 09:59"` のみで **視覚テキストなし** (iOS は title を表示しない)。`stale` class 出現 0 (9/20 分は発走済のため)、`鮮度` 語 0。前回・前々回に予告した降格を適用。EV が P と同格の `conf-tag` も継続
- **ダーク / コントラスト 3/5** — waku 4/6/7/8 白文字の AA 未達 **8 回目の持ち越し**。本改修で新規色なし
- **iOS / file:// + 予算 4/5** — 外部依存 0、同日版 364KB。DOM 開始タグ 5,445 (前回 4,924、9/20 は 3 場 36R で増) 。既定窓 2MB は未処置

## 反証の試み

- 「`today` の変更が出力レース集合を変える」→ `--from/--to` 明示では `today` は未参照 (`generator.py:316-317` の `or` 右辺)。引数なしでも JST 機では同日 → 本文 byte 一致。**不成立**
- 「ヘッダ時刻が UTC になった」→ 00:03:32 JST 一致。**不成立** (ただし別時計のまま = 留保)
- 「境界で日付が 1 日ずれる」→ HEAD 版は 00:08:30 JST で 09-21。**HEAD では不成立**。作業ツリーの変異版では **成立** (09-20) — これはコミット外
- 「テストが既定 path を守っている」→ `test_jst_date.py:97-99` は `current_jst_daystamp()` 同士の自己参照比較のみ。変異入りの作業ツリーで **12/12 pass** した = 既定 path (`now=None`) の正しさは無検査。**成立** (次アクション 3)

## 参考所見 (スコープ外、他 agent 向け)

- code-quality / validation: 上記 テスト空白。「変異 7 種がすべて落ちる」の主張は注入 path についてのみ真で、既定 path の変異 (`-1 day`) は素通り (本セッションで偶然実証)
- 運用: コミット文「9/21 は main で運用」と checkout 実態 (branch `jst-date-unify-20260920`) の食い違い。branch のまま 9/21 を迎えるなら、08:00 前に作業ツリーが HEAD と一致していることを再確認すること (本セッション中に 4 分間の変異が観測された)。main に戻すなら bat 側の `jst` import (`auto_predict_daily.bat:7`) が無い旧 bat になるので、そのどちらかを意図して選ぶ

## 前回からの差分

- 情報密度 5→4 (予告済の持ち越し適用、本改修起因ではない)。他 4 項目 ±0。総合 4.2→4.0
- 新規実測: main/branch 連続 3 回生成の差 2 行 / JST 境界の実時刻テスト / `.updated` 6.3:1・6.8:1 維持 / OPERATION.md 0 番の到達性 (Discord URL 経由)
- 前回提案 3 (スマホ手順) は対応済。提案 1 (差分行の日本語化)・2 (◎ 集合 payload) は未対応のまま (本改修の範囲外)
