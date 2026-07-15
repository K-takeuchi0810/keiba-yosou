# 採点 2026-07-15 23:52 (正規版)

**改修内容**: 日次答え合わせ基盤の完全化 — manifest builder provenance / パーサ span 専用バッファ化 / payouts 馬番統一 / 出力品質ゲート / horse_num 述語単一出典化 (db.py) / ingest '00' 確定後 DELETE + DB 406 行掃除 / fresh odds ギャップ検知 / 2026-07-12・06-21 CSV 再生成
**対象 commit**: `2a5ae4d` (コード) / `5c1353b` (データ)。実装は OpenAI Codex (指示書: `docs/codex_fix_20260715_provenance_and_cleanup.md`)
**対象ファイル**: `scripts/build_daily_results.py`, `db.py`, `jvlink_client/ingest.py`, `scripts/cleanup_placeholder_horse_rows.py`, `scripts/fresh_odds_coverage.py` + tests 4 ファイル + `data/results/2026-06-21|07-12/`

> 注: 本 scorecard が正規の expert-review (rubric 準拠 7 subagent 並列)。
> 同トピックの `20260715_2337_daily_results_provenance_cleanup.md` は外部ツール (OpenAI Codex) が
> 正規機構の外で作成した参考値であり、スコア推移の追跡に使用しないこと
> (validation-process-auditor の手続き所見参照。同ファイルには外部作成注記を追記済み)。
> 前回の正規基準は `20260715_0843_daily_results_integrity_2.md`。

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 (0843) | 差分 | 判定 |
|---|---:|---:|---:|---|
| GUI / UX 監査人 | 3.6 | 3.6 | ±0 (GUI 無変更。CSV 参考 3.8→4.5) | PASS |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 | PASS |
| 予想ロジック分析官 | 4.4 | 4.3 | +0.1 | PASS |
| 収益性ジャッジ | 4.1 | 4.0 | +0.1 | PASS |
| データ基盤エンジニア | 4.1 | 3.4 | **+0.7 (HOLD 解除)** | PASS |
| コード品質レビュアー | 4.2 | 4.0 | +0.2 | PASS |
| 検証プロセス監査人 | 4.4 | 4.3 | +0.1 | PASS |
| **平均** | **4.20** | **4.03** | **+0.17** | **7 PASS** |

- 0.3 以上の後退なし (全項目維持または改善)。
- **前回 HOLD (データ基盤) の解除条件 3 点 + 改善提案 3 点は全件実装を実測確認** (manifest provenance /
  コミット後再生成 / '00' 上流根絶)。
- 前回 (0843) の 7 名の改善提案は、スコープ外宣言済みのテンプレート data 属性化を除き**全件消化**。
- 削除 406 行の内容中立性は 3 名 (予想ロジック / データ基盤 / 検証プロセス) が backup DB への独立 SQL で
  裏取り: 全行ゼロ値プレースホルダ・features 19 クエリ非参照・starter_count 非依存 → **過去検証と F3 封印
  ホールドアウトへの影響なし**。

## 各専門家の所見

### GUI / UX 監査人 (3.6 維持 / CSV 参考 4.5 / PASS)

- 前回提案 3 件 (payouts 馬番統一 / manifest warnings / 品質アサート) **全件実装を実測確認**。
- payouts.csv 先頭ゼロ馬番 0 行 (前回 26/36)。5 CSV のキー表現が完全統一され表計算での払戻照合が成立。
- 再現性メタは 5/5: builder_git_sha + dirty + supersedes + 全成果物 sha256 で再現経路が閉じた (PROV 系 lineage の要諦を満たす)。
- 品質ゲートは CSV 書出し**前**に exit 1 する順序設計 (Nielsen 5 エラー予防)。
- 提案: ①オッズ td の消去法識別を class 正一致に (type-D、次回 web 改修同乗)、②--check-gaps の定期監視接続 (手動フラグのままでは空白が再び沈黙)、③品質ゲート上限の starter_count 連動。
- 参考: gui/app.py のデータ件数表示は '00' 掃除により正確化 (前回参考所見が副次解消)。

### モバイル HTML レビュアー (4.6 維持 / PASS)

- 前回指摘の残存誤読 2 経路の**構造的封鎖を 3 層で確認**: ①odds 欠損+人気あり → span 専用バッファ (`_td_span_buf`) で構文的に発生不能 + 回帰テスト、②馬名空白混入 → `"".join` 復帰 + nested span テスト。実データ 971 行で空白入り馬名 0 件・異常値 0 件。
- 06-21 は旧 420/501 行破損 → 全 501 行正常に復元。
- 品質ゲートは「パーサ回帰が再発しても破損 CSV が証跡として固定されない」多層防御と評価。
- 残存 (非ブロッキング): オッズ列の「class 無し td」消去法識別 (テンプレート契約の脆弱性、提案 1 = data 属性化で解消、スコープ外宣言済み)。pick-reason 内側にさらにネスト span が入ると popularity が静かに欠落する微小経路 (現テンプレートに存在しない構造)。

### 予想ロジック分析官 (4.4 / PASS、+0.1)

- **feature 分布不変性 5/5**: backup DB (19.4GB) への直接 SQL で削除 406 行 = 406 レース×1 行、違反 0 件。features.py の過去走系クエリ全 19 箇所が `confirmed_order > 0` 系条件を持ち削除行を元々 1 行も参照しない → 過去走特徴・raw_blended_probability は bit-identical。
- **train-serve 整合 5/5**: PK が `(レースキー, horse_num)` のため '00' 行はレースあたり 1 行に collapse しており、per-horse の予定情報はそもそも存在しない。DELETE で失うのは「枠順未確定 marker 1 行」のみで正規行の存在と論理的に排他 → **情報損失ゼロの主張は成立**。
- cleanup スクリプトは「dry-run 既定 → 事前条件全件検証 → online backup → BEGIN IMMEDIATE 下の再検証 → 削除 → 残数検証 → 失敗時 rollback」で破壊的 DB 操作の教科書的手順。
- 新規に特定した防御層ギャップ: **`web/generator.py:191` の馬行取得が無述語** — 再混入事故時に幻の '00' 馬が本番 HTML に出る唯一の経路。提案: ①同所への `SQL_VALID_HORSE_NUM` 適用、②monitor への placeholder count=0 チェック昇格。

### 収益性ジャッジ (4.1 / PASS、+0.1)

- 両日 971 行の `profit_loss_yen_100unit` を payouts.csv から独立再導出し**不一致 0**。manifest の csv_sha256 10 件も全一致。builder_git_sha は実在 commit と照合済み。
- 06-21 再生成で旧 84% 破損の morning_popularity が 501 行全て正常化 (5/5)。07-12 の空 301/470 は「HTML に朝オッズ掲載が 169 頭分しかない」ソース忠実であり破損ではない。
- 2 日累計: 賭け 7 / 的中 1 / 52.9% (点推定) — **n=7 は統計的に無、収益判断には一切使えない**規律を維持。「F3 封印ホールドアウトの入力となる日次台帳が改ざん検知つきで蓄積開始された」ことが本改修の価値。
- 留保: dirty 判定の `--untracked-files=no` は未追跡コード混入を検知しない。提案: ①warnings に morning_popularity カバレッジ追加 (空 64% を破損と誤読させない)、②dirty 判定の untracked 除外を data/results 限定に、③日次横断の累計 P/L 台帳 (n + Wilson CI 自動併記)。

### データ基盤エンジニア (4.1 / PASS、+0.7 — **HOLD 解除**)

- **解除条件 3/3 充足を実測**: ①provenance 刻印 (supersedes 鎖の sha256 を CRLF 変換込みで再計算し一致)、②commit (23:28) → backup (23:26) → 生成 (23:30) → データ commit (23:31) の順序整合、③DB '00' 行 0 / backup 実在。
- ingest DELETE はクラッシュ一貫性 (同一トランザクション、open_db の commit/rollback 出口一元)・冪等性・PK prefix 走査の性能安全を確認。回帰テストあり。
- cleanup は 3 段防御 (事前検査 abort / backup + BEGIN IMMEDIATE 内再検査 = TOCTOU 封鎖 / 削除後残数検証)。
- --check-gaps は 07-12 実ギャップで exit 1、直近 14 日一括で **false positive ゼロを実測**。
- 残存 3 点: (a) placeholder のみの SE ファイル単独再取込で '00' 行が**復活**する経路 (消費側フィルタで実害遮断済み)、(b) **06-21 の warnings null=0 は意味論に era 差あり** — 全 501 行の fetched_at が発走後の旧刻印遺産で、「0 = 完璧」と日付横断で読むのは誤読、(c) 検知器は完成したが **bat/monitor からの自動配線がゼロ**。提案: ①--check-gaps の自動化配線、②warnings に `post_start_stamped_rows` 追加、③'00' upsert 拒否ガード + 回帰テスト。

### コード品質レビュアー (4.2 / PASS、+0.2)

- 前回提案: ①述語単一出典化 = 充足 (3 変種置換、grep 確認)、②span 専用バッファ = 完全充足 (回帰テスト 1:1)、③テスト DB 注入 = 部分充足 (パーサは純粋単体化、`_run_main` の monkeypatch は残存)。
- 減点の主因: (a) **単一出典化した当の commit 内で `cleanup_placeholder_horse_rows.py:44-47` が述語を第 4 の inline 変種として再記述**する自己矛盾、(b) 馬番正規化が同ファイル内で 2 形態並存 ('00' の帰結が None と "0" で分岐)。
- **変更失敗モード (重要)**: `_find_run_gaps` は隣接 run ペアの間隔しか見ないため、**スケジューラ終日死亡や「9:05 の 1 回だけで停止」は警告ゼロで素通り** — 検知したかった障害クラスの最悪形が FN になる。窓開始→初回 / 最終→窓終了の仮想区間判定が必要。
- 提案: ①cleanup 内 inline 述語の置換 + db.py に Python 版 `is_valid_horse_num`、②gap 検知の窓端仮想区間 + 0 run 日の全欠落警告、③builder テストの --db 実体化。

### 検証プロセス監査人 (4.4 / PASS、+0.1)

- 前回提案 3 件 (06-21 再生成 / 生成器メタ / warnings 機械記録) **全件執行を実測確認**。宣言済み宿題 ('00' 上流対策) も執行 — 宣言不執行ゼロ。
- backtest.py の変更は共通述語への置換で**意味論的に同一** (diff 実測) → 過去 baseline (20260703 p26 paired) の再現性は保たれる。
- **F3 封印ホールドアウトへの影響なしを裏取り**: 削除行は全行ゼロ値 + 全消費経路が元々除外 + starter_count は races テーブル由来で horse_races 行数非依存 (features.py に COUNT クエリ 0 件を実測)。
- supersedes 鎖: 06-21 の supersedes 先は git blob + CRLF 変換で復元可能と**実証** (「追跡不能」所見を部分反証)。07-12 の旧版は untracked だったため復元不能 (破損 artifact につき軽微)。
- **手続き所見**: `20260715_2337_*.md` は Codex 作と判断 (rubric 必須構造の欠落 / untracked / 注記なし)。**廃棄せず冒頭に外部作成注記を追記して参考値として保存、スコア推移への使用は禁止**。無注記の外部 scorecard が 2 回続いており、3 回目からは正規採点との混線が構造化する。
- 提案: ①2337 への注記追記 (実施済み)、②gap 検知の定期監視接続、③'00' 逆順リプレイ防御 (upsert 拒否ガード)。

## 横断的に見た優先課題

1. **ギャップ検知の完全化 + 自動配線** (担当: data-pipeline-engineer + code-quality-reviewer + gui-ux-auditor + validation-process-auditor の 4 名一致)
   - 検知器は完成・実ギャップで動作確認済みだが、(a) bat/monitor からの呼び出しゼロで 07-12 型の空白は今も当日中に気づけない、(b) 隣接ペア方式のため**終日死亡・片端欠落が警告ゼロで素通り**する FN 穴。窓端仮想区間 + 0 run 全欠落警告を追加し、weekly_monitor.bat または日次 pipeline 末尾に `--check-gaps` を配線して exit 1 を alert に接続する。
2. **'00' 復活経路の封鎖 + 防御層の完成** (担当: data-pipeline-engineer + prediction-logic-analyst + validation-process-auditor)
   - placeholder のみの SE ファイル単独再取込で '00' 行が復活する経路が残存。`upsert_horse_race` に「同レースに正規行が存在する場合は '00' 挿入を拒否」の EXISTS ガード + 回帰テスト。あわせて `web/generator.py:191` (無述語の唯一の消費経路) に `SQL_VALID_HORSE_NUM` を適用し、monitor に placeholder count=0 チェックを昇格。
3. **warnings の意味論補強** (担当: data-pipeline-engineer + profitability-judge)
   - 06-21 の `null_odds_fetched_at_rows=0` は旧 era の発走後刻印遺産であり「0 = 鮮度完璧」と読むのは誤読。`post_start_stamped_rows` と `morning_popularity_populated_rows` を warnings に追加し、日付横断集計時の era 差を機械可視化する。

## 残課題 (スコープ外繰越)

- テンプレートへの data-odds/data-popularity 属性付与 (type-D、次回 web 改修に同乗)
- cleanup 内 inline 述語の一元化 / builder テストの monkeypatch 解消 (小規模リファクタ)
- 日次横断の累計 P/L 台帳 (n + Wilson CI) — F3 封印ホールドアウトの入力規律に接続
- untracked 残骸の整理 (CLAUDE.md ルール 0): `data/backtest/20260703_*.json`, `predictor/_v5_backup/`, scorecard 2 件
