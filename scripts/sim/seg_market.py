"""問いを変える: 「市場そのものが下手なのはどこか」を探す。

これまでは「特徴がオッズに情報を足せるか」を問うてきた。その問い方では
市場を基準に置いているので、答えは構造的に「市場が正しい」に寄る。

ここでは市場を検証対象にする。レースの種類ごとに、
  ・1 番人気の回収率 (市場が本命をどれだけ正しく値付けしているか)
  ・人気薄の回収率 (歪みの大きさ)
を測り、**市場の値付けが崩れている領域**を探す。
崩れている場所があれば、そこが独自性を出せる余地。
"""
import sys, sqlite3, math
sys.path.insert(0, ".")
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT h.win_popularity pop, h.win_odds/10.0 odds, h.age,
           r.distance dist, r.track_type_code tt, r.grade_code grade,
           r.track_code tc,
           (SELECT COUNT(*) FROM horse_races x
             WHERE x.race_year=h.race_year AND x.race_month_day=h.race_month_day
               AND x.track_code=h.track_code AND x.kaiji=h.kaiji
               AND x.nichiji=h.nichiji AND x.race_num=h.race_num
               AND x.horse_num NOT IN ('','00')) starters,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN p.tan_payout1/100.0 ELSE 0.0 END pay
      FROM horse_races h
      JOIN races r ON r.race_year=h.race_year AND r.race_month_day=h.race_month_day
       AND r.track_code=h.track_code AND r.kaiji=h.kaiji AND r.nichiji=h.nichiji
       AND r.race_num=h.race_num
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
""").fetchall()
conn.close()

def ci(v):
    n = len(v)
    if n < 2: return (0, 0, 0)
    m = sum(v)/n
    sd = math.sqrt(sum((x-m)**2 for x in v)/(n-1)); se = sd/math.sqrt(n)
    return m, m-1.96*se, m+1.96*se

def seg_report(title, keyfn):
    print(f"\n=== {title} ===")
    print(f"{'区分':>20} {'1番人気n':>9} {'1人気回収':>9} {'95%区間':>16} {'全馬回収':>9}")
    groups = {}
    for r in rows:
        k = keyfn(r)
        if k is None: continue
        groups.setdefault(k, []).append(r)
    for k in sorted(groups, key=lambda x: str(x)):
        g = groups[k]
        fav = [x["pay"] for x in g if str(x["pop"]).strip() == "1"]
        if len(fav) < 80: continue
        m, lo, hi = ci(fav)
        allr = sum(x["pay"] for x in g)/len(g)
        star = "  ←" if lo > 0.90 else ""
        print(f"{str(k):>20} {len(fav):9,d} {m*100:8.1f}% "
              f"[{lo*100:5.1f}%,{hi*100:5.1f}%] {allr*100:8.1f}%{star}")

def fs(r):
    s = r["starters"]
    if s <= 8: return "1. 8頭以下"
    if s <= 11: return "2. 9-11頭"
    if s <= 14: return "3. 12-14頭"
    if s <= 16: return "4. 15-16頭"
    return "5. 17頭以上"
seg_report("出走頭数ごと", fs)

def dist(r):
    d = r["dist"] or 0
    if d < 1400: return "1. 1400m未満"
    if d < 1800: return "2. 1400-1800"
    if d < 2200: return "3. 1800-2200"
    return "4. 2200m以上"
seg_report("距離ごと", dist)

seg_report("芝/ダート", lambda r: {"1":"芝","2":"ダート"}.get(str(r["tt"] or "").strip()[:1]))
seg_report("競馬場ごと", lambda r: f"track {r['tc']}")

def age(r):
    try: a = int(str(r["age"]).strip())
    except (ValueError, TypeError): return None
    return "1. 2歳" if a == 2 else ("2. 3歳" if a == 3 else "3. 4歳以上")
seg_report("馬齢ごと", age)

def grade(r):
    g = str(r["grade_code"] if "grade_code" in r.keys() else r["grade"] or "").strip()
    return "重賞(G1-G3)" if g in ("A","B","C") else "平場・特別"
seg_report("重賞かどうか", grade)
