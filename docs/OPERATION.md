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

## 8. 目標 (2026-05-16 設定)

**年間 110%, 月次変動は許容** (P14 採用と同時に設定)

- 年間 +10% = 月平均 +0.8% (= 100 円ベースで月 8 円利益 / 100 円賭金)
- 月次は -20% 〜 +50% の variance を許容
- 連続 3 ヶ月 -10% 未満 → 自動サスペンド + 戦略再選定
