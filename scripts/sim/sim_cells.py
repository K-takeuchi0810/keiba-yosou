"""人気 × オッズ帯 の全マス目を調べ、回収率 100% を超える領域があるか探す。

「探して一番良かったマス」は必ず良く見える (たくさん探せば偶然良いものが出る)
ので、多重比較の補正込みで判断する。
"""
import sys, sqlite3, math
sys.path.insert(0, ".")
FROM, TO = "20260101", "20260913"
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT h.win_popularity AS pop, h.win_odds AS odds, r.track_code AS track,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN p.tan_payout1 ELSE 0 END AS pay
      FROM horse_races h
      JOIN races r ON r.race_year=h.race_year AND r.race_month_day=h.race_month_day
       AND r.track_code=h.track_code AND r.kaiji=h.kaiji AND r.nichiji=h.nichiji
       AND r.race_num=h.race_num
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year || h.race_month_day) BETWEEN ? AND ?
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('', '00') AND h.win_odds > 0 AND p.tan_payout1 > 0
""", (FROM, TO)).fetchall()
conn.close()

def stats(v):
    n = len(v); m = sum(v)/n
    sd = math.sqrt(sum((x-m)**2 for x in v)/(n-1)) if n > 1 else 0
    return m, sd/math.sqrt(n) if n else 0

bands = [(1.0,2.0),(2.0,3.0),(3.0,5.0),(5.0,10.0),(10.0,20.0),(20.0,50.0),(50.0,1e4)]
cells = []
for p in range(1, 13):
    for lo_, hi_ in bands:
        v = [r["pay"]/100.0 for r in rows
             if str(r["pop"]).strip().isdigit() and int(r["pop"]) == p
             and lo_ <= r["odds"]/10.0 < hi_]
        if len(v) < 50:
            continue
        m, se = stats(v)
        cells.append((p, lo_, hi_, len(v), m, se))

n_cells = len(cells)
# 多重比較: n_cells 個試すので、片側 5% を n_cells で割る (ボンフェローニ)
from math import erf, sqrt
def z_for(alpha):
    lo_, hi_ = 0.0, 10.0
    for _ in range(200):
        mid = (lo_+hi_)/2
        if 1 - 0.5*(1+erf(mid/sqrt(2))) > alpha: lo_ = mid
        else: hi_ = mid
    return (lo_+hi_)/2
z_adj = z_for(0.05/n_cells)

print(f"調べたマス目: {n_cells} 個 (各 50 頭以上)")
print(f"多重比較の補正後に必要な z 値: {z_adj:.2f} (補正なしなら 1.64)")
print()
cells.sort(key=lambda c: -c[4])
print(f"{'人気':>4} {'オッズ帯':>13} {'頭数':>6} {'回収率':>7} {'補正なし下限':>11} {'補正後下限':>10}")
for p, lo_, hi_, n, m, se in cells[:8]:
    print(f"{p:>4} {lo_:5.1f}-{hi_:6.1f} {n:>6,} {m*100:6.1f}% "
          f"{(m-1.64*se)*100:10.1f}% {(m-z_adj*se)*100:9.1f}%")
print()
over = [c for c in cells if (c[4]-z_adj*c[5]) > 1.0]
print(f"補正後でも回収率 100% を超えるマス: {len(over)} 個")
naive = [c for c in cells if (c[4]-1.64*c[5]) > 1.0]
print(f"補正なしなら: {naive and len(naive) or 0} 個")
print()
print("=== 100% に届くには何が必要か (人気 1 番の帯で) ===")
v1 = [r["pay"]/100.0 for r in rows
      if str(r["pop"]).strip().isdigit() and int(r["pop"]) == 1]
hit = sum(1 for x in v1 if x > 0)/len(v1)
avg_odds = (sum(v1)/len(v1))/hit
print(f"  現状: 的中率 {hit*100:.1f}% / 的中時の平均配当 {avg_odds:.2f} 倍 "
      f"→ 回収率 {sum(v1)/len(v1)*100:.1f}%")
need = 1.0/avg_odds
print(f"  100% に届く的中率: {need*100:.1f}% "
      f"(現状比 +{(need/hit-1)*100:.0f}% 相対改善が必要)")
