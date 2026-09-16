"""公式の馬場発表が実態に遅れる「ずれ」は、使える大きさか。

仮説: 雨が降っているのに馬場がまだ「良」と発表されているレースでは、
      実際の馬場は発表より重い。市場が発表を信じているなら、
      道悪が得意な馬が過小評価される。

まず規模を測る (小さすぎるなら追わない)。
"""
import sys, sqlite3, collections
sys.path.insert(0, ".")
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
W = {"1": "晴", "2": "曇", "3": "雨", "4": "小雨", "5": "雪", "6": "小雪"}
G = {"1": "良", "2": "稍重", "3": "重", "4": "不良"}

rows = conn.execute("""
    SELECT (race_year||race_month_day) d, track_code tc, race_num rn,
           weather_code w, turf_condition tcond, dirt_condition dcond,
           track_type_code tt
      FROM races
     WHERE (race_year||race_month_day) BETWEEN '20250101' AND '20260913'
       AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
     ORDER BY d, tc, CAST(rn AS INTEGER)
""").fetchall()
conn.close()
print(f"対象レース: {len(rows):,} (2025-2026)")

def cond_of(r):
    tt = str(r["tt"] or "").strip()[:1]
    return str((r["dcond"] if tt == "2" else r["tcond"]) or "").strip()

cnt = collections.Counter()
for r in rows:
    w = str(r["w"] or "").strip()
    g = cond_of(r)
    if not w or not g: continue
    wet_weather = w in ("3", "4", "5", "6")
    cnt[(W.get(w, w), G.get(g, g))] += 1

print()
print("天候 × 馬場状態 の組み合わせ (レース数)")
print(f"{'天候':>6} {'良':>7} {'稍重':>7} {'重':>7} {'不良':>7}")
for wname in ("晴", "曇", "小雨", "雨", "小雪", "雪"):
    line = f"{wname:>6}"
    for gname in ("良", "稍重", "重", "不良"):
        line += f" {cnt.get((wname, gname), 0):7,d}"
    print(line)

wet_but_firm = sum(cnt.get((w, "良"), 0) for w in ("雨", "小雨", "雪", "小雪"))
wet_total = sum(v for (w, g), v in cnt.items() if w in ("雨", "小雨", "雪", "小雪"))
print()
print(f"雨・雪なのに馬場は「良」のまま: {wet_but_firm:,} レース "
      f"(雨雪レース {wet_total:,} の {wet_but_firm/wet_total*100:.0f}%)")

# 同じ日・同じ場で、後のレースで馬場が悪化したか (= 発表が遅れていた証拠)
by = collections.defaultdict(list)
for r in rows:
    by[(r["d"], r["tc"])].append(r)
lag = 0; lag_races = 0
for k, g in by.items():
    conds = [cond_of(r) for r in g]
    ws = [str(r["w"] or "").strip() for r in g]
    for i, (c, w) in enumerate(zip(conds, ws)):
        if c == "1" and w in ("3", "4", "5", "6"):
            later = [x for x in conds[i+1:] if x and x != "1"]
            if later:
                lag += 1
    if any(c == "1" and w in ("3","4") for c, w in zip(conds, ws)) and \
       any(c and c != "1" for c in conds):
        lag_races += 1
print(f"うち **その後同じ開催で馬場が実際に悪化した** レース: {lag:,}")
print(f"  (そういう日×場: {lag_races} 日)")
