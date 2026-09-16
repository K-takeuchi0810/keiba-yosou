"""開催中に馬場が実際に変わる頻度と時刻を測る。

天気予報が価値を持つ条件は「開催中に馬場が変わり、かつ市場がそれを
事前に織り込めていない」こと。まず前半 (どれくらい変わるか) を測る。
"""
import sys, sqlite3, collections
sys.path.insert(0, ".")
conn = sqlite3.connect("file:data/keiba.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
GOING = {"1": "良", "2": "稍重", "3": "重", "4": "不良", "0": "-", "": "-"}

rows = conn.execute("""SELECT (race_year||race_month_day) d, track_code tc,
                              announced_time t, going_turf gt, prev_going_turf pgt,
                              going_dirt gd, prev_going_dirt pgd, weather_code w,
                              prev_weather_code pw
                         FROM weather_going ORDER BY d, tc, t""").fetchall()
days = conn.execute("""SELECT COUNT(DISTINCT (race_year||race_month_day)||track_code)
                         FROM races WHERE (race_year||race_month_day)
                         BETWEEN '20260509' AND '20260913'
                          AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""").fetchone()[0]
conn.close()

real = []
for r in rows:
    t = str(r["t"] or "").strip()
    if not t or t == "00000000":
        continue                       # 時刻なし = 朝の初期設定とみなす
    gt_ch = str(r["gt"] or "") != str(r["pgt"] or "")
    gd_ch = str(r["gd"] or "") != str(r["pgd"] or "")
    if gt_ch or gd_ch:
        real.append((r["d"], r["tc"], t[-4:], r["pgt"], r["gt"], r["pgd"], r["gd"]))

keys = {(d, tc) for d, tc, *_ in real}
print(f"開催中に馬場が実際に変わった 開催日×場: {len(keys)} / 全 {days} = "
      f"{len(keys)/days*100:.1f}%")
print(f"  変更イベント総数: {len(real)}")
print()
print("変更の時刻分布 (何時台に変わるか):")
hh = collections.Counter(t[:2] for *_, t, _, _, _, _ in [(d, tc, t, a, b, c, e)
                                                          for d, tc, t, a, b, c, e in real])
for h in sorted(hh):
    print(f"  {h} 時台: {hh[h]} 回")
print()
print("実例 (直近 10 件):")
for d, tc, t, pgt, gt, pgd, gd in real[-10:]:
    turf = f"芝 {GOING.get(str(pgt),'?')}→{GOING.get(str(gt),'?')}" if str(pgt) != str(gt) else ""
    dirt = f"ダ {GOING.get(str(pgd),'?')}→{GOING.get(str(gd),'?')}" if str(pgd) != str(gd) else ""
    print(f"  {d} 場{tc} {t[:2]}:{t[2:]}  {turf} {dirt}")
