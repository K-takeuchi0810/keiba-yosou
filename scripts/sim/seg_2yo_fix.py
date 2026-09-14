"""キャリア層別 (修正版): キャリアは **そのレースより前** の出走のみで数える。

前版は DB 全体の出走回数で層分けしており、そのレースより後の出走も含んでいた。
「後でたくさん走った馬」が厚い層に寄るので、層の意味が歪む。
"""
import sys, sqlite3, math, collections
sys.path.insert(0, ".")
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# 全出走 (確定済み) を時系列で並べ、各馬の「そのレース時点までの出走回数」を作る
print("キャリア (レース時点まで) を計算中...")
prior = {}
cnt = collections.Counter()
for r in conn.execute("""SELECT blood_register_num bn, (race_year||race_month_day) d,
                                track_code tc, kaiji ka, nichiji ni, race_num rn
                           FROM horse_races
                          WHERE confirmed_order > 0 AND horse_num NOT IN ('','00')
                          ORDER BY d, track_code, race_num"""):
    key = (r["bn"], r["d"], r["tc"], r["ka"], r["ni"], r["rn"])
    prior[key] = cnt[r["bn"]]          # このレースより前の出走回数
    cnt[r["bn"]] += 1

rows = conn.execute("""
    SELECT h.race_year ry, h.race_month_day rmd, h.track_code tc, h.kaiji ka,
           h.nichiji ni, h.race_num rn, h.blood_register_num bn,
           (h.race_year||h.race_month_day) d,
           h.win_popularity pop,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN p.tan_payout1/100.0 ELSE 0.0 END pay
      FROM horse_races h
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
""").fetchall()
conn.close()

byrace = {}
for r in rows:
    k = (r["ry"], r["rmd"], r["tc"], r["ka"], r["ni"], r["rn"])
    byrace.setdefault(k, []).append(r)

def ci(v):
    n = len(v)
    if n < 2: return (0, 0, 0)
    m = sum(v)/n; sd = math.sqrt(sum((x-m)**2 for x in v)/(n-1))
    return m, m-1.96*sd/math.sqrt(n), m+1.96*sd/math.sqrt(n)

strata = {}
for k, g in byrace.items():
    vals = [prior.get((x["bn"], x["d"], x["tc"], x["ka"], x["ni"], x["rn"]), 0) for x in g]
    avg = sum(vals)/len(vals)
    if avg < 2: s = "1. 極浅 (平均2走未満)"
    elif avg < 5: s = "2. 浅い (2-5走)"
    elif avg < 10: s = "3. 中 (5-10走)"
    else: s = "4. 厚い (10走以上)"
    strata.setdefault(s, []).extend(g)

print()
print(f"{'キャリアの層':>22} {'馬数':>8} {'1人気n':>7} {'1人気回収':>9} {'95%区間':>16} "
      f"{'全馬回収':>9} {'歪み':>7}")
for s in sorted(strata):
    g = strata[s]
    fav = [x["pay"] for x in g if str(x["pop"]).strip() == "1"]
    if len(fav) < 50: continue
    m, lo, hi = ci(fav)
    allr = sum(x["pay"] for x in g)/len(g)
    print(f"{s:>22} {len(g):8,d} {len(fav):7,d} {m*100:8.1f}% "
          f"[{lo*100:5.1f}%,{hi*100:5.1f}%] {allr*100:8.1f}% {(m-allr)*100:+6.1f}pt")

print()
print("=== 最も浅い層を人気別に ===")
g = strata.get("1. 極浅 (平均2走未満)", [])
print(f"{'人気':>4} {'頭数':>7} {'的中率':>7} {'回収率':>8} {'95%区間':>16}")
for p in range(1, 7):
    v = [x["pay"] for x in g if str(x["pop"]).strip() == str(p)]
    if len(v) < 50: continue
    m, lo, hi = ci(v)
    print(f"{p:>4} {len(v):7,d} {sum(1 for x in v if x>0)/len(v)*100:6.1f}% "
          f"{m*100:7.1f}% [{lo*100:5.1f}%,{hi*100:5.1f}%]")
