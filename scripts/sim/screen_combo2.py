"""候補の「組み合わせ・条件付き効果」まで含めた選別テスト。

単独の主効果だけを見ても、「特定の条件でだけ効く」「他の特徴と組んで効く」
パターンは捕まえられない。そこで手で切るのをやめ、**勾配ブースティングに
組み合わせを探させて、未知期間での予測改善があるか**で判定する。

設計:
  基準モデル : オッズ (市場の答え) + 基本条件 だけ
  検証モデル : 基準 + 候補特徴
  比較       : 時間で分割した未知期間での対数損失・AUC
               改善が無ければ、候補は交互作用を含めて情報を持たない。

学習期間 2026-01-01〜06-30 / 検証期間 2026-07-01〜09-13 (未知)
"""
import sys, sqlite3, math
import numpy as np
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, ".")

conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
scr = {}
for r in conn.execute("""SELECT race_year,race_month_day,track_code,kaiji,nichiji,race_num,
                                SUM(CASE WHEN scratch_status='1' THEN 1 ELSE 0 END) late,
                                SUM(CASE WHEN scratch_status='2' THEN 1 ELSE 0 END) early
                           FROM race_scratches WHERE race_year='2026' GROUP BY 1,2,3,4,5,6"""):
    scr[tuple(r[i] for i in range(6))] = (r["late"], r["early"])

rows = conn.execute("""
    SELECT h.race_year,h.race_month_day,h.track_code,h.kaiji,h.nichiji,h.race_num,
           h.blood_register_num bn, (h.race_year||h.race_month_day) d,
           h.win_odds/10.0 odds, h.win_popularity pop, h.blinker b,
           h.horse_weight hw, h.weight_change_sign sg, h.weight_change_diff df,
           h.age, h.sex_code sex, h.burden_weight bw, h.waku_num waku, h.horse_num hn,
           r.distance dist, r.track_type_code tt, r.grade_code grade,
           (SELECT COUNT(*) FROM horse_races x
             WHERE x.race_year=h.race_year AND x.race_month_day=h.race_month_day
               AND x.track_code=h.track_code AND x.kaiji=h.kaiji
               AND x.nichiji=h.nichiji AND x.race_num=h.race_num
               AND x.horse_num NOT IN ('','00')) starters,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                THEN 1 ELSE 0 END won
      FROM horse_races h
      JOIN races r ON r.race_year=h.race_year AND r.race_month_day=h.race_month_day
       AND r.track_code=h.track_code AND r.kaiji=h.kaiji AND r.nichiji=h.nichiji
       AND r.race_num=h.race_num
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year||h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
     ORDER BY h.blood_register_num, d
""").fetchall()
conn.close()

prev_b = {}
data = []
for r in rows:
    bn = r["bn"]; b = (r["b"] or "0").strip()
    first_b = 1 if (b == "1" and prev_b.get(bn) == "0") else 0
    prev_b[bn] = b
    try:
        df = int(str(r["df"]).strip() or -1)
    except ValueError:
        df = -1
    sg = str(r["sg"] or "").strip()
    delta = (-df if sg == "-" else df) if df >= 0 else np.nan
    try:
        hw = float(str(r["hw"]).strip())
    except (ValueError, TypeError):
        hw = np.nan
    key = (r["race_year"], r["race_month_day"], r["track_code"],
           r["kaiji"], r["nichiji"], r["race_num"])
    late, early = scr.get(key, (0, 0))
    data.append(dict(
        d=r["d"], won=r["won"],
        log_odds=math.log(r["odds"]),
        pop=float(str(r["pop"] or 0).strip() or 0),
        starters=r["starters"],
        dist=float(r["dist"] or 0), tt=float(str(r["tt"] or 0).strip() or 0),
        age=float(str(r["age"] or 0).strip() or 0),
        sex=float(str(r["sex"] or 0).strip() or 0),
        # --- 候補 ---
        w_delta=delta, w_abs=hw, blinker=1.0 if b == "1" else 0.0,
        first_blinker=float(first_b),
        scr_late=float(late), scr_early=float(early),
        waku=float(str(r["waku"] or 0).strip() or 0),
        burden=float(str(r["bw"] or 0).strip() or 0),
    ))

BASE = ["log_odds", "pop", "starters", "dist", "tt", "age", "sex"]
CAND = ["w_delta", "w_abs", "blinker", "first_blinker", "scr_late", "scr_early",
        "waku", "burden"]
tr = [x for x in data if x["d"] <= "20260630"]
te = [x for x in data if x["d"] > "20260630"]
print(f"学習 {len(tr):,} 頭 / 検証 {len(te):,} 頭 (勝ち {sum(x['won'] for x in te):,})")

def run(cols, seed):
    Xtr = np.array([[x[c] for c in cols] for x in tr], dtype=float)
    ytr = np.array([x["won"] for x in tr])
    Xte = np.array([[x[c] for c in cols] for x in te], dtype=float)
    yte = np.array([x["won"] for x in te])
    m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                           min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                           random_state=seed, verbose=-1)
    m.fit(Xtr, ytr)
    p = m.predict_proba(Xte)[:, 1]
    return log_loss(yte, p), roc_auc_score(yte, p)

# 対照実験: この検証方法が「本当に改善を検出できるか」を確かめる。
# (a) 陰性対照: 完全な乱数列 → 改善しないはず
# (b) 陽性対照: 着順由来のリーク特徴 → 大幅に改善するはず
rng = np.random.default_rng(0)
for x in tr + te:
    x["noise"] = float(rng.normal())
# 陽性対照は「勝ったか」を 30% だけ混ぜた弱い手がかり (完全リークだと強すぎる)
for x in tr + te:
    x["weak_oracle"] = float(x["won"]) if rng.random() < 0.30 else 0.0

print()
print("未知期間での成績 (5 seed の平均、検証 = 学習に使っていない 7-9 月)")
rows_out = []
for name, cols in (("(1) オッズだけ", ["log_odds"]),
                   ("(2) 基準: オッズ+基本条件", BASE),
                   ("(3) 基準 + 候補特徴 (交互作用込み)", BASE + CAND),
                   ("(4) 陰性対照: 基準 + 乱数", BASE + ["noise"]),
                   ("(5) 陽性対照: 基準 + 弱い正解混入", BASE + ["weak_oracle"])):
    ll = []; au = []
    for s in range(5):
        a, b = run(cols, s); ll.append(a); au.append(b)
    rows_out.append((name, np.mean(ll), np.std(ll), np.mean(au), np.std(au)))
    print(f"  {name:36s} 対数損失 {np.mean(ll):.5f} (±{np.std(ll):.5f}) / "
          f"AUC {np.mean(au):.4f} (±{np.std(au):.4f})")

base_ll = rows_out[1][1]
print()
print("基準 (2) からの改善 (対数損失は小さいほど良い):")
for name, ll, sd, au, ausd in rows_out:
    if name.startswith("(2)"): continue
    print(f"  {name:36s} {(base_ll-ll)*1000:+7.3f} (×10^-3)")

# 候補の使われ方
print()
print("候補特徴がモデルにどれだけ使われたか (重要度)")
Xtr = np.array([[x[c] for c in BASE+CAND] for x in tr], dtype=float)
ytr = np.array([x["won"] for x in tr])
m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                       min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                       random_state=0, verbose=-1)
m.fit(Xtr, ytr)
imp = sorted(zip(BASE+CAND, m.feature_importances_), key=lambda x: -x[1])
tot = sum(v for _, v in imp) or 1
for k, v in imp:
    tag = "候補" if k in CAND else "基準"
    print(f"  {tag} {k:16s} {v:6d} ({v/tot*100:4.1f}%)")
