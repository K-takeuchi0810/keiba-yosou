"""本番モデルの「市場を混ぜない」予測確率を全馬分取り出す。

PRED_DISABLE_BLEND=1 で市場ブレンドを切り、実績だけの確率を得る。
発走 T-10 の PIT 再構成を通し、発走後の列はマスクする。
"""
import os, sys, sqlite3, csv
os.environ["PRED_DISABLE_BLEND"] = "1"
sys.path.insert(0, ".")
from scripts.backtest import list_races, horses_for_race
from predictor.pit_market import apply_pit_odds
from predictor.pit_view import mask_post_race
from predictor.rules import predict_race

OUT = sys.argv[1]
FROM, TO = "20260701", "20260913"
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
races = list_races(conn, FROM, TO, jra_only=True, require_confirmed=True)
print(f"対象 {len(races)} レース", flush=True)

cache = {}
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["race", "horse_num", "p_model", "score", "odds", "won"])
    for i, r in enumerate(races):
        race = dict(r)
        key = (race["race_year"], race["race_month_day"], race["track_code"],
               race["kaiji"], race["nichiji"], race["race_num"])
        horses = horses_for_race(conn, race)
        if not horses:
            continue
        pit, meta = apply_pit_odds(conn, race, horses)
        masked = [mask_post_race(h) for h in pit]
        try:
            preds = predict_race(masked, conn=conn, race=race, cache=cache)
        except Exception as e:
            print("skip", key, e, flush=True); continue
        pay = conn.execute("""SELECT tan_horse_num1 hn FROM payouts
            WHERE race_year=? AND race_month_day=? AND track_code=? AND kaiji=?
              AND nichiji=? AND race_num=? AND tan_payout1 > 0""", key).fetchone()
        if not pay:
            continue
        win = str(pay["hn"]).strip().lstrip("0")
        odds = {str(h["horse_num"]).strip(): (h.get("win_odds") or 0)/10.0 for h in pit}
        for p in preds:
            hn = str(p.horse_num).strip()
            w.writerow(["-".join(key), hn, f"{float(p.win_probability or 0):.6f}",
                        f"{float(p.score or 0):.3f}", f"{odds.get(hn, 0):.1f}",
                        1 if hn.lstrip('0') == win else 0])
        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(races)}", flush=True)
conn.close()
print("done", flush=True)
