"""モデルが見つける「余分な勝ち馬」が、帯の中で安い馬か高い馬かを調べる。

的中率は上がっているのに回収率が伴わないなら、帯の中で「より人気側 (安い側)」に
寄っているはず。だとすれば、市場が既に織り込んでいる情報を再発見しているだけになる。
"""
import sys, sqlite3, statistics as st
sys.path.insert(0, ".")
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# 帯ごとの「勝った馬の平均配当」と「出走馬の平均オッズ」
band = {}
for b in conn.execute("""
    SELECT h.win_popularity AS pop, AVG(h.win_odds/10.0) AS avg_odds,
           AVG(CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(h.horse_num AS INTEGER)
                    THEN p.tan_payout1/100.0 END) AS avg_win_pay
      FROM horse_races h
      JOIN payouts p ON p.race_year=h.race_year AND p.race_month_day=h.race_month_day
       AND p.track_code=h.track_code AND p.kaiji=h.kaiji AND p.nichiji=h.nichiji
       AND p.race_num=h.race_num
     WHERE (h.race_year || h.race_month_day) BETWEEN '20260101' AND '20260913'
       AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
       AND h.horse_num NOT IN ('','00') AND h.win_odds > 0 AND p.tan_payout1 > 0
     GROUP BY h.win_popularity""").fetchall():
    p = str(b["pop"]).strip()
    if p.isdigit():
        band[int(p)] = (b["avg_odds"], b["avg_win_pay"])

rows = conn.execute("""
    WITH latest AS (
      SELECT pl.*, ROW_NUMBER() OVER (
          PARTITION BY race_year,race_month_day,track_code,kaiji,nichiji,race_num,horse_num
          ORDER BY generated_at DESC) rn
        FROM prediction_log pl WHERE mark='◎')
    SELECT l.win_popularity AS pop, l.win_odds/10.0 AS odds,
           CASE WHEN CAST(p.tan_horse_num1 AS INTEGER)=CAST(l.horse_num AS INTEGER)
                THEN p.tan_payout1/100.0 ELSE 0.0 END AS pay
      FROM latest l
      JOIN payouts p ON p.race_year=l.race_year AND p.race_month_day=l.race_month_day
       AND p.track_code=l.track_code AND p.kaiji=l.kaiji AND p.nichiji=l.nichiji
       AND p.race_num=l.race_num
     WHERE l.rn=1 AND p.tan_payout1 > 0 AND l.win_odds > 0""").fetchall()
conn.close()

print(f"{'人気':>4} {'◎数':>5} {'◎の平均オッズ':>13} {'帯の平均':>9} {'差':>7} | "
      f"{'◎勝ち馬の配当':>13} {'帯の基準':>9}")
tot = []
for p in sorted({int(str(r['pop']).strip()) for r in rows
                 if str(r['pop']).strip().isdigit()}):
    v = [r for r in rows if str(r["pop"]).strip().isdigit()
         and int(str(r["pop"]).strip()) == p]
    if len(v) < 10 or p not in band:
        continue
    mo = st.mean([r["odds"] for r in v])
    wins = [r["pay"] for r in v if r["pay"] > 0]
    b_odds, b_pay = band[p]
    print(f"{p:>4} {len(v):>5} {mo:12.2f} {b_odds:9.2f} {mo-b_odds:+7.2f} | "
          f"{st.mean(wins) if wins else 0:12.2f} {b_pay:9.2f}")
    tot.append((len(v), mo - b_odds))
w = sum(n for n,_ in tot)
print(f"\n加重平均の差: {sum(n*d for n,d in tot)/w:+.2f} 倍")
print("(マイナス = モデルは帯の中で『より安い馬』を選んでいる")
print(" = 市場が既に織り込んでいる情報を再発見しているだけの可能性が高い)")
