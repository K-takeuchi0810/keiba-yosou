"""「印 1 位かつオッズ 5 倍以上だけ買う」規則の頑健性を確かめる。

6 つの規則を試して良かったものを見ているので、そのままでは偶然と区別できない。
確認すること:
  1. 期間を前半・後半に割っても同じ向きか
  2. 大きな払戻を除いても残るか
  3. 同じ価格帯を無選別に買った場合 (市場の基準) と比べて的中率が高いか
     ← これが本質。価格が同じなら、的中率の差だけが実力。
"""
import sys, sqlite3, math, random
sys.path.insert(0, ".")
random.seed(20260915)
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    WITH latest AS (
      SELECT pl.*, ROW_NUMBER() OVER (
          PARTITION BY race_year,race_month_day,track_code,kaiji,nichiji,race_num,horse_num
          ORDER BY generated_at DESC) rn
        FROM prediction_log pl)
    SELECT (l.race_year||l.race_month_day) d, l.track_code tc, l.kaiji ka,
           l.nichiji ni, l.race_num rc, l.horse_num hn, l.rank, l.win_odds/10.0 odds,
           p.tan_horse_num1 win_hn, p.tan_payout1/100.0 win_pay
      FROM latest l
      JOIN payouts p ON p.race_year=l.race_year AND p.race_month_day=l.race_month_day
       AND p.track_code=l.track_code AND p.kaiji=l.kaiji AND p.nichiji=l.nichiji
       AND p.race_num=l.race_num
     WHERE l.rn=1 AND p.tan_payout1 > 0 AND l.win_odds > 0
""").fetchall()

# 市場の基準: 同じオッズ帯を無選別に買った場合の的中率 (2026 通年)
base = {}
for r in conn.execute("""
    SELECT CAST(h.win_odds/10.0 AS INTEGER) b,
           AVG(CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                    THEN 1.0 ELSE 0.0 END) hit,
           AVG(CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                    THEN p.tan_payout1/100.0 ELSE 0.0 END) roi
      FROM horse_races h
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
     GROUP BY b"""):
    base[r["b"]] = (r["hit"], r["roi"])
conn.close()

races = {}
for r in rows:
    k = (r["d"], r["tc"], r["ka"], r["ni"], r["rc"])
    races.setdefault(k, {"h": [], "win": str(r["win_hn"]).strip().lstrip("0"),
                         "pay": r["win_pay"], "d": r["d"]})
    races[k]["h"].append({"hn": str(r["hn"]).strip().lstrip("0"),
                          "rank": r["rank"], "odds": r["odds"]})

picks = []
for v in races.values():
    if len(v["h"]) < 5: continue
    t = min(v["h"], key=lambda x: x["rank"])
    if t["odds"] < 5.0: continue
    won = t["hn"] == v["win"]
    b = base.get(int(t["odds"]), (0, 0))
    picks.append({"d": v["d"], "odds": t["odds"], "won": won,
                  "pay": v["pay"] if won else 0.0, "b_hit": b[0], "b_roi": b[1]})

def show(name, g):
    if len(g) < 30:
        print(f"  {name}: n={len(g)} (少なすぎ)"); return
    n = len(g); hit = sum(1 for x in g if x["won"])/n; roi = sum(x["pay"] for x in g)/n
    bh = sum(x["b_hit"] for x in g)/n; br = sum(x["b_roi"] for x in g)/n
    se = math.sqrt(bh*(1-bh)/n)
    print(f"  {name:>14}: n={n:4d}  的中 {hit*100:5.1f}% (同価格帯の基準 {bh*100:5.1f}%, "
          f"差 {(hit-bh)*100:+5.1f}pt = {abs(hit-bh)/se:.1f}SE)  "
          f"回収 {roi*100:6.1f}% (基準 {br*100:5.1f}%)")

print(f"「印 1 位かつオッズ 5 倍以上」の買い: {len(picks)} 件")
print()
print("1. 期間を割る")
ds = sorted({x['d'] for x in picks}); mid = ds[len(ds)//2]
show("全体", picks)
show("前半", [x for x in picks if x["d"] < mid])
show("後半", [x for x in picks if x["d"] >= mid])
print()
print("2. 大きな払戻を除く")
srt = sorted(picks, key=lambda x: -x["pay"])
for k in (1, 2, 3):
    g = srt[k:]
    n = len(g); roi = sum(x["pay"] for x in g)/n; br = sum(x["b_roi"] for x in g)/n
    print(f"  上位 {k} 件除外: 回収 {roi*100:6.1f}% (基準 {br*100:5.1f}%, "
          f"差 {(roi-br)*100:+6.1f}pt)")
print(f"  (除外した払戻: {[round(x['pay'],1) for x in srt[:3]]} 倍)")

print()
print("3. 100% に届くのに必要な的中率と、実測の比較")
n = len(picks)
bh = sum(x["b_hit"] for x in picks)/n
br = sum(x["b_roi"] for x in picks)/n
hit = sum(1 for x in picks if x["won"])/n
avg_win_pay = br/bh                       # 同価格帯で勝ったときの平均配当
need = 1.0/avg_win_pay
se = math.sqrt(hit*(1-hit)/n)
print(f"  同価格帯の基準: 的中 {bh*100:.1f}% / 勝ち時平均配当 {avg_win_pay:.2f} 倍 "
      f"→ 回収 {br*100:.1f}%")
print(f"  100% に必要な的中率: {need*100:.1f}%  (基準比 +{(need/bh-1)*100:.0f}% 相対)")
print(f"  実測の的中率      : {hit*100:.1f}% ± {1.96*se*100:.1f}pt  "
      f"(基準比 +{(hit/bh-1)*100:.0f}% 相対)")
print(f"  → 必要量を {'上回っている' if hit > need else '下回っている'} "
      f"(ただし区間は [{(hit-1.96*se)*100:.1f}, {(hit+1.96*se)*100:.1f}]%)")

print()
print("4. 封印窓で判定するとしたら何レース要るか")
vals = [x["pay"] for x in picks]
m = sum(vals)/len(vals)
sd = math.sqrt(sum((v-m)**2 for v in vals)/(len(vals)-1))
print(f"  この規則の 1 賭けあたりのばらつき SD = {sd:.2f} (◎ベタは 2.79)")
print(f"  買う割合: {n}/{len(races)} = {n/len(races)*100:.0f}% のレース")
for races_n in (800, 1600, 3200):
    bets = int(races_n * n/len(races))
    se_r = sd/math.sqrt(bets)
    print(f"  封印窓 {races_n:,} レース → 買い {bets:,} 件 / "
          f"CI 下限が 100% を超えるのに必要な観測回収率 {100*(1+1.96*se_r):.0f}%")
