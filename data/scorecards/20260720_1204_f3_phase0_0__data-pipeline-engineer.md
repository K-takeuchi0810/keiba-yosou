# データパイプライン技術者 採点 — F3 Phase 0.0

## 総合: 4.1 / 5（前回 4.0 → 今回 4.1、差分 +0.1）

初回監査 3.7 → 指摘対応後 4.1（再監査差分 +0.4）。

対象は `scripts/f3_phase0_0_eval.py`、`tests/test_f3_phase0_0_eval.py`、
`docs/F3_phase0_0_result.md`、`data/f3_phase0_0/metrics.json`。
指定の `.Codex/agents/_rubric.md` は存在しなかったため、直近の同担当
`20260512_2100_p05_wl_odds_8_20__data-pipeline-engineer.md` の形式を踏襲した。
今回の変更は実験専用経路で、JV-Link/raw ingest/schema 本体には変更がない。

初回の P0 だった script provenance、cache実日付境界、外部パス部分書込みは改善。
残る主な減点は成果物出力の非atomic性、実験成果物hash不足、長時間OOSの回復性である。

## 項目別

- **DB read-only / production 不変: 5.0/5**
  - OOS は `open_db_readonly()` を使用し、実 DB で `PRAGMA query_only=1`、
    UPDATE は `attempt to write a readonly database` で拒否された。
  - production 4成果物の現在 SHA-256 は metrics の before/after と全件一致。
  - monkeypatch、calibrator path/cache、環境変数は `finally` / context manager で復元。
- **日時窓 / sealed 境界: 4.5/5**
  - train=`20210101..20231231`、OOS=`20260101..20260614`、sealed開始=`20261001`。
    `_guard_unsealed` は開始・終了の双方で `>= 20261001` を拒否し、単体テストあり。
  - OOS SQL は日付 BETWEEN と `require_confirmed=True` を使い、実績は1578レース。
  - `_guard_cache_race_keys` が内部window宣言とは独立に実 race key のmin/max日付を
    検査し、事前登録窓外およびsealed開始以降を拒否する。テストもsealed混入を確認。
  - 現cacheは単調だが、run内ではrace key順序、groups/rows整合、実在日付までは未検証。
- **固定 split / seed・再現性: 4.0/5**
  - 時系列末尾20%、LightGBM 4種 seed、`deterministic=True`、bootstrap seedを固定。
  - 隔離出力への独立2回実行で control/treatment model と特徴定義の SHA-256 が一致。
  - cache SHA-256 は保存値と一致し、group合計142,713=label行数、10,368 race key、
    race key単調、範囲20210105..20231228を監査で確認。
  - `evaluation_script_sha256=5f7888...8fe0` は現行script実体、metrics、reportで一致。
    未追跡scriptをHEADだけで識別できなかった初回P0は実用上解消した。
  - ただし metrics の `generated_at=10:37:50` は修正前の長時間実行時刻のまま。
    digestは後付けされた現行scriptを示し、元実行時のbyte列を証明するものではない。
    次回はrun開始時にdigestを固定し、終了時の不変も検査すべき。
- **成果物整合 / idempotency / 回復性: 4.0/5**
  - metrics と report の生成時刻・主要数値は整合し、treatment 定義は109特徴で
    登録3特徴をすべて除外。cache と production には hash がある。
  - 実験モデル、特徴定義、allowlist、report 自体の hash は metrics にない。
  - cache/output/report はrun冒頭、`mkdir`・hash・学習より前に `_require_project_path`
    で検査される。外部パスは明示エラーとなり、初回再現の部分書込み経路は解消。
  - 固定OOSは historical `predictor/calibrator.json.bak` 必須で、欠損時はcurrentへ
    silent fallbackせずfail-closed。使用実体SHA-256 `d6793b...489` はmetricsと一致。
  - 個別 `write_text` / `save_model` は staging＋atomic replace ではなく、中断時に
    metrics・report・model 世代が混在し得る。
- **性能 / 運用性: 3.0/5**
  - DBはWAL readerでwriterを阻害せず、feature cacheとday-block集計は妥当。
  - 保存実績のOOSは4,972秒（82.9分）。checkpoint/resume/cancel/timeoutがなく、
    進捗表示も200レース条件のみ。再失敗時は全件再計算となる。
  - `--output-dir` / `--report` の外部拒否はテスト済みだが、CLI helpには制約説明がない。

## 実測・検証

- `git log --stat -3`: 直近3件は公開HTML更新で、今回4対象は未追跡。
- `.venv64/Scripts/python.exe -m pytest -q tests/test_f3_phase0_0_eval.py`:
  **7 passed**。cache実日付と外部パス拒否の2件を追加。
- production SHA-256: model/features/meta/calibrator の4件すべて現在値=before=after。
- cache SHA-256: `e249e4...b60a` で metrics と一致。
- historical calibrator SHA-256: `d6793b...489` で実体と metrics が一致。
- 独立2回: control model `b0bff5...08c7`、treatment model `debf5e...950c4`、
  control features `925a8e...f4d3`、treatment features `32b011...acc` が各回一致。
- raw先頭とサイズ、fetch_state、read-only DB 29テーブルを確認。DBへの書込みなし。
- OOS旧参照との差は母集団1620→1578、bets 199→425で非paired。reportが明記して
  おり、62.09%と旧70.70%の差を3リーク寄与と誤認させない扱いは妥当。

## 優先課題

1. **P1: 次回runでprovenanceを確定** — run開始時script SHAを保持して終了時に
   再検査し、依存コードのcommit/dirty状態も保存。後付けdigestと実行コードを区別する。
2. **P1: cache構造を完全検査** — race keyの単調性・実在日付、
   `sum(groups)==rows`、keys/groups一致をrun内で検証する。
3. **P1: 成果物をtransactional化** — staging directoryへ全件出力・hash検証後に
   atomic replace。全実験成果物とreportのhashをmanifest/metricsへ保存し、外部
   output pathでも落ちない相対/絶対パス表現にする。
4. **P1: 統合テスト追加** — read-only書込み拒否、production hash tripwire、
   runが3種外部パスを副作用前に拒否、途中失敗時に正式成果物が不変なことを検証。
5. **P2: 長時間OOSの回復性** — 日単位checkpoint/resume、定期進捗、cancelを追加。
