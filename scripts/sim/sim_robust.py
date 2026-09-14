"""「モデルは同じ人気帯の中で当たりを見分けている」の頑健性を確かめる。

確認すること:
  1. 上位の大きな払戻を除いても差が残るか (1-2 件の大穴で説明できないか)
  2. ブートストラップ信頼区間 (差が偶然の範囲か)
  3. 期間を前半・後半に割っても同じ向きか
"""
import sys, sqlite3, random, statistics as st
sys.path.insert(0, ".")
random.seed(20260914)
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
base = {}
for b in conn.execute("""
    SELECT h.win_popularity AS pop,
           AVG(CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                    THEN 1.0 ELSE 0.0 END) AS hit,
           AVG(CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                    THEN p.tan_payout1/100.0 ELSE 0.0 END) AS roi
      FROM horse_races h
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year || h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('', '00') AND h.win_odds > 0 AND p.tan_payout1 > 0
     GROUP BY h.win_popularity""").fetchall():
    p = str(b["pop"]).strip()
    if p.isdigit():
        base[int(p)] = (b["hit"], b["roi"])

rows = conn.execute("""
    WITH latest AS (
      SELECT pl.*, ROW_NUMBER() OVER (
          PARTITION BY race_year,race_month_day,track_code,kaiji,nichiji,race_num,horse_num
          ORDER BY generated_at DESC) rn
        FROM prediction_log pl WHERE mark='◎')
    SELECT l.race_year||l.race_month_day AS d, l.win_popularity AS pop,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(l.horse_num AS INTEGER)
                THEN p.tan_payout1/100.0 ELSE 0.0 END AS pay
      FROM latest l
      JOIN payouts p ON p.race_year=l.race_year AND p.race_month_day=l.race_month_day
       AND p.track_code=l.track_code AND p.kaiji=l.kaiji AND p.nichiji=l.nichiji
       AND p.race_num=l.race_num
     WHERE l.rn=1 AND p.tan_payout1 > 0""").fetchall()
conn.close()

data = [(r["d"], int(str(r["pop"]).strip()), r["pay"]) for r in rows
        if str(r["pop"]).strip().isdigit() and int(str(r["pop"]).strip()) in base]
print(f"対象: {len(data)} 件")

def summarize(rec):
    n = len(rec)
    roi = sum(x[2] for x in rec)/n
    exp_roi = sum(base[x[1]][1] for x in rec)/n
    hit = sum(1 for x in rec if x[2] > 0)/n
    exp_hit = sum(base[x[1]][0] for x in rec)/n
    return n, hit, exp_hit, roi, exp_roi

n, hit, ehit, roi, eroi = summarize(data)
print(f"\n全体: 的中 {hit*100:.1f}% (基準 {ehit*100:.1f}%, 差 {(hit-ehit)*100:+.1f}pt) / "
      f"回収 {roi*100:.1f}% (基準 {eroi*100:.1f}%, 差 {(roi-eroi)*100:+.1f}pt)")

print("\n--- 1. 大きな払戻を上から除いた場合 ---")
srt = sorted(data, key=lambda x: -x[2])
for k in (0, 1, 2, 3, 5):
    rec = srt[k:]
    n2, h2, eh2, r2, er2 = summarize(rec)
    print(f"  上位 {k} 件を除外: 回収 {r2*100:6.1f}% (基準 {er2*100:.1f}%, 差 {(r2-er2)*100:+6.1f}pt) "
          f"/ 的中差 {(h2-eh2)*100:+.1f}pt")
print(f"  (除外した払戻: {[round(x[2],1) for x in srt[:5]]} 倍)")

print("\n--- 2. ブートストラップ (レース単位で 5,000 回) ---")
diffs_roi, diffs_hit = [], []
for _ in range(5000):
    s = [data[random.randrange(len(data))] for _ in range(len(data))]
    _, h, eh, r, er = summarize(s)
    diffs_roi.append(r-er); diffs_hit.append(h-eh)
diffs_roi.sort(); diffs_hit.sort()
lo, hi = diffs_roi[int(0.025*5000)], diffs_roi[int(0.975*5000)]
lo2, hi2 = diffs_hit[int(0.025*5000)], diffs_hit[int(0.975*5000)]
print(f"  回収率の差: {(roi-eroi)*100:+.1f}pt  95%区間 [{lo*100:+.1f}, {hi*100:+.1f}]pt")
print(f"  的中率の差: {(hit-ehit)*100:+.1f}pt  95%区間 [{lo2*100:+.1f}, {hi2*100:+.1f}]pt")
print(f"  回収率の差が 0 以下の割合: {sum(1 for x in diffs_roi if x<=0)/5000*100:.1f}%")
print(f"  的中率の差が 0 以下の割合: {sum(1 for x in diffs_hit if x<=0)/5000*100:.1f}%")

print("\n--- 3. 期間を前半・後半に割る ---")
ds = sorted({x[0] for x in data}); mid = ds[len(ds)//2]
for name, rec in (("前半", [x for x in data if x[0] < mid]),
                  ("後半", [x for x in data if x[0] >= mid])):
    n3, h3, eh3, r3, er3 = summarize(rec)
    print(f"  {name} (n={n3:3d}): 的中差 {(h3-eh3)*100:+5.1f}pt / 回収差 {(r3-er3)*100:+6.1f}pt")
