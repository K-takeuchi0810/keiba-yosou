# 収益性 / 投資判断専門家 採点 — 予想生成通知の同日重複抑止 (commit b437db3)

## 判定: PASS

**改修タイプ**: type-B (通知層のみ。`BUY_FILTER` / calibrator / weights / backtest 不変)。
P25 固有ゲート (2026 holdout ROI 180% / CI 下限 / bonus_candidate / paired baseline) は **N/A (対象外)**。
P25 Required Evidence の欠如を理由に NOT_EVALUABLE にはしない。

**理由**: 依頼された 4 つの金銭的リスク経路をすべて自分で実測し、資金喪失経路に該当する
もの (「観察専用」一文の脱落、送信失敗の永久抑止) は **不成立**。停止条件抵触なし。
留保 1 件: 初回中止通知の後の「沈黙」が「依然中止」と「タスクが起動していない」を
区別できなくなり、スケジューラ停止の検知が翌日に遅れる (旧来の同文 3 通は暗黙の
生存信号だった)。これは金銭ではなく F3 封印窓の観察日 (1 日 ≒ 36 レース ≒ 800 の 4.5%)
を失うリスクで、判定を落とす水準ではない。

**根拠ファイル**: `scripts/notify_dedup.py:150-208`, `scripts/auto_predict.py:116-178,230-260,314-318`,
`tests/test_notify_dedup.py:192-212,390-417`, `tests/test_auto_predict_artifacts.py:114-139,212-220`,
`scripts/register_auto_predict_task.ps1:8-14,36-39`

**次アクション**: 09/20 (日) は開催日。共有 checkout が `notify-dedup-20260919` のままだと
`auto_predict.py:302-304` のブランチガードで `push_ok=False` になり Pages が更新されない
(通知は「main push 失敗」を送る)。08:00 までに main へ反映して checkout を戻すこと。

## 総合: 4.0 / 5 (参考スコア)

## 採点対象とスコープ外

- **対象**: 通知の消失/重複の非対称性、事故 (07-25 / 08-01 空ページ publish) 再発検知への影響、
  ユーザ誤認経路、「観察専用」一文の保持、「送った」と「届いた」の乖離。
- **スコープ外**: 回収率・EV・Kelly・買い目フィルタ。今回不変 (`git show HEAD --stat` の 5 ファイル
  に predictor/ web/ config は無い)。戦略の段階は **観察用** のまま (BUY_FILTER suspended、2026-08-22)。

## 実測 (このセッション、`.venv64` python + `NOTIFY_STATE_PATH` を一時 dir に向けて実行)

| 検証 | 結果 |
|---|---|
| `pytest tests/test_notify_dedup.py tests/test_auto_predict*.py` | **46 passed** (5.66s) |
| 完了通知 3 回 (push_ok True/True/False) | 送信 2 通。1 通目 185 字、2 通目 (変更あり) 201 字。**両方とも末尾行 = 「⚠ 観察専用 (実弾根拠となるエッジは未証明)」** |
| 中止 0/36 → 中止 0/36 → 中止 20/36 → 完了 | 送信 3 通 (初回 / 変更あり / 完了 first_time)。中止後の完了は必ず届く |
| `--force-notify` 後に通常起動 | 2 通 (force は記録しない → 次回再送)。**重複側に倒れる**、消失ではない |
| drift 中止 (6 artifact) の「変更あり」本文 | 906 字 < Discord 上限 2000。plain 454 字 |
| 本番状態ファイル `data/runtime/notification_state.json` | 不在 (commit 文の「架空 total:2 汚染」は残っていない)。gitignore 済 (`.gitignore:25`) |
| `git rev-parse --abbrev-ref HEAD` | `notify-dedup-20260919` (main は `999b3f9`、未マージ) |

## 依頼 4 点への回答

### 1. 通知の消失は金銭的損失に直結するか / 事故再発検知を遅らせるか

- 07-25 / 08-01 の空ページ publish を止めているのは coverage ゲート (`auto_predict.py:230-242`, exit 2)
  であり今回不変。回帰テスト `test_main_aborts_without_publishing_when_entries_missing` は通過。
- **初回の中止通知は抑止されない** (`decide` は prev None → first_time)。検知の第一報は遅れない。
- ただし旧挙動では 08:00 / 09:00 / 11:00 に同文 3 通 = 「3 回とも起動して 3 回とも中止」が読めた。
  新挙動では 2 通目以降が沈黙するため、「依然中止」と「watchdog kill / PC 停止でタスク未起動」が
  Discord 上で区別不能。OPERATION.md はタスクログ確認手順を書いている (`docs/OPERATION.md` 追記 82-89 行)
  が、ユーザは通知だけを見る運用 (`auto_predict.py:162-163` 自ら記述)。
- 直接の金銭損失は無い (実弾運用していない、通知本文は観察専用)。損なわれうるのは F3 封印窓の
  観察日。事前登録 800 → 1,600 レースの判定に対し 1 開催日 ≒ 36 レース。

### 2. 「予想が出ていない」「出た」の誤認経路

- 出ていないのに「出た」: 完了通知は `generation_complete` の first_time / changed でのみ送られ、
  中止通知と別キー (`test_different_notification_types_do_not_collide`)。中止のみの日に完了通知が
  出る経路は無い。
- 出たのに「出ていない」: 中止 → 完了の遷移は完了側が初回なので必ず届く (実測 3 通目)。
- 残る誤認: 08:00 完了通知の後、09:00 / 11:00 に **ページは黙って再生成される** (オッズ live で
  内容は変わる。commit 文でも 14 分差で 432 ハンクずれると実測)。ユーザは通知の時刻を予想の
  時刻と思う可能性がある。観察専用のため金銭影響は無いが、答え合わせ時に「どの版を見たか」が
  揺れる。ページ側に生成時刻表示があれば足りる (本 agent の担当外、参考所見)。

### 3. 変更通知でも「観察専用」一文が落ちないか

**実測で保持を確認** (上表)。`decide` の changed 経路は `f"🔁 ...\n{lines}\n\n{text}"` と全文を
連結する (`notify_dedup.py:173-177`) ので、一文は `_completion_message` の末尾行として残る。
既存テスト `tests/test_auto_predict_artifacts.py:212-220` は plain 本文のみを固定し、**changed
ラッパー経由の保持は未固定** (私の probe だけが確認)。Hard Fail には該当しない。

### 4. 「送ったことになっている」と「実際に届いた」の乖離 (反証)

- `notify_discord` は `urlopen(...).read()` 完了時のみ True (`notify_discord.py:29-39`)。HTTPError
  (400 / 429) や timeout は False → `record` されない → 次回再送 (`auto_predict.py:135-142`)。
  配線レベルのテスト `test_wiring_does_not_record_a_failed_send` で固定済み。
- 逆方向 (届いたが記録されない: 204 受信後の read 例外、`_save` 失敗) は **重複**になるだけ。
  非対称は正しい向き。
- 「記録されたが届かない」が成立するのは Discord が 2xx を返して配信しない場合のみで、コード側の
  欠陥ではない。本文 2000 字超は 400 で毎回失敗し永久に届かないが、今回の最大 906 字で余裕あり
  (この上限チェック自体は改修前から無い、pre-existing)。
- 同時実行: 3 トリガは別時刻、Task は `MultipleInstances=IgnoreNew` (08-08 scorecard で実測)。
  decide→record 間の競合は現状構成では起きない。`os.replace` の原子置換も確認。
- **結論: 反証不成立。** 実装は主張通り。

## 項目別 (type-B 用に読み替え)

- **回収率 / 収益主張: N/A** — 収益主張なし。CI 下限 100% 超の集合は存在せず、段階は観察用のまま
- **通知消失の非対称設計 (fail-open / 送信後記録): 4/5** — 実測・テストとも整合。減点: force 経路が
  記録せず翌起動で重複する仕様が OPERATION.md 未記載、Discord 2000 字上限の未検査 (pre-existing)
- **事故再発検知への影響: 3/5** — 第一報は遅れないが、沈黙が「継続中止」と「未起動」を区別できず、
  スケジューラ停止の検知が翌日以降に遅れる。旧来の暗黙の生存信号を代替する手当てが無い
- **誤認経路の遮断: 4/5** — 中止→完了、push_ok 反転は必ず届く (実測)。減点: 黙った再生成による
  版の揺れ
- **「観察専用」一文の保持: 4/5** — 実測で両経路保持。減点: changed ラッパー経由の保持がテストで未固定
- **段階区別 / 不確実性開示: 5/5** — 本文に観察専用を必須化 (`auto_predict.py:165-166`)、docs も
  収益主張を含まない。ベストプラクティス「配信文面にリスク開示を必須項目として固定しテストで守る」
  を満たす

## 停止条件チェック

- P25 再現性メタ / baseline paired / market_snapshot / payout 欠損: **N/A (type-B)**
- [x] 「観察専用」一文が全通知経路で保持 (実測)
- [x] 送信失敗が抑止に転化しない (テスト + 実測)
- [x] 中止通知が完了通知に化ける経路なし
- [x] 予測・filter・calibrator・資金管理は無変更 (stat 5 ファイル)
- [x] 実弾投入可・段階昇格を主張していない
- [x] 専門領域の停止条件 すべて不抵触

## 反証の試み

- 「変更通知で観察専用が落ちる」→ 実測 201 字本文の末尾行に存在。**不成立**
- 「送信失敗が記録されて永久消失する」→ `_notify` False で `record` 非到達、再起動で first_time。**不成立**
- 「抑止が事故検知を遅らせる」→ 第一報は遅れない。**部分成立**: 2 通目以降の沈黙で「未起動」を
  見分けられない (上記 3/5)
- 「テストが本番状態を汚す」→ 本番ファイル不在、conftest autouse で隔離、`NOTIFY_STATE_PATH` を
  ダミーに向けても 46 passed。**不成立**

## 主な改善提案

1. **最終トリガ (11:00) では中止系を抑止しない** — `register_auto_predict_task.ps1:14` の第 3 トリガに
   `--final-attempt` を渡し、`auto_predict.py:238-241,257-259` の `coverage_abort` /
   `artifact_drift_abort` だけ `force=True` にする。「その日の最終結果が中止だった」ことと「最終
   起動が行われた」ことを 1 通で確定させる。完了通知の抑止はそのまま
2. **changed ラッパー経由の観察専用保持をテストで固定** — `tests/test_notify_dedup.py` の `wired` 系に
   「push_ok True→False の 2 通目に `観察専用` が含まれる」assert を 1 件追加
3. **`notify_discord` に 2000 字ガード** — `notify_discord.py:29` で超過時は末尾を切らず先頭側
   (変更点リスト) を要約し、観察専用行を必ず残す。現状最大 906 字なので優先度は低い

## 前回からの差分

- 同系 (運用・通知経路) の直近評価 `20260808_0940_auto_predict_watchdog` は **PASS / 4.2**。今回
  **PASS / 4.0**。差分は「沈黙が生存信号を失う」の 3/5 による。戦略採点系の直近
  `20260919_1100_phase05_4b_foundation` (HOLD / 3.6) とは対象が異なり比較しない。
- 前回 (08-08) 提案 1「Task 結果 / watchdog finish / 当日 HTML の 3 点 healthcheck」は未実装。今回の
  抑止で通知側の冗長性が減ったため、この提案の重要度は上がった。

## 最終所見

段階: **観察用** (不変)。本改修は通知の重複を減らす運用改修であり、収益性・確率品質・
資金配分に一切触れていない。資金喪失経路として依頼された 2 点 (観察専用の脱落、送信失敗の
永久抑止) はいずれも実測で不成立。残る留保は「沈黙の意味が曖昧になる」観測性の後退で、
提案 1 で閉じられる。
