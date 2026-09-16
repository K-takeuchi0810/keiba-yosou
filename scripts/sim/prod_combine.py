"""本番モデル (112 特徴) はオッズに無い情報を持っているか。

市場ブレンドを切った純粋な予測確率と、市場の含意確率を **対等な 2 つの推定器**
として扱い、レース内で正規化したうえで 2 段目に重みを学習させる (Benter 方式)。

2 段目が実績側に重みを与えなければ、本番モデルは市場に無い情報を持っていない。
"""
import sys, csv, math, collections
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss

path = sys.argv[1]
rows = list(csv.DictReader(open(path, encoding="utf-8")))
print(f"読み込み: {len(rows):,} 行")

# 市場情報のあるレースだけを使う (T-10 のオッズが取れたもの)
byrace = collections.defaultdict(list)
for r in rows:
    byrace[r["race"]].append(r)
races = {k: v for k, v in byrace.items()
         if all(float(x["odds"]) > 0 for x in v) and len(v) >= 5
         and any(x["won"] == "1" for x in v)}
print(f"  市場情報あり・勝ち馬ありのレース: {len(races):,} "
      f"({sum(len(v) for v in races.values()):,} 頭)")

def norm(vals):
    t = sum(vals) or 1.0
    return [max(v/t, 1e-6) for v in vals]

recs = []
for k, v in races.items():
    date = k.split("-")[0] + k.split("-")[1]
    qm = norm([1.0/float(x["odds"]) for x in v])
    qf = norm([float(x["p_model"]) for x in v])
    for x, a, b in zip(v, qf, qm):
        recs.append({"d": date, "qf": a, "qm": b, "won": int(x["won"]),
                     "odds": float(x["odds"])})

tr = [x for x in recs if x["d"] <= "20260816"]
te = [x for x in recs if x["d"] > "20260816"]
print(f"  2 段目の学習 {len(tr):,} 頭 / 検証 {len(te):,} 頭 "
      f"(勝ち {sum(x['won'] for x in te)})")

Xtr = np.column_stack([np.log([x["qf"] for x in tr]), np.log([x["qm"] for x in tr])])
ytr = np.array([x["won"] for x in tr])
Xte = np.column_stack([np.log([x["qf"] for x in te]), np.log([x["qm"] for x in te])])
yte = np.array([x["won"] for x in te])

lr = LogisticRegression(max_iter=2000).fit(Xtr, ytr)
a, b = lr.coef_[0]
p_comb = lr.predict_proba(Xte)[:, 1]
qf_te = np.array([x["qf"] for x in te]); qm_te = np.array([x["qm"] for x in te])

print()
print(f"=== 2 段目が学習した重み ===")
print(f"  本番モデル (実績) : {a:+.3f}")
print(f"  オッズ (市場)     : {b:+.3f}")
print(f"  → 実績側の重みが 0 に近ければ、本番モデルは市場に無い情報を持っていない")
print()
print("=== 未知期間 (2026-08-17〜09-13) での判別力 ===")
for name, p in (("本番モデルだけ", qf_te), ("オッズだけ", qm_te), ("2 段結合", p_comb)):
    print(f"  {name:16s} AUC {roc_auc_score(yte, p):.4f}")

# 参考: 学習期間でも同じ形を見る (期間依存でないかの確認)
lr2 = LogisticRegression(max_iter=2000).fit(Xte, yte)
print()
print(f"  (期間を入れ替えて学習した場合の重み: 実績 {lr2.coef_[0][0]:+.3f} / "
      f"オッズ {lr2.coef_[0][1]:+.3f})")

# 実績側が上位に置いた馬の、市場との食い違い
print()
print("=== 本番モデルと市場が食い違ったとき ===")
byr = collections.defaultdict(list)
for x in te:
    byr[id(x)] = None
races_te = collections.defaultdict(list)
for x, r in zip(te, [k for k, v in races.items() if k.split("-")[0]+k.split("-")[1] > "20260816"
                     for _ in v]):
    races_te[r].append(x)
agree = dis = 0; agree_hit = dis_hit = 0
agree_roi = dis_roi = 0.0
for k, v in races_te.items():
    if len(v) < 5: continue
    top_f = max(v, key=lambda x: x["qf"])
    top_m = max(v, key=lambda x: x["qm"])
    same = top_f is top_m
    won = top_f["won"]
    pay = top_f["odds"] if won else 0.0
    if same:
        agree += 1; agree_hit += won; agree_roi += pay
    else:
        dis += 1; dis_hit += won; dis_roi += pay
if agree:
    print(f"  一致 (モデル 1 位 = 1 番人気): {agree:4d} レース 的中 {agree_hit/agree*100:5.1f}% "
          f"回収 {agree_roi/agree*100:6.1f}%")
if dis:
    print(f"  食い違い                    : {dis:4d} レース 的中 {dis_hit/dis*100:5.1f}% "
          f"回収 {dis_roi/dis*100:6.1f}%")
