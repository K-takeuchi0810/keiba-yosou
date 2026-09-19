# コード品質 / 保守性レビュー — F3 Phase 1 readiness（最終）

## 判定: PASS

**改修タイプ**: type-B（read-only 診断・測定ツール）。P25 固有の backtest 採用ゲートは N/A。

**理由**: 最終 HEAD `cb56778` は canonical `usable_snapshots`、read-only + `query_only` に加え、固定 dev 開始日、明示的 read transaction、JRA中央/その他内訳、凍結設計SHAの前後照合、UUID一時ファイルを実装した。初回レビューで指摘した「未検証の不変宣言」と固定 `.tmp` 競合は解消。停止条件に触れる欠陥はなく、成果物・focused test・全体testも整合した。残課題は二成果物の世代一括性と orchestration 失敗系テストの追加で、いずれも今回のreadiness測定を止める重大度ではない。

**根拠ファイル**: `scripts/f3_phase1_readiness.py:24`, `scripts/f3_phase1_readiness.py:40`, `scripts/f3_phase1_readiness.py:68`, `scripts/f3_phase1_readiness.py:229`, `scripts/f3_phase1_readiness.py:371`, `scripts/f3_phase1_readiness.py:508`, `tests/test_f3_phase1_readiness.py:80`

**次アクション**: `collect/run` の hash mismatch・query-only不成立・write failureを統合テストし、JSON/reportを同一run IDで相互参照させる。

## 総合: 4.5 / 5

- 前回正式スコア: **4.3 / 5**（F3 Phase 0-0b paired OOS）
- 初回レビュー: **4.2 / 5**（HEAD `5ba3808`）
- 最終: **4.5 / 5**（HEAD `cb56778`）
- 正式前回比: **+0.2** / 初回指摘対応比: **+0.3**
- 前回判定: **PASS** / 今回判定: **PASS**

## 項目別

- **DRY / 単一出典: 4.6 / 5** — PIT eligibility は `predictor.pit_gate.usable_snapshots` の一入口を維持（`:21`, `:113`）。track scope 集計は `_scope_summary` に抽出され、JRA/other の同型計算を重複させない（`:229-242`, `:320-323`）。測定、集計、描画、I/Oも関数境界が明確。残る平行記述は wide-drift の60/25とreport文面程度。
- **dead code / 未使用シンボル: 4.7 / 5** — `uuid`、`JRA_TRACK_CODES`、`FROZEN_DESIGN`、`_scope_summary` は全て実行経路で使用され、新規 dead symbol はない。対象 script の `print` はCLI summaryだけ（`:521`）でdebug残骸なし。repo必須scanで検出される `rules.py` 直接参照なしfeature 32件は本diff由来ではなくLGBM schema消費を含む既存事項。
- **マジックナンバー / 設定外出し: 4.0 / 5** — dev/sealed/near-T10/projection、JRA track code、出力先、凍結設計、本番artifactを冒頭定数へ集約（`:24-37`）。固定from_dateも同じ `DEV_FROM` を検証と既定値で共有（`:47-48`, `:508`, `:517`）。`20260930`、wide早期点60、週2日、100レース表示閾値はなお直書きだが、診断仕様の局所値として追跡可能。
- **テスト容易性 / 変更失敗モード: 4.4 / 5** — `analyze_race(conn, race)` と pure summary helpers はmemory SQLiteで検証できる。readiness 5件 + canonical PIT gate 5件のfocused **10 passed**で、異時刻、post-gate/NULL除外、固定from、sealed境界、分母、JRA/other集計を確認。全体 **371 passed / 4 skipped**。残る不足は `collect/run` のtransaction・design hash mismatch・atomic cleanup・二成果物片側失敗の直接test。
- **エラー処理 / ログ / 観測可能性: 4.8 / 5** — from_dateを `20260704` にfail-closed固定し、sealed上限をdata query前に拒否（`:40-50`）。read-only接続で `query_only` を再確認後 `BEGIN` し、走査中の一貫snapshotを確保（`:371-385`）。production 4 artifactと凍結設計を前後hash比較し、不一致時は出力前に停止、hash自体もJSONに記録（`:388-424`）。UUID temp + `finally unlink` で並行衝突と残骸を防止（`:68-75`）。残る観測性課題はdirty status/source hash未記録と、JSON置換後のreport失敗で世代がずれ得る点。

## 停止条件チェック

- [x] provenance: `git_sha`、window、PIT gate名/閾値、production hash、frozen design hashを記録。
- [x] read-only consistency: `open_db_readonly()` + `PRAGMA query_only=1` + `BEGIN`。
- [x] fixed development scope: `from_date == 20260704` を強制。
- [x] sealed guard: `to_date >= 20261001` を拒否。
- [x] production / frozen design: before/after SHA-256一致を実測し、成果物にも保存。
- [x] output collision safety: UUID unique temp、成功・失敗時ともcleanup。
- [x] P25 market/factorial/fresh-odds evidence: type-B のため N/A。

## 反証の試み

- 「DB走査中に書込み側の更新が混ざる」: `BEGIN` がrace列挙より前にあり、同一connectionのread transaction内で `usable_snapshots` を走査するため不成立。
- 「凍結設計不変はレポートの自己申告だけ」: artifactのbefore/after SHAが現ファイルSHAと一致し、scriptも不一致時にraiseするため不成立。
- 「地方/補助レースがJRA母集団に混入する」: 各raceに `track_scope` を付与し、成果物で JRA中央216件 / other 9件を分離しているため不成立。
- 「並行runが同じtmpを上書きする」: UUIDをファイル名に含め、現run後の対象dirにtmp残骸0件を確認したため不成立。

## 検証結果

- `git log --stat -3`: 最終 HEAD `cb56778`。初回から script +60/-4行、test +5行。
- `pytest tests/test_f3_phase1_readiness.py tests/test_pit_gate.py -q`: **10 passed in 0.33s**。
- 全体 `pytest -q`: **371 passed, 4 skipped in 10.18s**。`py_compile` / `git diff --check` 成功。
- 成果物: git SHA `cb567781...`、fixed window `20260704-20260719`、production 4 hash一致、frozen design SHA before=after=現ファイル、sealed access false、consistent transaction true。
- scope: JRA中央 **216 races / 19 drift-computable**、other **9 / 0**。UUID temp残骸0件。
- 必須scan（初回実測）: `predictor/rules.py` def 20、直書き `score +=/-=` 1、対象scriptのdebug print 0。

## 主な改善提案

1. **二成果物の世代を明示する** — JSON/report双方へ同一 `run_id` と相互hashを記録し、片側失敗・手動コピー後も対応関係を検証可能にする（`scripts/f3_phase1_readiness.py:508-512`）。
2. **orchestration失敗系testを追加する** — monkeypatchしたDB/hash/outputで、query-only不成立、design hash mismatch、atomic write失敗時cleanupを直接固定する（`tests/test_f3_phase1_readiness.py`）。
3. **残る仕様値をsymbolic化する** — wideの早期点60、projected race days/week=2、sealed前日を定数化し、payload説明/reportを同じ値から生成する（`:24-28`, `:300-307`, `:407-411`）。

## 初回レビューからの改善

- 凍結設計hash未検証: **解消**（before/after検証 + JSON記録）。
- 固定 `.tmp` 競合: **解消**（UUID unique temp + cleanup）。
- read consistency不明: **解消**（明示的 `BEGIN`）。
- 母集団scope混在: **解消**（JRA中央/other分離）。
- from_date任意変更: **解消**（`20260704`固定）。
- 総合: **4.2 → 4.5（+0.3）**。正式前回4.3比 **+0.2**、回帰警告なし。
