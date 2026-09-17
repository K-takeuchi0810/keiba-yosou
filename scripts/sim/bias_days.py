"""7 月の欠損が「特定の日」に固まっているかを見る。"""
import sys, sqlite3
from collections import defaultdict
sys.path.insert(0, ".")
from predictor.pit_t10 import t10_market
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
day = defaultdict(lambda: [0, 0])
for r in conn.execute("""SELECT * FROM races
      WHERE (race_year||race_month_day) BETWEEN '20260509' AND '20260831'
        AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10"""):
    race = dict(r)
    d = race["race_year"] + race["race_month_day"]
    day[d][0 if t10_market(conn, race) is not None else 1] += 1
conn.close()
print("開催日別の T-10 取得率 (取得/総数)")
zero = []
for d in sorted(day):
    g, m = day[d]
    tot = g + m
    bar = "#" * int(g / tot * 20)
    print(f"  {d}  {g:3d}/{tot:3d} {g/tot*100:5.1f}% {bar}")
    if g == 0:
        zero.append(d)
print()
print(f"取得ゼロの開催日: {len(zero)} 日 {zero}")
