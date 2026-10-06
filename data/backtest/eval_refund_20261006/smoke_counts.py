"""§8-6 の修正前後で、collect の集合の件数だけを比べる (回収率・係数・的中は見ない)。

usage: python smoke_counts.py <code_root> <out_json>
DB は本番 checkout の keiba.db を mode=ro で読む。
"""
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
PROD_DB = Path(r"C:\Users\kizun\dev\keiba-yosou\data\keiba.db")

import scripts.fundamental_model as fm  # noqa: E402
import scripts.market_offset_eval as moe  # noqa: E402

assert Path(moe.__file__).resolve().is_relative_to(root)
fm.DB_PATH = PROD_DB
moe.DB_PATH = PROD_DB
real_build = fm.build_dataset
moe.build_dataset = lambda f, t: real_build(f, t, db_path=PROD_DB) if "db_path" in real_build.__code__.co_varnames else real_build(f, t)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    samples, counts, info = moe.collect("20260509", "20260831")
fresh = {s["race_id"] for s in samples if s["lead_min"] <= moe.DEFAULT_MAX_LEAD_MINUTES}
out = {"root": str(root), "counts": dict(counts),
       "n_races_all": len({s["race_id"] for s in samples}), "n_horses_all": len(samples),
       "n_races_fresh": len(fresh),
       "exclusions": info.get("race_exclusions"),
       "exclusion_reasons": dict(Counter(e["reason"] for e in info.get("race_exclusions") or []))}
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "exclusions"}, ensure_ascii=False, indent=1))
