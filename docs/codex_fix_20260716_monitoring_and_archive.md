# Codex 作業指示: 監視完全化 + '00' 完全封鎖 + 予想 HTML 恒久蓄積 (完走型・全 5 ステージ)

前提: PR #3 (merge `1094160`) で日次答え合わせ基盤は main へマージ済み。本作業は正規
expert-review (`data/scorecards/20260715_2352_daily_results_provenance_cleanup_2.md`) の
横断課題 3 件 + 繰越の小リファクタ + HTML 恒久蓄積を **1 セッションで完走** するもの。

起動前の推奨設定:

```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッション
codex> /model    # reasoning effort = medium
# ステージ間で /compact を実行して履歴を圧縮すること
```

---

## ここから Codex へのプロンプト本文

競馬予想パイプラインの監視とデータ保全を完成させます。**途中で人間に確認を求めず、
ステージ 1→5 を順に完走**してください。各ステージ末尾の受入ゲートを満たせない場合は
自力で診断・修正して再試行 (最大 3 回)。それでも満たせない場合のみ、そのステージを
スキップ理由つきで最終報告に記載し、依存しない残ステージを続行すること。
説明文は最小限、差分ではなく実ファイルに書く。

### 全体ルール

- **最初に `git checkout -b codex/monitoring-and-archive main` で新ブランチを切る**。
  push はしない (PR は人間側で作成)
- コミットは指定ステージでのみ、**`git add <個別パス>` で明示指定** (git add -A / -u 禁止)
- **触ってはいけない untracked**: `data/backtest/20260703_*.json`・
  `data/scorecards/20260706_1137_*.md`・`predictor/_v5_backup/` (別タスク残骸。add も削除もしない)
- **専門家レビュー / scorecard の作成は行わない** — 正規の expert-review 機構は
  Claude Code 側にしかなく、Codex 産 scorecard は無効と運用決定済み (過去 2 回発生)。
  完了後のレビューは人間側で実施する
- `data/keiba.db` (19GB) を直接 read しない。確認は `sqlite3` CLI のみ
- HTML (370KB 級) を全文 read しない。grep / python ワンライナーで抽出
- テスト実行は `.venv64/Scripts/python.exe -m pytest`。DB を変更する改修は無い
  (今回 DB の中身には触らない — 前回の 406 行掃除で完了済み)

### ステージ 1: horse_num='00' の完全封鎖 (復活経路の遮断 + 防御層)

対象: `db.py` / `web/generator.py` / `scripts/monitor.py` / tests

背景: 前回 ingest に「確定後 DELETE」を実装し既存 406 行を掃除済みだが、レビューで
残存経路が特定された — 古い枠順確定前 SE ファイルを単独再取込すると '00' 行が復活し、
次の正規 SE 到着まで残る。また `web/generator.py` の馬行取得だけが無述語で、
復活時に幻の '00' 馬が本番 HTML に出る唯一の経路。

1-1. **upsert 拒否ガード**: `db.py` の `upsert_horse_race` (210 行付近) 冒頭に
   「挿入しようとする行が horse_num='00' で、かつ同一レースに horse_num != '00' の
   行が既に存在する場合は upsert をスキップ」を追加 (EXISTS 1 クエリ)。
   既存の確定後 DELETE (233-245 行付近) と対で復活経路が消える。
1-2. **generator への述語適用**: `web/generator.py:191` 付近の
   `SELECT * FROM horse_races` に `AND {db.SQL_VALID_HORSE_NUM}` を追加。
   同ファイル 242-247 行付近の Python 側 `not in ("", "00")` 除外は多層防御として残す。
1-3. **monitor へのカナリア昇格**: `scripts/monitor.py` に
   「`SELECT COUNT(*) FROM horse_races WHERE horse_num='00'` が非ゼロなら警告 + exit 1」
   のチェックを追加 (既存の警告出力の流儀に合わせる)。pytest 実行時だけでなく
   週次監視で invariant の破れを検知できるようにする。
1-4. **テスト**: (a) '00' → 正規行の順で upsert して '00' が消える (既存テストの維持確認)、
   (b) **正規行 → '00' の逆順**で upsert して '00' が挿入されないこと (新規、復活経路の回帰)、
   (c) monitor のカナリアが '00' 検出時に警告すること (合成 DB)。

**受入ゲート 1**: 新旧テスト全 pass。逆順リプレイのシナリオテストが green。

### ステージ 2: ギャップ検知の完全化 + 定期監視への配線

対象: `scripts/fresh_odds_coverage.py` / `weekly_monitor.bat` / `scripts/auto_predict_daily.bat` / tests

背景: `--check-gaps` は隣接 run のペア間隔しか見ないため、**フェッチャ終日死亡・
「9:05 に 1 回だけで停止」等の片端欠落が警告ゼロで素通り**する (レビューで特定した
false negative 穴)。また検知器はどの bat からも呼ばれておらず、2026-07-12 型の
2h10m 空白は今も当日中に気づけない。

2-1. **窓端仮想区間**: `_find_run_gaps` (75-98 行付近) で、開催日の run 時刻列の前後に
   監視窓の開始 (9:00) / 終了 (16:40) を仮想点として挿入して間隔判定する。
   run が 0 件の開催日は「全欠落」warning を出す。
   ※ 「開催日」判定は既存 JSONL の eligible 情報 or races テーブルの流儀に合わせる。
   非開催日に false positive を出さないこと (現状 FP ゼロを維持)。
2-2. **配線**: `weekly_monitor.bat` に `fresh_odds_coverage --last 7 --check-gaps` を追加し、
   exit 1 を既存の警告経路 (bat の errorlevel 処理の流儀) に接続。
   `scripts/auto_predict_daily.bat` にも当日分 (`--last 1 --check-gaps`) を追加して
   開催日当日に検知できるようにする。bat は cp932 の罠があるため **ASCII のみ** で記述
   (過去に PS 5.1/cp932 で非 ASCII が parse エラーを起こした事故あり)。
2-3. **テスト**: 合成 JSONL で (a) 中間ギャップ (既存)、(b) 朝一欠落 (窓開始→初回 run が
   15 分超)、(c) 尻切れ (最終 run→窓終了が 15 分超)、(d) 0 run 開催日の全欠落、
   (e) 非開催日は警告なし — の 5 ケース。
2-4. **実データ答え合わせ**: 2026-07-12 で従来どおり `gap 11:50->14:00 (130m)` が出る
   こと、直近 14 日一括で新たな false positive が出ないことを実行確認して報告に記載。

**受入ゲート 2**: 5 ケーステスト pass + 実データで既知ギャップ検知 + FP 増加ゼロ。

### ステージ 3: warnings 意味論補強 + 繰越小リファクタ

対象: `scripts/build_daily_results.py` / `db.py` / `scripts/cleanup_placeholder_horse_rows.py` / tests

3-1. **manifest warnings に 2 項目追加** (`build_daily_results.py` の manifest 構築部):
   - `post_start_stamped_rows`: `odds_fetched_at` が当該レースの発走時刻より後の行数
     (発走時刻が取れない場合はレース単位で最終レース発走後を代用してよい。実装方式を
     コメントで明記)。2026-06-21 の「null=0 = 鮮度完璧」誤読 (実際は全行発走後刻印の
     旧 era 遺産) を機械可視化する
   - `morning_popularity_populated_rows`: 非空 morning_popularity の行数
     (07-12 の 301/470 空を「破損」と誤読させない)
3-2. **dirty 判定の精緻化**: `git_provenance()` の `--untracked-files=no` を
   「`data/results/` 配下以外の untracked も dirty と見なす」判定に変更
   (`git status --porcelain -- . ':!data/results'` 相当)。未追跡モジュール混入の検知漏れを閉じる。
   ※ ただし上記「触ってはいけない untracked」3 件が存在する現状でも再生成が dirty=true に
   なるのは**仕様として正しい** (それらが残る限り provenance は汚れているのが事実)。
3-3. **述語の一元化を完遂**: `cleanup_placeholder_horse_rows.py:44-47` の inline 述語を
   `db.SQL_VALID_HORSE_NUM` 参照に置換。`db.py` に Python 版 `is_valid_horse_num(s) -> bool`
   を追加し、`web/generator.py` の Python 側除外をそれに置換。
3-4. **builder テストの正攻法化**: `tests/test_build_daily_results.py` の `_run_main` から
   `sqlite3.connect` の monkeypatch を除去し、tmp_path 上の実ファイル DB を `--db` で渡す
   (cleanup テストと同方式)。`race_num_of` を `main()` 内クロージャからモジュールレベル
   関数へ昇格し直接単体テスト可能にする。
3-5. **再生成はしない**: 今回 warnings のスキーマが変わるが、既存の 07-12 / 06-21 manifest は
   そのまま残す (旧スキーマ)。次回の日次生成から新スキーマが乗る。テストで新項目を検証。

**受入ゲート 3**: 全テスト green (monkeypatch 除去後も)。grep で
`horse_num != '00'` / `not in ("", "00")` の inline 変種が db.py 定義以外に残っていないこと。

### ステージ 4: 予想 HTML の恒久蓄積 (アーカイブ機構)

対象: `web/generator.py` / tests / 既存 iCloud snapshots の一括退避

背景: 過去の予想 HTML は iCloud `競馬予想/snapshots/` にしか残らず、
`_prune_old_files(snapshot_dir, "index_*.html")` + `SYNC_DIAGNOSTIC_RETENTION = 20` により
**20 件を超えると古い順に自動削除される** (答え合わせ用アーカイブとして当てにできない。
2026-05 月分は既に消失済み)。5 月以降の予想蓄積を恒久化する。

4-1. **publish 時の自動アーカイブ**: `web/generator.py` の `publish_to_icloud` (617 行付近、
   snapshot 保存処理 619-623 行付近の直後) に、同じ HTML を
   `data/results/<YYYY-MM-DD>/predictions_source_<yyyymmdd>_<HHMMSS>_git<short-sha>.html`
   として保存する処理を追加 (`<YYYY-MM-DD>` は**対象開催日** = render された予想の日付。
   HTML footer の日付 or render 呼び出しのパラメータから取得し、取得できない場合は
   publish 当日を使い warning を出す)。git sha は `git_provenance` 相当の short sha。
   同一ファイル名が既に存在する場合は上書きしない (時刻が異なれば別名になるので通常衝突しない)。
   iCloud snapshots の prune (retention 20) は**診断用としてそのまま維持**。
4-2. **既存 snapshots の一括退避**: iCloud `%USERPROFILE%\iCloudDrive\競馬予想\snapshots\`
   の `index_*.html` (現在約 17 件、2026-06-07〜07-12) を、ファイル名の日付から対象日を
   判別して `data/results/<YYYY-MM-DD>/archive/` へコピーする一回性スクリプト
   (`scripts/archive_icloud_snapshots.py`、`--dry-run` デフォルト) を作成して実行。
   iCloud 側は削除しない (コピーのみ)。同一 sha256 のファイルが既にあればスキップ。
   ※ 各 snapshot は「その時点で公開されていた HTML」であり日付フォルダの
   `predictions_source_*.html` と重複しうる — sha256 一致ならスキップでよい。
4-3. **テスト**: publish アーカイブは iCloud 側パスを tmp_path に差し替えて検証
   (既存テストの流儀を踏襲)。退避スクリプトは合成ファイルで dry-run / execute / 重複スキップ。

**受入ゲート 4**: 退避実行後、`data/results/*/archive/` (または該当日フォルダ) に
snapshot 由来の HTML が日付別に存在し、iCloud 側は不変。テスト green。

### ステージ 5: 最終検証 + コミット

5-1. `pytest tests/ -q` 全 green (前回 328 passed / 4 skipped + 今回の新規分)。
5-2. `python -m scripts.fresh_odds_coverage --last 14 --check-gaps` の出力を最終報告用に採取。
5-3. **コミット** (ステージ単位で 2 つに分割):
   - commit A (コード): db.py / web/generator.py / scripts/monitor.py /
     scripts/fresh_odds_coverage.py / scripts/build_daily_results.py /
     scripts/cleanup_placeholder_horse_rows.py / scripts/archive_icloud_snapshots.py /
     weekly_monitor.bat / scripts/auto_predict_daily.bat / tests/ の変更分 /
     docs/codex_fix_20260716_monitoring_and_archive.md
   - commit B (データ): `data/results/*/archive/` の退避 HTML
   メッセージは簡潔な英語 1 行 + 本文数行 (リポジトリの既存流儀)。
5-4. `git status --porcelain --untracked-files=no` に残変更が無いこと、
   指定外 untracked 3 件が不変であることを確認。

**受入ゲート 5**: 2 コミット存在、テスト全 green、push していない。

### 最終報告 (15 行以内)

1. ステージごとの完了/スキップ (スキップ時は理由)
2. 逆順リプレイテストの結果 ('00' 復活が防がれること)
3. ギャップ検知: 07-12 の検知出力 + 新規 5 ケースの結果 + FP 増加の有無
4. 退避した snapshot 件数と配置先の一覧 (日付別件数)
5. コミット 2 件の sha
6. push していないこと・指定外 untracked 3 件が不変であることの確認

---

## (Claude Code 側メモ — Codex には渡さない)

- Codex 完了後、**正規 expert-review (D1) を実行** — 重点: ステージ 1 の upsert ガードが
  取得層の正常経路 (枠順確定前の初回取込) を壊していないか、ステージ 4 のアーカイブが
  publish 失敗時に部分状態を残さないか
- ステージ 2 の bat 変更は cp932/ASCII 制約の検証を python-embedded-js とは別に目視確認
- 次の開催日after: ①ギャップ検知が実運用で発火しないこと (FP)、②新規日次生成の manifest に
  新 warnings スキーマが乗ること、③publish アーカイブが自動保存されることを確認
- 残課題 (今回もスコープ外): テンプレート data-odds 属性化 (type-D、web 改修同乗) /
  累計 P/L 台帳 (F3 設計相談が先) / 品質ゲート上限の starter_count 連動
