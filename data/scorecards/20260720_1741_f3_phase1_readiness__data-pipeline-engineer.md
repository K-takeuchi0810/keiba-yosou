# データパイプライン技術者 採点 — F3 Phase 1 readiness（最終HEAD）

## 判定: PASS

**理由**: type-Bのread-only診断ツールとして、canonical PIT gate、SQLite一貫read transaction、固定dev窓、封印境界、production 4成果物と凍結設計文書のhash guardを備えた。中央競馬とその他も明示分離され、採用を止める欠陥はない。

**根拠ファイル**: `scripts/f3_phase1_readiness.py:40`, `scripts/f3_phase1_readiness.py:68`, `scripts/f3_phase1_readiness.py:229`, `scripts/f3_phase1_readiness.py:371`, `tests/test_f3_phase1_readiness.py:50`, `data/f3_phase1_readiness/dev_odds_coverage.json`

**次アクション**: mutable DB入力のfingerprintとgit dirty/script hashをmanifestへ追加し、JSON/Markdownをpair transactionとして公開する。

## 総合: 4.6 / 5

公式前回 `20260720_1617_f3_phase0_0b_paired__data-pipeline-engineer.md` の **4.3** に対し **+0.3**。初回readinessレビュー4.4からは **+0.2**。判定はPASS継続。

改修タイプは **type-B（検証・診断ツール）**。JV-Link/raw ingest/schema本体は今回の差分外であり、その範囲へスコアを外挿しない。

## 項目別

- **DB read-only / 一貫性: 4.9/5**
  - `collect` は `open_db_readonly()` のみを使い、`PRAGMA query_only=1` を検証後に明示的 `BEGIN` を発行する (`scripts/f3_phase1_readiness.py:371-379`)。
  - races、horse_races、odds_snapshotsを同一SQLite snapshotで読むため、WAL writerと並走しても計測途中の世代混在を防ぐ。
  - 実DBでquery_only=1、write probeが `attempt to write a readonly database` となることを初回監査で確認済み。DBはWAL、canonical queryのrace 6-key indexも存在する。
  - `open_db_readonly` のWAL環境fallbackは `mode=rw + query_only=ON` であり、OSレベルread-onlyではないため満点から0.1減点。

- **PIT gate / 対象母集団整合性: 4.9/5**
  - `analyze_race` は独自cutoff SQLを持たず、実運用の `usable_snapshots` を直接使用する。gateは `fetched_at IS NOT NULL AND fetched_at <= T-10` (`scripts/f3_phase1_readiness.py:107-135`, `predictor/pit_gate.py:35-60`)。
  - 馬行を時刻でdedupし、異なる2時刻以上だけをdrift-computableとする。runtime post-cutoff guardも維持。
  - track 01–10を `jra_central`、それ以外を `other` としてrace単位で明示し、scope別件数・rateを保存する (`scripts/f3_phase1_readiness.py:141-146`, `scripts/f3_phase1_readiness.py:229-242`)。
  - 再生成値は中央216レース（usable 71、drift 19）/ その他9レース（usable 0、drift 0）。合計225と一致。初回実査のeligible 90時刻、partial timestamp 0も維持される。

- **封印 / artifact・設計guard: 4.9/5**
  - `from_date` は20260704完全固定、`to_date >= 20261001` はSQL前に拒否する。auto latest SQLも20260930以下 (`scripts/f3_phase1_readiness.py:40-51`, `scripts/f3_phase1_readiness.py:354-368`)。
  - 保存成果物に封印日付は0件、窓は `20260704..20260719`。
  - production 4成果物に加え、`F3_MARKET_RESIDUAL_DESIGN.md` のSHA-256を計測前後で比較し、不一致なら成果物生成前に停止する (`scripts/f3_phase1_readiness.py:372-398`)。
  - current/before/afterのproduction hashと凍結設計hashを再照合し、全件一致。設計文書のgit diffも空。

- **出力安全性 / 冪等性: 4.5/5**
  - 出力先は固定JSON/Markdownのみで、CLIからproduction/input pathへ変更できない。
  - temporary名をUUID付きrun固有名へ変更し、成功・失敗どちらでもfinally cleanup後にsame-directory replaceする (`scripts/f3_phase1_readiness.py:68-75`)。残存 `.tmp` は0件。
  - 同じ窓のread-only再集計は保存payloadのwindow/gate/database/races/daily/summaryと完全一致。
  - JSONとMarkdownは個別atomic replaceであり、2ファイル全体のtransaction/manifestではない。JSON成功後にreportが失敗した場合は世代が分かれ得るため0.5減点。

- **テスト / provenance / 観測性: 4.0/5**
  - focused（readiness + PIT gate）は **10 passed in 0.23s**。全体は **371 passed / 4 skipped in 10.16s**。
  - dev窓下限、封印上限、distinct時刻、scope集計、canonical gate、snapshot ingest冪等性をテストする。
  - JSONはgit SHA、窓、gate、生成時刻、read transaction、production/design hashを持つ。
  - DBはmutable inputだが、対象表件数/max(fetched_at)/data versionなどのDB fingerprint、git dirty/status、script SHA-256は未記録。同じgit SHAでも後日のDB追記を成果物単体で区別できない。
  - `collect` のBEGIN・hash mutation検知・atomic failure pathを直接注入する統合テストは未整備。

## 停止条件チェック

- [x] type-B成果物にgit SHA、評価窓、gate設定が記録される。
- [x] DB read-only + query_only + consistent read transactionを使用する。
- [x] canonical PIT gateでpost-cutoff / NULL snapshotを除外する。
- [x] dev開始日を固定し、封印期間をvalidationとSQL上限で遮断する。
- [x] production 4成果物と凍結設計文書のbefore/after hashが一致する。
- [x] 中央216 / その他9が明示され、scope partitionは全225レースと一致する。
- [x] 必須証拠欠落や有害な実装はなく、FAIL / HOLD / NOT_EVALUABLE条件に該当しない。

## 実測・監査メモ

- 最終HEAD: `cb56778119b3998510820116510d2fc87bad8f0d`。`5ba3808`からscript +60/-4、test +5。
- 保存payloadと再集計payloadのcoreは完全一致。production/design hash一致、sealed race 0。
- focused 10/10、full 371/371（skip 4）。対象コード・DB・production・凍結文書に未コミットtracked差分なし。

## 残る改善提案

1. **P1: provenance manifest** — DB対象表件数・max(fetched_at)・schema/data version、git dirty/status、script SHA-256をJSONへ保存する。
2. **P1: pair publish** — JSONとreportを同一run manifestで束ね、両方のhash検証後に世代切替する。
3. **P2: fault-injection tests** — read transaction、production/design mutation、atomic write失敗・cleanupをtemp DB/dirで統合検証する。
