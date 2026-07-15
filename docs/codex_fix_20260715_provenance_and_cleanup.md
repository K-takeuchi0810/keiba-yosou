# Codex 作業指示: daily_results 証跡完全化 + '00' 行根絶 (完走型・全 4 ステージ)

前提: 2026-07-12 監査→3 バグ修正は完了し、正規 expert-review で 6 PASS / 1 HOLD。
本作業は HOLD 解除条件 + レビュー横断課題を **1 セッションで最後まで** 実施するもの。
根拠 scorecard: `data/scorecards/20260715_0843_daily_results_integrity_2.md`

起動前の推奨設定:

```
cd C:\Users\kizun\dev\keiba-yosou
codex            # 新規セッション
codex> /model    # reasoning effort = medium
# ステージ間で /compact を実行して履歴を圧縮すること (4 ステージあるので必須)
```

---

## ここから Codex へのプロンプト本文

競馬予想パイプラインの答え合わせ基盤を完成させます。**途中で人間に確認を求めず、
ステージ 1→4 を順に完走**してください。各ステージ末尾の受入ゲートを満たせない場合は
自力で診断・修正して再試行 (最大 3 回)。それでも満たせない場合のみ、そのステージを
スキップ理由つきで最終報告に記載し、依存しない残ステージを続行すること。
説明文は最小限、差分ではなく実ファイルに書く。

### 全体ルール

- ブランチ: 現在の `claude/feature-bias-validation-yl5key` のまま作業。**push はしない**
- コミットは指定ステージでのみ、**`git add <個別パス>` で明示指定** (git add -A / -u 禁止)
- **触ってはいけない未コミット物**: `scripts/monitor.py` の既存変更・
  `tests/test_monitor_mining_coverage.py`・`predictor/_v5_backup/`・`data/backtest/*.json`
  (別タスクの作業中ファイル。add も revert もしない)
- `data/keiba.db` (288MB) を直接 read しない。確認は `sqlite3` CLI のみ
- HTML (370KB 級) を全文 read しない。grep / python ワンライナーで抽出
- テスト実行は `.venv64/Scripts/python.exe -m pytest`

### ステージ 1: build_daily_results.py の改修 (パーサ構造化 + 証跡完全化)

対象: `scripts/build_daily_results.py`, `tests/test_build_daily_results.py`, `db.py`

1-1. **span 専用バッファ化**: 現在の `" ".join(self._td_buf)` による分離は症状対処で、
   「odds 欠損 + popularity あり」の td (`<td><span class="pick-reason">6人気</span></td>`)
   で `^\s*([\d.]+)` が「6」に一致し odds=6.0 と誤読する経路が残る (レビュー 2 名が
   独立確認)。`handle_starttag` で `span` (class=pick-reason) 検出時に専用バッファへ
   切替え、popularity は span バッファから、odds は td 直下テキストからのみ抽出する。
   td 直下の join は `"".join` に戻す (馬名セルへの将来の空白混入リスク解消)。

1-2. **payouts.csv の馬番表現統一**: 現在 payouts だけ "04" とゼロ埋め、他 4 CSV は "4"。
   他 4 CSV に合わせて非ゼロ埋めに統一 (`lstrip("0")`、"10" はそのまま)。

1-3. **manifest への builder provenance**: manifest dict に追加:
   - `builder_git_sha`: `git rev-parse HEAD` の結果
   - `builder_git_dirty`: `git status --porcelain --untracked-files=no` が非空なら true
     (untracked を含めない。無関係な untracked で常時 dirty になるのを避ける)
   - `supersedes_manifest_sha256`: 出力先に既存 manifest.json があればその sha256、なければ null
   - `warnings`: `{"excluded_placeholder_rows": <'00'除外件数>, "null_odds_fetched_at_rows": <件数>}`
   既存の `version_meta.git_sha` (HTML footer 由来 = 予想生成時 sha) は**そのまま残す** (意味が違う)。

1-4. **出力品質ゲート**: CSV 書き出し前に検証し、違反時は件数つきで stderr に出して
   **exit 1** (静かに壊れた CSV を出さない):
   - 非空 morning_popularity が 1〜18 の範囲内
   - 出力行に horse_num が '00'・空・None のものがない (placeholder 除外件数の記録とは別)

1-5. **horse_num 有効性述語の単一出典化**: `db.py` に
   `SQL_VALID_HORSE_NUM = "horse_num IS NOT NULL AND TRIM(horse_num) != '' AND horse_num != '00'"`
   を定数化し、`scripts/backtest.py:585-587` / `scripts/build_daily_results.py` の SQL /
   `scripts/diag_discrepancy.py:95` の 3 変種を置換。**挙動は最強変種 (backtest 相当) に統一**。

1-6. **features_00_contamination.md に監査メタ追記**: 冒頭に 1 行
   (監査実施日 2026-07-15 / 対象 DB '00' 行数 406 / 判定時 git sha)。

1-7. **テスト追加** (既存 3 件は維持):
   - horse-name td に子 span を含む HTML → 馬名に空白が混入しない
   - odds 欠損 + popularity ありの td → odds が未設定のまま / popularity は取れる
   - payouts の馬番が他 CSV と同表現
   - 品質ゲート: popularity=310 を含む入力で exit 1 になる

**受入ゲート 1**: `pytest tests/test_build_daily_results.py -q` 全件 pass、
`pytest tests/ -q` が 316+新規 pass / 4 skip (既存回帰ゼロ)。

### ステージ 2: horse_num='00' プレースホルダの根絶 (ingest 防止 + DB 掃除)

対象: `jvlink_client/ingest.py` (SE 取込、157 行付近) / `db.py` (upsert_horse_race, 210-229 行付近) /
`scripts/cleanup_placeholder_horse_rows.py` (新規) / tests

背景: 枠順確定前 SE データの PK 衝突残骸として `horse_num='00'` 行が開催日ごと約 36 行
蓄積 (2026-05-10 以降、現在 406 行)。消費側は現状全経路で除外済みだが、
「'00' 行は confirmed_order=0」という暗黙不変条件 1 つに 19 クエリが依存する単一障害点。

2-1. **ingest 側の確定後掃除**: SE レコード取込と同一トランザクション内で、
   同一レースに `horse_num != '00'` の行が存在する場合に限り当該レースの '00' 行を
   DELETE (冪等)。挿入自体のスキップは不可 (枠順確定前の出走予定情報が失われるため)。

2-2. **既存 406 行の一括掃除スクリプト** `scripts/cleanup_placeholder_horse_rows.py` (新規、
   `--dry-run` デフォルト / `--execute` で実行):
   - 実行前に `data/keiba.db` を `data/keiba.db.bak_20260715` にコピー (バックアップ)
   - **事前チェック**: 全 '00' 行が「confirmed_order=0 かつ win_odds=0 かつ
     odds_fetched_at IS NULL かつ 同レースに '00' 以外の行が存在」を満たすこと。
     **1 件でも違反があれば削除せず violate 行を出力して abort** (ステージ 2 を中断し
     最終報告へ。他ステージは続行)
   - DELETE 後に `SELECT COUNT(*) ... WHERE horse_num='00'` = 0 を確認して件数報告
2-3. **invariant 回帰テスト**: `data/keiba.db` が存在する場合のみ実行 (なければ skip) の
   テストを追加: 「horse_races に horse_num='00' 行が 0 件」。掃除後は 0 が恒常状態になり、
   ingest 防止 (2-1) の破れを検知できる。

**受入ゲート 2**: dry-run → execute の順で実行し '00' 行 0 件、バックアップ存在、
全テスト green。

### ステージ 3: fresh odds スケジューラ空白検知

対象: `scripts/fresh_odds_coverage.py` / tests

背景: 2026-07-12 に 11:50→14:00 の 2h10m のフェッチャ起動空白があり、11 レース 137 頭の
odds_fetched_at が NULL になった。取得失敗カウンタでは原理的に検知できない障害クラス。

3-1. `scripts/fresh_odds_coverage.py` のレポートに「run 間隔ギャップ検知」を追加:
   `data/logs/fresh_odds_coverage.jsonl` の各開催日について 9:00〜16:40 の隣接 run
   間隔を計算し、15 分超のギャップを `WARNING: gap HH:MM->HH:MM (NNm)` として出力、
   ギャップありなら exit code 1 (`--check-gaps` オプション時のみ。既存挙動は不変)。
   ※ `scripts/monitor.py` は別タスクの未コミット変更があるため**触らない**。
3-2. テスト: 合成 JSONL (ギャップあり/なし) で検知を検証。
3-3. 実データで答え合わせ: `--check-gaps` を 2026-07-12 に対して実行し、
   11:50→14:00 のギャップが検知されることを確認して報告に記載。

**受入ゲート 3**: 07-12 の実ギャップを検知、合成テスト pass、既存出力の互換維持。

### ステージ 4: コミット → CSV 再生成 → 最終コミット (provenance を閉じる)

4-1. 全テスト green を最終確認 (`pytest tests/ -q`)。

4-2. **コード コミット (1 回目)**: 以下のみを明示 add してコミット。
   メッセージ例: `daily results: builder provenance + parser hardening + hn00 eradication + fetch gap alert`
   ```
   scripts/build_daily_results.py  tests/test_build_daily_results.py  db.py
   scripts/backtest.py  scripts/diag_discrepancy.py
   jvlink_client/ingest.py  scripts/cleanup_placeholder_horse_rows.py
   scripts/fresh_odds_coverage.py  tests/<新規テストファイル>
   docs/codex_audit_20260712_results.md  docs/codex_fix_20260712_results.md
   docs/codex_fix_20260715_provenance_and_cleanup.md
   data/scorecards/20260715_0039_daily_results_integrity.md
   data/scorecards/20260715_0843_daily_results_integrity_2.md
   ```

4-3. **CSV 再生成 (コミット済みコードで 2 日分)**:
   ```
   .venv64/Scripts/python.exe -m scripts.build_daily_results --date 20260712 ^
     --html data/results/2026-07-12/predictions_source_20260712_git2642e8c.html
   .venv64/Scripts/python.exe -m scripts.build_daily_results --date 20260621 ^
     --html data/results/2026-06-21/predictions_source_20260621_1023.html
   ```
   ※ ステージ 2 で '00' 行は DB から消えているため 06-21 も幽霊行なしで出るはず。

4-4. **再生成後の検証** (python ワンライナー、両日分):
   - manifest に builder_git_sha (= 4-2 の commit sha) / builder_git_dirty=false /
     supersedes_manifest_sha256 / warnings が入っている
   - 幽霊行 0、非空 morning_popularity 全行 1〜18、race_num 全 CSV 2 桁、
     payouts 馬番が他 CSV と同表現
   - profit_loss_yen_100unit 再計算が全行一致 (07-12: 470 行 / 06-21: 全行)
   - 06-21 固有: 旧 CSV で 420/501 行あった人気>18 が 0 件になっていること

4-5. **データ コミット (2 回目)**: `data/results/2026-07-12/` と `data/results/2026-06-21/`
   の全ファイルを add してコミット。
   メッセージ例: `data/results: regenerate 20260712+20260621 with fixed builder (provenance stamped)`

**受入ゲート 4**: 4-4 全項目 pass、`git log --oneline -2` に 2 コミット、
`git status --porcelain --untracked-files=no` に本作業関連の残変更なし。

### 最終報告 (15 行以内)

1. ステージごとの完了/スキップ (スキップ時は理由)
2. 受入ゲート 4 の検証結果 (両日分の行数・warnings 値・builder_git_sha)
3. '00' 行削除件数と backup パス
4. 07-12 ギャップ検知の出力 1 行
5. コミット 2 件の sha
6. push はしていないことの確認

---

## (Claude Code 側メモ — Codex には渡さない)

- Codex 完了後、**expert-review (D1) を再実行** — 特に data-pipeline-engineer の
  HOLD 解除確認 (builder provenance / '00' 上流対策 / ギャップ検知の 3 条件すべて充足のはず)
- ingest.py 改修は取得層に触るため、次回の実開催日 fetch 後に '00' 行が再増殖して
  いないか確認 (invariant テストが検知する設計だが初回は目視も)
- 残課題 (今回スコープ外): テンプレートへの data-odds/data-popularity 属性付与 (type-D、
  次回 web 改修に同乗) / evaluation_summary への「n<100 判断不能」注記 /
  iCloud snapshots の retention 問題 (別会話で提案済み、未着手)
