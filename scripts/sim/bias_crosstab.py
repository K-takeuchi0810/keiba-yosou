"""競馬場の偏りが「月の偏り」で説明できるかを切り分ける。

JRA は季節で開催場が変わるので、月と競馬場は交絡する。
7 月の取得率が 49.6% と落ちているなら、7 月に開催していた場の取得率が
低く見えるのは当然。**月を揃えて場を比べる**ことで切り分ける。
"""
import sys, sqlite3, json
from collections import defaultdict
sys.path.insert(0, ".")
d = json.load(open("data/backtest/pit_coverage_bias.json", encoding="utf-8"))

import sqlite3
from predictor.pit_t10 import t10_market
from config import DATA_SPLIT
TRACK = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
         "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
a, b = DATA_SPLIT["strategy_dev"]["from"], DATA_SPLIT["strategy_dev"]["to"]
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
cell = defaultdict(lambda: [0, 0])
for r in conn.execute("""SELECT * FROM races
      WHERE (race_year||race_month_day) BETWEEN ? AND ?
        AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""", (a, b)):
    race = dict(r)
    m = race["race_year"] + race["race_month_day"][:2]
    t = TRACK.get(race["track_code"], race["track_code"])
    got = t10_market(conn, race) is not None
    cell[(m, t)][0 if got else 1] += 1
conn.close()

months = sorted({m for m, _ in cell})
tracks = sorted({t for _, t in cell})
print("月 × 競馬場 の取得率 (取得/総数)")
print(f"{'':>6}", end="")
for m in months:
    print(f"{m[4:]+'月':>12}", end="")
print()
for t in tracks:
    print(f"{t:>6}", end="")
    for m in months:
        g, mi = cell.get((m, t), [0, 0])
        tot = g + mi
        print(f"{(f'{g}/{tot} {g/tot*100:.0f}%' if tot else '-'):>12}", end="")
    print()
print()
print("→ 同じ月の中で場による差があるか / 月をまたいで同じ場が変わるかを見る")
