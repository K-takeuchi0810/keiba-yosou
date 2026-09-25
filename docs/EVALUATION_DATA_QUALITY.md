# 評価成果物の品質台帳 (2026-09-25〜)

`data/results/<date>/` の評価成果物 (`evaluation_summary.csv` ほか CSV 5 本 + `manifest.json`)
のうち、**成績の主張に使ってはいけない**ものを記録する。

## 運用ルール (修復完了まで有効)

- `status=INVALID` の日を含む評価 CSV を使って、新しい成績の主張をしない。
  対象は `scripts/analyze_misses.py`、累積的中率、回収率集計、期間比較、モデル評価のすべて。
- 「CSV があるから読んでよい」ではない。**修復が完了するまでは既知の不正データとして使用禁止**。
- 分析コードに除外ロジックはまだ入れていない (JST 統一を遅らせないため)。守るのは人間側の運用。
- 削除も書き換えもまだしない。修復するときは再生成し、旧成果物との差分と理由を修復記録に残す
  (履歴を消さず、誤評価だったことを追えるようにする)。

## INVALID 一覧

| date | status | reason | affected_artifact | detected_at | repair_pending | 内容 |
|---|---|---|---|---|---|---|
| 2026-07-18 | INVALID | cross_date_prediction_contamination | evaluation_summary.csv / predictions.csv / final_odds.csv / race_results.csv (旧 builder `4ff5c0f`) | 2026-09-25 | true | 土曜 HTML に入っていた翌日 (日曜) の 2 レースが、土曜の同じ場・同じ R として土曜の着順で採点されている (31 行、◎ 2) |
| 2026-08-08 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | 同上 (30 行、◎ 2) |
| 2026-08-15 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | 同上 (32 行、◎ 2) |
| 2026-06-12 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | ★ **開催の無い日付 (金)** に週末分の予想 1,416 行がその日付として保存されている。一部混入ではなく**全面的に使用禁止** |
| 2026-06-17 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | ★ **開催の無い日付 (水)** に別日の予想 485 行。全面的に使用禁止 |
| 2026-07-03 | INVALID | cross_date_prediction_contamination | 同上 | 2026-09-25 | true | ★ **開催の無い日付 (金)** に別日の予想 479 行。全面的に使用禁止 |

## 未生成 (混入が分かっているので評価成果物を作っていない)

| date | status | reason | repair_pending | 備考 |
|---|---|---|---|---|
| 2026-08-22 | NOT_GENERATED | cross_date_prediction_contamination | true | 新 evaluator `8a91d73` で生成したが混入 (26 行、◎ 2 頭が並ぶレース 2) を確認して破棄。予想 HTML は保存済み |
| 2026-08-29 | NOT_GENERATED | cross_date_prediction_contamination | true | 同上 (20 行) |
| 2026-09-05 | NOT_GENERATED | cross_date_prediction_contamination | true | 同上 (27 行) |
| 2026-09-12 | NOT_GENERATED | cross_date_prediction_contamination | true | 同上 (28 行) |

## 原因

`scripts/build_daily_results.py` の HTML 解析は、レース ID (`race-20260823-01-11` など) の
**末尾の「場-R番号」だけ**を使い、日付を捨てている。日次分割 (2026-09-13) より前の土曜 HTML には、
先に出馬表が出た日曜のレースが入っているので、それが土曜の同じ場・同じ R に結合される。
金額への影響は 0 (該当期間の買い候補は 0 件) だが、**評価 N と的中率の母集団を別日の予想で
汚染している**。140% 検証では金額が発生する前に止めるべき種類の欠陥なので、重大度は下げない。

## 修復の予定 (JST 統一の後)

1. 解析を直す: レース ID から `prediction_date` / `venue` / `race_no` を取り出し、
   `prediction_date == 評価対象日` を必須にする。対象日と違う予想は**評価しないが黙って捨てない**
   (manifest に `foreign_date_predictions_dropped` / `foreign_date_race_ids` を記録)。
2. 不変量「1 レースにつき ◎ は最大 1 頭」を追加。2 頭出たら評価を続けずエラーにする。
3. 変異テストに最低限これらを入れる: レース ID の日付を無視する / 日付比較を常に true にする /
   manifest の drop 件数を 0 にする / 他日付の行を同じ場・同じ R へ結合する / 同一レースに ◎ 2 頭を許す。
4. 再生成: 未生成の 4 土曜 + INVALID の 6 日。旧成果物との差分と理由を修復記録に残す。
5. 以上が終わったら、この台帳の `repair_pending` を false にし、使用禁止を解除する。

## 関連する既知の互換性問題

- 2026-06-07〜08-16 の管理済み 21 日分は旧スキーマで、`horse_refunded` 列が無い。
  過去の返還 ◎ が不的中に数えられる (実害が確認できたのは 2026-07-11 の 1 レース、金額 0)。
  成績の主張に使う前に再生成が要る。上の INVALID と同じく、修復まで成績の主張には使わない。

## 有効な評価成果物 (新 evaluator `8a91d73` で初回生成、2026-09-25)

混入 0・◎ が 2 頭並ぶレース 0・manifest と CSV のハッシュ一致・除外行の金額 0 を確認済み。

| date | rows | evaluable | excluded (理由) | 返還馬 | ◎ 評価可 / 的中 | 買い候補 |
|---|---|---|---|---|---|---|
| 2026-08-23 | 466 | 466 | 0 | 1 | 36 / 9 | 0 |
| 2026-08-30 | 479 | 479 | 0 | 2 | 36 / 8 | 0 |
| 2026-09-06 | 491 | 491 | 0 | 0 | 36 / 7 | 0 |
| 2026-09-13 | 314 | 314 | 0 | 1 | 24 / 5 | 0 |
| 2026-09-19 | 287 | 287 | 0 | 1 | 24 / 7 | 0 |
| 2026-09-20 | 334 | 334 | 0 | 0 | 24 / 5 | 0 |
| 2026-09-21 | 320 | 159 | 161 (cancelled) | 1 | 12 / 3 | 0 |
| 2026-09-22 | 161 | 161 | 0 | 0 | 12 / 2 | 0 |

- `builder_git_dirty=true` は main checkout に untracked の成果物 (scorecards / backtest json など)
  があったため。tracked の差分は 0 で、builder のコードは SHA `8a91d73` と一致する。
  manifest は手で書き換えていない。将来 provenance を `tracked_dirty` / `untracked_present` に
  分ける案はコード品質のバックログ (JST 統一の後)。
- ◎ の数字は小標本で、予測能力の評価ではない。評価の会計が正しく動いたことの確認として扱う。
