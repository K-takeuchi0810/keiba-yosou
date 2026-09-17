"""最終市場が「最後まで修正しきれなかった」分があるかを、有意性込みで測る。

これが 140% の本命 (ユーザ指示):
  「AIが正しかった」だけでなく「市場が最後まで十分に修正しなかった」ケースこそ
  実際に利益へ変換できる Edge 候補。

注意: ここは **T-10 では知りえない最終の動きで層別している**ので、
そのままでは戦略にならない。市場の性質を知るための記述統計。
"""
import csv, math, random, collections
random.seed(20260918)
rows = [r for r in csv.DictReader(
    open("data/backtest/market_movements_t10_final.csv", encoding="utf-8"))
    if r["category"] == "same" and r["p_ratio"]]

bands = [("大きく買われた(>1.3)", lambda x: x > 1.3),
         ("やや買われた(1.1-1.3)", lambda x: 1.1 < x <= 1.3),
         ("横ばい(0.9-1.1)", lambda x: 0.9 <= x <= 1.1),
         ("やや売られた(0.77-0.9)", lambda x: 0.77 <= x < 0.9),
         ("大きく売られた(<0.77)", lambda x: x < 0.77)]

print("最終市場の較正: 実勝率 − 最終市場の含意確率 (レース単位ブートストラップ)")
print(f"{'群':>20} {'頭数':>6} {'実勝率':>8} {'最終予想':>9} {'差':>8} {'95%区間':>18}")
for name, f in bands:
    g = [r for r in rows if f(float(r["p_ratio"]))]
    if len(g) < 50:
        continue
    by_race = collections.defaultdict(list)
    for r in g:
        by_race[r["race_id"]].append(r)
    blocks = list(by_race.values())

    def gap(sample):
        n = len(sample)
        return (sum(int(x["won"]) for x in sample) / n
                - sum(float(x["p_final"]) for x in sample) / n)

    obs = gap(g)
    boot = []
    for _ in range(2000):
        s = []
        for _ in range(len(blocks)):
            s.extend(blocks[random.randrange(len(blocks))])
        boot.append(gap(s))
    boot.sort()
    lo, hi = boot[50], boot[1949]
    n = len(g)
    act = sum(int(x["won"]) for x in g) / n
    fin = sum(float(x["p_final"]) for x in g) / n
    mark = "  ←0をまたがない" if (lo > 0 or hi < 0) else ""
    print(f"{name:>20} {n:6,d} {act*100:7.2f}% {fin*100:8.2f}% {obs*100:+7.2f}pt "
          f"[{lo*100:+6.2f},{hi*100:+6.2f}]{mark}")
print()
print("正の差 = 最終市場でもまだ過小評価 (残った誤価格)")
print("※ 最終の動きで層別しているので T-10 時点では選べない。市場の性質の記述。")
