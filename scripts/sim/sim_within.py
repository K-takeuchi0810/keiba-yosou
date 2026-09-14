"""モデルの ◎ が「同じ人気帯の中で」当たりを見分けられているかを測る。

見分けられていない = モデルは価格帯を選んでいるだけで、市場を超える情報が無い。
実際に配信した予想 (prediction_log) を使う。
"""
import sys, sqlite3, math
sys.path.insert(0, ".")
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# 母集団: 2026 年 JRA の全馬 (人気帯ごとの基準値)
base = conn.execute("""
    SELECT h.win_popularity AS pop,
           SUM(CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                    THEN 1 ELSE 0 END) AS wins, COUNT(*) AS n,
           SUM(CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                    THEN p.tan_payout1 ELSE 0 END) AS pay
      FROM horse_races h
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year || h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('', '00') AND h.win_odds > 0 AND p.tan_payout1 > 0
     GROUP BY h.win_popularity
""").fetchall()
base_rate = {}
for b in base:
    p = str(b["pop"]).strip()
    if p.isdigit() and b["n"]:
        base_rate[int(p)] = (b["wins"]/b["n"], b["pay"]/b["n"]/100.0, b["n"])

# モデルが実際に配信した ◎
picks = conn.execute("""
    WITH latest AS (
      SELECT pl.*, ROW_NUMBER() OVER (
          PARTITION BY race_year,race_month_day,track_code,kaiji,nichiji,race_num,horse_num
          ORDER BY generated_at DESC) rn
        FROM prediction_log pl WHERE mark='◎')
    SELECT l.win_popularity AS pop,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(l.horse_num AS INTEGER)
                THEN p.tan_payout1 ELSE 0 END AS pay
      FROM latest l
      JOIN payouts p ON p.race_year=l.race_year AND p.race_month_day=l.race_month_day
       AND p.track_code=l.track_code AND p.kaiji=l.kaiji AND p.nichiji=l.nichiji
       AND p.race_num=l.race_num
     WHERE l.rn=1 AND p.tan_payout1 > 0
""").fetchall()
conn.close()

by_pop = {}
for r in picks:
    p = str(r["pop"]).strip()
    if p.isdigit():
        by_pop.setdefault(int(p), []).append(r["pay"]/100.0)

print(f"配信した ◎ の総数: {sum(len(v) for v in by_pop.values())}")
print()
print("◎ が選んだ人気帯ごとに、モデルの成績と『その帯をただ買った場合』を比べる")
print(f"{'人気':>4} {'◎数':>5} | {'◎的中率':>8} {'帯の基準':>8} {'差':>7} | "
      f"{'◎回収率':>8} {'帯の基準':>8} {'差':>7}")
tot_n = tot_hit = 0; tot_pay = 0.0; tot_exp_hit = 0.0; tot_exp_pay = 0.0
for p in sorted(by_pop):
    v = by_pop[p]
    if p not in base_rate or len(v) < 10:
        continue
    hit = sum(1 for x in v if x > 0)/len(v)
    roi = sum(v)/len(v)
    b_hit, b_roi, _ = base_rate[p]
    print(f"{p:>4} {len(v):>5} | {hit*100:7.1f}% {b_hit*100:7.1f}% {(hit-b_hit)*100:+6.1f}pt | "
          f"{roi*100:7.1f}% {b_roi*100:7.1f}% {(roi-b_roi)*100:+6.1f}pt")
    tot_n += len(v); tot_hit += sum(1 for x in v if x > 0); tot_pay += sum(v)
    tot_exp_hit += b_hit*len(v); tot_exp_pay += b_roi*len(v)
print()
print(f"合計 {tot_n} 件:")
print(f"  的中率  モデル {tot_hit/tot_n*100:.1f}%  vs  同じ帯を買った場合 {tot_exp_hit/tot_n*100:.1f}%"
      f"  → 差 {(tot_hit-tot_exp_hit)/tot_n*100:+.1f}pt")
print(f"  回収率  モデル {tot_pay/tot_n*100:.1f}%  vs  同じ帯を買った場合 {tot_exp_pay/tot_n*100:.1f}%"
      f"  → 差 {(tot_pay-tot_exp_pay)/tot_n*100:+.1f}pt")
se = math.sqrt(tot_exp_hit/tot_n*(1-tot_exp_hit/tot_n)/tot_n)
print(f"  的中率の差の標準誤差: {se*100:.1f}pt "
      f"→ 差は {abs(tot_hit/tot_n - tot_exp_hit/tot_n)/se:.2f} 標準誤差ぶん")
