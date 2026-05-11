---
name: keiba-backtest
description: 競馬予想の精度評価・バックテスト・回収率計算を実装するスキル。「予想の的中率を測る」「バックテスト走らせる」「回収率を出す」「単勝/複勝/馬連 のシミュレーション」「過去のデータで予想精度を確かめる」「ルール変更前後で比較」「リーク防止」のような要求で必ず使う。HR (払戻) レコードの取り込みが前提なので、未取り込みなら jvdata-record スキルへ誘導する。リーク防止 (未来データ参照禁止) ・買い目戦略 (単複・馬連 BOX 等) ・回収率の正しい計算 を扱う。
---

# 予想精度・バックテストスキル

## 何のためのスキル？

予想ロジック (`predictor/rules.py`) の良し悪しを **客観的な数字** で測るためのバックテスト基盤。

- 「直近 1 年で◎が何回 1 着になったか (的中率)」
- 「100 円ずつ買って何円返ってきたか (回収率)」
- 「ルール A と ルール B、どちらが優秀か」

これが無いと「特徴量足したら強くなった気がする」止まりで進歩しない。

## 前提

`HR` (払戻) レコードが DB に取り込まれている必要がある。未実装なら先に [jvdata-record スキル](../jvdata-record/SKILL.md) を使って `HR` (PDF p13, レコード長 719) のパーサ + `payouts` テーブルを作る。

最低限必要なテーブル:

```sql
CREATE TABLE payouts (
    race_year       TEXT NOT NULL,
    race_month_day  TEXT NOT NULL,
    track_code      TEXT NOT NULL,
    kaiji           TEXT NOT NULL,
    nichiji         TEXT NOT NULL,
    race_num        TEXT NOT NULL,
    -- 単勝
    tan_horse_num1  TEXT, tan_payout1 INTEGER,
    tan_horse_num2  TEXT, tan_payout2 INTEGER,  -- 同着用
    tan_horse_num3  TEXT, tan_payout3 INTEGER,
    -- 複勝 (1-3 着分)
    fuku_horse_num1 TEXT, fuku_payout1 INTEGER,
    fuku_horse_num2 TEXT, fuku_payout2 INTEGER,
    fuku_horse_num3 TEXT, fuku_payout3 INTEGER,
    fuku_horse_num4 TEXT, fuku_payout4 INTEGER,  -- 同着用 (5 着までありうる)
    fuku_horse_num5 TEXT, fuku_payout5 INTEGER,
    -- 枠連・馬連・ワイド・馬単・3 連複・3 連単
    -- ... (HR 仕様書参照, 全部実装しなくてもOK)
    PRIMARY KEY (race_year, race_month_day, track_code, kaiji, nichiji, race_num)
);
```

すべての券種を取り込まなくても **単勝・複勝** さえあれば的中率は測れる。

## バックテストの全体フロー

```
1. 評価期間を決める (例: 2024 年 1〜12 月)
2. 期間内の全レースを SELECT
3. 各レースで:
   a. 予想時に「未来データ」が見えないように conn を制限
   b. predict_race(horses, conn, race) を実行
   c. ◎ (rank=1) の horse_num を取得
   d. payouts と照合して的中判定 + 払戻金取得
4. 集計:
   - 単勝的中率 = 1 着的中 / 総レース
   - 単勝回収率 = sum(払戻) / (100 * レース数)
   - 複勝的中率 = 3 着以内的中 / 総レース
   - 複勝回収率
5. 比較: ルール A vs B でこれらの数字を並べる
```

## リーク防止 (最重要)

**バックテストで最大の失敗** は「未来データを使って予想して回収率が異常に高くなる」こと。具体的には:

### NG パターン

- `compute_features` で過去走を引くときに `before_date` を渡し忘れる
- 評価対象レースの `confirmed_order` がそのまま「過去走」として返ってくる
- 騎手・調教師勝率の集計に評価レースの結果が含まれる
- 過去走集計の中に「未来のレース」が混入

`features.py` の `before_date` フィルタ (`(race_year || race_month_day) < ?`) はリーク防止のためにあるので、**バックテスト時は絶対に省略しない**。

### OK パターン

```python
# レース日を before_date として明示的に渡す
before = race["race_year"] + race["race_month_day"]
preds = predict_race(horses, conn=conn, race=race)
# ↑ 内部で compute_features が before_date=before を使う
```

`features.py` の現状実装は `race_dict["race_year"] + race_dict["race_month_day"]` を使ってちゃんと当該日より前にフィルタしている ([features.py:109](predictor/features.py)) ので、**race_dict を正しく渡せばリークは起きない**。これを書き換えるとリークするので注意。

## 標準的なバックテストスクリプト

`scripts/backtest.py` を新規作成して、こんなインターフェイスで実装するのが推奨:

```python
# scripts/backtest.py
"""指定期間のレースで予想を実行し、的中率・回収率を計算する。

usage:
    python -m scripts.backtest --from 20240101 --to 20241231
    python -m scripts.backtest --from 20240101 --to 20241231 --bet tan
    python -m scripts.backtest --from 20240101 --to 20241231 --bet fuku
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import open_db
from predictor.rules import predict_race


def list_races(conn, from_date, to_date):
    return [dict(r) for r in conn.execute("""
        SELECT * FROM races
        WHERE (race_year || race_month_day) BETWEEN ? AND ?
        ORDER BY race_year, race_month_day, track_code, race_num
    """, (from_date, to_date)).fetchall()]


def horses_for_race(conn, race):
    return [dict(r) for r in conn.execute("""
        SELECT * FROM horse_races
        WHERE race_year=? AND race_month_day=? AND track_code=?
          AND kaiji=? AND nichiji=? AND race_num=?
        ORDER BY CAST(horse_num AS INTEGER)
    """, (race["race_year"], race["race_month_day"], race["track_code"],
          race["kaiji"], race["nichiji"], race["race_num"])).fetchall()]


def get_payout(conn, race, horse_num, bet_type):
    """bet_type='tan' or 'fuku'。horse_num が的中していれば払戻金を返す、外れなら 0。"""
    row = conn.execute("""
        SELECT * FROM payouts
        WHERE race_year=? AND race_month_day=? AND track_code=?
          AND kaiji=? AND nichiji=? AND race_num=?
    """, (race["race_year"], race["race_month_day"], race["track_code"],
          race["kaiji"], race["nichiji"], race["race_num"])).fetchone()
    if not row:
        return 0
    row = dict(row)
    if bet_type == "tan":
        for i in (1, 2, 3):
            if row.get(f"tan_horse_num{i}") == horse_num:
                return row.get(f"tan_payout{i}", 0) or 0
    elif bet_type == "fuku":
        for i in (1, 2, 3, 4, 5):
            if row.get(f"fuku_horse_num{i}") == horse_num:
                return row.get(f"fuku_payout{i}", 0) or 0
    return 0


def run_backtest(from_date, to_date, bet_type="tan"):
    with open_db() as conn:
        races = list_races(conn, from_date, to_date)
        n_total = 0
        n_hit = 0
        total_bet = 0
        total_return = 0
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            preds = predict_race(horses, conn=conn, race=race)
            top = next((p for p in preds if p.rank == 1), None)
            if not top or not top.mark:
                continue
            n_total += 1
            total_bet += 100
            payout = get_payout(conn, race, top.horse_num, bet_type)
            if payout > 0:
                n_hit += 1
                total_return += payout
        return {
            "races": n_total,
            "hits": n_hit,
            "hit_rate": n_hit / n_total if n_total else 0,
            "bet_total": total_bet,
            "return_total": total_return,
            "return_rate": total_return / total_bet if total_bet else 0,
        }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    ap.add_argument("--bet", default="tan", choices=["tan", "fuku"])
    args = ap.parse_args()
    result = run_backtest(args.from_date, args.to_date, args.bet)
    print(f"レース数:   {result['races']}")
    print(f"的中数:     {result['hits']}")
    print(f"的中率:     {result['hit_rate']*100:.1f}%")
    print(f"投資総額:   {result['bet_total']:,} 円")
    print(f"払戻総額:   {result['return_total']:,} 円")
    print(f"回収率:     {result['return_rate']*100:.1f}%")
```

## 評価指標の解釈

### 単勝的中率 / 回収率

| 指標 | ランダム | 人気馬狙い | プロ目標 |
|---|---|---|---|
| 単勝的中率 | ~7% | ~30% | 30%+ |
| 単勝回収率 | ~75% | ~75% | 100%+ |
| 複勝的中率 | ~21% | ~60% | 60%+ |
| 複勝回収率 | ~80% | ~80% | 100%+ |

**JRA の控除率** は単勝・複勝で約 20%、馬連で約 22.5%、3 連単で約 27.5%。つまり **何も考えず買うと回収率は約 75-80%** に収束する。これを超えてプラス収支にするのが予想ロジックの目標。

### 過信に注意

- レース数が **200 未満だと統計的にブレが大きい**。最低でも 1 年 (3000+ レース)
- 高グレード重賞 (G1) 限定の的中率は標本少なすぎて信頼できない
- 「特定の競馬場・距離だけ強い」のような偏りはオーバーフィット可能性あり

## 比較戦略 (ルール A vs B)

ルールを変えたら、**同じ期間で A と B を別々に走らせて比較**:

```python
# A: 既存ルール
result_a = run_backtest("20240101", "20241231")
# B: 新ルール (predictor/rules.py を編集後 or 別モジュール化)
result_b = run_backtest_with_rules_v2("20240101", "20241231")

print(f"A 的中率: {result_a['hit_rate']*100:.1f}% / 回収率: {result_a['return_rate']*100:.1f}%")
print(f"B 的中率: {result_b['hit_rate']*100:.1f}% / 回収率: {result_b['return_rate']*100:.1f}%")
```

差が小さい (1-2%) ときは偶然の可能性大。ブートストラップ (期間をランダムサンプリング) で信頼区間を出すと安心。

## 買い目戦略のバリエーション

単純に「◎を単勝買い」以外にも:

| 戦略 | 説明 | 必要券種 |
|---|---|---|
| 単勝 ◎ | 印 1 位を単勝 | 単勝 |
| 複勝 ◎ | 印 1 位を複勝 | 複勝 |
| 馬連 ◎-○ | 印 1-2 位 BOX | 馬連 |
| 馬連 ◎流し | 印 1 位から印 2,3,4 位へ流し | 馬連 |
| 馬単 ◎→○▲ | 印 1 位 1 着固定 | 馬単 |
| ワイド ◎-上位 | 印 1 位とワイドで広く | ワイド |
| 3 連複 ◎-○-▲△☆ | 1 位固定で 2,3 着流し | 3 連複 |

各戦略の払戻を `payouts` テーブルから引いてシミュレーションする。資金管理 (固定 100 円 / 期待値ベース変動) も別軸の設計事項。

## オッズ閾値による絞り込み

「オッズ N 倍以下は買わない」「N 倍以上の妙味馬だけ買う」のようなフィルタを入れると回収率が変わる:

```python
# 例: 単勝 5-30 倍ゾーンに絞る
horse_odds = horse["win_odds"] / 10.0  # SE.win_odds は ×10 整数
if not (5.0 <= horse_odds <= 30.0):
    continue  # この馬は買わない
```

人気馬 (1-3 倍) は的中率高いが回収率は低い、穴馬 (50 倍超) は的中率激低い、という分布なので **5-20 倍ゾーン** が妙味とよく言われる。これも実データで検証する。

## レポート形式

人間が読める形でこういう風にまとめると比較しやすい:

```
==== バックテスト結果 ====
期間:       2024/01/01 〜 2024/12/31
ルール:     v2 (馬場状態適性追加)
買い目:     ◎単勝 100円固定

レース数:   3245
印◎付き:    3198 (98.5%)
的中数:     1051
的中率:     32.9%
投資:       319,800 円
払戻:       352,400 円
回収率:     110.2%
収支:       +32,600 円

会場別:
  東京:     35.1% / 115.2%
  中山:     31.8% / 108.7%
  京都:     30.5% / 105.3%
  ...

距離別:
  〜1400m:  33.2% / 112.4%
  〜1800m:  31.5% / 107.8%
  〜2200m:  33.8% / 113.5%
  2400m〜:  29.1% / 102.6%
```

会場別・距離別ブレイクダウンは弱点を見つけるのに有効。**ある条件だけ回収率が極端に高い場合はオーバーフィット疑い**。

## 結果の永続化

バックテスト結果を `data/backtest/<timestamp>.json` 等に保存しておくと、後でルール変更前後の比較に使える:

```python
import json
from datetime import datetime
out = Path(f"data/backtest/{datetime.now():%Y%m%d_%H%M%S}.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({
    "from": from_date, "to": to_date, "bet": bet_type,
    "rule_version": "v2",  # 必ずバージョン記録
    **result,
}, indent=2, ensure_ascii=False))
```

## 落とし穴

### 1. 払戻データが全レースに揃っていない
過去 1 年分の `RACE` を取り込んでも、`HR` (払戻) は別タイミングで提供されることがある。バックテスト前に `payouts` テーブルの件数を確認:
```sql
SELECT COUNT(*) FROM races WHERE (race_year||race_month_day) BETWEEN '20240101' AND '20241231';
SELECT COUNT(*) FROM payouts WHERE (race_year||race_month_day) BETWEEN '20240101' AND '20241231';
```
件数が大きく違ったら HR 取り込み漏れ。

### 2. 異常レース (中止) の混入
`races` テーブルに中止レース (`data_div='9'`) が混じる可能性。`abnormal_code != '0'` の馬は除外。

### 3. 同着の扱い
1 着同着・3 着同着で複勝が 4-5 頭出ることがある。`fuku_horse_num4 / fuku_horse_num5` まで照合しないと取りこぼす。

### 4. 「印つき」の判定
`predict_race` のスコアが全馬同点 (`is_tentative` で True) のときは、印は馬番順に付くだけで意味がない。バックテストで「暫定」レースは除外するか別カウントするのが筋。

### 5. オッズの欠損
`SE.win_odds` は確定後の値。バックテストではこれを使って良いが、**実運用では発走前オッズを使うので結果が変わる**。実運用シミュレーションするなら `O1` レコードの時系列オッズを使う必要がある。
