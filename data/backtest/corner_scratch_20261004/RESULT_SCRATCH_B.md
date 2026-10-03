# Scratch B (本番の対象行だけの縮小 clone に backfill を当てる) — 結果 (2026-10-04)

- コード: scripts/backfill_corner_orders.py (afeb94d 時点)。clone と比較は scratch_b.py
- 本番 DB は mode=ro で開き、**1 つの読み取りトランザクション** で horse_races と races の対象行
  (JRA、2021-01-01〜2026-06-30) をコピーした。読み取りは 05:18:46〜05:18:51。本番 DB 本体の mtime (10/03 20:00:19) と
  WAL の mtime (10/04 00:05:10) は読み取りの前後で不変
- clone: horse_races 262,885 行 / races 19,056 行。そこに `backfill_corner_orders --apply` を当てた (raw は本番の data/raw/RACE)
- 結果: scratch_b_result.json / scratch_b_backfill_report.json (raw のファイルの一覧と sha256 を含む) / scratch_b.log

## 判定: **合格**

| 項目 | 結果 |
|---|---|
| backfill | applied、更新 262,113 行 = 予定 262,113 行、raw にあって DB に無いキー 0 |
| 適用後の検収 | 合格 (2021-01〜2026-06 の月ごとの `corner_order_4 > 0` は最小 96.56%、順位 > 出走頭数 0 件) |
| 主キーの集合 | 前後で同一 (262,885 行) |
| 変わったセルの列 | **corner_order_1〜4 だけ** (各 262,113 セル) |
| 個別に見た列 | win_odds / odds_fetched_at / odds_dataspec / win_popularity / jockey_code / jockey_short_name / burden_weight / horse_weight / weight_change_sign / weight_change_diff / finish_order / confirmed_order / finish_time / abnormal_code / final_3f / leg_quality_code / data_div / blood_register_num が **全行で完全一致** |
| NULL のまま | 772 行。すべて `data_div = 9` (中止になったレース) で確定着順が無い (走っていないので NULL が正しい) |

2026-05/06 の `odds_fetched_at` の刻印がある行も、`win_odds` と刻印の両方が変わっていない
(SE の再 upsert で起きる「発走前の刻印 + 確定オッズ」の PIT の汚染が、この処理では構造的に起きないことの E2E の確認)。

## 本番の backfill について (別のゲート)

本番 DB への実行は 10/05 以降に、非開催の確認 → ai-builder / fresh odds などの書き手の停止の確認 → DB / WAL の静止の確認 →
本番での dry-run → **ユーザーの明示の承認** → `--apply` → 適用後の監査 → ai-builder の互換確認、の順で行う。
`--apply` の開催日の拒否は安全装置の 1 つにすぎず、ユーザーの承認の代わりにはならない。
