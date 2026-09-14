"""候補 1 の選別テスト (改訂版2: レース全体の動きを差し引く)。

前版の欠陥を 2 つ直した:
  1. 「朝の最初」は 1R と 12R で発走までの距離が違う → **T-60 分と T-10 分**に固定
  2. 全帯合算が群ごとの価格構成に汚染されていた → **帯ごとの差を平均**し、
     帯を層としたブートストラップで区間を出す
"""
import sys, sqlite3, math, random
from datetime import datetime, timedelta
sys.path.insert(0, ".")
random.seed(20260914)

conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
races = conn.execute("""
    SELECT race_year, race_month_day, track_code, kaiji, nichiji, race_num, start_time
      FROM races
     WHERE (race_year||race_month_day) BETWEEN '20260502' AND '20260913'
       AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
       AND start_time IS NOT NULL AND TRIM(start_time) <> ''
""").fetchall()

recs = []
for r in races:
    key = tuple(r[k] for k in ("race_year", "race_month_day", "track_code",
                               "kaiji", "nichiji", "race_num"))
    s = str(r["start_time"]).strip()
    if len(s) != 4 or not s.isdigit():
        continue
    d = r["race_year"] + "-" + r["race_month_day"][:2] + "-" + r["race_month_day"][2:]
    try:
        start = datetime.fromisoformat(f"{d}T{s[:2]}:{s[2:]}:00")
    except ValueError:
        continue
    c10 = (start - timedelta(minutes=10)).isoformat()
    c60 = (start - timedelta(minutes=60)).isoformat()

    snaps = conn.execute("""
        SELECT horse_num, fetched_at, win_odds FROM odds_snapshots
         WHERE race_year=? AND race_month_day=? AND track_code=? AND kaiji=?
           AND nichiji=? AND race_num=? AND win_odds > 0 ORDER BY fetched_at""", key).fetchall()
    if not snaps:
        continue
    o60, o10 = {}, {}
    for sn in snaps:
        h = sn["horse_num"]
        if sn["fetched_at"] <= c60:
            o60[h] = sn["win_odds"] / 10.0
        if sn["fetched_at"] <= c10:
            o10[h] = sn["win_odds"] / 10.0
    pay = conn.execute("""SELECT tan_horse_num1 hn, tan_payout1 p FROM payouts
         WHERE race_year=? AND race_month_day=? AND track_code=? AND kaiji=?
           AND nichiji=? AND race_num=?""", key).fetchone()
    if not pay or not pay["p"]:
        continue
    winner = str(pay["hn"]).strip().lstrip("0")
    # レース全体の動きを差し引く (プールが膨らめば全馬のオッズが動くため)
    pairs = [(h, a, o60[h]) for h, a in o10.items()
             if o60.get(h) and o60[h] > 0 and a > 0]
    if len(pairs) < 4:
        continue
    raw = [math.log(a / b) for _, a, b in pairs]
    mean_move = sum(raw) / len(raw)
    for (h, a, b), d in zip(pairs, raw):
        won = str(h).strip().lstrip("0") == winner
        recs.append((a, d - mean_move, won, (pay["p"]/100.0) if won else 0.0))
conn.close()

print(f"対象: {len(recs):,} 頭 (T-60 と T-10 の両方でオッズが取れたもの)")
BUCKETS = [(1.0,3.0),(3.0,7.0),(7.0,15.0),(15.0,40.0),(40.0,1e9)]

def within_bucket_diff(sample):
    """帯ごとに「人気化」群と「人気落ち」群の回収率差を出し、頭数で重み付け平均。"""
    num = den = 0.0
    for lo, hi in BUCKETS:
        sub = [r for r in sample if lo <= r[0] < hi]
        if len(sub) < 150:
            continue
        ds = sorted(x[1] for x in sub)
        q1, q2 = ds[len(ds)//3], ds[2*len(ds)//3]
        a = [x for x in sub if x[1] <= q1]      # 人気化
        b = [x for x in sub if x[1] > q2]       # 人気落ち
        if not a or not b:
            continue
        w = min(len(a), len(b))
        num += w * (sum(x[3] for x in a)/len(a) - sum(x[3] for x in b)/len(b))
        den += w
    return num/den if den else 0.0

print()
print(f"{'T-10オッズ帯':>13} {'群':>8} {'頭数':>6} {'勝率':>7} {'回収率':>8}")
for lo, hi in BUCKETS:
    sub = [r for r in recs if lo <= r[0] < hi]
    if len(sub) < 150:
        continue
    ds = sorted(x[1] for x in sub)
    q1, q2 = ds[len(ds)//3], ds[2*len(ds)//3]
    for name, g in (("人気化", [x for x in sub if x[1] <= q1]),
                    ("横ばい", [x for x in sub if q1 < x[1] <= q2]),
                    ("人気落ち", [x for x in sub if x[1] > q2])):
        if not g: continue
        print(f"{lo:5.0f}-{hi if hi<1e8 else 999:5.0f} {name:>8} {len(g):6,d} "
              f"{sum(1 for x in g if x[2])/len(g)*100:6.1f}% "
              f"{sum(x[3] for x in g)/len(g)*100:7.1f}%")
    print()

obs = within_bucket_diff(recs)
print(f"帯を揃えた「人気化 − 人気落ち」の回収率差: {obs*100:+.1f}pt")
boot = []
for _ in range(2000):
    s = [recs[random.randrange(len(recs))] for _ in range(len(recs))]
    boot.append(within_bucket_diff(s))
boot.sort()
lo_, hi_ = boot[50], boot[1949]
print(f"  ブートストラップ 95% 区間: [{lo_*100:+.1f}, {hi_*100:+.1f}]pt")
print(f"  差が 0 をまたぐ: {'はい (信号なし)' if lo_ < 0 < hi_ else 'いいえ'}")
