# コード品質 / 保守性レビュアー 採点 — 37eaf61 「今日」の決定を jst.py に集約

**改修タイプ宣言**: 運用基盤 (type-B 相当、予測を変えない)。P25 固有ゲート (env_overrides / market_snapshot / weights / payout) は **N/A (対象外)**。汎用ゲート (DRY・dead code・設定外出し・テスト容易性・観測可能性) で採点。
**採点対象**: `jst.py` `scripts/auto_predict.py` `scripts/notify_dedup.py` `web/generator.py` `scripts/auto_predict_daily.bat` `tests/test_jst_date.py` + 影響を受ける既存テスト `tests/test_notify_dedup.py`。
**採点環境**: branch `jst-date-unify-20260920` HEAD=37eaf61、作業ツリー clean。pyflakes 未導入のため dead import は grep で確認。採点中に JST 日付が 09/20 から 09/21 に変わり、それ自体が下記の主要所見を実証した。

## 判定: HOLD

**理由**: 集約の設計 (tz 付き `now` 注入・naive 拒否・既定 UTC) は妥当だが、**この commit は既存テスト `tests/test_notify_dedup.py::test_jst_is_used_not_system_local_time` を沈黙のまま無効化しており、HEAD 無改変で 2026-09-21 00:00 JST 以降 FAIL する (実測: assert "20260921" == "20260920")**。同テストの monkeypatch 先 `notify_dedup.datetime` は `jst_today` が `jst.current_jst_daystamp` へ委譲した時点で経路外になり、09/20 中は実時刻との偶然一致で通っていた。commit 本文の「681 passed」は日付依存の真。加えて新設ガード `test_no_module_makes_its_own_today` は自分で植えた非対照 7 変異を **7/7 素通り** (下表)、うち 1 件は **コミット前と同一コードの復活** (`datetime.now(JST)`。後方互換で残した `JST` 再エクスポートがそれを可能にしている)。停止条件抵触は無し (実害は「テストが赤い」で、本番挙動は正しい)。
**根拠ファイル**: `tests/test_notify_dedup.py:262-278` / `scripts/notify_dedup.py:51-55,78-83` / `tests/test_jst_date.py:93-99,119-132` / `scripts/auto_predict_daily.bat:21` + `scripts/fetch_mining.py:18-20` / `web/publish_safety.py:58`
**次アクション**: 改善提案 1 (壊れた既存テストの修復 + 再エクスポートと `jst_today` の廃止) を **9/21 の 3 run 確認より前に** 入れる (suite が赤いままマージ判断に進めない)。提案 2 (AST ガード) は同 PR で。30 分規模。

## 総合: 3.0 / 5 (参考スコア)

## 項目別

- **DRY / 単一出典: 3/5** — `jst.py` の 3 関数 (datetime → date → daystamp の派生鎖) は粒度適切で、真実は `current_jst_datetime` の 1 箇所。留保: (a) `notify_dedup.jst_today` は「後方互換」ではなく **現役の別名** (`notify_dedup.py:213,255` と `auto_predict.py:191` が今も呼ぶ) で、同じ事実に 2 つの名前が生きている。(b) `JST = _JST` 再エクスポート (`notify_dedup.py:55`) の利用者は `tests/test_notify_dedup.py:278` のみ。この再エクスポートがあるために変異 M8b (コミット前の `datetime.now(JST).strftime`) が import エラーにならず全テスト通過する = 後方互換シムが「戻し」を無音で許す。(c) commit が「同じ 1 回の起動の中で今日が 2 通り」を解消したと書くが、**同じ bat の 9 行後** `auto_predict_daily.bat:21` の `fetch_mining --date today` は `fetch_mining.py:20` の `datetime.now().strftime("%Y%m%d")` (ローカル naive) で 5 つ目の「今日」を作っている。mining の取得対象日と予想対象日は同一であるべき値。(d) `web/publish_safety.py:58` の `date.today()` フォールバックは残存 (呼び出し側 `generator.py:603` が `today=` を渡すので現状は経路外だが、M14 で示す通り落としても検出されない)。
- **dead code / 未使用シンボル: 3/5** — `auto_predict.py:19` の `date` import は本文で未使用 (残る出現は `:268` のコメントのみ)。`notify_dedup.py:47` の `timezone` は未使用 (grep 1 件 = import 行)。`jst_today(now)` の `now` は **呼び出し側が誰も渡さない死んだ引数** (M7: 無視しても 77 件通過)。`JST` 再エクスポートは上記 (b)。他方、4 箇所の置換は完全で、旧 `datetime.now(JST)` の本体側残存は無し。
- **マジックナンバー / 設定外出し: 4/5** — `JST = timezone(timedelta(hours=9))` に「夏時間無し」の根拠コメント (`jst.py:44-45`)。境界テストの 14:59:59 / 15:00:00 はテスト内リテラルだが、境界値の記述はテストに置くのが正しい。`FINAL_ATTEMPT_HOUR = 11` は既存。留保: 既定を UTC にする決定はコードとテストの文字列一致 (`test_jst_date.py:87-88`) で守られており、挙動としては「tz 付きなら何でも同じ瞬間」なので、この文字列テストは設計意図の文書化にはなるが誤りを検出する力は M2 の 1 形態に限られる。
- **テスト容易性 / 変更失敗モード: 2/5** — 境界 5 件 (`:27-75`) は実効 (JST オフセットを変えれば落ちる構造)。**問題は「集約されていること」側の 4 件**: (i) `test_dedup_and_the_target_day_agree` (`:93-99`) は `auto_predict.current_jst_date() == current_jst_date()` = **import した同一関数オブジェクトの自己比較** で同語反復。`main()` が別の日付源を使っても通る (M3/M5/M6/M6b)。(ii) `test_no_module_makes_its_own_today` の正規表現 3 本は `date.today()` / `datetime.now().date()` / `datetime.today()` の **表記** しか見ない。`datetime.now(timezone.utc).date()` (UTC 日付 = 朝 07:00-11:00 JST の全 run で前日を指す最悪変異)、`from datetime import date as _d; _d.today()`、`datetime.now().strftime("%Y%m%d")` (このコードベースで最多の「今日」表記)、2 行分割、`datetime.utcnow().date()` がすべて素通り。逆に文字列リテラル内の `date.today()` は誤検出 (M12)。コメント除外だけで許可/禁止の精度は語彙 1 段目止まり。(iii) 既定 `now` の挙動テストが無い: M1 (既定が昨日を返す) を捕まえたのは `test_jst_date.py` ではなく `tests/test_auto_predict_artifacts.py:122-361` が **自前の `date.today()`** (8 箇所、ローカル naive) で fixture を組んでいるからで、これは偶然の対照。(iv) 上記 HOLD 理由の既存テスト無効化。
- **エラー処理 / 観測可能性: 3/5** — 良: naive `now` を `ValueError` で fail-fast (`jst.py:56-59`)、メッセージに理由。bat は Python 側と同一関数を呼び、`cd /d` 後なので `from jst import` は解決する。留保: (a) bat の `for /f` が失敗 (venv 欠損・import 失敗) すると `RUNDATE` 空で `auto_predict_daily_.log` に無音で落ちる (既存挙動だがコマンドが複雑化し失敗確率は上がった)。(b) 刻印の tz が混在: `auto_predict.py:360` 生成時刻 = ローカル naive、`generator.py:672` `generated_at` = ローカル naive、`notify_dedup.py:268` `sent_at` = `+09:00` 付き。同じ日の notify-audit で MARKER と state を突き合わせると片方だけ tz 表記が無い。commit が刻印を対象外と宣言したのは妥当だが、少なくとも tz の有無は揃えるべき。

### 自分で植えた変異 (`tests/` 4 ファイル 77 件 = jst_date / notify_dedup / auto_predict_artifacts / publish_safety。M1 は全体 686 件でも実行)

| # | 壊し方 | 結果 | 実害 |
|---|---|---|---|
| CTRL-A/C | auto_predict / generator を `date.today()` `datetime.now().date()` に戻す | **検出** (regex) | (対照) |
| CTRL-B | `sent_at` をローカル naive に | **検出** (`test_record_writes_the_date_so_pruning_works`) | (対照) |
| M2 | jst 既定を `datetime.now().astimezone()` | **検出** (文字列一致のみ、挙動は同一) | 無し |
| M1 | jst 既定 now を 24h 前に | **検出** — ただし `test_auto_predict_artifacts` の自前 `date.today()` fixture が偶然捕捉。`test_jst_date.py` 単体では 0 件 | 全 run が前日を対象に |
| M3 | auto_predict `datetime.now(timezone.utc).date()` | 素通り | **朝 3 run すべて前日** (JST 07-11 時 = UTC 前日 22-02 時)。無音 |
| M5 | `from datetime import date as _d; _d.today()` | 素通り | ローカル時刻依存に退行 |
| M6 / M6b | `datetime.now().strftime("%Y%m%d")` / 2 行分割 `.date()` | 素通り | 同上 |
| M12 | 文字列リテラルに `"date.today()"` | **誤検出** (FAIL) | ガードの精度不足の裏面 |
| M7 | `jst_today` が `now` を無視 | 素通り | 引数が契約になっていない |
| M8 | `jst_today = datetime.now().strftime(...)` | 素通り (旧テストを除外後) | JST 明示前の 08/22 以前の形へ退行 |
| M8b | `jst_today = datetime.now(JST).strftime(...)` **= コミット前の原文** | 素通り (focus 76/76。全体 run は要約行欠落で帰属不能、未確定) | 集約の「戻し」を誰も検出しない |
| M10 | generator `datetime.utcnow().date()` | 素通り | 引数なし起動で UTC 日付 |
| M14 | generator が `today=` を落とす → publish_safety の `date.today()` | 素通り | 完全性判定がローカル日付に退行 |

非対照 11 変異中 **素通り 9**。前回 (13/13 素通り) より対照層は増えたが、commit が主目的とする「独自の今日の復活検出」は 0/7。

## 変更失敗モード分析

1. **5 つ目の利用者を足すとき** (例: `fetch_mining` や新スクリプトで対象日が要る): 書き手が `datetime.now(timezone.utc).date()` と書くと、正規表現ガードは通り、`test_dedup_and_the_target_day_agree` も通る。本番では **朝の全起動が前日を対象** にし、`skip: 出馬表なし` か前日ページの再生成になる。誰も気付く経路が無い (通知は「今日」の記録を作るので dedup とも整合してしまう)。fail-fast にするには、`jst.py` 以外での `datetime.now` / `date.today` / `utcnow` 呼び出しを AST で禁止し、刻印用途は明示の許可リスト (行単位) に載せる。
2. **モジュール属性を monkeypatch するテスト** は、呼び出しが別モジュールへ移った瞬間に何も検証しない緑になる。今回 `test_jst_is_used_not_system_local_time` がまさにそれで、09/20 は通り 09/21 に落ちた。`now` 注入引数はこのために作られたのに、既存テストを引数注入に書き換えていない = 設計意図と既存資産が不整合。
3. **`RETENTION_DAYS` の cutoff** (`notify_dedup.py:188-189`) は `today` 文字列から `strptime` で naive datetime を作って引く。JST 日付の算術なので正しいが、`datetime` を naive で扱う唯一の残存箇所で、将来 `current_jst_datetime()` と引き算されると `TypeError` (aware と naive) で即落ちる。fail-fast なので許容、ただしコメントが無い。

## 依頼への回答

- **12 件は同語反復か**: 境界 5 件 (`:27-75`) は非同語反復 (JST オフセット・naive 拒否を直接固定)。`test_dedup_and_the_target_day_agree` は同語反復 (同一関数の自己比較)。`test_now_defaults_to_utc_not_local_time` は文字列一致で、挙動は不検証。`test_no_module_makes_its_own_today` の 3 件は表記ガードで上表の通り 7/7 素通り。`test_the_final_attempt_hour_is_judged_in_jst` と `test_the_batch_log_uses_the_same_source` は妥当。
- **正規表現ガード**: 指摘どおり別名 import・`strftime` 表記・tz 引数付き `now(...)` を通し、文字列リテラルを誤検出する。禁止リスト 3 本は語彙が狭く、許可リストは存在しない (刻印用 `datetime.now()` は「`.date()` が続かない」ことで偶然通っているだけ)。
- **jst.py の API 設計**: 3 関数の派生鎖は適切。naive 拒否は正しい (M2 の通り tz 付きなら既定が UTC か local かは挙動に影響せず、UTC 既定は「ローカル時刻を読まない」宣言としての意味)。`datetime | None` 型注釈が `_is_final_attempt(now=None)` では欠落 (`auto_predict.py:173`)。
- **後方互換の `jst_today` / `JST` 再エクスポート**: 排除すべき。`jst_today` は現役利用 3 箇所を持つ「第 2 の名前」、`JST` 再エクスポートの利用者はテスト 1 行のみで、それが M8b の「原文復活」を成立させている。単一出典は名前も 1 つにしないと構造では守れない。
- **4 箇所以外の「今日」**: 対象日として残るもの — `scripts/fetch_mining.py:20` (**同一 bat 内**)、`web/publish_safety.py:58` (フォールバック)、`gui/app.py:405` (GUI 既定対象日)、`scripts/fetch_fresh_odds.py:186-187` / `scripts/predict_t10.py:249` / `scripts/check_fresh_odds_health.py:516-517` / `scripts/fetch_results.py:24-26` (別スケジューラの対象日)、`scripts/fresh_odds_coverage.py:151-152` (同一 bat 内の窓)、`predictor/rules.py:124` (calibrator 期限判定の今日)。刻印 (`generated_at` 等) と区別した上で、同一 bat 内の 2 件 (`fetch_mining` / `fresh_odds_coverage`) は commit の主張「1 回の起動で今日は 1 通り」に直接反する。

## 停止条件チェック

- [ ] git_sha / env_overrides / market_snapshot / payout — **N/A** (予測・backtest に無関係)
- [x] 汎用: 新規経路に回帰テストあり (境界 5 件は実効)
- [x] 汎用: 例外の握り潰し無し / 無音失敗の新設無し (bat の RUNDATE 空は既存)
- [x] 汎用: **既存テストの無効化** — 停止条件ではないが HOLD 理由。HEAD の suite は 09/21 以降赤

## 反証の試み

- 「今日を各自で作る書き方が復活したら落ちるガード」に対し、原文復活 (M8b) を含む 7 形態で不成立。落ちるのは commit 本文が列挙した 3 表記のみ
- 「変異 7 種がすべて落ちる」は真 (CTRL-A/C・M2・JST オフセット変更は落ちる) だが、検出力は自分が選んだ表記に閉じている。別の 9 変異で 0 検出 (M1 は他ファイルの偶然)
- 「681 passed」は 09/20 のみ真。09/21 00:00 JST 以降は 1 failed (実測)

## 主な改善提案

1. **既存テストの修復 + 名前の一本化** — `tests/test_notify_dedup.py:269-274` の `FixedDateTime` monkeypatch を削除し `notify_dedup.jst_today(now=fixed)` (または `current_jst_daystamp(now=fixed)`) に。`:278` は `from jst import JST` に変更し `notify_dedup.py:51,55` の `_JST` / `JST` を削除。`jst_today` は 3 call site (`notify_dedup.py:213,255` `auto_predict.py:191`) を `current_jst_daystamp()` に置換して関数ごと削除。`auto_predict.py:19` の `date`、`notify_dedup.py:47` の `timezone` を import から外す。
2. **ガードを AST に** — `test_no_module_makes_its_own_today` を `ast.walk` で Call(func=Attribute(attr in {now, today, utcnow, fromtimestamp})) かつ受け手が `datetime` / `date` / 別名 (import を解決) を検出する形に。刻印用途は行単位の許可リスト `ALLOWED_STAMPS = {("scripts/auto_predict.py", 360), ...}` へ (行が動けば落ちる = 刻印の追加も明示的になる)。対象に `web/publish_safety.py` `scripts/fetch_mining.py` `scripts/fresh_odds_coverage.py` を追加。M3/M5/M6/M8b/M10/M14 が落ちることを確認してから commit。
3. **同一 bat 内の残り 2 源を寄せる** — `scripts/fetch_mining.py:20` を `current_jst_daystamp()` に (32bit venv でも repo root の `jst.py` は `sys.path.insert` 済で import 可)。`web/publish_safety.py:44` の `today: date | None = None` を必須引数にして `:58` のフォールバックを削除 (M14 が `TypeError` で即落ちる)。

## 前回からの差分 (直近 code-quality: 20260919_2100 notify_dedup = 3.6 / HOLD)

- DRY 4→3 (-1、現役の別名 + 再エクスポートが原文復活を許す + 同一 bat 内に別源が残る) / dead code 4→3 (-1、未使用 import 2 + 死んだ引数 1 が新規) / マジックナンバー 4→4 / テスト容易性 3→2 (-1、既存テストの無効化を実測、ガードは主目的の変異 0/7) / 観測可能性 3→3 (naive 拒否の fail-fast は加点、刻印 tz 混在で相殺)
- 判定 HOLD→HOLD。理由変更: 前回は「配線層の素通り + 無音退行」、今回は「HEAD の suite が翌日から赤 + 集約ガードが表記依存」。総合 3.6→3.0 (-0.6)。1 点超の変動なし。
