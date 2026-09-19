# データパイプライン技術者 採点 — b437db3 通知の重複抑止 (notify_dedup)

## 判定: HOLD

**理由**: 停止条件抵触なし。通知を **消す** 経路は実測で 1 つも見つからず (E3/E6/E8 すべて「次回再送」に倒れる)、設計の非対称性は正しい。HOLD の対象は (a) `record()` の失敗が **bare `pass` で完全に無音** — Windows では他プロセスが状態ファイルを開いているだけで `os.replace` が `PermissionError` になり (E3 で再現)、抑止が黙って死ぬ経路が実在する、(b) 本番未稼働 — 状態ファイルは存在せず、本日 08:00/09:00/11:00 の 3 run はすべて改修前コードで「3 通送信」(`data/logs/auto_predict_daily_20260919.log:36,73,110`)。次の開催日 1 日ぶんの実績で再評価できる。
**根拠ファイル**: `scripts/notify_dedup.py:119-132,186-208`、`scripts/auto_predict.py:116-143,199,319`、`scripts/register_auto_predict_task.ps1:8-14,49-52`、実測は本 scorecard「反証の試み」
**次アクション**: `record()` の except に WARN 出力を入れる (1 行)。`_save` の `os.replace` を Windows 向けに短いリトライ (3 回 / 50 ms) にする。開催日 1 日の log で `notify suppressed` 2 行 + 送信 1 通を確認してから PASS。

## 対象・改修タイプ

- 対象コミット: `b437db3` (`scripts/notify_dedup.py` 新規、`scripts/auto_predict.py`、`tests/`、`docs/OPERATION.md`)
- 改修タイプ: **type-C 相当 (運用層: 通知状態の永続化。取得 / ingest / 予測は不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**。fresh odds を総合判定のゲートにはしない。
- 採点軸は本改修に合わせ「状態ファイルのクラッシュ一貫性 / 競合 / 消失経路 / 観測可能性 / 日付境界・復旧」の 5 つに置き換えた。
- スコープ外: 通知文面の UX、Discord webhook の運用。予測側不変の主張 (sha256 一致) は commit message の自己申告で、本 agent は再実行していない (未検証)。

## 総合: 3.6 / 5 (参考スコア)

## 項目別

- **状態ファイルのクラッシュ一貫性: 4/5** — `tempfile.mkstemp` + `os.replace` (`notify_dedup.py:122-126`)。ディスクフル中断で旧内容が無傷 (E6)、不正 JSON は空扱いで fail-open (E7 の前段、`test_8`)。留保 3 点: (1) `mkstemp` と `replace` の間で落ちると `data/runtime/tmpXXXX.tmp` が残り、掃除する経路がリポ内に無い (E4 で残留を確認、`grep .tmp` 該当なし)。(2) `replace` 前に `fsync` 無し — 電源断で内容が化けうるが `_load` が空に倒すので実害は「重複 1 通」。(3) **有効な JSON だが値が dict でない** 状態 (手編集等) は `_prune` の `v.get` で `AttributeError` → decide は毎回 fail_open、record も毎回失敗し **自己修復しない** (E7: 2 回連続 `fail_open:AttributeError`、ファイル不変)。`test_8` は不正 JSON しか見ていない。
- **同時起動時の冪等性 / 競合: 3/5** — ロック無し。4 プロセス同時起動で **4 通全部 first_time** (E1、3 試行とも 4/4)、別キーの同時 record で **4 キー中 1 キーしか残らない** lost update (E2、3 試行とも)。ただし到達性を実測: 登録タスク `keiba-auto-predict` は `MultipleInstances=IgnoreNew`、トリガ 08:00/09:00/11:00、各 run 65-75 秒 (`auto_predict_daily_20260919.log:33-37,70-74,107-111`)、watchdog 1200 秒 → **スケジューラ経由では重なり得ない**。手動 CLI 起動とスケジューラ run の重複のみが経路で、結果は重複通知 (消失ではない)。許容範囲だが「ロック不要」の根拠がコードにもドキュメントにも書かれていない。
- **通知消失経路の閉鎖: 4/5** — 判定 (`decide`) と記録 (`record`) の分離、成功時のみ記録 (`auto_predict.py:135-137`)。`urlopen` は 4xx/5xx で `HTTPError` を投げ `notify_discord` が False を返す (`notify_discord.py:31-39`) ので Discord 429 も再送側。E3 (replace 失敗)・E6 (ディスクフル)・E8 (非 JSON 化 payload) のいずれも「記録されず次回再送」で **消失経路ゼロ**。留保: fail-open が正しく効くほど、逆に「抑止が死んでいること」に気付けない (次項)。
- **観測可能性: 3/5** — 抑止は `notify suppressed (...)` を stdout に出し、bat が `data/logs/auto_predict_daily_%RUNDATE%.log` に追記するので **後追い可能** (`auto_predict_daily.bat:8`)。OPERATION.md にも確認手順あり。欠陥 3 点: (1) **`record()` 失敗は bare `pass` で無音** (`notify_dedup.py:207-208`)。E3 で示した通り Windows では AV / バックアップ / エディタが JSON を開いている瞬間に `os.replace` が `PermissionError` になる。その日は 3 通届き、なぜ抑止が効かなかったかログに痕跡が無い。(2) **`_save` の `json.dump` に `default=str` が無い** のに `_canonical` にはある (`:103-104` vs `:125`) → 非 JSON 化 payload (Path 等) は判定が通り記録だけ毎回失敗 = 抑止が永久に無音で死ぬ (E8: 2 回連続 first_time、ファイル未作成)。現行 4 呼び出しの payload は int/str/bool/float/list[str] で安全だが、次に payload を足す人を守る仕組みがテストにしか無い。(3) 抑止時も `print("notified. push_ok=", ...)` が出る (`auto_predict.py:319`) — log の最終行だけ見ると送ったように読める。
- **日付境界 / 保持 / 復旧・バックアップ整合: 4/5** — `_prune` の `YYYYMMDD` 辞書順比較は 0 埋め固定長なので年跨ぎで正しい (E5: today=20260105 → cutoff 20251222、20251220 のみ削除)。JST は固定オフセット、DST 無し。状態消失 = 重複 1 通のみで、`data/runtime/*` を gitignore / バックアップ対象外にするのは **正しい**。OPERATION.md 手順 4「消しても予測に影響しない」と整合。留保: (1) **キーの対象日 `day` は `date.today()` (システムローカル) 由来** (`auto_predict.py:199`) で、モジュール docstring「日付は Asia/Tokyo で決める」は retention の `date_jst` にしか当たっていない。マシンが JST なので実害なしだが doc と code の不一致。(2) 6.5 バックアップ runbook に「`data/runtime/notification_state.json` は復旧対象外 (意図的)」の一文が無い。

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides: N/A (backtest artifact を生成しない改修)
- [x] baseline paired 比較: N/A
- [x] market_snapshot counts / payout 欠損: N/A
- [x] P25 fresh odds スケジューラ / coverage JSONL / bonus_candidate: N/A (type-C 運用層。取得・ingest 不変)
- [x] 専門領域 (本改修向け): 通知消失経路 → 実測ゼロ。partial write が残る経路 → なし (E6)。lock クリーンアップ → lock 自体が無い (競合は重複方向のみ)。**すべて不抵触**
- [x] テスト: `tests/test_notify_dedup.py` 23 passed、`-k "auto_predict or notify or scheduled"` 59 passed (自分で再実行)

## 反証の試み (すべて `.venv64` で実行、scratchpad 上の隔離ファイル)

| # | 反証シナリオ | 結果 |
|---|---|---|
| E1 | 同一キーを 4 プロセス同時に decide→record | **4/4 が first_time で送信** (3 試行とも)。ロック無しは事実。到達性はスケジューラでは無い (IgnoreNew + 1h 間隔 + 75 秒 run) |
| E2 | 別キーを 4 プロセス同時 record | **残存 1/4 キー** (lost update)。方向は「次回再送」 |
| E3 | 他プロセスが状態ファイルを read open 中に `_save` | **`PermissionError [WinError 5]`**。旧内容は無傷、tmp は削除された。`record` はこれを無音で握る |
| E4 | `mkstemp` 後 `replace` 前に `os._exit(9)` | `tmpxr90_q3w.tmp` が **残留**。掃除経路なし |
| E5 | today=20260105 で prune | cutoff 20251222、`20251220` のみ削除、`date_jst` 欠落は保持。**年跨ぎ正常** |
| E6 | `json.dump` 途中で ENOSPC | 旧内容一致 True、tmp 残留なし。**partial row なし** |
| E7 | 有効 JSON だが値が文字列 | 2 回連続 `fail_open:AttributeError`、ファイル不変 = **自己修復せず永久 fail-open** |
| E8 | payload に `Path` | `_canonical` は通るが `_save` が失敗 → 2 回連続 `first_time`、**ファイル未作成、ログ痕跡なし** |

- 改修の主張「送信失敗は記録せず再送する」→ **成立** (test_a_failed_send / E3 / E6 / E8 すべて再送側)
- 改修の主張「原子的に置換」→ **成立** (E6)。ただし Windows の `os.replace` は「排他オープン中の宛先には失敗する」原子性で、成功時のみ原子的
- 改修の主張「日付は JST 固定」→ **部分的にのみ成立** (`day` は `date.today()`)
- 改修の主張「同日 3 通 → 1 通」→ **本番未実証** (状態ファイル未作成、当日 3 run は改修前)

## 主な改善提案 (優先順)

1. **`record()` の失敗を無音にしない** — `notify_dedup.py:207-208` の `except Exception: pass` を `print(f"WARN: 通知状態の記録に失敗 ({type(exc).__name__}: {exc})。次回は重複して届きます", file=sys.stderr)` に。E3/E8 の両方がこれで log に残る。併せて `_save` の `json.dump` に `default=str` を付けて `_canonical` と揃える (`:125`)。
2. **`os.replace` の Windows リトライ** — `notify_dedup.py:126` を「`PermissionError` なら 50 ms 待って最大 3 回」に。AV/同期ツールの一瞬のハンドルで抑止が死ぬ確率を実質ゼロにする。合わせて `_save` 冒頭で `path.parent.glob("tmp*.tmp")` の古い残骸 (mtime > 1 日) を削除すれば E4 も閉じる。
3. **`day` を `jst_today()` 由来に統一するか docstring を直す** — `auto_predict.py:199` の `date.today()` を `datetime.now(JST).date()` に、または `notify_dedup.py:32-33` の「JST で決める」を「retention の基準日のみ JST」に書き換える。OPERATION.md 6.5 に「`data/runtime/notification_state.json` は復旧対象外 (消えても重複 1 通)」を 1 行追加。

## 前回からの差分

- 直近の本 agent scorecard は `20260919_1100_phase05_4b_foundation` (**3.4 / HOLD**、対象は特徴量基盤で軸が異なる)。同一サブシステム (auto_predict 運用) の前回は `20260808_0940_auto_predict_watchdog` (**4.0 / PASS**)。
- 4.0 → 3.6 (-0.4) は劣化ではなく **採点対象の追加**: watchdog 時点で存在しなかった状態ファイル層を新設し、その競合 (3/5) と観測可能性 (3/5) が新たな低点項目。既存の watchdog / ingest 経路は不変。
- 前回判定 PASS → 今回 HOLD の理由: 本番 1 日も回っていない新設の永続状態 + 無音失敗経路 (E3/E8)。次の開催日の log 1 本で解除可能。
