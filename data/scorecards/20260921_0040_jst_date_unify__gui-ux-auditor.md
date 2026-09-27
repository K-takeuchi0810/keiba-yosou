# GUI / UX 監査人 採点 — 37eaf61 「今日」の決定を jst.py 1 箇所に集約

## 判定: HOLD (前回維持 — 本改修由来の GUI 回帰なし / 自己提案 1 件を消化と認定 / 新規の降格なし)

**理由**: 改修タイプは **type-B 主体 + type-D 触接** と宣言する。`git show HEAD --stat` = 6 files (jst.py 新規 / scripts 3 / web/generator.py 6 行 / tests)。`gui/` `web/templates/` の差分は 0 行 (実測 `git diff main..HEAD -- gui/ web/templates/ | wc -l` = 0)。`web/generator.py` は rubric 表上 type-D だが、変更は `build_view_model` の **既定窓の起点 1 行** (`:315` `datetime.now().date()` → `current_jst_date()`) のみで、表示・テンプレート・ガード経路に触れない。GUI 表示日への影響を下記で実測し「JST 機では同値」を確認したので、ゲートは type-B 汎用 + JS パース回帰確認のみ適用。P25 固有ゲートは N/A。
**根拠ファイル**: `jst.py:47-69` / `web/generator.py:21,315-317` / `gui/app.py:69-118,395-415,1137-1143,2214-2229` / `scripts/auto_predict.py:117-164,389-395` / `tests/test_jst_date.py:95-141`
**次アクション**: (1) **運用上の即時事項**: 共有 checkout が現在 `jst-date-unify-20260920` に居る。`auto_predict.py:373-378` のブランチガードにより、このまま 9/21 09:00 の Task Scheduler 起動を迎えると `push_ok=False` → Discord に「Pages 更新なし」が届く。commit message の「9/21 は main で運用」を成立させるには起動前に main へ戻す必要がある (他セッション並走中なら git 操作は当人が行うこと)。(2) GUI 自身の「今日」2 箇所 (`gui/app.py:405` Python ローカル / `:2215,2219` JS `new Date()`) を jst.py に寄せ、`tests/test_jst_date.py:115-117` の監視対象に `gui/app.py` を加える (下記 提案 1)。

## 総合: 3.3 / 5 (前回 3.3、±0)

## 依頼事項への回答 (すべて実測)

1. **`_run_render_in_venv64` 経路で GUI の表示日が変わるか → 変わらない (JST 機)**
   - GUI は `cmd += ["--from", from_date]` / `["--to", to_date]` を **入力があるときだけ** 付ける (`gui/app.py:110-113`)。generator 側で `today` が効くのは両方 None のときのみ (`web/generator.py:316-317`)。
   - `run_prediction` は入力空欄なら `from_date=None, to_date=None` を渡す (`gui/app.py:1137-1138`) → 既定窓 today±14 日の起点が **ローカル → JST** に変わる。
   - 実測: `.venv64` で `current_jst_date()` = 2026-09-20、`datetime.now().date()` = 2026-09-20 (UTC 14:56 = JST 23:56、境界 4 分前でも一致)。OS tz = JST の本機では **同値**。差が出るのは OS tz ≠ JST のときだけで、その場合は改修後の方が auto_predict / Pages の対象日と一致する (改善方向)。
   - 生成後の表示日は HTML 側が `--from/--to` 解決後の日付を出すので、GUI プレビューの見え方に差分なし。

2. **GUI が独自に「今日」を作っている箇所 → 2 箇所ある (未統一)**
   - `gui/app.py:405` `_date_range`: `datetime.now().strftime("%Y%m%d")` (Python ローカル)。`get_dashboard` (`:837`) / `get_backtest` (`:826`) が両 input 空欄のとき使う = ダッシュボードの「今日レースがあるか / 最新開催日」判定。
   - `gui/app.py:2215,2219` JS `presetToday` / `presetWeekend`: ブラウザ (pywebview WebView2) の `new Date()` = OS ローカル。
   - どちらも jst.py を経由せず、`tests/test_jst_date.py:115-117` の復活ガード対象 (auto_predict / notify_dedup / generator の 3 module) にも **含まれていない**。JST 機では auto_predict と同じ日を指すので現時点の実害なし。OS tz ≠ JST なら「ダッシュボードは 9/20 に開催なしと表示、Pages は 9/21 分を公開済」という食い違いが起きうる (Nielsen 4 一貫性 / Nielsen 1 可視性の潜在リスク、**現状は憶測ではなく条件付き事実**)。
   - 副次: `web/generator.py:301,672` の `generated_at` は **ローカル naive**、`:886` `published_at` はローカル aware、`:315` `today` は JST。「日付は JST、時刻はローカル」の混在が生成物に残る。JST 機では見えない。

3. **前回提案「`notified.` の無条件 print」の消化 → 消化と認定 (留保つき)**
   - `scripts/auto_predict.py:395` が `print(f"notify: {'ok' if sent else 'failed'}. push_ok={push_ok}")` に変更済。
   - 実測 (`_notify` を stub 化し 3 ケース実走):
     - 初回送信: `notify-audit ... decision=first_time delivered=ok` → `notify: ok`
     - 同内容 2 回目: `notify suppressed (...): duplicate` → `notify-audit ... decision=duplicate attempted=no delivered=-` → **`notify: ok`**
     - 内容変更 + POST 失敗: `WARN: 送信に失敗...` → `notify-audit ... delivered=failed` → `notify: failed`
   - 前回指摘の **「suppressed の直後に notified. (=送った) と嘘をつく」矛盾は解消**。`_notify_once` は抑止時に `return True` (`:150`) するため、抑止も送信成功も同じ `ok` になる点は残るが、直前の `notify-audit` 行 (`decision= / attempted= / delivered=`) が事実を一意に示すので「嘘」ではなく「冗長 + 語の粗さ」。前回の降格予告 (未消化なら 3.5 → 3.0) は **適用しない**。ただし 4 に上げるには `ok` を `sent / suppressed(duplicate) / failed` の 3 値にするか、audit 行に一本化して最終行を削るかのどちらかが要る。

4. **JS パース回帰確認 → PASS**: `.venv32` で `CONTROL_HTML` の `<script>` を抽出 (22,428 chars、前回と同一長) → `node --check` OK。CONTROL_HTML 無変更 (diff 0 行) と整合。

## 項目別

- **タスクフロー / 発見性: 3/5** (変動なし — GUI 無変更。日付プリセット「今日 / 週末 / 最新」の導線は据え置き)
- **エラーの人間化 / 回復支援: 3/5** (変動なし。`_error_hint` / `StalePublishRefused` 日本語化 (`gui/app.py:1161-1181`) は無変更)
- **システム状態の可視性: 3.5/5** (変動なし。前回提案の矛盾行は解消 = 降格回避。`ok` の 3 値化が残るため加点はしない)
- **状態整合性 / 誤読防止: 3/5** (変動なし。改修は auto_predict 系 4 箇所の「今日」を一致させ、GUI との一致は **JST 機という前提に依存したまま**。GUI 2 箇所が単一出典から外れている事実を新規に記録するが、現時点でユーザ可視の差分が無いため降格しない)
- **レイアウト / 入力効率 / a11y: 4/5** (変動なし)

## 停止条件チェック

- [x] GUI / テンプレート差分なし (`gui/` `web/templates/` 0 行)
- [x] JS `node --check` PASS (.venv32 実測、22,428 chars)
- [x] GUI JS 契約テスト + 新規 jst テスト同居実走: `tests/test_jst_date.py` + `tests/test_gui_js_contract.py` → **18 passed** (.venv64)
- [x] `_run_render_in_venv64` 経路の表示日不変を実測 (JST 機)
- [x] 専門領域別 Hard Fail 不抵触 (P25 固有: type-B のため N/A。fresh/stale 表示・補正発火区別は本改修の対象外)
- [ ] (該当外) git_sha / market_snapshot / paired baseline — backtest 成果物を出さない改修のため N/A (NOT_EVALUABLE には用いない)

## 反証の試み

- 主張「『今日』は 1 箇所で決まる」に対し「GUI にも『今日』がある」を確認 → **部分的に不成立**: 宣言した 4 箇所については成立 (`tests/test_jst_date.py:95-99,115-141` が固定)。リポ全体では `gui/app.py:405` (Python) と `:2215,2219` (JS) が残り、ガードの対象外。JST 機では同値のため実害は現状なし。
- 主張「generator の既定窓変更は GUI に影響しない」に対し「入力空欄で run_prediction すると既定窓が使われる」を確認 → 使われる (`gui/app.py:1137-1138` → `web/generator.py:316-317`) が、起点日は実測で同値 → **主張成立 (JST 機の範囲で)**。
- 主張「notified. の矛盾は解消」に対し「抑止時に `notify: ok` が出る」を実測 → 出る。ただし直前の audit 行が `attempted=no delivered=-` を示し、行内で「送った」とは書いていないため **矛盾 (嘘) は解消、粒度の粗さは残る**。

## 主な改善提案 (優先順)

1. **GUI の「今日」を jst.py に寄せ、ガード対象に追加** — `gui/app.py:405` を `from jst import current_jst_daystamp` + `today = current_jst_daystamp()` に。JS 側は `presetToday` / `presetWeekend` (`:2214-2229`) が `new Date()` を読む代わりに、`get_dashboard` 応答に `today_jst` を含めて JS がそれを使う (pywebview の `api` 往復 1 回)。`tests/test_jst_date.py:115-117` のリストに `gui/app.py` を追加し、JS 側は `new Date()` の出現数を固定する契約テスト (`tests/test_gui_js_contract.py`) で回帰を止める。期待効果: OS tz に依らずダッシュボード・生成・通知・Pages が同じ日を指す (Nielsen 4)。
2. **`auto_predict.py:395` の最終行を 3 値化 or 削除** — `_notify_once` が `Decision.reason` を返すよう戻り値を `tuple[bool, str]` にし、`notify: sent` / `notify: suppressed (duplicate)` / `notify: failed (will retry next run)` を出す。あるいは `notify-audit` 行に一本化して最終行を消す (同じ事実を 2 書式で出さない)。
3. **生成物のタイムスタンプも JST 明示** — `web/generator.py:301,672` の `datetime.now()` を `current_jst_datetime()` に。HTML フッタの「生成時刻」が日付 (JST) と別 tz になる混在を消す。JST 機では見えないが、提案 1 と同じ前提依存を 1 つ減らす。

## 参考所見 (GUI 外・運用)

- **9/21 朝の起動前に checkout を main に戻すこと**。`auto_predict.py:373-378` は HEAD ≠ main で push を中止し `push_ok=False` を通知本文に載せる (`:222`)。commit message の運用計画 (「9/21 は main で運用」) と現在の checkout 状態 (`jst-date-unify-20260920`) が食い違っている。ユーザ視点では「予想は生成されたのに Web 版が更新されない」通知が届く事故になる (Nielsen 1: 状態は見えるが、原因がブランチだと本文からは読めない)。
- 抑止・送信失敗・最終確認の区別は依然ログ (`data/logs/auto_predict_daily_YYYYMMDD.log`) のみ。ログ名の日付が bat 側でも `current_jst_daystamp` に揃った (`auto_predict_daily.bat:7`) ので、「対象日 = ログ名 = dedup キー」の追跡は一貫した。

## 過去提案の消化追跡

- **「`notified.` の無条件 print を結果別 1 行に」(0919_2100 起点) → 本 commit で消化** (留保: `ok` の 3 値化は新提案 2 として継続)
- 「`predictor/experiments/` 分離」: 未消化 (4 回目)。他領域の参考所見でユーザ可視 UX 差なし、GUI 軸の降格には用いない (記録のみ)
- GUI 本体の残課題 (進捗 ETA / キャンセル全ステージ / 買い候補と観察候補の視覚分離): 本改修の対象外で残存、HOLD の主因

## 前回からの差分

- 総合 3.3 → 3.3 (±0)。全 5 項目変動なし。GUI 回帰 0 件
- 前回判定 HOLD → 今回 HOLD 維持。理由: 総合 4 未満、GUI 自体の課題は本改修の対象外。本改修に起因する減点・停止条件抵触なし
