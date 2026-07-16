# Codex 作業指示: カナリア再設計 + 警告の人間到達 + アーカイブ堅牢化 (完走型・全 5 ステージ)

前提: PR #4 (監視完全化) / PR #5 (血統辞書) は main へマージ済み (main=`ca8de7a`、342 tests green)。
本作業は正規 expert-review (`data/scorecards/20260716_0050_monitoring_and_archive.md`) の
横断課題 3 件を **1 セッションで完走** する第 3 サイクル。

起動前の推奨設定:

```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッション
codex> /model    # reasoning effort = medium
# ステージ間で /compact を実行して履歴を圧縮すること
```

---

## ここから Codex へのプロンプト本文

競馬予想パイプラインの監視アラートを「正しく鳴り、人間に届く」状態に仕上げます。
**途中で人間に確認を求めず、ステージ 1→5 を順に完走**してください。各ステージ末尾の
受入ゲートを満たせない場合は自力で診断・修正して再試行 (最大 3 回)。それでも満たせない
場合のみ、そのステージをスキップ理由つきで最終報告に記載し、依存しない残ステージを
続行すること。説明文は最小限、差分ではなく実ファイルに書く。

### 全体ルール

- **最初に `git status --short` を確認**。tracked ファイルに未コミット変更が既にあれば
  **作業を開始せず**その内容を報告して終了する (別ストリームの作業中の可能性があるため。
  これだけは走り抜け例外)。untracked のみなら続行してよい
- **`git checkout -b codex/alerting-and-hardening main` で新ブランチを切る**。push はしない
- コミットは最終ステージのみ、`git add <個別パス>` で明示指定 (git add -A / -u 禁止)
- **触ってはいけない untracked**: `data/backtest/20260703_*.json`・`predictor/_v5_backup/`・
  `docs/handoff_20260716_sireline_session.md` (add も削除もしない)
- **専門家レビュー / scorecard の作成は行わない** (正規機構は Claude Code 側のみ。運用決定済み)
- `data/keiba.db` (19GB) を直接 read しない (sqlite3 CLI は可)。**DB の中身を変更しない**
  (本改修はむしろ監視系を read-only 化する方向)
- **Discord への実送信禁止**: `data/discord_webhook.txt` は本物の secret。テストでは
  `_notify` を必ず mock し、検証で実 POST を発行しないこと
- bat / ps1 は **ASCII のみ** (PS 5.1 / cp932 の parse 事故が既知)
- テスト実行は `.venv64/Scripts/python.exe -m pytest`

### ステージ 1: monitor '00' カナリアの再設計 (レビュー 6 名一致の最優先)

対象: `scripts/monitor.py` (163-218 行付近) / `db.py` / tests

現行カナリアの 3 欠陥を同時に直す:

1-1. **偽陽性ウィンドウの解消**: 現行は `horse_num='00'` の raw count を数えるが、
   '00' は枠順確定前の**正当な過渡状態** (木金に翌週出馬表を取込むと日曜の週次監視が誤警報)。
   検査述語を **violation 定義 = 「同一レースに正規馬番行が共存する '00' 行」** に変更する。
   `scripts/cleanup_placeholder_horse_rows.py` の事前チェックと同じ定義なので、判定 SQL を
   共通化できるなら db.py か cleanup 側に関数として一元化する (述語の変種を増やさない)。
1-2. **述語の非対称解消**: '00' だけでなく `NOT (SQL_VALID_HORSE_NUM)` (NULL / 空文字含む)
   を violation 対象に含める。
1-3. **early-return の廃止**: 現行は違反検出で Brier / mining 検査より前に `return 1` し、
   違反解消まで週次の drift 監視が丸ごと停止する。警告フラグに退避して**全検査を完走**させ、
   最後に exit code を OR 合成する方式へ (`auto_predict_daily.bat` の bit 合成と同じ思想)。
1-4. **警告文に復旧導線**: violation 警告に
   `-> run: python -m scripts.cleanup_placeholder_horse_rows --dry-run` の 1 行を添える。
1-5. **テスト**: (a) 枠順確定前の単独 '00' (正規行なし) では警告しない、
   (b) 正規行と共存する '00' で警告する、(c) NULL/空文字馬番でも警告する、
   (d) violation 警告があっても Brier 検査が実行される (呼び出し順の検証)。

**受入ゲート 1**: 新テスト 4 件 + 既存テスト全 green。実 DB に対する monitor 実行で
違反 0・exit 0 (現 DB はクリーンなはず)。

### ステージ 2: 警告の人間到達 (「アラームは鳴るが誰も居ない部屋」の解消)

対象: `scripts/auto_predict.py` / `scripts/auto_predict_daily.bat` / `weekly_monitor.bat` /
`scripts/fresh_odds_coverage.py` / `scripts/register_auto_predict_task.ps1` / `scripts/monitor.py` / tests

背景: Task Scheduler 実行は stdout をリダイレクトせず破棄するため、ギャップ警告も monitor
警告も現状 **exit code しか人間に届かない**。ユーザが日常監視するチャネルは Discord
(`auto_predict.py` の `_notify`)。

2-1. **bat 出力のログファイル固定**: 両 bat の実行全体を
   `data/logs/auto_predict_daily_%DATE%.log` / `data/logs/weekly_monitor_%DATE%.log` 相当へ
   append リダイレクト (ASCII で書ける形式で。%DATE% の形式はロケール依存なので
   python 側か `%date:~0,4%...` 等で安全に)。古いログの削除は不要 (テキストで軽量)。
2-2. **ギャップ警告の Discord 連携**: `auto_predict_daily.bat` で gap 検知の exit code を
   環境変数 or 引数で `scripts.auto_predict` に渡し、`_notify` の通知文に
   「WARN: 前日オッズ取得ギャップ検知 (詳細はログ)」を併記する。auto_predict が
   スキップされる日 (開催日でない) は通知自体が無いので、gap 警告時のみの単独通知でもよい
   (実装が単純な方を選ぶ。ただし _notify の失敗で predict 本体を落とさないこと)。
2-3. **monitor 警告の Discord 連携**: `weekly_monitor.bat` の警告時 (exit 非 0) に、
   同じ webhook へ 1 行通知を送る小さな python ワンライナー or `scripts/notify_discord.py`
   (新規、_notify 相当を関数化して auto_predict.py と共用) を呼ぶ。
2-4. **gap 警告に開催日を付与**: `fresh_odds_coverage.py` の警告文を
   `WARNING: gap <YYYY-MM-DD> HH:MM->HH:MM (NNm)` 形式に (複数日窓での特定可能化)。
2-5. **監視系 DB 接続の read-only 化**: `fresh_odds_coverage.py` の `_load_open_dates` と
   `monitor.py` の violation カウントを `open_db` → `open_db_readonly` に変更
   (db.py 自身の docstring 準拠。ingest / GUI との write-lock 競合窓を排除)。
2-6. **weekly_monitor.bat の復旧手順文言を復活**: 前々版にあった Brier 警告時の具体的
   アクション (suspend → filter_sweep --recent-3fold → 必要なら train_lgbm。
   CLAUDE.md ルール 4 参照) を ASCII コメント or echo で戻す。
2-7. **register_auto_predict_task.ps1 の chain 説明更新**: 34-36 行付近の説明に
   ギャップ検知段と exit bit の意味 (1=gap / 2=predict) を追記 (ASCII のみ)。
2-8. **テスト**: gap 警告文の日付フォーマット、notify 関数の共用化 (mock で送信内容検証、
   実送信なし)、read-only 接続でも既存機能が動くこと。

**受入ゲート 2**: 実 JSONL で `--check-gaps --last 14` を実行し、既知の 07-12 ギャップが
**日付付き**で表示され、FP 増加ゼロ。テスト全 green。bat/ps1 が ASCII のみ
(`python -c "print(all(b<128 for b in open(f,'rb').read()))"` で確認)。

### ステージ 3: アーカイブ堅牢化

対象: `web/generator.py` / `scripts/auto_predict.py` / tests

3-1. **原子書込 + sha 記録**: `_archive_prediction_html` の `shutil.copy2` 直書きを
   「一時ファイルへ書き → `os.replace`」の原子コピーに変更し、コピー後に sha256 を
   source と照合。`_sync_status.json` に `repository_archive_sha256` を追加。
3-2. **例外時 fail-safe**: アーカイブ処理全体を try/except で包み、失敗時は
   `repository_archive: null` + logger.error で publish 本体を続行 (iCloud 側の
   `_sync_status.json` が旧状態のまま残って sha 照合が偽不一致を報告する現行の
   失敗モードを解消)。
3-3. **自動 commit への追加**: `scripts/auto_predict.py` の `git add` 対象 (99 行付近、
   現在 `docs/index.html` のみ) に、当日生成された
   `data/results/<date>/predictions_source_*.html` を追加。アーカイブの改ざん耐性は
   push されて初めて成立する。該当ファイルが無い日 (publish 失敗等) でも add が
   エラーで止まらないようにする。
3-4. **0-run 開催日 FN の緩和**: fetch_full が朝失敗すると当日の races 行が無く
   `_load_open_dates` が当日を開催日と認識できない (0-run 全欠落警告が沈黙する)。
   フォールバックとして「coverage JSONL の当日 eligible>0 の記録」も開催日判定に
   加える (races テーブルとの OR)。テスト 1 件。
3-5. **テスト**: 原子書込 (途中失敗で部分ファイルが残らない)、例外時 fail-safe、
   auto_predict の add 対象 (mock)、3-4 のフォールバック。

**受入ゲート 3**: テスト全 green。`_sync_status.json` スキーマの後方互換
(新フィールド追加のみ、既存フィールド不変) を diff で確認。

### ステージ 4: manifest warnings の仕上げ (小)

対象: `scripts/build_daily_results.py` / tests

4-1. warnings に `"schema": 2` を明示 (新旧 manifest の判別を「キー不在推論」から昇格)。
4-2. `post_start_unclassified_rows` を追加 (start_time 欠損 / parse 失敗で判定できなかった
   行数。「post_start=0 かつ unclassified=全行」を「鮮度完璧」と誤読させない)。
4-3. 品質ゲートの人気上限を固定 18 から「レースの starter_count」連動に
   (starter_count が取れない場合のみ 18 に fallback)。
4-4. 既存の 07-12 / 06-21 manifest は**再生成しない** (旧スキーマのまま保持、監査履歴)。
   テストで新スキーマを検証。

**受入ゲート 4**: テスト全 green。

### ステージ 5: 最終検証 + コミット

5-1. `pytest tests/ -q` 全 green (342 passed / 4 skipped + 新規分)。
5-2. 実データ確認 3 点を最終報告用に採取: (a) `--check-gaps --last 14` の日付付き出力、
   (b) `python -m scripts.monitor --days 30` の exit code と警告有無、
   (c) bat 2 本 + ps1 1 本の ASCII 確認結果。
5-3. **コミット (1 回)**: 変更した py / bat / ps1 / tests /
   `docs/codex_fix_20260716_alerting_and_hardening.md` を明示 add。
   メッセージは英語 1 行 + 本文数行。
5-4. `git status --porcelain --untracked-files=no` が空、指定外 untracked 3 件が不変、
   push していないことを確認。

**受入ゲート 5**: 1 コミット存在、テスト全 green、DB 不変 (sqlite3 で '00' count=0 のまま)。

### 最終報告 (15 行以内)

1. ステージごとの完了/スキップ (スキップ時は理由)
2. カナリア新述語のテスト結果 (単独 '00' 非警告 / 共存 '00' 警告 / Brier 非マスク)
3. 実データ採取 3 点 (5-2)
4. Discord 連携の実装方式 (どこから何を通知するか 1-2 行。実送信はしていないこと)
5. コミット sha
6. push していないこと・指定外 untracked 不変の確認

---

## (Claude Code 側メモ — Codex には渡さない)

- Codex 完了後、**正規 expert-review (D1) を実行** — 重点: ①カナリア新述語が
  cleanup 側と単一出典になっているか、②Discord 連携の失敗が predict/monitor 本体を
  落とさないか (通知は best-effort であるべき)、③bat のログリダイレクトが errorlevel
  伝播を壊していないか
- レビュー PASS 後に PR 作成 (branch `codex/alerting-and-hardening`)
- **次の開催日 (7/18-19) 後の運用確認**とセットで検収するのが理想:
  ①ギャップ検知の実運用 FP、②新 manifest スキーマ (schema:2) の日次生成、
  ③publish 自動アーカイブ + 自動 commit、④Discord 通知の実着弾 (本改修後の初開催日)
- 残課題 (今回もスコープ外): テンプレート data-odds 属性化 (type-D、web 改修同乗、3 サイクル
  繰越) / 累計 P/L 台帳 (F3 設計相談が先) / 古い worktree 3 件の掃除
