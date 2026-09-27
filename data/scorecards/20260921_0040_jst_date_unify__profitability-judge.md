# 収益性 / 投資判断専門家 採点 — 「今日」の決定を jst.py に集約 (commit 37eaf61, branch jst-date-unify-20260920)

## 判定: PASS

**改修タイプ**: type-B (運用基盤。`git show HEAD --stat` = jst.py / auto_predict.py / auto_predict_daily.bat /
notify_dedup.py / web/generator.py / tests。`BUY_FILTER` / calibrator / weights / backtest 不変)。
P25 固有ゲート (2026 holdout ROI 180% / CI 下限 / bonus_candidate / paired baseline) は **N/A (対象外)**。

**理由**: 依頼された 5 点をすべて自分で実測。資金喪失経路 (「観察専用」一文の脱落) は 3 パターンとも不成立、
1 日分の予想を落とす境界ミスの経路も本改修の範囲内では残っていない。停止条件抵触なし。
ただし **9/21 を守るはずの「main で運用」は現在の checkout 状態では成立していない** (下記「依頼 2」)。
これは改修の欠陥ではなく運用状態なので判定は落とさないが、08:00 前の必須アクションとして先頭に置く。

**根拠ファイル**: `jst.py:48-69`, `scripts/auto_predict.py:173-175,234-242,270-278,301-315,343-347,371-380`,
`scripts/auto_predict_daily.bat:7`, `scripts/fetch_mining.py:18-20`, `tests/test_jst_date.py`,
`tests/test_notify_e2e.py:103-122`, `data/logs/auto_predict_daily_20260920.log`

**次アクション (9/21 08:00 JST より前、必須)**: `git -C C:/Users/kizun/dev/keiba-yosou switch main` を実行し
`git branch --show-current` が `main` を返すことを確認する。現在は `jst-date-unify-20260920` (実測)。
このままだと 9/21 の 3 起動は (a) 新コードで動き、(b) `auto_predict.py:371-374` のブランチガードで
`push_ok=False` → Pages が 9/20 のページのまま止まり、(c) 予想 commit 3 件が feature ブランチに積まれる。

## 総合: 4.0 / 5 (参考スコア。N/A 項目は平均から除外)

## 実測 (このセッション、`.venv64` python、`NOTIFY_STATE_PATH` を scratchpad に向けて実行)

| 検証 | 結果 |
|---|---|
| `pytest tests/test_jst_date.py tests/test_notify_dedup.py tests/test_auto_predict_artifacts.py` | **63 passed** (0.79s) |
| bat と同じ一行 `python -c "from jst import current_jst_daystamp; print(...)"` (repo root) | `20260920` (成功。cwd 依存の import は bat の `cd /d` で満たされる) |
| 通知 3 パターン (`_notify_once` 経由、`_notify` をスタブ) | 完了 first_time 185 字 / 変更あり 201 字 / **最終確認 heartbeat 98 字**。**3 通とも末尾行 = 「⚠ 観察専用 (実弾根拠となるエッジは未証明)」** |
| heartbeat を同日 2 回呼ぶ | 2 回目は `decision=duplicate` で抑止 (1 通だけ、設計通り) |
| `generation_failed` 経路 (`auto_predict.py:343-347`) から `_final_confirmation` が呼ばれるか | **呼ばれない** (inspect で確認) |
| `git merge-base --is-ancestor main HEAD` | ff 可能 (main `fe9c6a5` の直上に 1 commit) |
| `git branch --show-current` | **`jst-date-unify-20260920`** (main でない) |
| 9/20 本番ログ | 08:00 `first_time delivered=ok recorded=ok` / 09:00 `duplicate` / 11:00 `duplicate`、3 回とも `push_ok=True`、Pages commit 3 件 (08:01 / 09:01 / 11:01) |

## 依頼 5 点への回答

### 1. 対象日を 1 日間違えて空ページ / 予想欠落になる経路は残っているか

- 生成対象日は `current_jst_date()` 1 回だけ読む (`auto_predict.py:270,278`)。generator には `--from day --to day` を
  明示で渡す (`:339`) ので generator 側の既定窓 (`web/generator.py:312`) は本番では使われない。DB の
  `race_year/race_month_day` は JRA 暦 = JST なので `_race_days` との突合も同じ暦。
- 既定 `now` は `datetime.now(timezone.utc).astimezone(JST)` (`jst.py:56-63`)。OS tz が UTC に変わっても JST 日付。
  依存は「システム時計が正しいこと」だけ。naive 拒否は実測 (test 5)。
- 3 トリガは 08/09/11 時で、JST 0 時境界から 8 時間以上離れる。bat の `RUNDATE` (起動時 1 回) と python の
  `today` (4 秒後) が別日になる余地は事実上ない。
- **残る穴 (本改修の範囲外だが同じ chain 内)**: `scripts/fetch_mining.py:20` の `--date today` は
  `datetime.now()` (ローカル、naive) のまま。`fetch_full.py:36` も `date.today()`。commit 文の「4 箇所」は
  chain 全体では 6 箇所で、`test_no_module_makes_its_own_today` の対象 3 モジュールに fetch_mining は入っていない。
  JST 機のいまは実害なし。ただし OS tz がずれた日には「予想は JST 今日、マイニング (DM/TM) はローカル今日」
  と食い違い、mining 特徴 (依存度 67%、memory 記録) が欠けた予想が出る。空ページではないが質が落ちる。
- 空ページ publish 自体は coverage ゲート (`:301-315`) が今回も不変で止める (回帰テスト通過)。**結論: 本改修が
  触った 4 箇所については経路なし。fetch_mining の 5 箇所目が未統一。**

### 2. 「9/21 の 3 起動より後にマージ」の判断が守るもの / 残るリスク

- **守るもの**: 対象日決定という単一障害点の改修を、24 レース日 (再現機会は週 2 日しかない) に初出しさせない。
  main (`fe9c6a5`) は 9/20 に 3 run とも正常 (上表) で、その状態を 9/21 も使える。方針として正しい。
- **成立条件が満たされていない**: 方針は「main で運用」だが共有 checkout は feature ブランチ (実測)。Task Scheduler は
  この checkout の HEAD を実行するので、放置すると **9/21 は新コードで動く**。しかもブランチガード
  (`auto_predict.py:371-374`) が `push_ok=False` にし、Pages は 9/20 のページで止まる (通知本文は「main push
  失敗のため未更新」)。iCloud への copy (`_stage_publish_artifacts`, `:363`) は commit より前なので iPhone 経路は
  生きる = 予想そのものは失わないが、Web 版は 1 日欠ける。前回 scorecard (09-19) の次アクションと同じ穴。
- **switch main 後にも残るもの**: (i) 新コードの初本番は 9/22 (火, 非開催) の `skip: ['20260922']` と log 名で
  部分確認できる。マージ後 9/22 朝に `data/logs/auto_predict_daily_20260922.log` の存在と skip 行の日付を見ること。
  (ii) マージ前に 9/21 の予想 commit 3 件が main に乗るので、ff はできなくなる (rebase or merge 要)。

### 3. 「観察専用」一文は 3 パターンすべてに残っているか

**実測で 3 パターンとも保持** (上表: 185 / 201 / 98 字、いずれも末尾行)。テスト固定も 3 経路そろった:
完了 `tests/test_auto_predict_artifacts.py:220`、heartbeat 本文 `tests/test_notify_dedup.py:619`、
実 HTTP POST まで通した heartbeat `tests/test_notify_e2e.py:122`。前回の減点 (changed ラッパー経由の未固定) は
E2E の `posts[1]` が文字列一致で見ており、私の probe の 201 字本文とも一致。解消と判断。

### 4. 「沈黙が生存信号を失う」指摘は解消したか

- **解消した部分**: coverage_abort / artifact_drift_abort が続いた日は 11:00 に heartbeat 1 通 (`:313,333`)。
  「中止 1 通のあと沈黙」= 最終起動が動かなかった、と読める。`--final-attempt` を bat が渡していなくても
  `_is_final_attempt()` (JST 11 時以降) で発火し、`StartWhenAvailable` の遅延起動でも `hour >= 11` なので落ちない。
- **穴 1 (未解消)**: `generation_failed` (`web.generator` の非 0 終了、`:343-347`) は `_final_confirmation` を
  呼ばない。generator が 3 回とも失敗する日は 08:00 に 1 通、その後沈黙で、「未起動」と区別できない。
  これは中止系と同じ「その日の予想が出ない」結末なので heartbeat の対象にすべき。
- **穴 2 (設計上の割り切り)**: 08:00 成功日に 09:00 / 11:00 が動かなくても無音。9/20 ログでは 3 回とも再生成
  している (odds 更新)。動かなくてもページは 08:00 版が残るので予想は失わないが、「最新オッズで再生成された」
  ことは Discord からは分からない。観察専用のため金銭影響なし。docs に「成功日の沈黙は正常」と書いてあれば足りる。

### 5. 9/20 実証: 「生成成功日の重複抑止は実運用確認済み」は妥当か

- 9/20 の 3 run 時点の main は `1548ca0` (9/19 20:50 マージ、dedup + heartbeat 込み)。ログは first_time
  (`delivered=ok recorded=ok`) → duplicate → duplicate、`push_ok=True` × 3、Pages commit 3 件。**主張は妥当**。
- 主張の範囲に注意: 実証されたのは「成功日・payload 不変」の 1 系列のみ。changed 経路 / 中止→heartbeat 経路は
  pytest E2E (`fe9c6a5`) のみで本番未観測。`delivered=ok` は HTTP 2xx であって人が読んだ証拠ではない。

## 項目別 (type-B 用に読み替え)

- **回収率 / 収益主張: N/A** — 収益主張なし。段階は **観察用** のまま (BUY_FILTER suspended、2026-08-22)
- **対象日決定の整合性 (境界・tz・注入): 4/5** — 4 箇所統一、UTC 15:00 境界と naive 拒否をテスト固定、bat も同一
  関数。減点: `fetch_mining.py:20` / `fetch_full.py:36` が未統一で復活ガードの対象外 (依頼 1)
- **運用リスク管理 / 反映タイミング: 3/5** — 「開催日前夜に入れない」方針は正しいが、checkout が feature ブランチの
  ままでは方針が実現しない (依頼 2)。前回 scorecard と同じ穴が再現。08:00 前に switch すれば実害ゼロ
- **沈黙 / 生存信号 (heartbeat): 4/5** — 中止 2 種は 1 通で「動いた」を確定できる。減点: `generation_failed` が対象外
  (依頼 4 穴 1)
- **「観察専用」開示 / 段階区別: 5/5** — 3 経路すべて実測保持 + 3 経路ともテスト固定 (E2E は実 HTTP まで)。
  「配信文面のリスク開示を必須項目として固定しテストで守る」を満たす

## 停止条件チェック

- P25 再現性メタ / baseline paired / market_snapshot / payout 欠損: **N/A (type-B)**
- [x] 「観察専用」一文が全 3 経路で保持 (実測)
- [x] 送信失敗が抑止に転化しない (不変、`:153-162`)
- [x] 対象日を誤って空ページ / 別日を publish する経路なし (本改修範囲)
- [x] 予測・filter・calibrator・資金管理は無変更 (stat 6 ファイル)
- [x] 実弾投入可・段階昇格を主張していない
- [x] 専門領域の停止条件 すべて不抵触

## 反証の試み

- 「heartbeat から観察専用が落ちる」→ 98 字本文の末尾行に存在。**不成立**
- 「境界をまたぐと対象日と log 名がずれる」→ 両方 `current_jst_daystamp/date` を同じ UTC 時計から導出、
  起動は 08/09/11 時。**不成立** (ただし fetch_mining は別時計 = 部分成立、tz 一致のいまは無害)
- 「9/21 は main で守られる」→ checkout が feature ブランチ。**現状では不成立** (switch main で成立)
- 「heartbeat で沈黙は全部読める」→ `generation_failed` 連続日は読めない。**部分成立**
- 「9/20 の実証は抑止コードを含まない版で走った」→ main は 9/19 20:50 に `1548ca0`、run は 9/20 08:00。**不成立**

## 主な改善提案

1. **`generation_failed` にも heartbeat** — `scripts/auto_predict.py:343-347` の `_notify_once(...)` 直後に
   `_final_confirmation(args, day, f"生成失敗 rc={r.returncode}")` を追加。中止 3 種すべてで「最終起動が
   動いた」を 1 通で確定できる。`tests/test_notify_e2e.py` に generation_failed 版を 1 件
2. **`fetch_mining --date today` を jst に寄せる** — `scripts/fetch_mining.py:20` を `current_jst_daystamp()` に。
   `tests/test_jst_date.py:114` の parametrize に `scripts/fetch_mining.py` を追加して復活ガードに入れる
3. **開催日前夜の checkout 検査を手順化** — `docs/OPERATION.md` の反映手順に「`git branch --show-current` が
   `main` であること」を 08:00 前チェックとして明記。09-19 / 09-20 と 2 夜連続で feature ブランチのまま
   夜を越えており、手順化しないと再発する

## 前回からの差分 (20260919_2100_notify_dedup: PASS / 4.0)

- 事故再発検知への影響 3 → 沈黙/生存信号 4 (+1): heartbeat 実装 + E2E。generation_failed の穴は残る
- 「観察専用」保持 4 → 5 (+1): 前回未固定だった changed 経路が E2E (実 HTTP) で固定、heartbeat 含む 3 経路実測
- 運用リスク管理 (新設) 3: checkout 状態が「main で運用」と矛盾。前回の次アクションが再発
- 総合 4.0 → 4.0 (±0)

## 最終所見

段階: **観察用** (不変)。本改修は予想を出す日を決める配線の統一で、収益性・確率・資金配分に触れない。
資金喪失経路 (観察専用の脱落) は 3 経路実測で不成立。1 日分の予想を落とす境界経路は改修範囲内には無い。
いま最も実害に近いのは改修ではなく **checkout が feature ブランチのまま 9/21 08:00 を迎えること** で、
これは 1 コマンドで潰せる。マージは 9/21 の 3 run 後、9/22 の skip ログで新コードの初本番を確認する。
