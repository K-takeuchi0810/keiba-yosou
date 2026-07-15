# features.py の horse_num='00' 汚染調査

監査メタ: 実施日 2026-07-15 / 対象DBの`horse_num='00'`行数 406 / 判定時git sha `34671c4ae5c887af8cd281c957ad258b663dc526`

## 結論

- 調査対象: `predictor/features.py` の `horse_races` 参照19箇所
- 汚染あり: **0件**
- DB内のプレースホルダは406行。`blood_register_num`、`jockey_code`、`trainer_code` は全行に値があるため識別子条件だけでは除外できないが、406行すべて `confirmed_order=0`、`corner_order_4=0/NULL` であり、現行クエリの成績条件で自然除外される。

確認SQL:

```sql
SELECT COUNT(*),
       SUM(confirmed_order > 0),
       SUM(corner_order_4 > 0)
FROM horse_races
WHERE horse_num='00';
-- 406|0|0
```

## クエリ別判定

| 行 | 関数・用途 | 汚染 | 除外理由 | 影響対象の特徴量 |
|---:|---|---|---|---|
| 132 | `recent_corner_stats` | なし | `corner_order_4 > 0` かつ `confirmed_order > 0` | `recent_4corner_avg_position`, `recent_4corner_position_change`, samples |
| 190 | `grade_class_close_loss` 勝馬時刻サブクエリ | なし | `hr2.confirmed_order = 1` かつ `finish_time > 0` | `grade_close_loss`, `grade_midfield_close` の基準時刻 |
| 200 | `grade_class_close_loss` 対象馬過去走 | なし | `hr.confirmed_order > 0` かつ `finish_time > 0` | `grade_close_loss`, `grade_midfield_close` |
| 257 | `horse_past_runs` | なし | 血統登録番号で絞った上で `hr.confirmed_order > 0` | 近走着順・時計・上がり・人気・オッズ・脚質・馬体重等の過去走系全般 |
| 297 | `relative_race_metrics` | なし | レースキーで絞った上で `confirmed_order > 0` | `relative_time_diff`, `final3_rank` 系 |
| 330 | `jockey_winrate` | なし | `confirmed_order > 0` | `jockey_win_rate`, `jockey_rides` |
| 355 | `trainer_winrate` | なし | `confirmed_order > 0` | `trainer_win_rate`, `trainer_runs` |
| 377 | `same_day_track_bias` | なし | `confirmed_order BETWEEN 1 AND 3` | 当日脚質傾向のlegacy判定・sample数 |
| 420 | `same_day_track_bias_detail` | なし | `confirmed_order BETWEEN 1 AND 3` | `same_day_bias_score`, `same_day_bias_note`, samples |
| 476 | `same_day_gate_bias_detail` | なし | `confirmed_order BETWEEN 1 AND 3` | `same_day_gate_bias_score`, `same_day_gate_bias_note`, samples |
| 536 | `sire_surface_stats` | なし | `hr.confirmed_order > 0` | 父系の馬場別top3率・samples（legacy helper） |
| 657 | `_bloodline_stats_uncached` | なし | 共通WHERE句に `hr.confirmed_order > 0` | 父・母父のsurface/distance/going別top3率・samples |
| 714 | `_track_recent_stats` | なし | `confirmed_order > 0` | `track_recent_30d/90d_*` |
| 761 | `_entity_recent_stats` | なし | `confirmed_order > 0` | 騎手30/90日、厩舎30日、馬90日のtop3率・samples |
| 798 | `_jockey_track_stats` | なし | `confirmed_order > 0` | `jockey_track_top3_rate`, samples |
| 833 | `_trainer_track_stats` | なし | `confirmed_order > 0` | `trainer_track_top3_rate`, samples |
| 872 | `_horse_track_stats` | なし | `confirmed_order > 0` | `horse_track_top3_rate`, samples |
| 917 | `_sire_track_stats` | なし | `hr.confirmed_order > 0` | `sire_track_top3_rate`, samples |
| 1272 | cornerデータ存在確認 | なし | `corner_order_4 > 0` | 4角特徴量計算の有効化フラグ |

現時点では `features.py` への修正は不要。将来、着順・4角条件を持たない `horse_races` 集計を追加する場合は、明示的に `horse_num != '00'` を付ける必要がある。
