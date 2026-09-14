"""候補 5: 馬体重・増減の選別テスト。

値そのものは発走前に公表されるものと同じなので、取り込みが発走後でも
「情報が価格に入っているか」の判定には使える (運用に載せる段階で取得
タイミングの改修が要るのは別問題)。

仮説: 大幅な体重増減は状態の変化を示すが、市場が織り込みきれていないのでは。
"""
import sys, sqlite3, random, math
sys.path.insert(0, ".")
random.seed(20260915)
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT h.win_odds/10.0 odds, h.horse_weight hw,
           h.weight_change_sign sg, h.weight_change_diff df,
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

recs = []
for r in rows:
    try:
        d = int(str(r["df"]).strip() or -1)
    except ValueError:
        continue
    if d < 0:
        continue
    sg = str(r["sg"] or "").strip()
    delta = -d if sg == "-" else d
    recs.append((r["odds"], delta, r["pay"]))
print(f"対象: {len(recs):,} 頭 (体重増減が取れたもの)")
print(f"  増減の分布: 中央値 {sorted(x[1] for x in recs)[len(recs)//2]} kg / "
      f"±10kg 超 {sum(1 for x in recs if abs(x[1])>10):,} 頭")

BUCKETS = [(1.0,3.0),(3.0,7.0),(7.0,15.0),(15.0,40.0),(40.0,1e9)]
GROUPS = [("大幅減(-10kg超)", lambda d: d < -10), ("やや減(-4〜-10)", lambda d: -10 <= d < -4),
          ("横ばい(±4)", lambda d: -4 <= d <= 4), ("やや増(+4〜+10)", lambda d: 4 < d <= 10),
          ("大幅増(+10kg超)", lambda d: d > 10)]
print()
print(f"{'オッズ帯':>12} {'群':>16} {'頭数':>7} {'勝率':>7} {'回収率':>8}")
for lo, hi in BUCKETS:
    sub = [x for x in recs if lo <= x[0] < hi]
    for name, f in GROUPS:
        g = [x for x in sub if f(x[1])]
        if len(g) < 100: continue
        print(f"{lo:5.0f}-{hi if hi<1e8 else 999:5.0f} {name:>16} {len(g):7,d} "
              f"{sum(1 for x in g if x[2]>0)/len(g)*100:6.1f}% "
              f"{sum(x[2] for x in g)/len(g)*100:7.1f}%")
    print()

def mk(f):
    def stat(sample, use_roi):
        num = den = 0.0
        for lo, hi in BUCKETS:
            sub = [x for x in sample if lo <= x[0] < hi]
            a = [x for x in sub if f(x[1])]
            b = [x for x in sub if -4 <= x[1] <= 4]
            if len(a) < 100 or len(b) < 100: continue
            w = min(len(a), len(b))
            if use_roi:
                num += w*(sum(x[2] for x in a)/len(a) - sum(x[2] for x in b)/len(b))
            else:
                num += w*(sum(1 for x in a if x[2]>0)/len(a) - sum(1 for x in b if x[2]>0)/len(b))
            den += w
        return num/den if den else 0.0
    return stat

for name, f in GROUPS:
    if name.startswith("横ばい"): continue
    stat = mk(f)
    ow, orr = stat(recs, False), stat(recs, True)
    bw, br = [], []
    for _ in range(1500):
        s = [recs[random.randrange(len(recs))] for _ in range(len(recs))]
        bw.append(stat(s, False)); br.append(stat(s, True))
    bw.sort(); br.sort()
    print(f"「{name} − 横ばい」 勝率差 {ow*100:+.2f}pt [{bw[37]*100:+.2f},{bw[1462]*100:+.2f}] / "
          f"回収差 {orr*100:+.1f}pt [{br[37]*100:+.1f},{br[1462]*100:+.1f}]")
