"""Grid-search small weight changes against backtest return rate."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest import run_backtest

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS_PATH = ROOT / "predictor" / "weights.json"


def set_path(data: dict, path: str, value: float) -> dict:
    out = copy.deepcopy(data)
    cur = out
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", required=True)
    ap.add_argument("--path", default="recent_avg.excellent")
    ap.add_argument("--values", required=True, help="comma separated numbers")
    ap.add_argument("--bet", default="tan", choices=["tan", "fuku"])
    ap.add_argument("--filter-from-config", action="store_true")
    args = ap.parse_args()

    original = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    values = [float(v.strip()) for v in args.values.split(",") if v.strip()]
    print("path,value,bets,hits,hit_rate,return_rate,profit")
    try:
        for value in values:
            WEIGHTS_PATH.write_text(
                json.dumps(set_path(original, args.path, value), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            result = run_backtest(
                args.from_date,
                args.to_date,
                args.bet,
                filter_from_config=args.filter_from_config,
                progress_every=0,
            )
            print(
                f"{args.path},{value},{result['races_bet']},{result['hits']},"
                f"{result['hit_rate'] * 100:.1f},{result['return_rate'] * 100:.1f},"
                f"{result['return_total'] - result['bet_total']}"
            )
    finally:
        WEIGHTS_PATH.write_text(
            json.dumps(original, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
