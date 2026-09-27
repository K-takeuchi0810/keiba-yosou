# データパイプライン技術者 採点 — 37eaf61 「今日」の決定を jst.py 1 箇所に集約

## 判定: HOLD

**理由**: 停止条件抵触なし。コード自体に実害欠陥は見つからず、前回 HOLD の 2 事由は両方解除を確認した。HOLD の対象は **checkout の状態**: スケジューラ `keiba-auto-predict` (次回 2026/09/21 08:00) は `C:\Users\kizun\dev\keiba-yosou\scripts\run_auto_predict_daily.ps1` → 同ツリーの `auto_predict_daily.bat` を実行するが、そのツリーは今 `jst-date-unify-20260920` に居る (reflog 23:45:03 で main から移動、以後戻していない)。このままだと「9/21 は main で運用」は成立せず、9/21 の 3 run は本ブランチで動き、`auto_predict.py:373-379` のブランチガードで **push が止まって Pages が開催日に更新されない** (commit は feature ブランチに積まれる)。加えて bat の新 RUNDATE 行は縮退時に無音でログ名が `auto_predict_daily_.log` に落ちる (実測)。
**根拠ファイル**: `scripts/auto_predict_daily.bat:7`、`scripts/auto_predict.py:270,278,339,373-379`、`scripts/notify_dedup.py:213,255,268,276-280`、`jst.py:47-69`、`data/logs/auto_predict_daily_20260920.log:35,74,113`、`data/runtime/notification_state.json`、schtasks 実測 (本 scorecard「反証」)
**次アクション**: (1) **9/21 08:00 より前に `git checkout main`** (jst.py は main に無いので消えるのが正常。tracked 変更なしを確認済)。(2) 9/21 の 3 run を main で完了 → 9/22 (非開催日) に merge → `data/logs/auto_predict_daily_20260922.log` が **その名前で** 生成されることを確認 (`_.log` が出ていないこと)。(3) bat に `if not defined RUNDATE` の縮退を 2 行入れる。これで PASS。

## 対象・改修タイプ

- 対象: `37eaf61` (`jst.py` 新規 / `scripts/auto_predict.py` / `scripts/auto_predict_daily.bat` / `scripts/notify_dedup.py` / `web/generator.py` / `tests/test_jst_date.py`)。`git diff --stat HEAD` は空 = 作業ツリー内容は HEAD と一致 (jst.py の ` M` は 00:02:15 に同内容で書き直された stat 差のみ、`git diff jst.py` 空)。
- 改修タイプ: **type-D 相当 (運用層: 生成対象日・ログ名・重複判定の日付決定基盤。取得 / ingest / 予測ロジックは不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**。fresh odds を総合判定のゲートにしない。
- 採点軸は本改修に合わせ「bat 起動経路の堅牢性 / 日付決定の単一出典と境界一貫性 / 依存・起動コスト / 退行ガード / 反映運用と前回 HOLD 解除」の 5 つに置き換えた。
- スコープ外: 通知文面、生成 HTML の中身。「681 passed」は再実行せず、関連 94 件 + jst 12 件のみ自分で再実行。変異 7 種が落ちる主張は再実行していない (未検証)。

## 総合: 3.8 / 5 (参考スコア)

## 項目別

- **bat 起動経路の堅牢性 (RUNDATE 決定・縮退・cp932): 3/5** — 本番ログを汚さないよう、bat 1-8 行目を RUNDATE 行 **原文のまま** 複製し LOGFILE だけ scratchpad に向けた replica を `C:\` から `chcp 932` で実行。**正常系**: `RUNDATE=[20260921]`、`cd /d` が for /f より先なので外部 cwd からでも `jst` を解決 (`bat:3` → `:7`)。出力は ASCII 8 桁のみで cp932 の影響なし。**縮退**: import 失敗 (`ModuleNotFoundError`) / 非 0 終了 / python.exe 不在の 3 モードすべて `RUNDATE=[]` → `auto_predict_daily_.log` に落ち、traceback は stderr = リダイレクト開始前なので **ログに残らない** (wscript 隠し実行では消失)。処理自体は続行するので予想は出る (実害はログ名のみ) が、`if not defined RUNDATE` の受け皿が無い。旧行も python 依存だったが stdlib のみで失敗面は「python 不在」だけだった。新行は「jst.py 不在 / cwd 不正 / 同名モジュール衝突」が加わる (site-packages に `jst` 無しは確認)。**プロセス数は増えていない** — 旧行も python を 1 回起動していた (`main:bat:5`)。
- **日付決定の単一出典 / 境界一貫性: 4/5** — 生成対象日 `today` は 1 回の読取 (`auto_predict.py:270`) から `day` → generator `--from/--to` (`:339`) → dedup の subject (`:34,:55,:385`) に流れる。**対象日と dedup キーの一致は構成上保証**。naive 拒否 (`jst.py:56-59`)、既定 UTC (`:55`)。留保: (1) 同一 run 内でも時計の読取は複数 — bat RUNDATE (別プロセス)、`decide` の prune 基準 (`notify_dedup.py:213`)、`record` の `date_jst`/`sent_at` (`:255,:268`)、`_is_final_attempt`。深夜 0 時をまたぐと **ログ名 ≠ 対象日** になりうる (bat 起動 → auto_predict 起動の間隔は 9/20 実測 2.9 秒 `log:1,32` だが fetch_full が重い日は分単位)。`date_jst` のずれは retention にしか効かず無害。到達性: トリガ 08/09/11 なので手動起動でしか起きない。「すべて同じ日」は **設計保証ではなくスケジュール依存**。(2) 同じ bat 内の `fetch_mining --date today` (`fetch_mining.py:20` ローカル `datetime.now()`)、`fetch_full` (`:36` `date.today()`)、`fresh_odds_coverage` (`:80,151-152`) は集約対象外のまま。「今日」を決める箇所は 4 → 1 ではなく 7 → 4。
- **依存 / 起動コスト (循環・config 非依存): 5/5** — ベストプラクティスは「時刻ユーティリティはプロジェクト内 import ゼロの葉モジュール + tz-aware + 注入可能な時計」で、本実装はこれを満たす。`jst.py` の import は `datetime` のみ (`:42`)、`-X importtime` で jst 自体 2.7 ms、import 後の `sys.modules` に config/db/numpy/pandas/sqlite3 無し (実測)。`web/generator.py:21` は `sys.path.insert` 直後・`config` より前に置かれ循環なし。起動時間: 新行 0.112-0.120 s / 旧行 0.113-0.118 s / `python -c pass` 0.111-0.123 s (各 5 回・3 回) → **差は測定誤差内**。
- **退行ガード / テスト: 4/5** — `tests/test_jst_date.py` 12 passed、関連 `-k "notify or auto_predict or scheduled or jst"` 94 passed (自分で再実行)。境界 (UTC 15:00 / JST 00:00 / UTC マシン) を now 注入で直接叩いている。留保: (1) 正規表現ガード (`:114-132`) は 3 モジュール限定で fetch_* / coverage は対象外。(2) `test_dedup_and_the_target_day_agree` (`:93-99`) は実時刻を 2 回別々に読むので JST 0 時ちょうどに flap しうる (now 注入で書ける)。(3) `test_now_defaults_to_utc_not_local_time` はソース文字列検査で、実装を書き換えると壊れやすい。
- **反映運用 / 前回 HOLD 解除: 3/5** — **前回 HOLD 2 事由は解除**: (a) `record()` の無音失敗は `b3fa151` で WARN 出力化 (`notify_dedup.py:276-280`)。(b) 本番実績: 9/20 の 3 run で `notify-audit ... first_time/duplicate/duplicate` (`log:35,74,113`)、`notify suppressed` 2 行 (`:73,:112`)、状態ファイル 1 キー (`generation_complete:20260920`, `sent_at 08:01:17+09:00`) — 「同日 3 通 → 1 通」成立。**今回の問題**: schtasks 実測で 3 トリガとも `run_auto_predict_daily.ps1` (このツリー) を指し、ps1 は git checkout をしない (`grep` 該当なし)。ツリーは feature ブランチ。9/21 08:00 に本ブランチで走ると生成は成功するが `HEAD != main` で push 停止 (`auto_predict.py:373-379`)、`push_ok=False` が通知 payload に入り、**開催日に Pages が前日のまま** (iCloud 側は別経路で更新される可能性はあるが未確認)。commit message の「9/21 は現在の main で運用」を成立させる操作 (`git checkout main`) が未実施。

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides: N/A (backtest artifact を生成しない改修)
- [x] baseline paired 比較: N/A
- [x] market_snapshot counts / payout 欠損: N/A
- [x] P25 fresh odds スケジューラ / coverage JSONL / bonus_candidate: N/A (type-D 運用層)。参考: `keiba-fresh-odds` は登録済・前回 09/20 19:00 result 0 (schtasks 実測)
- [x] 専門領域 (本改修向け): partial write を残す経路 → なし (状態ファイル層は不変)。無限待ち / lock 未掃除 → 該当コード無し。予想を 1 日落とす経路 → 見つからず (縮退時もログ名のみ劣化)。**すべて不抵触**
- [x] テスト: 12 + 94 passed (自分で再実行)

## 反証の試み (すべて `.venv64`、bat は scratchpad 複製で本番ログ非接触を確認: `auto_predict_daily_20260920.log` 6767 byte 不変、`_.log` 未生成)

| # | 反証シナリオ | 結果 |
|---|---|---|
| E1 | bat を `C:\` から起動 (cd 前に import されないか) | `cd /d` が `:3`、for /f が `:7` → RUNDATE=20260921。**成立** |
| E2 | import 失敗 (`jst_missing`) | RUNDATE 空 → `auto_predict_daily_.log`、traceback は stderr でログ外。**縮退は無音** |
| E3 | python が 0 以外で終了 (`SystemExit(3)`) | 同上 RUNDATE 空。for /f は終了コードを見ない |
| E4 | python.exe 不在 | 同上。旧行と同じ失敗形 |
| E5 | 環境変数 RUNDATE=19990101 を事前設定 | 正常系では上書きされる。失敗系では **stale 値を継承** (bat は `set RUNDATE=` を先にしない) |
| E6 | cp932 コンソール (`chcp 932`) | 8 桁 ASCII のみ、化けなし |
| E7 | 起動コスト「python が 1 つ増える」 | **前提が誤り**: 旧行も python 起動。時間差 0 (測定誤差内) |
| E8 | jst が config を import / 循環 | `sys.modules` に無し、importtime 2.7 ms。**成立 (import しない)** |
| E9 | 「9/21 は main で運用」 | **不成立**: checkout は feature ブランチ、scheduler はこのツリーを指す、ps1 は checkout しない |
| E10 | 0 時境界で対象日 / dedup / ログ名が一致 | 対象日 = dedup subject は同一読取で一致。ログ名は別プロセスで **設計上は一致保証なし** (到達性はトリガ時刻で実質ゼロ) |

- 改修の主張「4 箇所を 1 箇所に集約」→ 宣言した 4 箇所については **成立**。同 bat 内の fetch_mining / fetch_full / fresh_odds_coverage は残る (主張外だが「今日」を決めている)。
- 改修の主張「now を注入できる / naive 拒否」→ **成立** (テスト + コード)。

## 主な改善提案 (優先順)

1. **開催日前の checkout 復帰 (今すぐ)** — `git checkout main` を 9/21 08:00 前に実行。合わせて commit message の「反映のタイミング」節に「**ツリーを main に戻してから就寝する**」を明記。共有 checkout でブランチを切って夜を越す運用は、ブランチガード (`auto_predict.py:373-379`) が無ければ main 流入になる事故クラスと同根。
2. **bat の縮退受け皿** — `scripts/auto_predict_daily.bat:7` の直前に `set RUNDATE=`、直後に `if not defined RUNDATE set RUNDATE=unknown` を追加し、`:run` 冒頭で `if "%RUNDATE%"=="unknown" echo [WARN] RUNDATE fallback (jst import failed)` を出す。E2-E5 が「名前で気付ける + 継承しない」に変わる。
3. **ガードの範囲と flap** — `tests/test_jst_date.py:114-118` の parametrize に `scripts/fetch_mining.py` を足すか、docstring に「fetch 系はデータ取得日の意味で別契約」と明記。`:93-99` は `now=` を固定して 2 読取の不一致を消す。

## 前回からの差分

- 前回 (本 agent、同サブシステム): `20260919_2100_notify_dedup` **3.6 / HOLD**。今回 **3.8 / HOLD** (+0.2)。軸を差し替えているので項目単位の比較は不可。
- 前回 HOLD 事由 2 件 (record 無音失敗 / 本番未稼働) は **両方解除を実測** (`b3fa151`、9/20 log 3 行 + 状態 1 キー)。
- 今回 HOLD を維持する理由は前回と別: 改修コードでなく **checkout 状態と bat 縮退の無音**。前者は 1 コマンドで解け、後者は 2 行。9/22 の非開催日 run で新 bat 行が scheduler 経由 (wscript 隠し実行) でも正しいログ名を作ることを確認すれば PASS。

## 追記 (00:09 JST): 共有 checkout に変異が植わったまま

- 採点中に `jst.py` の作業ツリー内容が HEAD から離れた: 00:02 時点は同内容 (stat 差のみ)、**00:07:03 に `jst.py:54` が `datetime.now(timezone.utc) - timedelta(days=1)` に書き換わり**、00:09:42 時点でも残存 (blob `9c13aa5c` ≠ HEAD `b59af796`)。並走する別 agent の変異テストと推定 (scratchpad に `mutate*.py` あり)。
- 本 scorecard のテスト実測 (12 + 94 passed) は 00:00-00:01 = HEAD 内容に対するもの。bat 縮退プローブ (00:03) も HEAD 内容。
- **このまま 08:00 を迎えると、生成対象日・dedup キー・ログ名がすべて「前日」になる** (jst.py を全員が参照するので、集約の利点がそのまま単一障害点になる)。次アクション (1) の `git checkout main` は、この変異が **restore された後** に行うこと (未 restore で checkout すると feature ブランチ側に変異が持ち越されるか、checkout 自体が拒否される)。
- 教訓: 共有 checkout 上で変異テストを走らせる agent は、変異 → 検証 → **restore を 1 つの try/finally** で閉じ、開催日前夜には行わない。`feedback_shared_checkout_git_ops` と同じ事故クラス。
