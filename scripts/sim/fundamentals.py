"""オッズを特別扱いせず、一つの推定器として比較する。

これまでの検証はすべて「オッズに情報を足せるか」を問うていた。この枠組みでは
オッズと同じ情報を持つ特徴は「情報なし」と出るが、それは予測力が無いことを
意味しない。

ここでは 3 つを同列に比べる:
  (A) 実績だけの予想 (オッズも人気も一切使わない)
  (B) オッズだけ
  (C) 両方を合わせたもの

(C) > (B) なら、実績側はオッズに無い情報を持っていることになる。
(A) が (B) に匹敵するなら、2 つは別々の推定器として組み合わせる価値がある。

特徴はすべて **そのレースより前** の情報だけで作る (PIT)。
"""
import sys, sqlite3, math, collections
import numpy as np
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, ".")

conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
print("過去実績を時系列で積み上げ中 (PIT)...")

rows = conn.execute("""
    SELECT (h.race_year||h.race_month_day) d, h.track_code tc, h.kaiji ka,
           h.nichiji ni, h.race_num rc, h.horse_num hn,
           h.blood_register_num bn, h.jockey_code jc, h.trainer_code trc,
           h.age, h.sex_code sex, h.burden_weight bw, h.waku_num waku,
           h.horse_weight hw, h.weight_change_sign wsg, h.weight_change_diff wdf,
           h.blinker bl, h.win_odds/10.0 odds, h.confirmed_order fin,
           r.distance dist, r.track_type_code tt, r.grade_code gr,
           m.sire_breeding_num sire,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN 1 ELSE 0 END won
      FROM horse_races h
      JOIN races r ON r.race_year=h.race_year AND r.race_month_day=h.race_month_day
       AND r.track_code=h.track_code AND r.kaiji=h.kaiji AND r.nichiji=h.nichiji
       AND r.race_num=h.race_num
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
      LEFT JOIN horse_masters m ON m.blood_register_num = h.blood_register_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20250101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
     ORDER BY d, h.track_code, h.race_num, h.horse_num
""").fetchall()
conn.close()
print(f"  {len(rows):,} 頭 (2025-2026)")

def rate(w, n, prior_w=1.0, prior_n=12.0):
    return (w + prior_w) / (n + prior_n)

h_n = collections.Counter(); h_w = collections.Counter(); h_t3 = collections.Counter()
h_last = {}; h_lastfin = {}
j_n = collections.Counter(); j_w = collections.Counter()
t_n = collections.Counter(); t_w = collections.Counter()
s_n = collections.Counter(); s_w = collections.Counter()
hd_n = collections.Counter(); hd_w = collections.Counter()   # 馬×距離帯

def dband(d):
    d = int(d or 0)
    return 0 if d < 1400 else (1 if d < 1800 else (2 if d < 2200 else 3))

data = []
for r in rows:
    bn, jc, trc, sire = r["bn"], r["jc"], r["trc"], r["sire"]
    db = dband(r["dist"])
    try: fin = int(r["fin"] or 0)
    except (TypeError, ValueError): fin = 0
    try: dd = int(str(r["wdf"]).strip() or -1)
    except ValueError: dd = -1
    delta = (-dd if str(r["wsg"] or "").strip() == "-" else dd) if dd >= 0 else np.nan
    try: hw = float(str(r["hw"]).strip())
    except (TypeError, ValueError): hw = np.nan
    days = np.nan
    if bn in h_last:
        try:
            a = h_last[bn]; b = r["d"]
            from datetime import date
            da = date(int(a[:4]), int(a[4:6]), int(a[6:]))
            dbb = date(int(b[:4]), int(b[4:6]), int(b[6:]))
            days = (dbb - da).days
        except Exception: pass
    feat = dict(
        d=r["d"], won=r["won"], odds=r["odds"],
        # --- 実績系 (オッズ・人気を一切含まない) ---
        h_starts=h_n[bn], h_winrate=rate(h_w[bn], h_n[bn]),
        h_t3rate=rate(h_t3[bn], h_n[bn], 3.0, 12.0),
        h_lastfin=h_lastfin.get(bn, np.nan), h_days=days,
        hd_rate=rate(hd_w[(bn, db)], hd_n[(bn, db)]),
        j_winrate=rate(j_w[jc], j_n[jc], 1.0, 20.0), j_rides=j_n[jc],
        t_winrate=rate(t_w[trc], t_n[trc], 1.0, 20.0), t_runs=t_n[trc],
        s_winrate=rate(s_w[sire], s_n[sire], 1.0, 30.0) if sire else np.nan,
        age=float(str(r["age"] or 0).strip() or 0),
        sex=float(str(r["sex"] or 0).strip() or 0),
        burden=float(str(r["bw"] or 0).strip() or 0),
        waku=float(str(r["waku"] or 0).strip() or 0),
        dist=float(r["dist"] or 0), tt=float(str(r["tt"] or 0).strip() or 0),
        w_abs=hw, w_delta=delta,
        blinker=1.0 if str(r["bl"] or "").strip() == "1" else 0.0,
    )
    data.append(feat)
    # 更新 (このレースの結果は次以降にだけ使う)
    h_n[bn] += 1; hd_n[(bn, db)] += 1; j_n[jc] += 1; t_n[trc] += 1
    if sire: s_n[sire] += 1
    if r["won"]:
        h_w[bn] += 1; hd_w[(bn, db)] += 1; j_w[jc] += 1; t_w[trc] += 1
        if sire: s_w[sire] += 1
    if 0 < fin <= 3: h_t3[bn] += 1
    h_last[bn] = r["d"]; h_lastfin[bn] = float(fin) if fin > 0 else np.nan

FUND = ["h_starts","h_winrate","h_t3rate","h_lastfin","h_days","hd_rate",
        "j_winrate","j_rides","t_winrate","t_runs","s_winrate",
        "age","sex","burden","waku","dist","tt","w_abs","w_delta","blinker"]
tr = [x for x in data if "20250401" <= x["d"] <= "20260630"]
te = [x for x in data if x["d"] > "20260630"]
print(f"学習 {len(tr):,} 頭 / 検証 {len(te):,} 頭 (勝ち {sum(x['won'] for x in te):,})")

def fit_predict(cols, seed=0):
    Xtr = np.array([[x[c] for c in cols] for x in tr], float)
    ytr = np.array([x["won"] for x in tr])
    Xte = np.array([[x[c] for c in cols] for x in te], float)
    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=31,
                           min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                           random_state=seed, verbose=-1)
    m.fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]

yte = np.array([x["won"] for x in te])
odds_te = np.array([x["odds"] for x in te])
p_market = 1.0 / odds_te                      # 市場の含意確率 (未正規化)

print()
print("=== 3 つを同列に比較 (未知期間 2026-07〜09) ===")
p_fund = np.mean([fit_predict(FUND, s) for s in range(3)], axis=0)
p_both = np.mean([fit_predict(FUND + ["odds"], s) for s in range(3)], axis=0)
for name, p in (("(A) 実績だけ (オッズ不使用)", p_fund),
                ("(B) オッズだけ", p_market/ p_market.sum() * yte.sum() if False else p_market),
                ("(C) 実績 + オッズ", p_both)):
    auc = roc_auc_score(yte, p)
    print(f"  {name:28s} AUC {auc:.4f}")

# ---------------------------------------------------------------------------
# 正しい合わせ方: 特徴を混ぜるのではなく、2 つの「確率」を結合する
# ---------------------------------------------------------------------------
print()
print("=== 2 つの推定器として結合する (レース内で正規化 → 2 段目で重みを学習) ===")

# レース単位のキーを持たせる
for x, r in zip(data, rows):
    x["race"] = (r["d"], r["tc"], r["ka"], r["ni"], r["rc"])
tr = [x for x in data if "20250401" <= x["d"] <= "20260630"]
te = [x for x in data if x["d"] > "20260630"]

# 学習期間を 2 つに割り、前半で実績モデルを学習 → 後半で 2 段目の重みを学習
mid = "20260201"
tr1 = [x for x in tr if x["d"] < mid]
tr2 = [x for x in tr if x["d"] >= mid]
print(f"  1 段目学習 {len(tr1):,} / 2 段目学習 {len(tr2):,} / 検証 {len(te):,}")

def fit_on(train_set, cols, seed=0):
    X = np.array([[x[c] for c in cols] for x in train_set], float)
    y = np.array([x["won"] for x in train_set])
    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=31,
                           min_child_samples=50, subsample=0.8,
                           colsample_bytree=0.8, random_state=seed, verbose=-1)
    m.fit(X, y)
    return m

def pred(m, s, cols):
    return m.predict_proba(np.array([[x[c] for c in cols] for x in s], float))[:, 1]

m1 = fit_on(tr1, FUND)
p2 = pred(m1, tr2, FUND)
pte = pred(m1, te, FUND)

def normalize(sample, p):
    """レース内で合計 1 になるよう正規化する。"""
    by = {}
    for x, v in zip(sample, p):
        by.setdefault(x["race"], []).append(v)
    tot = {k: sum(v) for k, v in by.items()}
    out = []
    for x, v in zip(sample, p):
        t = tot[x["race"]] or 1.0
        out.append(max(v/t, 1e-6))
    return np.array(out)

def market_norm(sample):
    raw = np.array([1.0/x["odds"] for x in sample])
    return normalize(sample, raw)

q2_f, q2_m = normalize(tr2, p2), market_norm(tr2)
qt_f, qt_m = normalize(te, pte), market_norm(te)
y2 = np.array([x["won"] for x in tr2]); yte = np.array([x["won"] for x in te])

from sklearn.linear_model import LogisticRegression
X2 = np.column_stack([np.log(q2_f), np.log(q2_m)])
Xt = np.column_stack([np.log(qt_f), np.log(qt_m)])
lr = LogisticRegression(max_iter=1000).fit(X2, y2)
p_comb = lr.predict_proba(Xt)[:, 1]
a, b = lr.coef_[0]

print()
print(f"  2 段目が学習した重み: 実績 {a:+.3f} / オッズ {b:+.3f}")
print(f"  (実績の重みが 0 に近ければ、実績はオッズに情報を足していない)")
print()
for name, p in (("実績だけ", qt_f), ("オッズだけ", qt_m), ("2 段結合", p_comb)):
    print(f"  {name:12s} AUC {roc_auc_score(yte, p):.4f}")

print()
print("  ※ 参考: 本番モデル (112 特徴) は AUC 0.803 と記録されており、")
print("     ここで急造した実績モデル (20 特徴、0.7515) より強い。")
