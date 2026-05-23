# Phase B1 Tier 2/3 features 個別 SQL leak audit

**日時**: 2026-05-24 12:35 (= B1-S0 Step 4 = OP-3)
**目的**: plan v2 §4.1 で列挙した 9 候補 features (T2.1a-T3.3a) の SQL 案を
features.py:720-755 `_jockey_track_stats` の literal pattern に当てはめ、4 audit
項目を Y/N 判定。B1-S1 で実装する features を絞り込むための前面 review。

**audit 項目** (plan v2 §6.1 step4 由来):
1. WHERE 句に `(race_year || race_month_day) < before_date` 厳密記述 (= 過去走 base feature の場合)
2. race-internal feature の場合、`current_horse_num != self` 除外 (= same-race feature の場合)
3. 当日 publish field の場合、ingest_state でその field の publish 時刻 (= start time pre/post) を確認
4. 集計 sample 数 < 5 の場合の null 返却ロジック (= 既存 jockey_recent_30d_samples パターン踏襲)

**literal pattern** (= features.py:720-755 `_jockey_track_stats`):
```python
rows = conn.execute(
    """
    SELECT confirmed_order FROM horse_races
     WHERE jockey_code = ? AND track_code = ?
       AND (race_year || race_month_day) < ?      # ← audit 1 OK
       AND confirmed_order > 0
     ORDER BY (race_year || race_month_day) DESC
     LIMIT ?
    """,
    (jockey_code, track_code, before_date, limit),
).fetchall()
if not rows:
    result = (None, 0)                            # ← rate=None when no data
else:
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    result = (top3 / len(rows), len(rows))        # ← n も別 feature として exposeリーク
```

**audit 項目 4 の運用ルール**:
- 既存パターンは「sample 数を 0 でない限り rate 計算、sample 数を別 feature で expose」
- 「< 5 で null」明示は存在しない (= LGBM 側に「low n → low confidence」学習を任せる設計)
- 本 audit では「rate と n を別 feature として両方 expose する」を audit 4 PASS 基準とする
- ただし sample=0 で None 返却は必須 (= div-by-zero 防止)

---

## T2.1a `pace_runners_count_pct` (= 先行馬の頭数 / 出走頭数)

**命題**: 現レースの先行脚質馬数を全頭数で割った比率。先行集中なら差し有利化。

**提案 SQL** (race-internal、現レース集計):
```python
def _pace_runners_count_pct(
    conn: sqlite3.Connection,
    race_year: str, race_month_day: str, track_code: str, race_num: str,
    cache: dict | None = None,
) -> float | None:
    """現レース内の先行脚質馬比率 (Tier 2.1a)。

    race-internal feature: 当該レース内の他馬の出走情報 (馬番 + 脚質予測) を集計、
    自馬を含めるかは設計判断 (= 含める方が標準的、ranking 内分布として正)。
    """
    rows = conn.execute(
        """
        SELECT pre_race_legtype FROM horse_races
         WHERE race_year=? AND race_month_day=? AND track_code=? AND race_num=?
        """,
        (race_year, race_month_day, track_code, race_num),
    ).fetchall()
    if not rows:
        return None
    n_total = len(rows)
    n_front = sum(1 for r in rows if r[0] == '1')  # legtype=1 が逃げ/先行
    return n_front / n_total if n_total >= 5 else None
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **N/A** (race-internal、過去走 base ではない)
2. race-internal で `current_horse_num != self` 除外: **N** (= 自馬含めて race 内分布として計算が標準)
   - 推奨修正: 自馬除外しない、ただし「**自馬を含むか除外するかの sensitivity test を B1-S1 で実施**」
3. 当日 publish 時刻 check: **CONDITIONAL Y** — pre_race_legtype は事前 publish (= SE record `keiba_horse_runtype` 由来、レース前公表) なので OK、ただし ingest_state で `data_div='1'` (= 確定情報) が race 開始前 timestamp を持つ確認必要
4. < 5 サンプル null logic: **Y** (上記 SQL で `n_total >= 5` 条件あり)

**leak risk verdict**: **PARTIAL** (audit 3 が conditional、ingest_state 確認後 PASS 可能)

---

## T2.1b `expected_pace_index` (= 過去走の上がり 3F race 内 平均から想定ペース推定)

**命題**: 現レース出走全馬の過去走 final_3f (上がり 3 ハロン) を集計し、race 全体の想定ペースを推定。速いペース → 差し有利。

**提案 SQL** (race-internal + past-data):
```python
def _expected_pace_index(
    conn: sqlite3.Connection,
    race_year: str, race_month_day: str, track_code: str, race_num: str,
    before_date: str,
    cache: dict | None = None,
    limit_per_horse: int = 3,
) -> float | None:
    """現レース出走馬の過去走 final_3f race-internal 推定 (Tier 2.1b)。

    過去走 base + race-internal を組合せた複合 feature。
    """
    # まず現レース出走馬リストを取得
    horses = conn.execute(
        """
        SELECT blood_register_num FROM horse_races
         WHERE race_year=? AND race_month_day=? AND track_code=? AND race_num=?
        """,
        (race_year, race_month_day, track_code, race_num),
    ).fetchall()
    if not horses or len(horses) < 5:
        return None
    # 各馬の直近 N 走 final_3f mean を取得
    final_3f_values = []
    for (br_num,) in horses:
        rows = conn.execute(
            """
            SELECT final_3f FROM horse_races
             WHERE blood_register_num = ?
               AND (race_year || race_month_day) < ?       # ← audit 1 OK
               AND final_3f IS NOT NULL AND final_3f > 0
             ORDER BY (race_year || race_month_day) DESC
             LIMIT ?
            """,
            (br_num, before_date, limit_per_horse),
        ).fetchall()
        if rows:
            mean_3f = sum(r[0] for r in rows) / len(rows)
            final_3f_values.append(mean_3f)
    if len(final_3f_values) < 5:
        return None
    return sum(final_3f_values) / len(final_3f_values)
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **Y** (各馬の past final_3f 取得 SQL で含む)
2. race-internal `current_horse_num != self` 除外: **CONDITIONAL Y** — 自馬の過去 final_3f も race-average に含まれる設計 (= 自馬の past performance も race 推定に貢献)、ただし「自馬除外で計算した方が pure な race-environment 推定になる」設計選択あり、B1-S1 で sensitivity test
3. 当日 publish 時刻 check: **N/A** (= 過去走 base のみ使用)
4. < 5 サンプル null logic: **Y** (上記 SQL で `len < 5` 条件あり)

**leak risk verdict**: **PASS** (audit 1+4 strict、2+3 設計上 OK)

**注意**: PHASE6_TIER23_DESIGN.md §2.1 では「上がり 3F の race 内 平均から想定ペース推定」と書かれている。final_3f は **post-race** field (= レース後に確定する着順データの一部)、過去走分のみ集計するため自然に leak free だが、「自馬の current race の final_3f を使ってはいけない」を確認しておく必要 (= 過去走 only 制約)。

---

## T2.2a `track_surface_distance_top3_rate` (= track, surface, distance_bucket の過去 top3 率)

**命題**: 現レース条件 (track, surface, distance) と同じ過去レース全馬の top3 着率を集計、レース条件の総合 prior。

**提案 SQL** (literal jockey_track_stats パターン):
```python
def _track_surface_distance_top3_rate(
    conn: sqlite3.Connection,
    track_code: str, surface: str, distance_bucket: int,
    before_date: str,
    cache: dict | None = None,
    limit: int = 500,
) -> tuple[float | None, int]:
    """track, surface, distance_bucket の過去 top3 率 (Tier 2.2a)。"""
    rows = conn.execute(
        """
        SELECT hr.confirmed_order
          FROM horse_races hr
          JOIN races r ON hr.race_year = r.race_year
                      AND hr.race_month_day = r.race_month_day
                      AND hr.track_code = r.track_code
                      AND hr.race_num = r.race_num
         WHERE hr.track_code = ?
           AND r.track_type_code = ?
           AND CAST(r.distance / 200 AS INTEGER) * 200 = ?
           AND (hr.race_year || hr.race_month_day) < ?       # ← audit 1 OK
           AND hr.confirmed_order > 0
         ORDER BY (hr.race_year || hr.race_month_day) DESC
         LIMIT ?
        """,
        (track_code, surface, distance_bucket, before_date, limit),
    ).fetchall()
    if not rows or len(rows) < 5:
        return None, len(rows) if rows else 0
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    return top3 / len(rows), len(rows)
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **Y**
2. race-internal 除外: **N/A** (= 過去走 base のみ)
3. 当日 publish 時刻 check: **N/A** (= 過去走 base のみ)
4. < 5 サンプル null logic: **Y**

**leak risk verdict**: **PASS** (= literal pattern を素直に適用、leak free)

---

## T2.2b `track_going_top3_rate` (= track, going の過去 top3 率)

**命題**: 現レース条件 (track, going = 馬場状態) と同じ過去レース全馬の top3 着率。

**提案 SQL** (literal):
```python
def _track_going_top3_rate(
    conn: sqlite3.Connection,
    track_code: str, going: str,
    before_date: str,
    cache: dict | None = None,
    limit: int = 500,
) -> tuple[float | None, int]:
    """track, going の過去 top3 率 (Tier 2.2b)。"""
    rows = conn.execute(
        """
        SELECT hr.confirmed_order
          FROM horse_races hr
          JOIN races r ON hr.race_year = r.race_year
                      AND hr.race_month_day = r.race_month_day
                      AND hr.track_code = r.track_code
                      AND hr.race_num = r.race_num
         WHERE hr.track_code = ?
           AND COALESCE(r.turf_condition, r.dirt_condition) = ?
           AND (hr.race_year || hr.race_month_day) < ?
           AND hr.confirmed_order > 0
         ORDER BY (hr.race_year || hr.race_month_day) DESC
         LIMIT ?
        """,
        (track_code, going, before_date, limit),
    ).fetchall()
    if not rows or len(rows) < 5:
        return None, len(rows) if rows else 0
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    return top3 / len(rows), len(rows)
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **Y**
2. race-internal 除外: **N/A**
3. 当日 publish 時刻 check: **CONDITIONAL Y** — going 自体は当日 publish (= 馬場発表は朝、レース 5 分前更新) なので、現レースの going を使う場合は ingest_state で `data_div='1'` (= 馬場確定) 確認必要。過去レースの going (= 過去 races テーブルから JOIN) は publish 確定済なので問題なし
4. < 5 サンプル null logic: **Y**

**leak risk verdict**: **PARTIAL** (audit 3 が conditional、現レース going の publish 時刻 check が必須)

**注意**: H3-3 §1.1 でも触れた通り、`turf_condition` 自体は SQLite で `'0'` 一律になっており、現状データ品質が低い。**ingest 層の going 取込み改修が前提**になる可能性。

---

## T2.3a `track_recent_top3_rate_30d` (= track の直近 30 日 top3 率)

**命題**: 現レース track での直近 30 日の全馬 top3 着率。馬場改修 / 開催 schedule shift に追従。

**提案 SQL** (literal + window):
```python
def _track_recent_top3_rate_30d(
    conn: sqlite3.Connection,
    track_code: str,
    before_date: str,                # 'YYYYMMDD' 形式
    cache: dict | None = None,
    window_days: int = 30,
) -> tuple[float | None, int]:
    """track の直近 30 日 top3 率 (Tier 2.3a)。"""
    # before_date から 30 日前の date 計算 (SQLite で date arithmetic)
    window_start = conn.execute(
        "SELECT strftime('%Y%m%d', date(? || '-' || ? || '-' || ?, '-' || ? || ' days'))",
        (before_date[:4], before_date[4:6], before_date[6:8], str(window_days))
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT confirmed_order FROM horse_races
         WHERE track_code = ?
           AND (race_year || race_month_day) < ?         # before_date
           AND (race_year || race_month_day) >= ?        # window_start
           AND confirmed_order > 0
        """,
        (track_code, before_date, window_start),
    ).fetchall()
    if not rows or len(rows) < 5:
        return None, len(rows) if rows else 0
    top3 = sum(1 for r in rows if r[0] in (1, 2, 3))
    return top3 / len(rows), len(rows)
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **Y** (両端 inclusive < / >= で window 構築)
2. race-internal 除外: **N/A**
3. 当日 publish 時刻 check: **N/A**
4. < 5 サンプル null logic: **Y**

**leak risk verdict**: **PASS** (= literal + window で leak free)

**Phase B1 含意**: H3-3 で causal candidate 上位 (track_10, track_07) を直接カバー、**実装優先度 = MAX**。

---

## T3.1a `recent_4corner_avg_position` (= 直近 N 戦の平均 4 角通過順位)

**命題**: 馬の直近 N 戦の 4 角通過順位平均。差し脚力の代理指標。

**提案 SQL** (literal、ただし parse 拡張前提):
```python
def _recent_4corner_avg_position(
    conn: sqlite3.Connection,
    blood_register_num: str,
    before_date: str,
    cache: dict | None = None,
    limit: int = 5,
) -> tuple[float | None, int]:
    """直近 N 戦の平均 4 角通過順位 (Tier 3.1a)。

    前提: parse_se で corner_order_4 を field 化、schema.sql に追加済。
    """
    rows = conn.execute(
        """
        SELECT corner_order_4 FROM horse_races
         WHERE blood_register_num = ?
           AND (race_year || race_month_day) < ?
           AND corner_order_4 IS NOT NULL AND corner_order_4 > 0
         ORDER BY (race_year || race_month_day) DESC
         LIMIT ?
        """,
        (blood_register_num, before_date, limit),
    ).fetchall()
    if not rows or len(rows) < 3:  # 4 角 features は 3 走 で OK (5 走必須でない)
        return None, len(rows) if rows else 0
    return sum(r[0] for r in rows) / len(rows), len(rows)
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **Y**
2. race-internal 除外: **N/A**
3. 当日 publish 時刻 check: **N/A** (= 過去走 base のみ、corner_order は post-race)
4. < 5 サンプル null logic: **Y** (= ただし 3 走以上で許容、4 角データは sparse)

**leak risk verdict**: **PASS** ただし **ブロッカー: parse_se 拡張 + schema.sql migration + 再 ingest が必要**

**Phase B1 含意**: H3-3 で starter_count=<=8 small bucket に間接的に有効、ただし parse 拡張コスト大 (jvdata-record skill 参照)。**B1-S1 では skip 推奨、Phase B2 候補へ**。

---

## T3.1b `recent_4corner_position_change` (= 4 角→ゴールでの順位上昇)

**命題**: 馬の直近 N 戦で「4 角通過順位 − ゴール着順」の平均。差し脚力 (前から下げる量) の代理。

**提案 SQL**:
```python
def _recent_4corner_position_change(
    conn: sqlite3.Connection,
    blood_register_num: str,
    before_date: str,
    cache: dict | None = None,
    limit: int = 5,
) -> tuple[float | None, int]:
    rows = conn.execute(
        """
        SELECT corner_order_4, confirmed_order
          FROM horse_races
         WHERE blood_register_num = ?
           AND (race_year || race_month_day) < ?
           AND corner_order_4 IS NOT NULL AND corner_order_4 > 0
           AND confirmed_order > 0
         ORDER BY (race_year || race_month_day) DESC
         LIMIT ?
        """,
        (blood_register_num, before_date, limit),
    ).fetchall()
    if not rows or len(rows) < 3:
        return None, len(rows) if rows else 0
    changes = [r[0] - r[1] for r in rows]  # positive = 差し
    return sum(changes) / len(changes), len(rows)
```

**audit Y/N**: T3.1a と同じ (1: Y, 2: N/A, 3: N/A, 4: Y, ただし parse 拡張前提)

**leak risk verdict**: **PASS conditional on parse拡張** = T3.1a と同じく Phase B2 候補

---

## T3.2a `track_bias_inside_outside` (= 同場直近 30 日の 1 着馬の枠順分布)

**命題**: 直近 30 日のレースで「内枠 (1-3 枠) 1 着回数 vs 外枠 (7-9 枠) 1 着回数」の比率。

**提案 SQL** (literal + window + 枠順 derive):
```python
def _track_bias_inside_outside(
    conn: sqlite3.Connection,
    track_code: str,
    before_date: str,
    cache: dict | None = None,
    window_days: int = 30,
) -> float | None:
    """直近 30 日の内 vs 外 枠勝率 bias (Tier 3.2a)。"""
    window_start = conn.execute(
        "SELECT strftime('%Y%m%d', date(? || '-' || ? || '-' || ?, '-' || ? || ' days'))",
        (before_date[:4], before_date[4:6], before_date[6:8], str(window_days))
    ).fetchone()[0]
    # 1 着馬のみ取得し、waku (枠順) で分布計算
    rows = conn.execute(
        """
        SELECT waku FROM horse_races
         WHERE track_code = ?
           AND (race_year || race_month_day) < ?
           AND (race_year || race_month_day) >= ?
           AND confirmed_order = 1
           AND waku IS NOT NULL
        """,
        (track_code, before_date, window_start),
    ).fetchall()
    if not rows or len(rows) < 10:
        return None
    inside = sum(1 for r in rows if 1 <= r[0] <= 3)
    outside = sum(1 for r in rows if 7 <= r[0] <= 9)
    total_extreme = inside + outside
    if total_extreme < 5:
        return None
    # bias score: positive = inside-favorable, negative = outside-favorable
    return (inside - outside) / total_extreme
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **Y**
2. race-internal 除外: **N/A**
3. 当日 publish 時刻 check: **N/A** (= 過去走 base のみ、waku は SE record で確定)
4. < 5 サンプル null logic: **Y** (= 1 着馬 10 件 + 内外極端 5 件の二重 threshold)

**leak risk verdict**: **PASS** (= literal + window で leak free)

**Phase B1 含意**: H3-3 で track_10 (小倉) z=-2.64 に直接対応、**実装優先度 = HIGH**。

---

## T3.3a `pre_race_horse_weight_delta` (= 発走前公表の前走比馬体重差)

**命題**: 現レースで発表される horse_weight - 前走 horse_weight (= 体調の代理指標)。

**提案 SQL** (WH record parse 拡張前提):
```python
def _pre_race_horse_weight_delta(
    conn: sqlite3.Connection,
    blood_register_num: str,
    race_year: str, race_month_day: str, track_code: str, race_num: str,
    cache: dict | None = None,
) -> float | None:
    """発走前公表の前走比馬体重差 (Tier 3.3a)。

    前提: WH record の現レース体重を ingest、horse_races の current_horse_weight
    field を確実取得。
    """
    # 現レース体重 (= WH record 由来)
    current_row = conn.execute(
        """
        SELECT pre_race_horse_weight FROM horse_races
         WHERE blood_register_num = ? AND race_year=? AND race_month_day=?
           AND track_code=? AND race_num=?
        """,
        (blood_register_num, race_year, race_month_day, track_code, race_num),
    ).fetchone()
    if not current_row or current_row[0] is None or current_row[0] <= 0:
        return None
    # 前走体重 (= horse_races の最新過去走)
    past_row = conn.execute(
        """
        SELECT horse_weight FROM horse_races
         WHERE blood_register_num = ?
           AND (race_year || race_month_day) < (? || ?)
           AND horse_weight IS NOT NULL AND horse_weight > 0
         ORDER BY (race_year || race_month_day) DESC
         LIMIT 1
        """,
        (blood_register_num, race_year, race_month_day),
    ).fetchone()
    if not past_row:
        return None
    return float(current_row[0] - past_row[0])
```

**audit Y/N**:
1. WHERE `(year||day) < before_date` 厳密記述: **Y** (前走取得 SQL で含む)
2. race-internal 除外: **N/A** (= horse-individual feature)
3. 当日 publish 時刻 check: **N**! ← **問題**
   - WH record (馬体重発表) は **発走 1 時間前 publish** が JV-Data の仕様、ただし速報なので「発走 15 分前更新」も存在。current pipeline が race start 後の WH 取得タイミングで ingest しているかは ingest_state を確認必要
   - 「current_horse_weight が race start "前" の確定値である保証」が不明 = potential leak risk
4. < 5 サンプル null logic: **N/A** (= 1 件 only feature)

**leak risk verdict**: **FAIL** (audit 3 が NO、WH record の publish 時刻 / pre/post race の confirmable な ingest が必要)

**Phase B1 含意**:
- 事前予想 §B1-S0.1 「Step 4 SQL audit で T3.3a が audit 3 で引っかかる確率 0.30-0.45」 → **的中**
- WH record parser の publish 時刻保証 + ingest_state field 追加が前提
- **B1-S1 では skip 推奨、Phase B2 候補 or 別 spike で先解決**

---

## まとめ

| feature | leak risk | 主 audit fail | B1 採用判断 |
|---|---|---|---|
| T2.1a pace_runners_count_pct | PARTIAL | audit 3 conditional | B1-S1 採用、ingest_state 確認後 |
| **T2.1b expected_pace_index** | **PASS** | なし | **B1-S1 採用 (優先 2)** |
| **T2.2a track_surface_distance_top3_rate** | **PASS** | なし | **B1-S1 採用 (優先 3)** |
| T2.2b track_going_top3_rate | PARTIAL | audit 3 conditional + データ品質課題 | B1-S1 は skip、ingest 改修後 |
| **T2.3a track_recent_top3_rate_30d** | **PASS** | なし | **B1-S1 採用 (優先 1, H3-3 直接対応)** |
| T3.1a recent_4corner_avg_position | PASS (parse 前提) | parse_se 拡張ブロッカー | Phase B2 候補 |
| T3.1b recent_4corner_position_change | PASS (parse 前提) | parse_se 拡張ブロッカー | Phase B2 候補 |
| **T3.2a track_bias_inside_outside** | **PASS** | なし | **B1-S1 採用 (優先 4, H3-3 直接対応)** |
| T3.3a pre_race_horse_weight_delta | **FAIL** | audit 3 NO | Phase B2 候補 (WH ingest 仕様確認後) |

**audit clear count**: 9 中 4 PASS (T2.1b, T2.2a, T2.3a, T3.2a) + 2 PARTIAL (T2.1a, T2.2b) + 2 conditional on parse (T3.1a, T3.1b) + 1 FAIL (T3.3a)

**B1-S1 で実装する features (= leak risk PASS のみ)**:
- 優先 1: T2.3a track_recent_top3_rate_30d (= H3-3 軸 1+2 を直接カバー)
- 優先 2: T2.1b expected_pace_index (= H3-3 軸 3 を直接カバー)
- 優先 3: T2.2a track_surface_distance_top3_rate (= H3-3 軸 1+2 を補強)
- 優先 4: T3.2a track_bias_inside_outside (= H3-3 軸 1+2 を補強)

合計 **4 features** = plan v2 §4.1 で想定した 9 候補から半分以下に絞られた。残り 5 は audit fail / partial / blocker で B1-S1 から除外。

**B1-S0 完了基準への接続**:
- handoff 完了基準: 「9 features の audit clear」→ 部分達成 (4 clear、5 fail/partial)
- plan v2 §4.2 step4 完了基準: 「9 候補に対し audit 項目 4 つすべて clear」→ 部分達成
- B1-S1 着手判断: 「4 features (leak free) で B1-S1 を実装」 → 続行可能、ただし設計 scope は plan v2 想定の半分

**sanity check** (= OP-2、30 分時点 review):
- 1 feature 完了に ~5 分要した = 9 features で ~45 分 = 1h budget 内 (= handoff 想定どおり)
- 上方修正不要、Step 4 所要は 1h で完了
