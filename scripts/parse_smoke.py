"""取得済みの RADW / SEDW ファイルをパースして人間可読サマリを出す。"""

import io
import sys
from pathlib import Path

# Windows コンソールが cp932 で UnicodeEncodeError を出さないように
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jvlink_client import parse_ra_file, parse_se_file

RACE_DIR = ROOT / "data" / "raw" / "RACE"

# 最新の RA / SE ファイルをそれぞれ 1 個取る
ra_files = sorted(RACE_DIR.glob("RADW*.jvd"))
se_files = sorted(RACE_DIR.glob("SEDW*.jvd"))
ra_file = ra_files[-1]
se_file = se_files[-1]

print(f"=== {ra_file.name} ===")
races = parse_ra_file(ra_file)
print(f"  parsed {len(races)} race records\n")
for r in races[:3]:
    print(f"  [{r.race_id}] R{r.race_num} 距離{r.distance}m 発走{r.start_time} "
          f"出走{r.starter_count}/{r.registered_count}頭 グレード'{r.grade_code}'")
    print(f"    競走名本題: {r.race_name!r}")
    print(f"    略称(10):   {r.race_short10!r}")
print()

print(f"=== {se_file.name} ===")
horses = parse_se_file(se_file)
print(f"  parsed {len(horses)} horse-race records\n")
for h in horses[:5]:
    print(f"  {h.race_id} 馬番{h.horse_num} 枠{h.waku_num} {h.horse_name!r} "
          f"({h.sex_code}/{h.age}歳) 騎手{h.jockey_short_name!r} 調教師{h.trainer_short_name!r}")
    print(f"    着順 入線={h.finish_order} 確定={h.confirmed_order} "
          f"タイム={h.finish_time} 単勝オッズ={h.win_odds} 人気={h.win_popularity} "
          f"後3F={h.final_3f}")
