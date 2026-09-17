"""採用した T-10 スナップが、決定時刻からどれだけ余裕があるかを見る。

余裕がほぼ 0 なら「違反 0 件」は綱渡りで、少しの誤差で崩れる。
十分な余裕があるなら 0 件は信用できる。
"""
import sys, sqlite3, statistics as st
from datetime import datetime
sys.path.insert(0, ".")
from predictor.pit_t10 import t10_market, _parse_announced
from config import DATA_SPLIT

a, b = DATA_SPLIT["strategy_dev"]["from"], DATA_SPLIT["strategy_dev"]["to"]
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
races = conn.execute("""
    SELECT * FROM races WHERE (race_year||race_month_day) BETWEEN ? AND ?
      AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""", (a, b)).fetchall()

recv_margin, obs_margin, no_obs = [], [], 0
for r in races:
    m = t10_market(conn, dict(r))
    if m is None:
        continue
    dt = datetime.fromisoformat(m.decision_time)
    recv_margin.append((dt - datetime.fromisoformat(m.odds_received_at)).total_seconds() / 60)
    if m.odds_observed_at:
        obs_margin.append((dt - datetime.fromisoformat(m.odds_observed_at)).total_seconds() / 60)
    else:
        no_obs += 1
conn.close()

def show(name, v):
    if not v:
        print(f"  {name}: なし"); return
    v = sorted(v)
    print(f"  {name}: n={len(v)} 中央値 {st.median(v):.1f} 分 / "
          f"最小 {v[0]:.1f} / 5% {v[int(0.05*len(v))]:.1f} / 最大 {v[-1]:.1f}")
    print(f"    0 分以下 (=違反): {sum(1 for x in v if x < 0)} 件 / "
          f"1 分未満の綱渡り: {sum(1 for x in v if 0 <= x < 1)} 件")

print("決定時刻からの余裕 (プラスなら決定時刻より前 = 正常)")
show("受信時刻", recv_margin)
show("発表時刻", obs_margin)
print(f"  発表時刻が取れなかったレース: {no_obs}")
