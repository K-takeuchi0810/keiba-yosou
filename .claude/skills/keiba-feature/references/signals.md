# 競馬予想シグナル カタログ

実装済みと未実装のシグナルを、効きそうな順に整理。各シグナルの実装スケッチ付き。

## カテゴリ別

### 1. 過去走パフォーマンス (実装済み)

| シグナル | 計算方法 | 重み目安 |
|---|---|---|
| 直近 3 走平均着順 | `mean(past[:3].confirmed_order)` | ±15 |
| 直近最高着順 | `min(past[:3].confirmed_order)` | +8 (= 1) |
| 過去走数 | `len(past)` | フィルタ用 |

### 2. 適性 (一部実装済み)

| シグナル | 計算 | 状態 | 重み |
|---|---|---|---|
| 同種トラック (芝/ダート) 勝利数 | `track_type_code` 一致 | 実装済 | +5/win |
| 同種トラック複勝率 | 1-3 着比率 | 実装済 | +4 |
| 同距離 (±100m) 出走数 | `abs(dist - p.dist) <= 100` | 実装済 | +3 |
| 同距離複勝率 | 同上 + 1-3 着 | 実装済 | +4 |
| 重賞経験 | `grade_code in (A,B,C,G,H,I)` | 実装済 | +5 |
| 同コース (track_code) | `track_code` 一致 | **未実装** | +5 |
| 距離区分適性 (短/マイル/中/長) | distance バケット | **未実装** | +4 |
| 馬場状態適性 | `turf_condition` × 過去成績 | **未実装** | +5/-3 |

### 3. 騎手・調教師 (一部実装済み)

| シグナル | 計算 | 状態 | 重み |
|---|---|---|---|
| 騎手勝率 (直近 100) | wins / rides | 実装済 | ±12 |
| 調教師勝率 (直近 100) | wins / runs | 実装済 | ±6 |
| 騎手 × 厩舎 相性 | jockey × trainer の過去成績 | **未実装** | +5 |
| 騎手の同コース勝率 | jockey × track_code | **未実装** | +5 |
| 騎手の今開催連勝数 | 当週内勝利数 | **未実装** | +3 |
| 厩舎の今年勝率 | trainer × race_year | **未実装** | +3 |

### 4. 当日情報 (一部実装済み)

| シグナル | データ源 | 状態 | 重み |
|---|---|---|---|
| マイニング予想順位 | `SE.mining_predicted_order` | 実装済 | +20 (=1) |
| 単勝人気 | `SE.win_popularity` | 実装済 | +15 (=1) |
| 異常区分 | `SE.abnormal_code` | 実装済 | -1000 |
| 馬体重トレンド (前走比) | `SE.weight_change_diff` | 部分実装 | ±2 |
| 馬体重絶対値 | `SE.horse_weight` | **未実装** | 適正レンジ評価 |
| 発走前馬体重 | `WH` レコード | **未実装** | ±3 |
| 発走前オッズ変動 | `O1` 時系列 | **未実装** | +5 (急落=注目) |

### 5. レース間隔 (未実装)

| シグナル | 計算 | 重み |
|---|---|---|
| 休み明け (60 日超) | 前走から日数 | -3 |
| 連闘 (1 週) | 前走から 7 日以内 | +2 (人気馬) / -2 |
| 適切な間隔 (2-4 週) | 14-28 日 | +1 |

### 6. レース条件 (未実装)

| シグナル | 計算 | 用途 |
|---|---|---|
| 性別限定戦の符号 | `RA.race_symbol_code` | フィルタ (出走資格チェック) |
| 斤量変動 | 前走 burden_weight 比 | +2 (減量) / -2 (増量) |
| 牝馬限定戦 | symbol_code | 性別フィルタ |
| 重賞 (G1/G2/G3) | grade_code | レース格付け |

### 7. 上がりタイム (未実装)

| シグナル | 計算 | 重み |
|---|---|---|
| 直近 3F 絶対値 | `final_3f` | 33 秒台で +5 |
| 直近 3F 順位 | レース内順位 | +3 |

### 8. 血統 (未実装、要 BLOD 取り込み)

| シグナル | 計算 | 重み |
|---|---|---|
| 父系のダート適性 | sire × ダート連対率 | +3 |
| 父系の距離適性 | sire × 距離連対率 | +3 |
| 母父 (BMS) 効果 | broodmare sire | +2 |

### 9. 調教 (未実装、要 SLOP/WOOD 取り込み)

| シグナル | 計算 | 重み |
|---|---|---|
| 直前坂路最速時計 | 過去 1 ヶ月の最速 | +3 |
| ウッド時計 | 同上 | +3 |
| 調教の動き (一杯/馬なり) | 仕上げ強度 | +2 |

## 実装スケッチ集

### 同コース実績

```python
def same_course_stats(conn, blood_register_num, track_code, before_date, limit=20):
    rows = conn.execute("""
        SELECT confirmed_order FROM horse_races
        WHERE blood_register_num = ?
          AND track_code = ?
          AND (race_year || race_month_day) < ?
          AND confirmed_order > 0
        ORDER BY race_year DESC, race_month_day DESC
        LIMIT ?
    """, (blood_register_num, track_code, before_date, limit)).fetchall()
    if not rows:
        return None, 0
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    return top3 / len(rows), len(rows)
```

### 距離区分適性

```python
def distance_bucket(d: int) -> str:
    if d <= 1400: return "sprint"
    if d <= 1800: return "mile"
    if d <= 2200: return "middle"
    return "long"

def same_bucket_top3(conn, blood_register_num, race_distance, before_date):
    bucket = distance_bucket(race_distance)
    past = horse_past_runs(conn, blood_register_num, before_date)
    same = [p for p in past if distance_bucket(p["distance"]) == bucket]
    if not same:
        return None, 0
    top3 = sum(1 for p in same if p["confirmed_order"] in (1, 2, 3))
    return top3 / len(same), len(same)
```

### 休み明け

```python
def days_since_last_run(conn, blood_register_num, before_date):
    row = conn.execute("""
        SELECT race_year, race_month_day FROM horse_races
        WHERE blood_register_num = ?
          AND (race_year || race_month_day) < ?
          AND confirmed_order > 0
        ORDER BY race_year DESC, race_month_day DESC
        LIMIT 1
    """, (blood_register_num, before_date)).fetchone()
    if not row:
        return None
    from datetime import date
    last = date(int(row[0]), int(row[1][:2]), int(row[1][2:]))
    today = date(int(before_date[:4]), int(before_date[4:6]), int(before_date[6:]))
    return (today - last).days
```

### 馬場状態適性

```python
def track_condition_stats(conn, blood_register_num, track_type_code, condition, before_date):
    """良馬場/重馬場での過去成績。
    track_type_code: '10' (芝1200) 等。turf/dirt 判定は web/codes.py:track_type 参照。
    condition: turf_condition or dirt_condition の値 ('1'=良 '2'=稍重 '3'=重 '4'=不良)
    """
    is_turf = 10 <= int(track_type_code) <= 22
    cond_col = "r.turf_condition" if is_turf else "r.dirt_condition"
    rows = conn.execute(f"""
        SELECT hr.confirmed_order
        FROM horse_races hr JOIN races r
          ON hr.race_year = r.race_year AND hr.race_month_day = r.race_month_day
         AND hr.track_code = r.track_code AND hr.kaiji = r.kaiji
         AND hr.nichiji = r.nichiji AND hr.race_num = r.race_num
        WHERE hr.blood_register_num = ?
          AND {cond_col} = ?
          AND (hr.race_year || hr.race_month_day) < ?
          AND hr.confirmed_order > 0
    """, (blood_register_num, condition, before_date)).fetchall()
    if not rows:
        return None, 0
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    return top3 / len(rows), len(rows)
```

## 重み調整の検証手順

1. 新シグナル追加 → 1 開催 (土日 2 日分) で予想を出す
2. 印 (◎○▲) の分布を見る — 1 シグナルに極端に支配されていないか
3. [keiba-backtest スキル](../keiba-backtest/SKILL.md) で過去 1 年の的中率・回収率を測る
4. 新シグナル追加前後で **回収率改善** していなければ重みを下げる or 削除

ルールベースは「足し算で改善」が前提。**単独で +回収率を出さないシグナルは入れない**。
