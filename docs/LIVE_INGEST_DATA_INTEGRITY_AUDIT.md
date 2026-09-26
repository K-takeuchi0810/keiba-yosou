# ライブ取り込みのデータ完全性監査 (2026-09-26)

別プロジェクト `ai-builder` のライブ取り込みが、keiba-yosou の本番 DB (`data/keiba.db`) の
現在値を更新・削除している。それが **汚染** に当たるのか、当たるならどの範囲かを、
読み取りだけで確かめた記録。コード・タスク・DB・評価成果物は一切変更していない。

- 観測: 2026-09-26 20:19〜20:30 JST (開催日。観測中にも DB は変化しうる)
- DB は `mode=ro` で開いた。止まったまま残っているプロセス (90 個) は停止していない
- 判定は 3 種類に分ける: **単なる現在値の更新** / **PIT の再現性を壊す更新** /
  **履歴そのものを失わせる削除**

## 結論 (要約)

| 種類 | 実害の確認 | 内容 |
|---|---|---|
| 単なる現在値の更新 | — | 出走取消・天候馬場の記録の追加 (発表時刻つき、上書きではない) |
| **PIT の再現性を壊す更新** | **あり (小)** | 騎手・斤量・発走時刻・馬体重・単勝オッズの現在値を、予想の後に上書きする。4 開催日で予想の後の騎手変更 2 頭・発走時刻変更 1 レース。変更の記録が残っているものは復元できる |
| 履歴を失わせる削除 | **なし (潜在リスクのみ)** | 削除の処理はあるが、元データ 9,439 本と DB を突き合わせて削除の形跡 0 |
| (別の問題) 予想の時点で DB に無かった公式の変更 | **あり** | 9/22 に 15 頭の騎手変更 (2 頭は斤量も) が、2 日前に発表済みなのに予想に反映されていなかった |
| (別の問題) T−10 の市場の出自 | **要再検証** | 8 月以降の `odds_snapshots` の大半が `ai-builder` の 0B30。同じ発表時刻でも 0B31 と値が数 % ずれる |

**「ai-builder が DB を汚染している」とは結論しない。** 書いている値は公式の速報で、
時刻の刻印も正しい。問題は (1) 現在値を上書きすること自体が PIT の再現を難しくすること、
(2) keiba-yosou の T−10 の市場が、文書化されていない外部の取り込みに依存していること。

## 1. 書き込みの範囲と読み手の対応表

書き手はすべて keiba-yosou の本番 checkout のコードを import して使う
(`ai-builder\deploy\windows\fetch-live-jvdata.py` が `sys.path` に keiba-yosou を入れ、
`db.open_db` / `jvlink_client` / `jvlink_client.ingest.ingest_all` を使う)。
raw ファイルも keiba-yosou の `data/raw/0B11` `0B12` `0B14` `0B30` に書く。

| 書き手 | テーブル | 列 | 操作 | 元のレコード | 時刻・来歴の保持 | 現在値の上書き | keiba-yosou の読み手 | PIT のリスク |
|---|---|---|---|---|---|---|---|---|
| ai-builder `ingest_wh_files` | horse_races | horse_weight, weight_change_sign, weight_change_diff | UPDATE | 0B11 WH (馬体重) | **無し** (raw 0B11 のみ) | する | 特徴 (w_abs, w_delta)、予想表示 | **高** (履歴テーブルが無い) |
| keiba-yosou `upsert_jockey_change` (ai-builder の 0B14 から) | jockey_changes | 全列 (old/new, announced_time) | INSERT/UPSERT | 0B14 JC | あり (announced_time, data_created) | — | ほぼ無し | 低 |
| 同上 | horse_races | jockey_code, burden_weight, jockey_short_name, jockey_apprentice_code | UPDATE | 0B14 JC | jockey_changes に old/new | する | 特徴 (騎手・斤量)、予想表示、答え合わせ | **中** (jockey_changes が残っていれば復元可) |
| keiba-yosou `upsert_start_time_change` | start_time_changes / races.start_time | 全列 / start_time | UPSERT / UPDATE | 0B14 TC | start_time_changes に old/new | する | **T−10 の基準**、発走前/後の判定、fresh odds の対象選び | **中** (記録が残れば復元可) |
| keiba-yosou `upsert_course_change` | course_changes / races.distance, track_type_code | 全列 | UPSERT / UPDATE | 0B14 CC | course_changes | する | 特徴 (距離・馬場) | 中 (観測期間に発生 0) |
| keiba-yosou `upsert_race_cancellation` | race_cancellations | 全列 | UPSERT | 0B14 AV | あり | — | 取消の把握 | 低 |
| keiba-yosou `upsert_weather_going` | weather_going | 全列 | UPSERT | 0B14 WE | あり (announced_time) | — | 馬場の特徴 | 低 |
| ai-builder `reconcile_0b14_snapshot` | 上の 5 テーブル | 行 | **DELETE** (最新の 0B14 に無ければ) | — | **失われる** | — | — | **潜在** (§4) |
| 同上 | horse_races / races | 騎手・斤量・発走時刻・コース | UPDATE (取り消された変更を元に戻す) | — | — | する | 同上 | 中 |
| keiba-yosou `update_win_odds` (ai-builder の 0B30 から) | horse_races | win_odds, win_popularity, odds_fetched_at, odds_dataspec | UPDATE | 0B30 O1 | fetched_at = raw ファイルの更新時刻 | する (最新 1 枚) | 表示・最終オッズ扱い | 中 (発走後は NULL 刻印で確定扱い) |
| keiba-yosou `insert_odds_snapshot` (同上) | odds_snapshots | 全列 (source='0B30') | INSERT OR REPLACE | 0B30 O1 | あり (fetched_at, announced_at) | — | **T−10 の市場** (`predictor/pit_gate.py`、`pit_market.py`) | §3 |
| keiba-yosou `upsert_race` / `upsert_horse_race` / `upsert_payout` | races / horse_races / payouts | 行全体 | UPSERT | 0B12 RA/SE/HR (速報成績) | data_div ('1' 速報 / '2' 確定) | する | 答え合わせ・確定払戻の判定 | 低 (発走後の値。data_div で区別済み) |

補足: 騎手変更・発走時刻変更・コース変更が本体の列を上書きするのは、keiba-yosou 自身の
取り込み処理 (`db.py` の `upsert_jockey_change` など) の設計でもある。`ai-builder` が
加えているのは「取り消された変更を元に戻す」処理と、「最新の取得に無い記録の削除」。

## 2. PIT の実害 (予想の時点の値 × 変更の発表時刻 × 今の DB)

保存済みの予想 HTML (各日 08:00 / 09:00 / 11:00 の 3 本) には、馬ごとの **騎手名・斤量**、
レースごとの **発走時刻** が載っている。これを予想の時点の値として、今の DB と突き合わせた
(スクリプト: 作業用、DB は読み取り専用)。HTML に載っていない項目 (馬体重・オッズ) は
HTML から推測していない。

| 開催日 | 比べた頭数 (1 本あたり) | 騎手の違い | そのうち予想の **後** に発表 | 斤量の違い | 発走時刻の違い |
|---|---|---|---|---|---|
| 9/20 | 334 | 1 頭 (3 本とも) | 08:00・09:00 の 2 本 | 0 | 0 |
| 9/21 | 320 | 0 | — | 0 | 0 |
| 9/22 | 161 | 15 頭 (3 本とも) | 0 (発表は 9/20 17:30) | 2 頭 | 0 |
| 9/26 | 313 | 1 頭 (3 本とも) | 3 本とも | 0 | 1 レース (3 本とも) |

- **PIT の再現性を壊す更新 (実例)**
  - 9/20 阪神 1R 11 番: 騎手変更の発表 09:23。08:00・09:00 の予想は変更前の騎手、今の DB は変更後
  - 9/26 阪神 7R 4 番: 騎手変更の発表 12:53 (西村淳也 → 北村友一)。3 本とも変更前、今の DB は変更後
  - いずれも `jockey_changes` に old/new と発表時刻が残っているので、予想の時点の値は復元できる
- **予想の時点で DB に無かった公式の変更 (逆向き。PIT の漏れではない)**
  - 9/22 中山 15 頭: 騎手変更 (2 頭は斤量 55→53、56→54 も) の発表は 9/20 17:30 (中山の順延が決まった日)。
    `data_created` は 9/21。3 本の予想はすべて変更前の騎手で作られた
  - 9/26 阪神 1R: 発走時刻 10:00 → 10:01 の発表は 08:20。09:00・11:00 の予想も 10:00 のまま
  - 9/26 の `ai-builder` の起動のうち 09:07〜11:04 の回は、起動直後に止まったまま残っている。
    これが反映の遅れの原因かどうかは **未確定** (出力が保存されていないため)
- **状態**: 予想の後の変更は 4 開催日で 2 頭 + 1 レース。影響する特徴は騎手・斤量・発走時刻。
  今の DB をそのまま過去の予想の再現や分析に使うと、この 2 頭 + 1 レースで PIT の漏れになりうる。
  **PIT_UNTRUSTED** として扱う範囲は「今の DB の horse_races.jockey_code / burden_weight / races.start_time を、
  予想の時点の値として読む分析」。変更の記録で復元できる

## 3. オッズの干渉

| 月 (2026) | 0B30 (ai-builder) の行数 | 0B31 (keiba-yosou fresh odds) | backfill_0B31 |
|---|---|---|---|
| 05 | 0 | 0 | 24,600 |
| 06 | 0 | 0 | 11,364 |
| 07 | 0 | 4,595 | 0 |
| **08** | **85,911** | 9,317 | 0 |
| **09** | **112,419** | 7,434 | 0 |

- `predictor/pit_gate.py` の T−10 の選択は、取得元 (`source`) で絞っていない
  (`fetched_at IS NOT NULL AND fetched_at <= 発走 − n 分` の最新値)。したがって 8 月以降の
  **T−10 の市場の大半は ai-builder の 0B30 から選ばれている**
- 時刻の刻印は正しい: どちらの取得元も「取得時刻が提供元の発表時刻より前」の行は 0、
  発表から取得までの遅れは平均 約 1.7 分
- **値は一致しないことがある**: 同じ (レース, 馬, 発表時刻) を両方が持つ 5,734 組のうち、
  単勝オッズの一致は 3,458 組 (60%)、人気の一致は 5,552 組 (97%)。食い違う組の比
  (0B30 / 0B31) は中央値 0.991、範囲 0.81〜1.94。どちらも公式の速報だが、
  同じ発表時刻で値が違う理由は **未確定** (JV-Data の仕様の確認が要る)。
  どちらが正しいかは決めていない (「0B31 が正、0B30 が誤」とは扱わない)
- **REQUIRES_REVALIDATION**: 8 月以降の T−10 の市場を使った分析 (Phase 0.5-4A / 4B の評価窓
  2026-05-09〜08-31 のうち 8 月分を含む) は、市場の値の出自が外部の取り込みに依存している。
  結論を変えるほどの差かは未検証
- `horse_races.win_odds` の最終値も、開催日の多くの馬で 0B30 から書かれている
  (9/20: 308/334 頭、9/26: 171/313 頭)。発走後の取得は `odds_fetched_at=NULL` の確定扱いになる
  (2026-08-22 に「毎分実行の外部 live ingest」として対処済み、`db.update_win_odds` の注釈)

## 4. 削除の実害

`reconcile_0b14_snapshot` は、最新の 0B14 の取得に含まれない行を、出走取消・騎手変更・
天候馬場・発走時刻変更・コース変更の各テーブルから削除し、騎手・発走時刻・コースを
元の値に戻す。「0B14 の取得が成功して空なら、変更はもう無い」という前提に立つ。

keiba-yosou の `data/raw/0B14` に残っている元データ 9,439 本 (2026-05-09〜09-26) を
keiba-yosou のパーサで読み、DB と突き合わせた。

| テーブル | 元データに現れた件数 | DB の行数 | 元データにあって DB に無い | 同じ日の取得の間で一度消えて再び現れた |
|---|---|---|---|---|
| race_cancellations | 30 | 30 | 0 | 0 |
| jockey_changes | 83 | 57 | **26** | 0 |
| start_time_changes | 33 | 33 | 0 | 0 |
| course_changes | 0 | 0 | 0 | 0 |
| weather_going | 156 | 156 | 0 | 0 |

- 中身のある取得にはさまれた「0 件の取得」も 0 回
- `jockey_changes` の 26 件 (8/02: 1、8/08: 5、8/09: 12、8/15: 8) は、その日の最後の取得にも
  残っていた (= 取り消されていない)。削除の規則では消えない。DB の `jockey_changes` は
  `data_created` 8/15 から始まっており、**取り込みが始まる前の分が一度も入らなかった** と見るのが自然
  (JC の取り込みは 2026-09-17 のコミット `09b6f65` で本番の稼働に合わせて記録された)。
  元データには残っているので復元できる
- **判定**: 削除の処理は存在するが、観測期間に **履歴を失わせた削除の形跡は無い**。
  ただし、取得が途中で失敗して空が返った場合に消える設計であることは変わらない (潜在リスク)

## 5. 並行性

| タスク | 時刻 | JV-Link |
|---|---|---|
| keiba-auto-predict (fetch_full) | 08:00 / 09:00 / 11:00 | 使う |
| keiba-morning-odds | 08:45 | 使う |
| keiba-fresh-odds | 09:00〜19:00、10 分ごと | 使う |
| keiba-trend-collect-raceday | 20:00 | 使う |
| MAIBuilder Live JRA Data | 開催日の時間帯、**1 分ごと** (9/26 は 12:06 から 6 時間 24 分) | 使う |
| MAIBuilder Live JRA Data Controller | 00:05 から 6 時間ごと | 使わない (DB を読む) |

- 開催日の日中は、keiba-yosou の fresh odds (10 分ごと) と ai-builder (1 分ごと) が同じ時間帯に
  JV-Link と DB を使う
- ai-builder の起動のうち 30 回 (9/20 に 2、9/21 に 5、9/22 に 10、9/26 に 13) が、起動直後
  (CPU 0.2〜0.27 秒) で止まったまま残っている。keiba-yosou 側の取得との重なりが原因かは、
  keiba-yosou の fresh odds のログに実行ごとの時刻が無いため **未確定**
- keiba-yosou の fresh odds のログにはエラーが無い (9/26)

## 6. 分からなかったこと / 次に確かめること

1. 0B30 と 0B31 で同じ発表時刻の単勝オッズが違う理由 (JV-Data の仕様)
2. 0B14 の「空の応答」が「変更が無い」を意味するのか (仕様)
3. ai-builder の起動が止まる原因 (出力が保存されていない)
4. 馬体重 (horse_weight) は履歴テーブルが無く、現在値の上書きだけ。予想の時点の値は
   raw 0B11 から復元するしかない
5. 8 月以降の T−10 の市場を 0B31 だけに絞った場合に、0.5-4A / 4B の結論が変わるか

## 7. 扱い (2026-09-26 時点。修正は別途判断)

- 評価成果物 (`data/results`) への影響は確認していない。`docs/EVALUATION_DATA_QUALITY.md` には
  まだ参照を足さない
- PIT_UNTRUSTED: 今の DB の騎手・斤量・発走時刻・馬体重を「予想の時点の値」として読む分析
- REQUIRES_REVALIDATION: 8 月以降の T−10 の市場を使った分析 (出自が ai-builder の 0B30 に依存)
- ai-builder のプロセス・タスク・コードには触れていない (ユーザーの確認待ち)
