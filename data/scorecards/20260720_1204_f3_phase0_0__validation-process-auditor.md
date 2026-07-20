# 検証プロセス監査人 採点

## 総合: 4.4 / 5（前回 4.6 → -0.2）

F3 Phase 0-0 は、事前登録した3チャネルを固定 split / seed / params で control と treatment に分け、validation で差を定量化する実験として概ね正しい。cache は 2021-2023 の 10,368 race / 142,713 rows、時系列末尾20%を validation（8,294 / 2,074 race）とし、M2-control と M2-treatment は seed=20260720、781 rounds、同一 LightGBM params で学習している。成果物の feature 定義を機械比較し、112→109特徴で除外が `same_day_bias_score` / `leg_quality_available` / `same_day_bias_available` の3件だけであることを確認した。

主要結果は M2-control−treatment が AUC +0.002539、Brier -0.000147、LogLoss -0.000789、race top-1 ±0。pre-sealed OOS（2026-01-01〜06-14）は treatment 425 bets / 65 hits / 62.09%、開催日 block bootstrap 95% CI [48.97%, 76.28%]。ただし旧参照は 1,620 race / 199 bets / 70.70% に対し現行は 1,578 race / 425 betsで、コードcommitも異なる。文書が明記する通り、この差は非pairedであり、3チャネル除外の OOS 回収率寄与とは解釈できない。

sealed guard、cache実 race key の独立検査、プロジェクト外パス拒否、readonly DB、production artifact SHA-256前後一致を確認。現行 production SHA は metrics の after と一致し、評価script SHAおよび historical calibrator SHAも現物一致。対象テストは `.venv64/Scripts/python.exe -m pytest -q tests/test_f3_phase0_0_eval.py` で **7 passed**。

## 項目別

| 採点軸 | 今回 | 前回 | 差分 | 根拠 |
|---|---:|---:|---:|---|
| バックテスト設計の正しさ | 4/5 | 5/5 | -1 | race単位 top-1、AUC/Brier/LogLoss、OOS買い目、50開催日の block bootstrap CI、1,578 race / 82.9分のsanityを保存。一方、OOSは treatment のみで、同一stack・同一raceの M2-control を走らせていない。旧参照との race/bet 母集団差が大きく、ROIの対照実験は未成立。 |
| 時系列リーク防止 | 5/5 | 5/5 | ±0 | train/valは時系列順、2026 OOSは学習窓より後、sealed開始2026-10-01より前。`_guard_unsealed` に加え cache の実 race key も事前登録窓外/sealedを拒否。`predictor/features.py` は過去走を `< before_date`、同日biasを `start_time < ?` で前向きに限定。DBは `open_db_readonly()`。production 4成果物は実行前後SHA一致。 |
| calibration / reliability 計測 | 4/5 | 5/5 | -1 | validation 28,224 rowsについて Brier/LogLossを4モデル並列保存し、OOSは固定 historical calibrator を fail-closed で要求してSHAも保存。ただし F3 metrics に reliability bin（count / avg_probability / actual_win_rate）がなく、control−treatment のBrier/LogLoss差にも race/day cluster CIがない。 |
| A/B比較 / バージョン管理 | 4/5 | 5/5 | -1 | M0-public/M1-zero-fill と M2-control/M2-treatment を併記し、固定params/seed/rounds、cache SHA、script SHA、calibrator SHA、production before/after SHA、control/treatmentモデルとfeature定義を保存。反面、script/test/docは監査時点でuntracked、metricsの `git_sha=068efb0...` はF3コードを含まない。実験モデル/feature成果物自身のSHA manifestもない。 |
| 過適合監視 / 期間分割評価 | 5/5 | 4/5 | +1 | 2021-2023内の時系列 train/valに加え、2026-01-01〜06-14の固定OOS、さらに2026-10-01以降のsealedをコードで分離。事前登録3特徴のallowlistも固定され、恣意的な特徴追加をテストで防止。単一20% splitであり、境界が2023-05-21同日内（`...08_02`→`...08_03`）なのは軽微な残存課題。 |

## 監査で確認した具体的証拠

- `git log --stat -3`: 直近3commitはいずれも予想HTML公開で、F3実験コードを含まない。
- `metrics.json`: cache SHA `e249e4...b60a`、script SHAは現物一致、split 114,489/28,224 rows、8,294/2,074 races。
- feature artifact比較: control 112、treatment 109、removedは事前登録3件のみ、addedなし。
- production artifact: `lgbm_model.txt` / `lgbm_features.json` / `lgbm_meta.json` / `calibrator.json` のbefore=after、現物SHAとも一致。
- historical calibrator: `predictor/calibrator.json.bak` を必須化し、SHA `d6793b...d489` が現物一致。currentへのsilent fallbackはない。
- OOS: treatment 425 bets / 65 hits / 26,390円戻り / 62.09%、day-block CI [48.97%, 76.28%]、B=10,000、seed=20260720。
- 旧参照: 1,620 races / 199 bets / 70.70% vs 現行 1,578 races / 425 bets。非paired比較である旨を metrics/report に明記。
- テスト: 7 passed（3件allowlist、zero-fill限定、sealed拒否、cache race key、外部path拒否、race top-1、bootstrap決定性）。

## 優先課題

1. **M2-control と M2-treatment を同一OOS runnerで並列評価する** — race/payout universeを固定し、開催日blockで paired ROI差・bet選択差・95% CIを保存する。現状の62.09% vs 旧70.70%は3チャネル効果ではないため、これが最優先。
2. **validation差に cluster CI と reliability binsを追加する** — raceまたは開催日block bootstrapで ΔAUC / ΔBrier / ΔLogLoss / Δtop-1 の95% CIを出し、probability binごとの count / avg_probability / actual_win_rateもcontrol/treatment並列で保存する。可能なら split 境界も開催日単位に丸める。
3. **実験一式をcommitし、完全なartifact manifestを残す** — F3 script/test/docを含むcommit SHAをmetricsへ記録し、M2モデル、feature JSON、blocked allowlist、旧参照JSONにもSHA-256を付与する。現行script SHAは有効だが、未追跡のためVCS上の再現経路が未完成。

## 前回からの差分

- バックテスト設計: 5→4。固定された分類対照は成立したが、OOS回収率のpaired対照がない。
- 時系列リーク防止: 5→5。cache実日付/sealed/path guard、readonly DB、本番SHA不変が揃った。
- calibration/reliability: 5→4。Brier/LogLossはあるが、reliability binと差のCIがない。
- A/B・版管理: 5→4。実験SHAと固定条件は強いが、F3コード未commit・成果物SHA不足。
- 過適合監視: 4→5。固定OOSと将来sealedを明示的に分離し、前回の第三hold-out課題を直接改善した。

総合低下は -0.2 で、-0.3以上の回帰警告閾値には達しない。ただし、**OOSでの3チャネル寄与はまだ未確定**であり、F3 Phase 0-0の結論は validation上の「事前登録3チャネル差」に限定するのが妥当。
