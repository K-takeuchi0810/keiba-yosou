# 運用マニュアル (keiba-yosou)

P14 (`only_t04_09_ev_ge_110`) 採用後の運用ルール一覧。
P12 失敗 (TEST 184% → PROD 45% 大暴落) を受けた再発防止策。

## 1. 日次運用 (本番予想)

### 朝の予想生成
```powershell
cd C:\Users\kizun\dev\keiba-yosou
# JV-Link でデータ取得 (32-bit)
.venv32\Scripts\python.exe -m scripts.fetch_full --since-last

# 予想生成 + 買い目算出 (64-bit、P14 small-mode)
.venv64\Scripts\python.exe -m scripts.predict --date 20260516 --only-bets --bet-size-mode third
```

オプション:
- `--bet-size-mode third` (推奨): bet_unit / 3 で小口運用 (P14 信頼性確立まで)
- `--bet-size-mode half`: 信頼性確立後の中間段階
- `--bet-size-mode kelly_quarter`: 最終的に Kelly 1/4 運用 (要 Kelly 信頼性確認)
- `--bet-size-mode flat`: bet_unit のまま (推奨されない、P14 信頼性が確立した後でのみ)

`--bet-unit 100` (default) のままで:
- third → 1 件 33 円 (実質的に 10 円単位丸めで 30 円)
- half → 50 円
- flat → 100 円

実際の現金運用時は `--bet-unit 1000` (= 1 件 330 円 small / 1000 円 flat) などに調整。

## 2. 週次監視 (Windows Task Scheduler 登録)

### 前提条件

`weekly_monitor.bat` は scripts.monitor の前に回帰テスト (pytest) を実行する。
事前に `.venv64` へ dev 依存を導入しておくこと:

```
.venv64\Scripts\python.exe -m pip install -r requirements-dev.txt
```

未導入でも `weekly_monitor.bat` は pytest をスキップして続行する
(誤警告を出さないようガード済) が、その場合 helper の回帰検知は働かない。

### Task Scheduler への登録手順

1. `Win + R` → `taskschd.msc` で起動
2. 「タスクの作成」をクリック
3. **全般タブ**
   - 名前: `keiba-yosou Weekly Monitor`
   - 「ユーザーがログオンしているかどうかにかかわらず実行する」にチェック
   - 「最上位の特権で実行する」にチェック
4. **トリガータブ**
   - 新規 → 毎週 → 日曜日 10:00 → OK
5. **操作タブ**
   - 新規 → プログラムの開始
   - プログラム: `C:\Users\kizun\dev\keiba-yosou\weekly_monitor.bat`
   - 開始 (オプション): `C:\Users\kizun\dev\keiba-yosou`
6. **条件タブ**
   - 「コンピューターを AC 電源で使用している場合のみタスクを開始する」のチェックを外す
7. **設定タブ**
   - 「タスクが既に実行中の場合に適用される規則: 新しいインスタンスを開始しない」
   - 「タスクが要求時に実行されるようにする」にチェック

### 監視内容と対応フロー

```
週次自動実行 (weekly_monitor.bat)
  │
  ├── pytest tests/ -q  (共通 helper の回帰検知)
  │   └── 失敗で WARNING 表示 + exit code に bit1 (=2) を加算
  │       (pytest 未導入の env ではスキップ、誤警告なし)
  │
  ├── scripts.monitor --days 30 --threshold 0.20
  │   ├── 直近 30 日の予測 vs 結果から Brier を計算
  │   ├── 訓練時 baseline (lgbm_meta.json の val_brier 0.0604) と比較
  │   └── +20%% 悪化 (= Brier > 0.0725) で警告 + exit code に bit0 (=1) を加算
  │
  └── 最終 exit code (Task Scheduler でログを開かず切り分け可能):
      0 = 正常 / 1 = Brier drift / 2 = pytest 回帰 / 3 = 両方
      Brier drift (exit code に 1 を含む) の場合の推奨対応:
      ├── 推奨対応 1: scripts.filter_sweep --recent-3fold で robust 再選定
      ├── 推奨対応 2: scripts.train_lgbm で LGBM 再訓練 (TRAIN を rolling forward)
      └── 推奨対応 3: config.BUY_FILTER_DEFAULT.whitelist_tracks=[] で即サスペンド
```

### Task Scheduler の失敗通知 (任意)

「操作」タブで複数アクション設定可能:
- メイン: `weekly_monitor.bat`
- 失敗時 (exit code != 0): PowerShell で `Show-Notification` を呼び出す or メール送信

### 予想生成通知の重複抑止 (2026-09-19 追加)

`scripts/auto_predict.py` は開催日の朝に **3 回**起動される。3 回とも同じ結果に
なるのが普通なので、以前は同じ本文が 3 通 Discord に届いていた。

いまは `scripts/notify_dedup.py` が `(通知の種類, 対象日)` をキーに **中身**で
判定する:

| 状況 | 挙動 |
|---|---|
| 初回 | 全文を送る |
| 中身が同じ (本文の生成時刻だけ違う) | 送らない |
| 中身が変わった | 「🔁 前回から変更あり」+ 変更点 + 全文 |
| 判定に失敗した (状態ファイル破損など) | **送る**。重複を 1 通許す方が、中止通知を消すよりまし |
| Discord への送信そのものが失敗した | 記録しない。**次の起動で再送する** |
| 最終起動 (11:00) まで中止が続いた | **最終確認を 1 通**送る (下記) |

**最終確認 (heartbeat)**: 抑止を入れると「依然中止」と「タスクが起動しなかった」が
Discord 上で区別できない (以前は同文 3 通が暗黙の生存信号だった)。最終起動 (11:00) まで
中止が続いた場合だけ、**中止通知の再送ではなく別の意味の通知**として 1 通送る。

    通常起動が成功し状態も変わらない → 無通知
    最終起動まで中止が続いた         → 最終確認 1 通
    最終起動自体が動かなかった       → 最終確認が来ない  ← これを読み取るのが目的

最終起動かどうかは JST 時刻で判断する (`FINAL_ATTEMPT_HOUR = 11`)。Task Scheduler は
トリガごとに違う引数を渡せないため。登録側 (`register_auto_predict_task.ps1` の
`ThirdStartTime`) とずれないようテストで突き合わせてある。

**監査ログ**: 通知の判断は毎回 1 行残る。**Discord を静かにしても監査ログまで
静かにしてはいけない**ので、抑止したときも必ず出る。

    notify-audit type=generation_complete subject=20260920 decision=duplicate attempted=no delivered=- recorded=-

`decision` は first_time / changed / duplicate / fail_open / forced。
`attempted` は送信を試みたか、`delivered` は Discord が受けたか、`recorded` は状態を
書けたか。`grep notify-audit data/logs/auto_predict_daily_YYYYMMDD.log` で 1 日ぶんが追える。

**通知が来ないときの確認手順**:

0. **スマホしか手元にない場合はここだけ**: Pages を開いてヘッダの `更新 <日時>`
   を見る。通知が抑止されても生成と publish は毎回走るので、時刻が今朝なら
   「予想は出ている、通知が重複だったので黙っただけ」。時刻が古ければ生成自体が
   動いていない。
1. コンソール / タスクログ (`data/logs/auto_predict_daily_YYYYMMDD.log`) に
   `notify suppressed (generation_complete:YYYYMMDD): duplicate` が出ていれば、
   抑止であって失敗ではない。`WARN: 通知の記録に失敗しました` が出ていれば
   抑止が効かず重複が届く状態 (通知は失われていない)。
2. 状態は `data/runtime/notification_state.json` (gitignore 済、JST で 14 日保持)。
   `sent_at` と `payload` を見れば「いつ何を送ったか」が分かる。
3. どうしても再送したいときは `--force-notify` を付けて起動する。
   **注意**: force 送信は記録を残さないので、次の通常起動で同じ通知がもう 1 通届く。
4. 状態ファイルを消せば次回は初回扱いになる (消しても予測には一切影響しない)。
   バックアップ runbook (6.5) の対象外で **正しい**。失っても重複 1 通で済む。

**同時起動**: ロックは無い。`keiba-auto-predict` は `MultipleInstances=IgnoreNew`
かつトリガが 08:00 / 09:00 / 11:00、1 回 65-75 秒なのでスケジューラ経由では重ならない。
手動 CLI と重なった場合の最悪値は重複 1 通で、通知が消える側には倒れない。

**触ってはいけない範囲**: この層は通知だけを見る。予測・特徴量・DB 取込・PIT・
評価処理に手を入れてはいけない。

導入時の確認と、**その証拠としての強さ** (2026-09-19 の検証監査で格付けし直した):

| 確認 | 強さ |
|---|---|
| `git diff --stat` で `web/` `predictor/` `config.py` `db.py` の差分が 0 行 | **主たる証拠** |
| `web.generator` のプロセスに `scripts.auto_predict` / `scripts.notify_dedup` が載らない (import graph) | **主たる証拠** |
| 同日 HTML を 変更後→変更前→変更後 と連続生成し 3 本一致 | **弱い (ほぼ同語反復)**。generator の命令列が両状態で同一なので一致は恒等式。実際に測れたのは「85 秒の窓でデータが動かなかった」ことだけ |
| `prediction_log` 18,893 行の sha256 一致 | **弱い (同語反復)**。`--log-predictions` を付けずに回したので書き込み自体が起きない |
| 封印モデル成果物 6 点のハッシュ不変 | 有効。ただし **`config.artifact_drift()` で確認してはいけない** — `SEALED_FROM` 未設定のあいだ無条件で `[]` を返すので、確認したつもりになる。`config.SEALED_ARTIFACTS` の各ファイルを直接 sha256 すること |

用語の注意: **「bit-identical」とは言えない**。生成時刻の 1 行を除いた一致であり、
除外した時点で完全一致ではない。正しい言い方は「生成時刻行を除いて一致」。
再現手順: `grep -v 'class="updated"' index.html | sha256sum` (この正規化で
`c0782ff493fc0eba...`)。

もう 1 点の注意: **generator 自身は `scripts.notify_discord` を遅延 import する**
(`web/generator.py:69,79` のアーカイブ失敗・出力不完全の通知)。この経路は重複抑止を
**通らない**ので、同じ障害が続けば毎回届く。意図的 (障害通知は消したくない)。

**注意**: オッズは live で動くので、時間を空けた 2 本の HTML は当然ずれる
(14 分空けたら 432 ハンクずれた。20:00 の傾向収集バッチによる DB 更新と時刻が一致)。
前後比較は必ず連続で回すこと。

## 3. 月次運用 (戦略の rolling 再選定)

### 月初 (毎月 1 日) チェック

```powershell
# 直近 3-fold で robust 戦略を再検証
.venv64\Scripts\python.exe -m scripts.filter_sweep --recent-3fold > data\backtest\YYYYMM_recent_3fold.csv

# 現採用戦略 (P14 = only_t04_09_ev_ge_110) の min_return が >= 80%% か確認
# 崩れていれば config.BUY_FILTER_DEFAULT を更新 + 新 scorecard 作成
```

### TRAIN 期間の rolling forward

3 ヶ月ごとに `config.DATA_PERIODS["train"]` を更新:
- 2026-05: `train = 20210101-20231231` (固定で 3 年、当初設定)
- 2026-08: `train = 20210501-20240430` (3 ヶ月 rolling forward)
- 2026-11: `train = 20210801-20240731` (同上)

更新後に `scripts.train_lgbm --from <new_from> --to <new_to> --save --n-trials 60`。

## 4. 四半期運用 (大改修)

### 賞味期限管理

- P14 採用 = 2026-05-16
- **賞味期限 = 2026-08-15** (= 3 ヶ月後)
- 賞味期限超過時に必ず `--recent-3fold` 再実行 + 戦略採用判断やり直し

### Phase 6 Tier 2/3 features の追加検討

3 ヶ月ごとに Phase 6 設計を進める:
- Tier 2: pace, draw bias by track, surface×track×distance
- Tier 3: 4 角通過順位, 馬場バイアス direction, 馬体重 delta
- 詳細は `data/scorecards/20260515_2200_p13_holdout_failure_and_p14_recovery.md` Phase 6 章

## 5. リスク管理 (賭金縮小ロジック)

### 現状 (2026-05-16 時点)

- `--bet-size-mode third`: 固定 1/3 倍。連敗 / 連勝に応じて自動調整なし。
- 手動で運用者が「3 連敗したら一週間休む」等のルール適用。

### Phase 7 で本実装予定

- `predictor/risk.py` (新規): drawdown tracker (直近 N レースの累積収支記録)
- bet size = base × max(0.5, 1 - drawdown_pct × 0.05)
  - 例: 累積 -20%% 時 → 賭金 0.5 倍
- 月次累積 -30%% で即サスペンド (人間介入トリガー)

## 6. 緊急停止 / 退避モード

何かおかしいと感じたら **即座に** 以下を実行:

```python
# config.py の BUY_FILTER_DEFAULT を編集
"whitelist_tracks": [],  # 空にする → is_whitelisted_race 常に False → buy_only ゼロ
```

または環境変数で一時停止:
```powershell
$env:PRED_DISABLE_LGBM=1   # LGBM 無効化 (rule のみで動作)
$env:BET_WHITELIST=0       # whitelist 無効化
```

## 6.5 バックアップ / 復旧 runbook (2026-06-13 追加)

`data/keiba.db` (約 430MB) は唯一のデータストア。破損・誤削除に備える。

### 週次バックアップ (推奨)

```powershell
# WAL を本体へ反映してからコピー (sqlite3 CLI がある場合)
# 無い場合は GUI / スクリプトが動いていない状態で 3 ファイルをまとめてコピー
Copy-Item data\keiba.db     data\backup\keiba_$(Get-Date -Format yyyyMMdd).db
Copy-Item data\fetch_state.json data\backup\fetch_state_$(Get-Date -Format yyyyMMdd).json
# 世代は 4 つ程度残す (約 1.7GB)
```

### DB 破損時の復旧手順

1. **バックアップがある場合**: 最新の `data/backup/keiba_*.db` を `data/keiba.db` に戻す。
   `fetch_state.json` も同日付のものに戻す (戻さないと差分取得の起点がずれるが、
   UPSERT 冪等なので重複取得しても壊れない)
2. **バックアップが無い場合**: raw (`data/raw/`, 約 6.3GB) から全量再構築:
   ```powershell
   Remove-Item data\keiba.db, data\keiba.db-wal, data\keiba.db-shm
   .venv32\Scripts\python.exe -c "from jvlink_client.ingest import ingest_all; print(ingest_all(force=True))"
   ```
   - 処理順は ingest_all 内で RACE → マスタ → 0B* (リアルタイム) に固定済み
     (0B* は horse_races 行への UPDATE のため RACE が先に必要)
   - 所要時間は数時間規模 (未実測。初回実行時にここへ実測値を記録すること)
   - **注意**: 事前オッズスナップショット (0B31 の途中経過) は raw に残っている
     最終版のみ復元される
3. `fetch_state.json` が壊れた場合: そのまま起動してよい (fromtime が 1986 に
   戻り全量再取得になるだけ。warning ログが出る)。時間を節約したいなら
   バックアップから戻すか、`data/raw/` の最新ファイル名の日時を参考に手で書く

## 7. 関連スキル / ドキュメント

- [.claude/skills/project-state/SKILL.md](../.claude/skills/project-state/SKILL.md) — 現状サマリ
- [.claude/skills/expert-review/SKILL.md](../.claude/skills/expert-review/SKILL.md) — 改修後の自動採点
- [.claude/skills/keiba-backtest/SKILL.md](../.claude/skills/keiba-backtest/SKILL.md) — backtest 設計
- [CLAUDE.md](../CLAUDE.md) — 必須ルール 4 で本書を参照

## 8. 目標 (2026-06-14 改定)

**年間 180%, 月次変動は許容** (P25 検証設計時に上方改定)

- 年間 +80% = 月平均 +6.7% (= 100 円ベースで月 6.7 円利益 / 100 円賭金)
- 月次は -20% 〜 +50% の variance を許容
- 連続 3 ヶ月 -10% 未満 → 自動サスペンド + 戦略再選定

## 9. 3代血統 (父母父/母母父)・産地の反映と検証 (2026-07-05 追加)

webapp 出馬表の 父母父・母母父・産地表示は、UM (競走馬マスタ) の 3 代血統と
HN (繁殖馬マスタ) の産地名を使う。**列の追加は writer 起動時に自動** だが、
**中身は再取込しないと全馬 NULL のまま** (ingested_files に記録済みのため)。

### 9-1. データ反映手順 (実機・32bit venv)

```
.venv32/Scripts/python.exe -c "from jvlink_client.ingest import ingest_all; \
    print(ingest_all(force=True, dataspecs=['DIFN', 'BLOD']))"
```

- **必ず dataspecs を DIFN (UM) と BLOD (HN) に限定する**。
- 補足: HS (HOSE) の horse_masters 書込みは 2026-07-05 に INSERT OR IGNORE 化
  したため、dataspec 無指定の force でも UM 行が空文字で潰れることは無くなったが、
  無指定 force は全 dataspec を再取込して数時間かかるので時間の無駄。

### 9-2. バイト位置の実機検証 (状態: UM=確定済み / HN=-2 ずれ確定・修正済み)

**UM idx8/idx12 (父母父/母母父) は 2026-07-06 実 DB で確定済み** — ディープ産駒 6 頭
すべての父母父 = Alzao と一致、充填 89-94% (scripts/verify_pedigree.py の出力)。

**HN の birth_year 以降の tail は -2 バイトずれが確定 → parse_hn を修正済み (2026-07-06)**。
`scripts.probe_hn_offsets` の実 .jvd (HNVM2020…) ダンプで、国内産レコードの産地が
従来 210 では '平町…11'(先頭欠け+繁殖番号混入) だったのに対し **208 で '安平町' と
正しく読め**、かつ 持込区分=0(国内)+産地あり / =9(外国)+産地空 が相関して全フィールドが
-2 補正で整合した。修正後の正しいオフセット:

| フィールド | 旧(誤) | 新(-2) |
|---|---|---|
| birth_year | 197 | **195** |
| sex/breed/coat | 201/202/203 | **199/200/201** |
| 持込区分 | 205 | **203** |
| 輸入年 | 206 | **204** |
| 産地名(20) | 210 | **208** |
| sire_breeding_num | 230 | **228** |
| dam_breeding_num | 240 | **238** |

**この -2 は sire_breeding_num にも及んでいた = 血統遡上 (traversal) が繋がらなかった
主因の 1 つ**。修正を反映するには BLOD 再取込が必須 (§9-4 の runbook)。反映手順:

- 実機で `git pull` (parse_hn 修正を取得) →
- `.venv32\Scripts\python.exe -m scripts.bootstrap --dataspecs BLOD` で BLOD 再取込
  (breeding_horses を新オフセットで埋め直す) →
- `python -m scripts.audit_sire_lines` で **traversal_hit が 0% から上昇**することを確認 →
- 産地の目視検証 (下記) を通過したら config.HN_BIRTHPLACE_VERIFIED=True に反転。

**gen3 の順列取り違えと HN 数字フィールドの入替は無音で誤る**ため、確認を省略しない。

1. **UM gen3 の血統表突合** (順列ミスはこれでしか検出できない・確定済みだが再確認可):
   ```sql
   SELECT horse_name, sire_name, sire_dam_sire_name, dam_dam_sire_name
   FROM horse_masters WHERE sire_name = 'ディープインパクト' LIMIT 5;
   ```
   → sire_dam_sire_name (父母父) が **Alzao** (ディープの母ウインドインハーヘアの父)
   になっているか。キズナ産駒でも同様に父母父 = **ストームキャット**
   (キズナの母父) を確認。netkeiba/JBIS の血統表と 2-3 頭突合。
2. **HN 産地名の目視**:
   ```sql
   SELECT birthplace, COUNT(*) FROM breeding_horses
   GROUP BY birthplace ORDER BY 2 DESC LIMIT 30;
   ```
   → 上位が 安平町/新冠町/日高町/米/愛/英 等の地名・国名か。
   **数字が混入していたら 205-229 の順序疑い** → 表示を止めて再調査。
3. **数字フィールドの入替検出** (無音故障対策):
   - `SELECT DISTINCT mochikomi_kubun FROM breeding_horses` → {0,1,2} 程度の小集合か
   - `SELECT DISTINCT import_year ...` → '0000' または 19xx/20xx の 4 桁のみか
   - クロス整合: import_year が実年の馬は birthplace が国名系、内国産は '0000'。
     既知例: ノーザンテースト = 加 (1971 生・輸入)。
4. **充填率**: `SELECT COUNT(*) FILTER (WHERE sire_dam_sire_name != '') * 1.0 / COUNT(*)
   FROM horse_masters` → force 再取込後に 9 割超が期待値。
5. 異常時: webapp の表示は自動縮退しないので、該当フィールドの表示を止めてから
   parser のオフセットを再調査 (docs/JV-Data4901.pdf §13 UM / §18 HN と照合)。

あわせて `python -m scripts.audit_sire_lines` (系統辞書の独立突合、scorecard
20260705_0500 の残作業) も同じセッションで流すと効率が良い。

### 9-3. 「その他」削減の効果測定 (英語名辞書・仮名正規化の検証)

2026-07-06 に「その他」の主因 2 つ (JV-Data の大書き仮名 vs 辞書小書き仮名の差、
海外祖先の英語名格納) を _normalize (NFKC+仮名+小文字+記号畳み込み) と英語名辞書で
対処した。効果は実 DB でしか測れないため以下を実行:

```
python -m scripts.audit_sire_lines
```

- gen3 列 (父母父/母母父) を含む 4 世代の dict_hit / traversal_hit / unknown 内訳が出る。
- **unknown 上位に英語名 (Mr.Prospector 系のピリオド/空白変種、Sadler's Wells 系の
  アポストロフィ、全角ローマ字) や既知種牡馬が残っていれば、その実綴りを辞書に追記**
  (綴り変種は _normalize で大半吸収されるが、想定外表記は残り得る)。
- 改修前後の unknown 率比較は HEAD~1 checkout で再実行。
- **残る「その他」の一部は正しい** (パーソロン系メジロマックイーン、In Reality 系
  ダノンレジェンド 等の 11 大系統外 = 誤答よりその他が誠実)。これらは辞書に載せない。

直接クエリで残存英語名を確認する場合 (gen3 両列):
```sql
SELECT sire_dam_sire_name, COUNT(*) FROM horse_masters
WHERE sire_dam_sire_name GLOB '*[A-Za-z]*' GROUP BY 1 ORDER BY 2 DESC LIMIT 30;
```

### 9-4. traversal_hit=0 (「その他」大量残存) の切り分けと BLOD 埋め直し runbook (2026-07-06 追加)

2026-07-06 実機 audit で `breeding_horses=6957 行 / traversal_hit=0.0% / unknown=56.5%` を観測。
父系遡上 (traversal) が全く効いておらず、「その他」大量残存の主因は辞書不足でなく **血統遡上
データ (breeding_horses=HN 繁殖馬) の欠落**。切り分けと修復の順序:

**前提 (2026-07-06 済)**: HN オフセットの -2 ずれは実 .jvd で**確定・parse_hn 修正済み**
(§9-2。sire_breeding_num=228 等)。**再 probe は不要** — 既存 breeding_horses は旧オフセットの
garbage 値を保持しているので、下記の再取込で新オフセット値に置き換えるのが要点。

1. **audit で現状を保存** (before): `python -m scripts.audit_sire_lines --top 40 > data/audit_before.txt`。
   `breeding_horses` 行数と `traversal_hit` を記録 (今回の基準は `data/audit_sire_lines/20260706_before_blod.txt`)。
2. **parse_hn 修正を取得**: 実機で `git pull` (HN -2 補正入り)。
3. **BLOD を一括取込** (option=4 セットアップ。差分でなく繁殖馬マスタ全体):
   ```
   .venv32\Scripts\python.exe -m scripts.bootstrap --dataspecs BLOD
   ```
   (全 dataspec 5-15GB を再取得せず BLOD=HN だけ埋め直す。JRA-VAN フルデータ契約が前提。
   upsert は breeding_num PK の REPLACE なので旧 garbage 行は新オフセット値へ決定的に置換される。)
4. **audit を再実行で閉ループ確認** (after): `python -m scripts.audit_sire_lines --top 40`。
   **traversal_hit が 0% から上昇し unknown が低下**したら「旧オフセット/行数不足」が主因だったと確定。
   **上がらない場合の切り分け** (HN 内部だけに戻さない):
   - (a) breeding_horses 行数が増えていない → BLOD 取得自体が失敗/HN 未取得 (probe_hn_offsets の
     インベントリで HN ファイル数を確認)。
   - (b) 行は増えたが traversal 0% → 遡上の**入口**の疑い: UM(競走馬マスタ)側の sire_breeding_num
     と HN の breeding_num(PK) の**採番系が突合しない** or UM gen3 の breeding_num フィールド位置ずれ。
     `SELECT sire_breeding_num FROM horse_masters LIMIT 5` と `SELECT breeding_num FROM breeding_horses
     LIMIT 5` の桁・体系を突合する。
5. **深祖 founder は BLOD では終端しない**: Nasrullah/Man o'War 等の古い海外始祖は JRA-VAN の
   繁殖馬マスタに個別行が無いのが通例。中間祖先まで BLOD で chain が通っても、最終停止は
   `LINE_BY_SIRE`/`FOUNDERS` の名前照合が担う。よって**辞書 (founder) 併用は恒久的に必要**
   (辞書は「深祖の終端」、BLOD は「中間 chain の充填」で役割が異なる)。
6. 上記 4 で traversal_hit が上昇し、産地の目視検証 (§9-2) も通れば
   `config.HN_BIRTHPLACE_VERIFIED=True` に反転して産地表示を有効化する。

## 10. 亀谷公式リスト突合 (国別血統タイプの確定手順) (2026-07-05 追加)

出馬表の国系統バッジ・傾向集計の父/母父国系統軸は、亀谷敬正の「国別血統」
(日本型/米国型/欧州型) を `predictor/sire_lines.py` の COUNTRY_BY_LINE (系統既定) +
COUNTRY_OVERRIDE (種牡馬個別) で近似している。**これは暫定分類**で、確定には
会員サイトの公式リストとの手動突合が必要 (JV-Link 内に独立ソースが無いため
`audit_sire_lines.py` のような DB 突合では確定できない)。

### 10-1. 突合の対象 (優先順)

コード内 docstring で「公式リスト未突合」と明記済みの枝を優先確認する:

1. **キングマンボ系の米/日 split** — キンカメ/ロードカナロア/ドゥラメンテ等。現状
   一律 usa (Mr.Prospector 基盤)。2022 改訂前は「日本型」とされた時期があり、
   改訂後の公式帰属を確認。JRA 最頻出系統のため実害大。
2. **マクフィ** (ドバウィ系=欧州?)、**チーフベアハート/タリスマニック** (北米発展?)。
3. **プリンスリーギフト枝** (テスコボーイ/サクラバクシンオー/ビッグアーサー等)。
4. **ノーザンテースト** (仏 G1 → eur 可)。
5. **ナスルーラ系の Never Bend 直系枝の米/欧 (2026-07-06)** — ミルリーフ(欧州発展)は
   `COUNTRY_OVERRIDE`=eur、その子孫ミルジョージも eur・Red God 欧州枝イエローゴッドも eur
   に補正済。一方 Never Bend 直仔ブレイヴエストローマン・Never Beat 枝アローエクスプレスは
   nasrullah 既定の usa のまま (Never Bend 自体は米国馬で、eur は Mill Reef 枝固有という
   判断)。公式突合で Never Bend 系全体の型を確認し、枝ごとの usa/eur 割りを確定する。
6. **11 大系統外の 3 系統 (2026-07-06 追加)** — personon (パーソロン系: シンボリルドルフ/
   トウカイテイオー/メジロマックイーン枝)、stsimon (セントサイモン系: Ribot/Princequillo/
   Round Table 枝)、hyperion (ハイペリオン系: Hyperion/Aureole/Swaps 枝)。現状いずれも
   `COUNTRY_BY_LINE` で **eur (欧州型) 暫定**。founder が古典的欧州スタミナ系で非 SS のため
   保守既定として eur を置いたが、亀谷公式リスト未突合。特に Princequillo/Round Table 枝は
   北米競走の実績があり型論では usa 寄りの見方もあるため要確認。

### 10-2. 突合手順

1. 亀谷氏の会員サイト (血統ビーム) / 書籍『血統ビーム 名種牡馬読本』の国別分類表を参照。
2. 上記対象種牡馬の公式タイプと `classify_country(名前, line_key)` の出力を突合。
   ```
   .venv32/Scripts/python.exe -c "from predictor.sire_lines import classify_country, classify_sire; \
     [print(n, classify_country(n, classify_sire(n))) for n in ['キングカメハメハ','ロードカナロア','マクフィ','サクラバクシンオー','ノーザンテースト']]"
   ```
3. 不一致は `COUNTRY_OVERRIDE` に種牡馬名→正しいタイプを追記
   (系統既定値と異なる個別例外のみ。既定値そのものがずれていれば COUNTRY_BY_LINE を修正)。
4. **2022 年 8 月以降の再改訂の有無**も確認 (亀谷氏は分類を定期的に見直す。
   本実装のカットオフは 2026-01)。
5. 追記後 `tests/test_sire_lines.py` の country 系テストに regression を 1 行固定。

### 10-3. 確定済み (2026-07-05 予想ロジック監査で補正)

- ND 北米発展枝 (クロフネ/フレンチデピュティ/マインドユアビスケッツ/War Front 枝) → 米国型
- ロベルト系米国残留枝 (ナダル) → 米国型
- ナスルーラ系欧州分枝 (トニービン/バゴ/ジャングルポケット/レインボウクエスト/
  タマモクロス等) → 欧州型
これらは血統事実として確度が高く override 済み。残りは 10-1 の未突合枝。
