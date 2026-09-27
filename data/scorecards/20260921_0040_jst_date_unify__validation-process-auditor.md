# 検証プロセス監査人 採点 — 37eaf61 「今日」の決定を jst.py 1 箇所に集約

## 判定: FAIL

**理由**: 本 commit は自分の証拠を翌日に壊す。`tests/test_notify_dedup.py:262-278` (`test_jst_is_used_not_system_local_time`) は `notify_dedup.datetime` を monkeypatch して「JST で判定」を検証していたが、`jst_today()` が `jst.current_jst_daystamp` へ委譲された結果 patch が **不活性化**し、残った assert `== "20260920"` は実時刻を比較する。**2026-09-21 00:00 JST 以降、無改変 HEAD で決定的に 1 件 fail** (00:01:47 / 00:22:16 の 2 回、`git diff` 空を前後で確認して再現: assert '20260921' == '20260920')。commit message の「681 passed」は 9/20 中だけ真だった時限つき証拠で、監査対象そのもの (証拠を生む仕組み) の欠陥なので停止条件「実害のある欠陥」に該当。加えて **9/21 08:00 の本番 3 起動は宣言に反して branch コードで走る** (下記 Q4)。
**改修タイプ**: type-B/C (運用基盤の日付決定。predictor / backtest / GUI 非接触)。P25 固有ゲート・6 agent 統合は N/A。参考: 兄弟 5 名は PASS 3 (prediction 4.7 / profitability 4.0 / mobile 4.0 条件付) + HOLD 2 (data-pipeline 3.8 / gui-ux 3.3)。本判定は type-B 汎用ゲート (証拠の再現性) 単独で下す。
**根拠ファイル**: `jst.py:47-69`、`scripts/auto_predict.py:173-175,191,236,270,371-378`、`scripts/notify_dedup.py:78-83,213,255,268`、`web/generator.py:312-317`、`scripts/auto_predict_daily.bat:3,7`、`tests/test_jst_date.py:80-90,94-99,116-133`、`tests/test_notify_dedup.py:262-278,569-584`、`tests/test_notify_e2e.py:71-100`、`data/logs/auto_predict_daily_20260920.log:35,73-74,112-113`、`data/runtime/notification_state.json`、scratchpad `mutate2.py` / `mutate3.py` / `probe.py`
**次アクション**: (1) `tests/test_notify_dedup.py:262-278` を `jst_today(now=datetime(2026,9,19,16,30,tzinfo=timezone.utc)) == "20260920"` へ書き換え (monkeypatch 撤去)。(2) **9/21 08:00 JST より前に共有 checkout を `main` へ戻す** (現在 `jst-date-unify-20260920`; 並行セッション無しを確認してから)。(3) 正規表現ガードを AST ベースか「`from jst import` 以外の時刻 API 呼出し全禁止」に強化し、generator 既定窓の意味テストを追加。

## 総合: 2.4 / 5 (参考スコア)

## 項目別

- **検証設計の正しさ (テストが証拠として持続するか): 2/5** — 上記の時限 fail。旧実装 (`datetime.now(JST).strftime`) では patch が効いて任意日付で通っていたことを diff で確認 (notify_dedup.py 旧 76-78 行)。集約テスト `test_dedup_and_the_target_day_agree` (test_jst_date.py:94-99) は **import した名前同士**を比較しており、`main()` 内の `today` 変数を見ていない = auto_predict 側は同語反復 (下記 M3'/M4 が素通り)。全 suite の独立再実行 (.venv64、木が clean であることを前後で確認、00:22-00:28 JST): **1 failed, 679 passed, 6 skipped / 327 s / rc=1** (主張 681 passed / 5 skipped に対し 1 件 fail + 1 件 skip 化)。fail は上記 `test_jst_is_used_not_system_local_time` のみ。先行 2 回は兄弟 agent の変異ハーネスが `scripts/notify_dedup.py` を並行書換していた (mtime 00:21:28、` M` が一時出現) ため 62% で途絶し破棄。
- **時間境界の扱い (リーク分類学①の運用版、Q2): 3/5** — 自分の probe: UTC 15:00 / JST 00:00 / UTC 22:00→JST 07:00 / 年跨ぎ 12-31 15:00Z→20270101 / JST 入力の冪等 / EDT 入力 / `FINAL_ATTEMPT_HOUR` 10:59:59→False, 11:00:00→True、いずれも正。抜け: (a) **「同じ 1 起動に今日が 2 通り」は解消されていない** — `main()` は 1 回読む (auto_predict:270) が `decide`/`record` (notify_dedup:213,255)、`_final_confirmation_message` (auto_predict:191)、`_is_final_attempt()` (auto_predict:236) が各自クロックを読む = 1 起動あたり最大 4 回の独立読取。出典は 1 箇所化されたが **瞬間は 1 つでない**。08-11 時運用で実害はほぼ無いが commit message の主張は過大。(b) `now.tzinfo is None` は Python の aware 定義でない: `utcoffset()` が None を返す tzinfo は素通りし、`astimezone` がローカル解釈する (probe NoneTZ 15:00 → 20260920、M18 で確認)。(c) `tests/test_notify_e2e.py:73` が `date.today()` (ローカル) で fixture DB を作る = 5 つ目の自前「今日」。UTC 機の 15:00-24:00Z で E2E が偽陰性になる。ガードは tests/ を検査対象外。
- **変異テストの主張 (Q1): 2/5** — 独立設計 18 変異 (byte-safe 復元、00:00 以降は時限 fail テストを deselect)。**撃墜 10**: M7 record の date_jst を UTC 日付 / M8 JST=+9:30 / M9 既定 now をローカル aware / M10 naive 黙認 / M11 >= を > に / M12 `_is_final_attempt` が now 無視 / M13 bat を Get-Date に (REM に関数名残置) / M15 auto_predict +1 日 / M16 astimezone を replace(tzinfo=JST) に / M17 bat が関数結果を捨てて %date% 採用。**生存 7 (有効 17 中)**: M2 generator `datetime.now().strftime` 経由 (ローカル復活、正規表現の 3 綴りに非該当) / M3' auto_predict `datetime.utcnow().date()` (UTC 日付 — 00:22 JST の実行時点で実際に 9/20 を返していたのに素通り) / M4 auto_predict `time.strftime` (ローカル) / M5 `jst_today(now)` が now 無視 (誰も now 付きで呼ばない) / M6 notify_dedup `datetime.now(JST).strftime` (自前今日・JST 綴り) / M14 generator −1 日 / M18 utcoffset None 素通り。依頼者の「変異 7 種すべて落ちる」は **テストを書いた綴りだけ**に成立し、同じ故障クラスの別綴りは generator 3/3、auto_predict 2/3、notify_dedup 2/2 が生存。generator 既定窓は意味テスト 0 本 (test_template_render / test_output_defects / test_publish_safety を含めても生存)。
- **本番実証 / E2E の主張 (Q3): 3/5** — log:35 first_time attempted=yes delivered=ok recorded=ok、:73-74 / :112-113 duplicate attempted=no、state に generation_complete:20260920 sent_at 08:01:17+09:00 → 「生成成功日の抑止は実運用確認済み」は **成立** (1 日・同一 payload・push_ok=True の 1 シナリオに限る)。E2E: 実 HTTP POST / 500→未記録→再送 (e2e:162-179) は本物で成立。over-claim 2 点: (i) docstring「時刻 08:00/09:00/11:00 を模擬」は実際には `_is_final_attempt` を lambda で **stub** (e2e:97) — 本番の時刻ゲート (bat はフラグを渡さず hour>=11 のみ、bat:30) は E2E 経路に乗らず単体テスト 1 本のみ。3 回目は `--final-attempt` フラグと stub を同時に立てるので各経路単独は未分離。(ii) E2E は coverage 0/3 固定のみで changed (0→10→24 と増える現実の系列) は E2E 未検証。E2E を入れた `fe9c6a5` 自体は expert-review 未通過 (20260920 付 scorecard 0 件)。
- **運用移行 / 統合判定 (Q4・Q5): 2/5** — `git branch --show-current` = jst-date-unify-20260920、`git worktree list` で本 checkout が branch HEAD。`keiba-auto-predict` は next=2026/09/21 08:00 で `C:\Users\kizun\dev\keiba-yosou\scripts\run_auto_predict_daily.ps1` → bat `cd /d C:\Users\kizun\dev\keiba-yosou` (bat:3)。**checkout を戻さなければ 9/21 は branch コードで走る**。さらに auto_predict.py:371-378 の branch ガードで push_ok=False → Pages 未更新・通知は「main push 失敗のため未更新」・predictions: 20260921 commit が feature branch に積まれる。DB では 0921 = 24R/24R 出走馬入り = 実開催日。「9/21 は現在の main で運用」は checkout 切替を伴わない限り **不成立**。「マージしない」判断自体は妥当 (main は HEAD..main 0 件で乖離なし; 9/21 の predictions commit が main に乗った後の rebase は軽微)。ルール 1-ter: 30 分超の bg 計算なし (suite ≈ 8 分) → **非該当は妥当**。ただし 1-ter の趣旨 (実行される HEAD と意図した HEAD の同期確認) が今回まさに抜けている。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (type-B/C、backtest JSON 生成なし)。HTML の git 刻印は既存
- [x] baseline paired 比較 / market_snapshot / payout 欠損 — N/A
- [ ] 専門領域: 「証拠を生む仕組み」の欠陥 — **抵触**: HEAD で翌日から決定的 fail する回帰テスト (再現 2 回 + 変異 3 件が同テストで偽撃墜)
- [x] 前回宣言の執行: 「autouse 解除で本番 state が書かれる状態が残っていたら FAIL」→ `tests/test_notify_dedup.py:569-584` が fixture 有効性を assert、`tests/test_auto_predict_artifacts.py:272` が `--force-notify` 配線を固定 → **条件解消、この理由での FAIL はしない**

## 反証の試み

- 「681 passed」→ 00:00 JST 以降 1 failed (無改変 HEAD、2 回再現) → **不成立 (時限つき)**
- 「変異 7 種すべて落ちる」→ 同クラス別綴り 7/17 生存 → **主張の一般化は不成立**
- 「同じ起動内の今日が 1 通りになる」→ 1 起動あたり 4 箇所の独立クロック読取 → **出典 1 化のみ成立**
- 「9/21 は main で運用」→ checkout が branch + scheduler が固定パス → **切替なしでは不成立**
- 「生成成功日の抑止は実運用確認済み」→ log + state で **成立** (限定つき)
- 「中止経路は隔離 E2E で確認済み」→ HTTP/dedup 配線は成立、時刻ゲートと changed 系列は **未検証**

## 主な改善提案

1. **時限テストの修正** — `tests/test_notify_dedup.py:267-278` の FixedDateTime monkeypatch を削除し `assert notify_dedup.jst_today(now=fixed) == "20260920"` に。同時に `tests/test_jst_date.py` へ `jst_today(now=...)` の now 尊重 (M5) と generator 既定窓 (`build_view_model(from_date=None, ...)` が JST 今日 ±14 日になること、M2/M14) の意味テストを追加
2. **08:00 前の checkout 復帰** — 並行セッション不在を確認後 `git -C C:\Users\kizun\dev\keiba-yosou checkout main`。これを 3 起動の前提として scorecard 統合に明記。恒久策: bat 冒頭で `git rev-parse --abbrev-ref HEAD` が main でなければ notify して exit (auto_predict の push ガードより前段で止める)
3. **ガードの強化 + 単一 now の貫通** — 正規表現 3 綴りを「`from jst` 以外での `(datetime|date|time).(now|today|utcnow|strftime)(` 呼出し禁止」に広げ、`main()` 冒頭で `now = current_jst_datetime()` を 1 回取り `_notify_once` → `decide/record(now=...)`・`_is_final_attempt(now)`・`_final_confirmation_message(now)` へ渡す。`jst.py:55` の判定を `now.utcoffset() is None` に

## 前回からの差分

- 前回 (20260919_2100 notify_dedup): 3.0 / HOLD → 今回 2.4 / FAIL (−0.6)。1 点未満だが根拠を列挙: 時限 fail の再現 2 回 (00:01:47, 00:22:16)、独立変異 18 件の生存 7 件 (harness path 記載)、scheduler 実行パス vs checkout branch の実測
- 前回宣言 (提案 1・2 の回帰固定) は **執行済・解消を確認**。今回の新宣言: 次回この系列の commit で `test_jst_is_used_not_system_local_time` が実時刻依存のまま残っていれば **再度 FAIL**、生存変異 M2/M4/M5/M6 のいずれかが依然素通りなら HOLD 上限
