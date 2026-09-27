# keiba-yosou に依存している外部プロジェクト (2026-09-27)

keiba-yosou のコードや本番データを、このリポジトリの外から **直接** 使っているものの一覧と、
変更するときに守る契約。CLAUDE.md 必須ルール 5 の正本。

背景と既知の欠陥は `docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md` (2026-09-26 監査)。

## ai-builder (`C:\Users\kizun\dev\ai-builder`)

**依存の向き: ai-builder → keiba-yosou。** keiba-yosou は ai-builder を import しない。
ai-builder は keiba-yosou を兄弟ディレクトリとして `sys.path` に入れ、**main checkout のコードを
そのまま** import する (ブランチやバージョンの固定は無い)。keiba-yosou の main で起きた変更は、
次の実行から ai-builder に効く。

### 1. ライブ取り込み (本番 DB と raw に **書く**)

| 項目 | 内容 |
|---|---|
| 実体 | `ai-builder/deploy/windows/fetch-live-jvdata.py` (`fetch-live-jvdata.cmd` → `run-live-jvdata-hidden.vbs`) |
| タスク | `MAIBuilder Live JRA Data` (開催時間帯に 1 分ごと、上限 4 分)。有効・無効は `MAIBuilder Live JRA Data Controller` (6 時間ごと、`configure-live-jvdata-task.py` / `Configure-LiveJvdataTask.ps1`) が開催日に合わせて切り替える |
| Python | keiba-yosou の `.venv32\Scripts\python.exe` (32bit、JV-Link COM) |
| import | `db.open_db`、`jvlink_client.JVLinkClient`、`jvlink_client.ingest._split_records` / `ingest_all`、`jvlink_client.parser.parse_av` / `parse_cc` / `parse_jc` / `parse_tc` / `parse_we`。Controller は `db.open_db` |
| JV-Link | `JVRTOpen` の 0B11 (馬体重)・0B12 (速報成績)・0B14 (取消・騎手・発走時刻・コース・天候)・0B30 (全賭式オッズ) |
| 書く先 | 本番の `data/keiba.db` (horse_races・races の現在値の UPDATE、0B14 の各テーブルの INSERT / DELETE、`ingest_all` 経由の払戻・オッズ)、`data/raw/0B11` `0B12` `0B14` `0B30` |
| ロック | `ai-builder/out/cache/fetch-live-jvdata.lock` (20 分で奪取)。keiba-yosou 側の取得とは排他していない |

**keiba-yosou の予想への実際の影響**: T−10 の市場 (`predictor.pit_t10.t10_market`) は取得元を
区別せずに最新の枚を選ぶので、8〜9 月は選ばれた馬の約 81% が ai-builder の 0B30 だった
(監査文書 3-bis)。ai-builder を止めると、keiba-yosou の T−10 の市場の鮮度が落ちる。

### 2. ai-builder 本体 (読み取りのみ)

| 項目 | 内容 |
|---|---|
| 実体 | `ai-builder/builder/keiba_bridge.py`・`evaluate.py`・`matrix.py`・`matrix_daily.py` など |
| import | `db.open_db_readonly`、`predictor.rules.predict_race` / `is_tentative`、`predictor.features.compute_features` / `horse_past_runs`、`predictor.sire_lines`、`scripts.backtest.list_races` / `horses_for_race` / `get_payout_row` / `payout_from_row` / `popularity_config` / `race_odds_untrusted`、`web.codes.track_type` / `track_name` |
| DB | 本番の `data/keiba.db` を読み取り専用で開く |

## 変更するときの契約 (互換確認が必須になる変更)

次のどれかを変える変更は、**ai-builder への影響を確認してから** main に入れる。

- `db.py` (特に `open_db` / `open_db_readonly`、`update_*` / `upsert_*` / `insert_odds_snapshot` の引数と意味)
- `jvlink_client/**` (`JVLinkClient` の初期化・終了・`fetch_realtime` の戻り値、`ingest_all`、parser の関数名と戻り値)
- DB の schema / migration (テーブル・列・主キー。特に `odds_snapshots` の主キーと列)
- raw の保存形式 (ディレクトリ・ファイル名 `<spec>_<key>_<epoch>.jvd`・レコード区切り)
- JV-Link の初期化・終了の手順、`.venv32` の中身 (pywin32 など)
- 上の表 2 に挙げた読み取り側の関数 (`predictor.rules` / `predictor.features` / `scripts.backtest` / `web.codes` の名前と戻り値)

**記録の必須化**: 該当する変更のコミットメッセージかレビュー記録 (scorecard) に、次のどれかを書く。

    ai_builder_impact: none | tested | requires_followup

- `none`: 上の一覧に当たらないことを確認した (理由を 1 行)
- `tested`: 当たるので確認した (何をどう確かめたか)
- `requires_followup`: 当たるが、ai-builder 側の対応が要る (その内容。ai-builder のコードは keiba-yosou 側からは変更しない)

### 確認のしかた

ai-builder のコードとタスクには触れずに、次を確かめる。

1. **ライブ取り込みが起動できる**: 変更後の main で `fetch-live-jvdata.py` の import が通る
   (`.venv32\Scripts\python.exe -c "import sys; sys.path.insert(0, r'C:\Users\kizun\dev\keiba-yosou'); from db import open_db; from jvlink_client import JVLinkClient; from jvlink_client.ingest import _split_records, ingest_all; from jvlink_client.parser import parse_av, parse_cc, parse_jc, parse_tc, parse_we"`)。
   読み取り側も同様に `predictor.rules` などの import が通る
2. **raw が作られる**: 開催日に `data/raw/0B14` `0B30` に新しいファイルが増える
3. **DB への取り込みが成功する**: 同じ時間帯の `odds_snapshots` に `source='0B30'` の行が増える
4. **keiba-yosou 側の取得と競合しない**: keiba-yosou の fresh odds (0B31) と自動予想のログにエラーが出ない

## 現在の決定 (2026-09-27 ユーザー決定、CHAT 推奨どおり)

- **短期**: 今の共有構成を維持する。この文書と CLAUDE.md 必須ルール 5 で、暗黙の依存を明示の契約にする
- **中期**: JV-Link からのライブ取り込みの責任を 1 か所にまとめる
- **長期**: ai-builder が keiba-yosou の main checkout を直接 import する構成をやめる
  (例: 取り込みのサービスが raw / snapshot を 1 回だけ取って保存し、keiba-yosou と ai-builder はそれを読む)
- 9/28 の JST 検証の前には構成を変えない。分離の設計は JST を閉じた後に行う

## 既知のリスク (監査文書への参照)

| リスク | 参照 |
|---|---|
| 現在値の上書きで予想の時点の値が再現しにくい (PIT) | 監査文書 2 |
| 0B14 の空の応答で、変更の記録を削除し現在値を元に戻す | 監査文書 4 |
| `odds_snapshots` の主キーに source が無く、同じ秒の観測が片方消える | 監査文書 3-bis |
| 7 月前半の 0B31 が DB に無い (raw から復元可能) | 監査文書 3-ter |
| `backfill_announced_at.py` が同じ秒の発表時刻を別の取得元の値で上書きする | 監査文書 3-quater |
| JV-Link の呼び出しで止まったプロセスが残る (4 分の上限は wscript しか止めない)。再開すると古い対象日で 0B14 の照合が走り、その日の記録を削除しうる | 監査文書 5-bis、2026-09-26 に 90 個を停止 (`data/logs/ai_builder_stale_processes_20260926_*`) |
| 開催日の日中に、keiba-yosou と ai-builder が同じ JV-Link と DB を並行して使う (concurrent writer) | 監査文書 5 |
