"""T-10 → 最終の価格変化の分布と、大きく動いた馬が実際どう走ったか。"""
import csv, statistics as st
rows = list(csv.DictReader(open("data/backtest/market_movements_t10_final.csv",
                                encoding="utf-8")))
rows = [r for r in rows if r["category"] == "same" and r["p_ratio"]]
print(f"対象 {len(rows):,} 頭 (馬集合一致レースのみ)")
ratios = sorted(float(r["p_ratio"]) for r in rows)
print(f"確率の変化率 p_final/p_t10: 中央値 {st.median(ratios):.3f} / "
      f"5% {ratios[int(0.05*len(ratios))]:.3f} / 95% {ratios[int(0.95*len(ratios))]:.3f}")
print()
print("変化の大きさ別に、実際の勝率と『T-10 が示していた確率』を比べる")
print(f"{'群':>16} {'頭数':>6} {'実勝率':>8} {'T-10の予想':>10} {'最終の予想':>10}")
bands = [("大きく買われた (1.3倍超)", lambda x: x > 1.3),
         ("やや買われた (1.1-1.3)", lambda x: 1.1 < x <= 1.3),
         ("横ばい (0.9-1.1)", lambda x: 0.9 <= x <= 1.1),
         ("やや売られた (0.77-0.9)", lambda x: 0.77 <= x < 0.9),
         ("大きく売られた (0.77未満)", lambda x: x < 0.77)]
for name, f in bands:
    g = [r for r in rows if f(float(r["p_ratio"]))]
    if not g: continue
    n = len(g)
    actual = sum(int(r["won"]) for r in g) / n
    pt10 = sum(float(r["p_t10"]) for r in g) / n
    pfin = sum(float(r["p_final"]) for r in g) / n
    print(f"{name:>16} {n:6,d} {actual*100:7.2f}% {pt10*100:9.2f}% {pfin*100:9.2f}%")
print()
print("→ 実勝率が T-10 の予想より高い群 = T-10 時点で過小評価されていた")
print("   実勝率が 最終の予想 より高い群 = 最終市場でもまだ過小評価 (=狙い目候補)")
