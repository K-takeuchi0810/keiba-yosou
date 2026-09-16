"""天候は特徴として使えるか + 開催中に馬場が変わる頻度はどれくらいか。

2 つを分けて見る:
  (A) 天候そのもの (weather_code) が、馬場状態に加えて情報を持つか
      → 確立した選別テスト (同じ価格帯で揃えて勝率差) にかける
  (B) 開催中に馬場が変わる頻度
      → 変わるなら「天気予報」は市場より先に知る手段になりうる。
        JV-Data に予報は無いので、これは外部データの候補になる。
"""
import sys, sqlite3, math, random, collections
sys.path.insert(0, ".")
random.seed(20260917)
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

WEATHER = {"1": "晴", "2": "曇", "3": "雨", "4": "小雨", "5": "雪", "6": "小雪"}
GOING = {"1": "良", "2": "稍重", "3": "重", "4": "不良"}

rows = conn.execute("""
    SELECT h.win_odds/10.0 odds, r.weather_code w,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN p.tan_payout1/100.0 ELSE 0.0 END pay
      FROM horse_races h
      JOIN races r ON r.race_year=h.race_year AND r.race_month_day=h.race_month_day
       AND r.track_code=h.track_code AND r.kaiji=h.kaiji AND r.nichiji=h.nichiji
       AND r.race_num=h.race_num
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20250101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
""").fetchall() if True else []

recs = [(r["odds"], str(r["w"] or "").strip(), r["pay"]) for r in rows]
print(f"(A) 天候の選別テスト — 対象 {len(recs):,} 頭 (2025-2026)")
print(f"    天候の分布: ", end="")
cnt = collections.Counter(x[1] for x in recs)
print(", ".join(f"{WEATHER.get(k,k)}:{v:,}" for k, v in cnt.most_common(6)))

BUCKETS = [(1.0,3.0),(3.0,7.0),(7.0,15.0),(15.0,40.0),(40.0,1e9)]
def stat(sample, wet, use_roi):
    num = den = 0.0
    for lo, hi in BUCKETS:
        sub = [x for x in sample if lo <= x[0] < hi]
        a = [x for x in sub if x[1] in wet]
        b = [x for x in sub if x[1] in ("1", "2")]      # 晴・曇
        if len(a) < 100 or len(b) < 100: continue
        w = min(len(a), len(b))
        if use_roi:
            num += w*(sum(x[2] for x in a)/len(a) - sum(x[2] for x in b)/len(b))
        else:
            num += w*(sum(1 for x in a if x[2] > 0)/len(a)
                      - sum(1 for x in b if x[2] > 0)/len(b))
        den += w
    return num/den if den else 0.0

wet = ("3", "4", "5", "6")   # 雨・小雨・雪・小雪
ow, orr = stat(recs, wet, False), stat(recs, wet, True)
bw, br = [], []
for _ in range(1500):
    s = [recs[random.randrange(len(recs))] for _ in range(len(recs))]
    bw.append(stat(s, wet, False)); br.append(stat(s, wet, True))
bw.sort(); br.sort()
print(f"    帯を揃えた「雨・雪 − 晴・曇」")
print(f"      勝率の差  : {ow*100:+.2f}pt  95%区間 [{bw[37]*100:+.2f}, {bw[1462]*100:+.2f}]pt")
print(f"      回収率の差: {orr*100:+.1f}pt  95%区間 [{br[37]*100:+.1f}, {br[1462]*100:+.1f}]pt")

print()
print("(B) 開催中に馬場が変わる頻度")
ch = conn.execute("""SELECT (race_year||race_month_day) d, track_code tc,
                            COUNT(*) n, MIN(announced_time) a, MAX(announced_time) b
                       FROM weather_going
                      WHERE (going_turf <> prev_going_turf OR going_dirt <> prev_going_dirt)
                      GROUP BY d, tc ORDER BY d""").fetchall()
days = conn.execute("""SELECT COUNT(DISTINCT (race_year||race_month_day)||track_code)
                         FROM races WHERE (race_year||race_month_day)
                         BETWEEN '20260509' AND '20260913'
                          AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""").fetchone()[0]
conn.close()
print(f"    馬場が変わった開催日×場: {len(ch)} / 全 {days} = {len(ch)/days*100:.1f}%")
for r in ch[:6]:
    print(f"      {r['d']} 場{r['tc']}: {r['n']} 回変更 ({r['a']}〜{r['b']})")
