"""方針の核心を実装する: AI に「市場の誤差」だけを学習させる。

これまで: 勝つ馬を予測するモデルを作り、後から市場と混ぜていた。
これから: logit(P) = logit(P_market) + f(特徴)  の f だけを学習する。

実装は LightGBM の init_score に logit(市場確率) を渡すこと。
こうするとモデルは「市場からのズレ」だけを学ぶ。市場を再発見する無駄が消える。

評価は的中率でも AUC でもなく **市場に対する情報利得** (対数損失の改善)。
市場を上回れなければ 0 以下になる。
"""
import sys, sqlite3, math, collections
import numpy as np
import lightgbm as lgb
from sklearn.metrics import log_loss, roc_auc_score
sys.path.insert(0, ".")

conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
print("特徴を時系列で積み上げ中 (PIT)...")
rows = conn.execute("""
    SELECT (h.race_year||h.race_month_day) d, h.track_code tc, h.kaiji ka,
           h.nichiji ni, h.race_num rc,
           h.blood_register_num bn, h.jockey_code jc, h.trainer_code trc,
           h.age, h.sex_code sex, h.burden_weight bw, h.waku_num waku,
           h.horse_weight hw, h.weight_change_sign wsg, h.weight_change_diff wdf,
           h.blinker bl, h.win_odds/10.0 odds, h.confirmed_order fin,
           r.distance dist, r.track_type_code tt, r.turf_condition tcond,
           r.dirt_condition dcond, r.weather_code wc,
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
print(f"  {len(rows):,} 頭")

def rate(w, n, pw=1.0, pn=12.0): return (w+pw)/(n+pn)
hn_ = collections.Counter(); hw_ = collections.Counter(); ht_ = collections.Counter()
jn = collections.Counter(); jw = collections.Counter()
tn = collections.Counter(); tw = collections.Counter()
sn = collections.Counter(); sw = collections.Counter()
h_last = {}; h_lastfin = {}
data = []
for r in rows:
    bn, jc, trc, sire = r["bn"], r["jc"], r["trc"], r["sire"]
    try: fin = int(r["fin"] or 0)
    except (TypeError, ValueError): fin = 0
    try: dd = int(str(r["wdf"]).strip() or -1)
    except ValueError: dd = -1
    delta = (-dd if str(r["wsg"] or "").strip() == "-" else dd) if dd >= 0 else np.nan
    try: hwt = float(str(r["hw"]).strip())
    except (TypeError, ValueError): hwt = np.nan
    days = np.nan
    if bn in h_last:
        try:
            from datetime import date
            a, b = h_last[bn], r["d"]
            days = (date(int(b[:4]), int(b[4:6]), int(b[6:]))
                    - date(int(a[:4]), int(a[4:6]), int(a[6:]))).days
        except Exception: pass
    tt = str(r["tt"] or "").strip()[:1]
    cond = str((r["dcond"] if tt == "2" else r["tcond"]) or "").strip()
    data.append(dict(
        d=r["d"], race=(r["d"], r["tc"], r["ka"], r["ni"], r["rc"]),
        won=r["won"], odds=r["odds"],
        h_starts=hn_[bn], h_winrate=rate(hw_[bn], hn_[bn]),
        h_t3rate=rate(ht_[bn], hn_[bn], 3.0, 12.0),
        h_lastfin=h_lastfin.get(bn, np.nan), h_days=days,
        j_winrate=rate(jw[jc], jn[jc], 1.0, 20.0), j_rides=jn[jc],
        t_winrate=rate(tw[trc], tn[trc], 1.0, 20.0),
        s_winrate=rate(sw[sire], sn[sire], 1.0, 30.0) if sire else np.nan,
        age=float(str(r["age"] or 0).strip() or 0),
        sex=float(str(r["sex"] or 0).strip() or 0),
        burden=float(str(r["bw"] or 0).strip() or 0),
        waku=float(str(r["waku"] or 0).strip() or 0),
        dist=float(r["dist"] or 0), tt=float(tt or 0),
        cond=float(cond or 0), weather=float(str(r["wc"] or 0).strip() or 0),
        w_abs=hwt, w_delta=delta,
        blinker=1.0 if str(r["bl"] or "").strip() == "1" else 0.0,
    ))
    hn_[bn] += 1; jn[jc] += 1; tn[trc] += 1
    if sire: sn[sire] += 1
    if r["won"]:
        hw_[bn] += 1; jw[jc] += 1; tw[trc] += 1
        if sire: sw[sire] += 1
    if 0 < fin <= 3: ht_[bn] += 1
    h_last[bn] = r["d"]; h_lastfin[bn] = float(fin) if fin > 0 else np.nan

# 市場確率: レース内で正規化 (控除率を外す)
by = collections.defaultdict(list)
for i, x in enumerate(data): by[x["race"]].append(i)
for k, idx in by.items():
    tot = sum(1.0/data[i]["odds"] for i in idx)
    for i in idx:
        data[i]["q"] = max((1.0/data[i]["odds"])/tot, 1e-6)

FEAT = ["h_starts","h_winrate","h_t3rate","h_lastfin","h_days","j_winrate","j_rides",
        "t_winrate","s_winrate","age","sex","burden","waku","dist","tt","cond",
        "weather","w_abs","w_delta","blinker"]
tr = [x for x in data if "20250401" <= x["d"] <= "20260630"]
te = [x for x in data if x["d"] > "20260630"]
print(f"学習 {len(tr):,} / 検証 {len(te):,} (勝ち {sum(x['won'] for x in te)})")

def logit(p): return np.log(p/(1-p))
Xtr = np.array([[x[c] for c in FEAT] for x in tr], float)
ytr = np.array([x["won"] for x in tr])
Xte = np.array([[x[c] for c in FEAT] for x in te], float)
yte = np.array([x["won"] for x in te])
qtr = np.array([x["q"] for x in tr]); qte = np.array([x["q"] for x in te])

# 基準: 市場だけ
ll_mkt = log_loss(yte, qte)
print()
print(f"市場だけの対数損失: {ll_mkt:.5f}  (AUC {roc_auc_score(yte, qte):.4f})")

# 市場を土台にして「誤差だけ」を学習
print()
print("市場を init_score に置き、誤差だけを学習した場合:")
for lr_, n_est in ((0.02, 200), (0.02, 500), (0.05, 300)):
    res = []
    for seed in range(3):
        m = lgb.LGBMClassifier(n_estimators=n_est, learning_rate=lr_, num_leaves=15,
                               min_child_samples=200, subsample=0.8,
                               colsample_bytree=0.8, random_state=seed, verbose=-1)
        m.fit(Xtr, ytr, init_score=logit(qtr))
        raw = m.predict(Xte, raw_score=True) + logit(qte)
        p = 1/(1+np.exp(-raw))
        res.append(log_loss(yte, p))
    gain = ll_mkt - np.mean(res)
    print(f"  lr={lr_} 木={n_est}: 対数損失 {np.mean(res):.5f}  "
          f"市場に対する情報利得 {gain*1000:+.3f} (×10^-3)  "
          f"{'改善' if gain > 0 else '悪化'}")
