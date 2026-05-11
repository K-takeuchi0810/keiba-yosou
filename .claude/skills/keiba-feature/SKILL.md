---
name: keiba-feature
description: 競馬予想の特徴量・スコアリングルールを追加・調整するスキル。「予想ロジック改善」「特徴量追加」「シグナル追加」「脚質を考慮」「休み明け / 馬場状態 / 距離適性 / 騎手厩舎相性 を取り入れる」「印 (◎○▲) のつけ方を変更」「ルールベースの重み調整」のような要求で必ず使う。`predictor/features.py` と `predictor/rules.py` の既存パターンに合わせて新シグナルを足すための型・落とし穴・パターン集を持つ。
---

# 予想特徴量・ルール追加スキル

## 何のためのスキル？

`predictor/features.py` (特徴量計算) と `predictor/rules.py` (スコアリング) を拡張するときに、既存パターンと整合する形で新シグナルを足すためのガイド。

具体的には:
- `compute_features` の戻り値 dict にどう新フィールドを足すか
- `_score_one` でどう加点・減点するか
- 過去走 SQL の組み立て方 (主キー結合の罠)
- データ品質によるスキップ判定 (件数不足・欠損値)
- スコアレンジの設計 (基準 50、印 5 段階)
- 「暫定」フラグの扱い

## 既存アーキテクチャの理解

```
入力: horse dict (SE 由来) + race dict (RA 由来) + DB conn
  ↓ predictor/features.py
特徴量 dict (例: {recent_avg_finish: 3.2, jockey_win_rate: 0.15, ...})
  ↓ predictor/rules.py の _score_one()
score (float) + reasons (list[str])
  ↓ predict_race()
[Prediction(horse_num, score, rank, mark, rationale)] (馬数分)
```

スコアは **基準値 50** からの加減算。印は上位 5 頭に `◎ ○ ▲ △ ☆`。

## 新シグナル追加の標準フロー

1. **シグナルの仮説を立てる** — 「○○なら勝ちやすい」を 1 文で
2. **必要データが DB にあるか確認** — 無ければ先に [jvdata-record スキル](../jvdata-record/SKILL.md) でレコード追加
3. **`features.py` に算出関数を追加** — 過去走 SQL or 集計
4. **`compute_features()` の戻り値に新フィールドを追加** — `feat["xxx"] = ...`
5. **`rules.py:_score_one()` に加点ロジックを追加** — `if feat.get("xxx"): score += N; reasons.append("...")`
6. **重みを調整** — 後述の「重み設計のコツ」参照
7. **ノイズ確認** — 全馬 0 点になっていないか / 全馬同点になっていないか

## features.py の規約

### 既存ヘルパ
```python
horse_past_runs(conn, blood_register_num, before_date, limit=12)
    # 指定馬の過去走 (新しい順)。confirmed_order > 0 に絞り済み
jockey_winrate(conn, jockey_code, before_date, sample=100)
    # → (rate or None, sample_count)
trainer_winrate(conn, trainer_code, before_date, sample=100)
```

### 新ヘルパを書くときの規約

```python
def xxx_signal(
    conn: sqlite3.Connection,
    key: str,                    # 馬・騎手・調教師コード等
    before_date: str,            # YYYYMMDD 8 桁。指定日「より前」のデータのみ使う
    limit_or_sample: int = N,
) -> tuple[float | None, int]:   # (シグナル値 or 不足時 None, サンプル数)
    if not key or key == "0" * len(key):
        return None, 0
    rows = conn.execute("...").fetchall()
    if not rows:
        return None, 0
    # ... 計算 ...
    return value, len(rows)
```

**3 つの重要ルール**:
1. **`before_date` より前** のデータだけ使う (リーク防止)。本番予想時に未来データが見えると、バックテストで過大評価される
2. **無効なキー** (`"00000"` など) は早期 None 返し
3. **件数も返す** — 件数が少ないと信頼区間広いので、`_score_one` 側で「最低 N 件以上」のフィルタが必要

### 過去走 SQL の罠

`races` と `horse_races` を結合するときは **主キー全 6 列を JOIN ON に書く** こと。`race_year` だけで結合するとデカルト積になる。

```sql
JOIN races r
  ON hr.race_year = r.race_year
 AND hr.race_month_day = r.race_month_day
 AND hr.track_code = r.track_code
 AND hr.kaiji = r.kaiji
 AND hr.nichiji = r.nichiji
 AND hr.race_num = r.race_num
```

**before_date は文字列連結比較**:

```sql
WHERE (hr.race_year || hr.race_month_day) < ?
  -- ↑ 渡す側は YYYYMMDD 8 桁の文字列
```

整数キャストするとゼロ埋めが落ちて誤判定する (例: `"20240105"` < `"20231231"` は文字列なら False = 正しい)。

## rules.py の重み設計のコツ

### スコアレンジ

- **基準**: 50
- **強いシグナル** (例: マイニング 1 位、騎手勝率 20%超): +12〜+25
- **中シグナル** (例: 同距離複勝経験): +4〜+8
- **弱シグナル** (例: 重賞経験あり): +2〜+5
- **減点** (例: 直近平均着順悪い): -5〜-15
- **失格級減点** (異常区分): -1000 (実質除外)

全シグナル合計の理論最大は +60〜+80 程度に収める。これを超えると 1 シグナル依存になり過剰適合。

### 件数による信頼区間ガード

サンプルが少ないシグナルは信頼できないのでスコア反映しない。例:

```python
jr = feat.get("jockey_win_rate")
jn = feat.get("jockey_rides", 0)
if jr is not None and jn >= 30:   # 最低 30 騎乗
    if jr >= 0.20: score += 12
    elif jr >= 0.12: score += 6
    elif jr < 0.04: score -= 4
```

`jn >= 30` のような最低件数フィルタがないと、新人騎手が「1 戦 1 勝 (= 100%)」で爆上がりする。

### 同点回避

`_score_one` のスコアが全馬同じになると `rules.py:predict_race` が「暫定」扱いに落ちる。発走前は情報少ないので暫定になりがちだが、確定後 (オッズ・マイニング入手後) も全馬同点ならルール側のバグ。

判定: `predict_race` の `score_range = max - min` が 1.5 未満なら全員暫定。

## よく追加されるシグナル一覧

[references/signals.md](references/signals.md) に既存 + 追加候補のシグナルを優先順位付きで列挙。代表例:

### A. 既存シグナル (過去走ベース)
- 直近 3 走平均着順
- 直近最高着順
- 同種トラック実績 (芝/ダート/障害)
- 同距離適性 (±100m)
- 重賞経験

### B. 既存シグナル (騎手・調教師)
- 騎手勝率 (直近 100 騎乗)
- 調教師勝率 (直近 100 出走)

### C. 既存シグナル (当日)
- マイニング予想順位
- 単勝人気
- 異常区分

### D. 未実装で効きそう (推奨追加順)

| 優先 | シグナル | 必要データ | 重みの目安 |
|---|---|---|---|
| 1 | 馬場状態適性 (良/重) | `RA.turf_condition`, 過去走 | +5 / -3 |
| 2 | 休み明け / 連闘 | `SE` 過去走の日付差 | -3 / +2 |
| 3 | 同コース実績 (track_code 一致) | `SE` 過去走 | +5 |
| 4 | 距離区分適性 (短距離/マイル/中/長) | distance | +4 |
| 5 | 性別限定戦の符号 | `RA.race_symbol_code` | フィルタ |
| 6 | 斤量変動 | 前走 burden_weight 比 | +2 / -2 |
| 7 | 騎手×厩舎相性 | jockey_code × trainer_code 過去走 | +5 |
| 8 | 馬体重トレンド (発走前) | `WH` (要追加実装) | +2 / -2 |
| 9 | 父系適性 (ダート短距離血統 等) | `BLOD` (要追加実装) | +3 |
| 10 | 上がり 3F の絶対値 | `SE.final_3f` | +5 |

詳細は [references/signals.md](references/signals.md)。

## 落とし穴

### 1. 全馬に同じスコアを足してもランキングは変わらない
「斤量重い順に減点」のような全馬一律な減点は無意味。**馬間で差がつくシグナル**だけ意味がある。

### 2. 平均と最大の混同
`recent_avg_finish` (平均) と `recent_best_finish` (最高) は別シグナル。両方使って良いが、相関が高いので重みは控えめに。

### 3. 標本の偏り
- 引退間近の騎手は最近の騎乗が少なく、データが古い。`before_date` で切らないと最新シグナルにならない
- 新馬は過去走ゼロ。`past_count == 0` の場合、過去走ベースのスコアは全部 0 になる → 「事前情報のみ」フォールバック

### 4. データ取得タイミング
- マイニング予想 (`mining_predicted_order`): 発走 30 分前以降にしか入らない (それまでは 0)
- 単勝人気 (`win_popularity`): 発走直前確定
- 確定オッズ (`win_odds`): 発走直前
- 確定着順 (`confirmed_order`): レース後

「予想生成時刻」によって使えるシグナルが違う。`feat.get("xxx") or 0` のような **0 と未取得を区別する**フォールバックを必ず書く。

### 5. NaN / None の伝播
`compute_features` の戻り値に None が入ると `_score_one` で `None * 5` のような型エラー。**`if feat.get("xxx") is not None`** で必ずガード。

## 簡単な動作確認

新シグナルを足したら:

```bash
.venv32\Scripts\python.exe -c "
from db import open_db
from predictor.rules import predict_race

with open_db() as conn:
    # 適当なレースを 1 つ取って予想を出す
    race = dict(conn.execute('SELECT * FROM races LIMIT 1').fetchone())
    horses = [dict(r) for r in conn.execute(
        '''SELECT * FROM horse_races
           WHERE race_year=? AND race_month_day=? AND track_code=?
             AND kaiji=? AND nichiji=? AND race_num=?''',
        (race['race_year'], race['race_month_day'], race['track_code'],
         race['kaiji'], race['nichiji'], race['race_num'])
    ).fetchall()]
    preds = predict_race(horses, conn=conn, race=race)
    for p in preds[:5]:
        print(p.rank, p.mark, p.horse_num, f'{p.score:.1f}', p.rationale)
"
```

スコア分布が広がっているか、印が偏っていないか目視。

## 機械学習に切り替えたくなったら

ルールベースで頭打ちになったら ML への移行を検討。`features.py` の戻り値 dict はそのまま特徴量ベクトルとして LightGBM 等に流せる。学習用ラベルは `confirmed_order == 1` (勝ち) や `<= 3` (複勝圏)。

ただし JV-Data の規約上、**学習データを外部に持ち出せない**ため、すべてローカル学習で完結させる。`scikit-learn` / `lightgbm` を `requirements.txt` に追加してから別モジュール `predictor/ml.py` で実装するのが筋。

ルールベース版とのアンサンブル (`final_score = 0.5 * rule_score + 0.5 * ml_score`) も有効。
