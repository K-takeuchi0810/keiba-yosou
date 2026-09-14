"""「今の仕組みで回収率 100% を超えうるか」の天井シミュレーション。

モデルを動かさずに、市場側だけで到達可能な上限を測る。

考え方:
  どんな選び方をしても、選ばれる馬は必ずどれかの「人気帯」に属する。
  人気帯ごとの回収率が全部 100% を大きく下回るなら、帯の中で当たりを
  選り分けられない限り 100% には届かない。逆にどこかの帯が 100% を
  超えていれば、そこを狙う余地がある。
"""
import sys, sqlite3, math
sys.path.insert(0, ".")

FROM, TO = "20260101", "20260913"
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT h.win_popularity AS pop, h.win_odds AS odds,
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
       AND h.horse_num NOT IN ('', '00')
       AND h.win_odds > 0 AND p.tan_payout1 > 0
""", (FROM, TO)).fetchall()
conn.close()

def ci(vals):
    n = len(vals)
    if n < 2:
        return (0, 0, 0)
    m = sum(vals)/n
    sd = math.sqrt(sum((v-m)**2 for v in vals)/(n-1))
    se = sd/math.sqrt(n)
    return m, m-1.96*se, m+1.96*se

print(f"対象: {len(rows):,} 頭 (2026 年 JRA、確定払戻あり)")
print()
print("=== 人気順ごとの単勝回収率 (その人気の馬を全部買った場合) ===")
print(f"{'人気':>4} {'頭数':>7} {'的中率':>7} {'回収率':>7}  {'95%区間':>16}")
by_pop = {}
for r in rows:
    try:
        p = int(str(r["pop"]).strip() or 0)
    except ValueError:
        continue
    if p <= 0:
        continue
    by_pop.setdefault(p, []).append(r["pay"]/100.0)
best = None
for p in sorted(by_pop):
    if p > 12:
        continue
    v = by_pop[p]
    m, lo, hi = ci(v)
    hits = sum(1 for x in v if x > 0)
    mark = ""
    if best is None or m > best[1]:
        best = (p, m)
    print(f"{p:>4} {len(v):>7,} {hits/len(v)*100:6.1f}% {m*100:6.1f}%  [{lo*100:5.1f}%,{hi*100:5.1f}%]{mark}")
print()
print("=== オッズ帯ごとの単勝回収率 ===")
bands = [(1.0,1.5),(1.5,2.0),(2.0,3.0),(3.0,5.0),(5.0,10.0),(10.0,20.0),
         (20.0,50.0),(50.0,100.0),(100.0,10000.0)]
print(f"{'オッズ帯':>14} {'頭数':>7} {'的中率':>7} {'回収率':>7}  {'95%区間':>16}")
for lo_, hi_ in bands:
    v = [r["pay"]/100.0 for r in rows if lo_ <= r["odds"]/10.0 < hi_]
    if len(v) < 30:
        continue
    m, lo, hi = ci(v)
    hits = sum(1 for x in v if x > 0)
    print(f"{lo_:6.1f}-{hi_:6.1f} {len(v):>7,} {hits/len(v)*100:6.1f}% {m*100:6.1f}%  [{lo*100:5.1f}%,{hi*100:5.1f}%]")
