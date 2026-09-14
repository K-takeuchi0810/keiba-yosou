"""モデルの「見分ける力」を、より高い価格に向けられるか。

分かっていること (本日検証済み):
  ・モデルは同じ人気帯の中で勝ち馬を +3.9pt 多く見つける (頑健)
  ・しかしその力を帯の中の「安い馬」に使っているので回収率に結びつかない

なら、印の上位を保ったまま価格の高い馬を選べば改善するか。
prediction_log に全馬の順位が入っているので、モデルを再実行せずに試せる。

注意: 複数の規則を試すので、良く見えた規則は偶然の可能性がある。
      ここでの目的は「向きを変える余地があるか」の当たりを付けること。
"""
import sys, sqlite3, random, math
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
    SELECT l.race_year ry, l.race_month_day rmd, l.track_code tc, l.kaiji ka,
           l.nichiji ni, l.race_num rc, l.horse_num hn, l.rank, l.win_odds/10.0 odds,
           p.tan_horse_num1 win_hn, p.tan_payout1/100.0 win_pay
      FROM latest l
      JOIN payouts p ON p.race_year=l.race_year AND p.race_month_day=l.race_month_day
       AND p.track_code=l.track_code AND p.kaiji=l.kaiji AND p.nichiji=l.nichiji
       AND p.race_num=l.race_num
     WHERE l.rn=1 AND p.tan_payout1 > 0 AND l.win_odds > 0
""").fetchall()
conn.close()

races = {}
for r in rows:
    k = (r["ry"], r["rmd"], r["tc"], r["ka"], r["ni"], r["rc"])
    races.setdefault(k, {"horses": [], "win": str(r["win_hn"]).strip().lstrip("0"),
                         "pay": r["win_pay"]})
    races[k]["horses"].append({"hn": str(r["hn"]).strip().lstrip("0"),
                               "rank": r["rank"], "odds": r["odds"]})
races = {k: v for k, v in races.items() if len(v["horses"]) >= 5}
print(f"対象レース: {len(races):,}")

def evaluate(pick):
    picks = []
    for v in races.values():
        h = pick(v["horses"])
        if h is None: continue
        picks.append(v["pay"] if h["hn"] == v["win"] else 0.0)
    if not picks: return None
    n = len(picks); roi = sum(picks)/n; hit = sum(1 for x in picks if x > 0)/n
    sd = math.sqrt(sum((x-roi)**2 for x in picks)/(n-1)) if n > 1 else 0
    se = sd/math.sqrt(n)
    return n, hit, roi, roi-1.96*se, roi+1.96*se

def top(hs):
    return min(hs, key=lambda h: h["rank"])

def top_above_median(hs):
    med = sorted(h["odds"] for h in hs)[len(hs)//2]
    c = [h for h in hs if h["odds"] >= med]
    return min(c, key=lambda h: h["rank"]) if c else None

def longest_in_top(k):
    def f(hs):
        c = sorted(hs, key=lambda h: h["rank"])[:k]
        return max(c, key=lambda h: h["odds"]) if c else None
    return f

def top_if_odds_at_least(x):
    def f(hs):
        t = min(hs, key=lambda h: h["rank"])
        return t if t["odds"] >= x else None
    return f

print()
print(f"{'選び方':>28} {'買い数':>6} {'的中率':>7} {'回収率':>8} {'95%区間':>18}")
rules = [
    ("現行: 印 1 位", top),
    ("印 1 位 (オッズ5倍以上のみ)", top_if_odds_at_least(5.0)),
    ("印 1 位 (オッズ10倍以上のみ)", top_if_odds_at_least(10.0)),
    ("上位3頭で最も高オッズ", longest_in_top(3)),
    ("上位5頭で最も高オッズ", longest_in_top(5)),
    ("中央値以上で印が最上位", top_above_median),
]
for name, f in rules:
    r = evaluate(f)
    if not r: continue
    n, hit, roi, lo, hi = r
    print(f"{name:>28} {n:6,d} {hit*100:6.1f}% {roi*100:7.1f}% "
          f"[{lo*100:6.1f}%,{hi*100:6.1f}%]")
