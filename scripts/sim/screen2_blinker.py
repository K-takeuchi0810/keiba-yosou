"""候補 2: ブリンカーの選別テスト。

仮説: ブリンカー着用、特に **初装着** は変わり身の予兆だが、
      市場が織り込みきれていないのではないか。

確定オッズで層を揃えたうえで比較する。初装着は「前走が非着用」で判定。
"""
import sys, sqlite3, random, math
sys.path.insert(0, ".")
random.seed(20260915)
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT h.blood_register_num bn, (h.race_year||h.race_month_day) d,
           h.blinker b, h.win_odds/10.0 odds,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN p.tan_payout1/100.0 ELSE 0.0 END pay
      FROM horse_races h
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
     ORDER BY h.blood_register_num, d
""").fetchall()

# 初装着 = 前走が非着用 (同じ馬の 1 つ前のレース)
prev = {}
recs = []
for r in rows:
    bn = r["bn"]; b = (r["b"] or "0").strip()
    p_b = prev.get(bn)
    first = (b == "1" and p_b == "0")
    prev[bn] = b
    recs.append((r["odds"], b, first, r["pay"]))
conn.close()
print(f"対象: {len(recs):,} 頭 / ブリンカー着用 {sum(1 for x in recs if x[1]=='1'):,} / "
      f"うち初装着 {sum(1 for x in recs if x[2]):,}")

BUCKETS = [(1.0,3.0),(3.0,7.0),(7.0,15.0),(15.0,40.0),(40.0,1e9)]
print()
print(f"{'オッズ帯':>12} {'群':>10} {'頭数':>7} {'勝率':>7} {'回収率':>8}")
for lo, hi in BUCKETS:
    sub = [x for x in recs if lo <= x[0] < hi]
    for name, g in (("着用", [x for x in sub if x[1] == "1"]),
                    ("非着用", [x for x in sub if x[1] == "0"]),
                    ("初装着", [x for x in sub if x[2]])):
        if len(g) < 100: continue
        print(f"{lo:5.0f}-{hi if hi<1e8 else 999:5.0f} {name:>10} {len(g):7,d} "
              f"{sum(1 for x in g if x[3]>0)/len(g)*100:6.1f}% "
              f"{sum(x[3] for x in g)/len(g)*100:7.1f}%")
    print()

def diff(sample, pick):
    num = den = 0.0
    for lo, hi in BUCKETS:
        sub = [x for x in sample if lo <= x[0] < hi]
        a = [x for x in sub if pick(x)]; b = [x for x in sub if x[1] == "0" and not x[2]]
        if len(a) < 100 or len(b) < 100: continue
        w = min(len(a), len(b))
        num += w*(sum(x[3] for x in a)/len(a) - sum(x[3] for x in b)/len(b)); den += w
    return num/den if den else 0.0

def wdiff(sample, pick):
    num = den = 0.0
    for lo, hi in BUCKETS:
        sub = [x for x in sample if lo <= x[0] < hi]
        a = [x for x in sub if pick(x)]; b = [x for x in sub if x[1] == "0" and not x[2]]
        if len(a) < 100 or len(b) < 100: continue
        w = min(len(a), len(b))
        num += w*(sum(1 for x in a if x[3]>0)/len(a) - sum(1 for x in b if x[3]>0)/len(b)); den += w
    return num/den if den else 0.0

for label, pick in (("着用 − 非着用", lambda x: x[1] == "1"),
                    ("初装着 − 非着用", lambda x: x[2])):
    o_w, o_r = wdiff(recs, pick), diff(recs, pick)
    bw, br = [], []
    for _ in range(2000):
        s = [recs[random.randrange(len(recs))] for _ in range(len(recs))]
        bw.append(wdiff(s, pick)); br.append(diff(s, pick))
    bw.sort(); br.sort()
    print(f"帯を揃えた「{label}」")
    print(f"  勝率の差  : {o_w*100:+.2f}pt  95%区間 [{bw[50]*100:+.2f}, {bw[1949]*100:+.2f}]pt")
    print(f"  回収率の差: {o_r*100:+.1f}pt  95%区間 [{br[50]*100:+.1f}, {br[1949]*100:+.1f}]pt")
