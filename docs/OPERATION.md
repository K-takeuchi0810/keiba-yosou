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

### 9-2. バイト位置の実機検証 (暫定確定 → 確定に昇格させる手順)

UM idx8/idx12 と HN 205-229 は「検証済みアンカーからの導出 + 構造体知識」による
**暫定確定** (詳細は jvlink_client/parser.py の docstring)。以下を 1 回実行して
確定に昇格させる。**gen3 の順列取り違えと HN 数字フィールドの入替は無音で誤る**
ため、この確認を省略しないこと。

1. **UM gen3 の血統表突合** (順列ミスはこれでしか検出できない):
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
