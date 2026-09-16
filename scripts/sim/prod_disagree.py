"""食い違ったレースで、モデルの馬と 1 番人気のどちらが良かったか。

これが本質的な比較。食い違い時にモデルの馬を買う価値があるかは、
同じレースで 1 番人気を買った場合と直接比べないと分からない。
"""
import sys, csv, math, collections
path = sys.argv[1]
rows = list(csv.DictReader(open(path, encoding="utf-8")))
byrace = collections.defaultdict(list)
for r in rows:
    byrace[r["race"]].append(r)
races = {k: v for k, v in byrace.items()
         if all(float(x["odds"]) > 0 for x in v) and len(v) >= 5
         and any(x["won"] == "1" for x in v)}

def ci(v):
    n = len(v)
    if n < 2: return (0, 0, 0)
    m = sum(v)/n
    sd = math.sqrt(sum((x-m)**2 for x in v)/(n-1))
    return m, m-1.96*sd/math.sqrt(n), m+1.96*sd/math.sqrt(n)

agree_m, dis_m, dis_f, all_f = [], [], [], []
for k, v in races.items():
    top_f = max(v, key=lambda x: float(x["p_model"]))
    fav = min(v, key=lambda x: float(x["odds"]))
    pm = float(top_f["odds"]) if top_f["won"] == "1" else 0.0
    pf = float(fav["odds"]) if fav["won"] == "1" else 0.0
    all_f.append(pf)
    if top_f is fav:
        agree_m.append(pm)
    else:
        dis_m.append(pm); dis_f.append(pf)

print(f"全 {len(races)} レース (2026-07-04〜09-13、市場情報あり)")
print()
print(f"{'':>34} {'n':>5} {'回収率':>8} {'95%区間':>18}")
for name, v in (("全レースで 1 番人気を買う", all_f),
                ("一致時: モデル=1番人気を買う", agree_m),
                ("食い違い時: モデルの馬を買う", dis_m),
                ("食い違い時: 1 番人気を買う", dis_f)):
    m, lo, hi = ci(v)
    print(f"{name:>34} {len(v):5d} {m*100:7.1f}% [{lo*100:6.1f}%,{hi*100:6.1f}%]")

print()
d = [a-b for a, b in zip(dis_m, dis_f)]
m, lo, hi = ci(d)
print(f"食い違い時の差 (モデル − 1番人気、同じレースで対応させた比較):")
print(f"  {m*100:+.1f}pt  95%区間 [{lo*100:+.1f}, {hi*100:+.1f}]pt  (n={len(d)})")
print(f"  → 区間が 0 をまたぐ: {'はい (優位とは言えない)' if lo < 0 < hi else 'いいえ'}")
