"""候補 3: 出走取消・除外の選別テスト。

仮説: 有力馬が取り消されると残りの馬の勝つ確率は上がるが、市場がそれを
      織り込みきれていないのではないか。

やること: 確定オッズで層を揃えたうえで、「取消のあったレースの馬」と
          「取消の無いレースの馬」で勝率と回収率を比べる。
          確定オッズで揃えてなお差が出るなら、市場は最後まで織り込めていない。
"""
import sys, sqlite3, random
sys.path.insert(0, ".")
random.seed(20260915)
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# レースごとの取消・除外頭数 (scratch_status 1=取消 2=除外)
scr = {}
for r in conn.execute("""SELECT race_year,race_month_day,track_code,kaiji,nichiji,race_num,
                                COUNT(*) n
                           FROM race_scratches
                          WHERE scratch_status IN ('1','2') AND race_year='2026'
                          GROUP BY 1,2,3,4,5,6"""):
    scr[tuple(r[i] for i in range(6))] = r["n"]

rows = conn.execute("""
    SELECT h.race_year,h.race_month_day,h.track_code,h.kaiji,h.nichiji,h.race_num,
           h.horse_num, h.win_odds/10.0 AS odds,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN p.tan_payout1/100.0 ELSE 0.0 END AS pay
      FROM horse_races h
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
""").fetchall()
conn.close()

recs = []
for r in rows:
    key = (r["race_year"], r["race_month_day"], r["track_code"],
           r["kaiji"], r["nichiji"], r["race_num"])
    recs.append((r["odds"], scr.get(key, 0), r["pay"]))
print(f"対象: {len(recs):,} 頭")
n_scr = sum(1 for x in recs if x[1] > 0)
print(f"  うち取消のあったレースの馬: {n_scr:,} ({n_scr/len(recs)*100:.1f}%)")

BUCKETS = [(1.0,3.0),(3.0,7.0),(7.0,15.0),(15.0,40.0),(40.0,1e9)]
print()
print(f"{'オッズ帯':>12} {'群':>10} {'頭数':>7} {'勝率':>7} {'回収率':>8}")
for lo, hi in BUCKETS:
    sub = [x for x in recs if lo <= x[0] < hi]
    for name, g in (("取消あり", [x for x in sub if x[1] > 0]),
                    ("取消なし", [x for x in sub if x[1] == 0])):
        if len(g) < 100: continue
        print(f"{lo:5.0f}-{hi if hi<1e8 else 999:5.0f} {name:>10} {len(g):7,d} "
              f"{sum(1 for x in g if x[2]>0)/len(g)*100:6.1f}% "
              f"{sum(x[2] for x in g)/len(g)*100:7.1f}%")
    print()

def diff(sample):
    num = den = 0.0
    for lo, hi in BUCKETS:
        sub = [x for x in sample if lo <= x[0] < hi]
        a = [x for x in sub if x[1] > 0]; b = [x for x in sub if x[1] == 0]
        if len(a) < 100 or len(b) < 100: continue
        w = min(len(a), len(b))
        num += w*(sum(x[2] for x in a)/len(a) - sum(x[2] for x in b)/len(b)); den += w
    return num/den if den else 0.0

def wdiff(sample):
    num = den = 0.0
    for lo, hi in BUCKETS:
        sub = [x for x in sample if lo <= x[0] < hi]
        a = [x for x in sub if x[1] > 0]; b = [x for x in sub if x[1] == 0]
        if len(a) < 100 or len(b) < 100: continue
        w = min(len(a), len(b))
        num += w*(sum(1 for x in a if x[2]>0)/len(a) - sum(1 for x in b if x[2]>0)/len(b)); den += w
    return num/den if den else 0.0

o_roi, o_win = diff(recs), wdiff(recs)
br, bw = [], []
for _ in range(2000):
    s = [recs[random.randrange(len(recs))] for _ in range(len(recs))]
    br.append(diff(s)); bw.append(wdiff(s))
br.sort(); bw.sort()
print(f"帯を揃えた「取消あり − 取消なし」")
print(f"  勝率の差  : {o_win*100:+.2f}pt  95%区間 [{bw[50]*100:+.2f}, {bw[1949]*100:+.2f}]pt")
print(f"  回収率の差: {o_roi*100:+.1f}pt  95%区間 [{br[50]*100:+.1f}, {br[1949]*100:+.1f}]pt")
