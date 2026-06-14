"""フェーズ4 検証: diag_blend_decompose の CSV から、_investment_probability の
blend 重み (model_blend を係数 k で縮小 = 市場重みを増やす) と discount on/off を
sweep し、top-1 (◎) の Brier・EV 較正・EV フィルタ回収率を 2025H2 / 2026 別に測る。

bet の払戻は k に依存しない (賭ける馬は不変)。k が変えるのは:
  - 投資確率 invest = (cal*w + market*(1-w))*discount の値 → Brier
  - それに基づく EV = invest*odds → EV フィルタの選別と「EV 較正」

k=1.0: 現行重み再現 / k=0.0: 市場のみ / discount off も比較。
市場のみ Brier が現行 blend より低ければ「モデルが calibration を悪化させている」証拠。

usage:
    python -m scripts.diag_blend_sweep --in data/diag/decompose_2025H2_2026.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from predictor.rules import _w
from predictor.stats import bootstrap_return_rate

TIERW = {
    "高信頼": _w("model_blend.high", 0.85),
    "標準": _w("model_blend.standard", 0.78),
    "接戦": _w("model_blend.close", 0.70),
    "混戦": _w("model_blend.tight", 0.62),
    "暫定": _w("model_blend.tentative", 0.30),
}
DEFAULT_W = _w("model_blend.default", 0.55)
DISC = {"base": _w("discount.base", 0.92), "over8": _w("discount.over8", 0.90),
        "over15": _w("discount.over15", 0.82), "over30": _w("discount.over30", 0.72)}


def f(r, k):
    try:
        return float(r[k] or 0)
    except (ValueError, TypeError):
        return 0.0


def discount(odds: float) -> float:
    d = DISC["base"]
    if odds >= 30:
        d *= DISC["over30"]
    elif odds >= 15:
        d *= DISC["over15"]
    elif odds >= 8:
        d *= DISC["over8"]
    return d


def invest_prob(r, k: float, use_discount: bool) -> float:
    cal = f(r, "cal_model_top")
    mkt = f(r, "market_top")
    odds = f(r, "odds")
    w = min(1.0, TIERW.get((r["confidence"] or "").strip(), DEFAULT_W) * k)
    blended = cal * w + mkt * (1 - w) if mkt > 0 else cal
    return blended * discount(odds) if use_discount else blended


def brier(rows, k, ud):
    if not rows:
        return 0.0
    return sum((invest_prob(r, k, ud) - int(r["y_win"]))**2 for r in rows) / len(rows)


def ret_filter(rows, k, ud, ev_min):
    pays = []
    for r in rows:
        ev = invest_prob(r, k, ud) * f(r, "odds")
        if ev >= ev_min:
            pays.append(int(r["tan_payout"] or 0))
    n = len(pays)
    if n == 0:
        return (0, 0.0, (0, 0))
    ret = sum(pays) / (100 * n)
    _, lo, hi = bootstrap_return_rate(pays, [100] * n)
    return (n, ret, (lo, hi))


def ev_buckets(rows, k, ud):
    out = []
    for lo, hi in [(0, 0.8), (0.8, 1.0), (1.0, 1.2), (1.2, 1.5), (1.5, 99)]:
        pays = [int(r["tan_payout"] or 0) for r in rows
                if lo <= invest_prob(r, k, ud) * f(r, "odds") < hi]
        n = len(pays)
        ret = sum(pays) / (100 * n) if n else 0.0
        out.append((lo, hi, n, ret))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    args = ap.parse_args()
    rows = list(csv.DictReader(open(args.inp, encoding="utf-8")))

    folds = [
        ("2025H2", [r for r in rows if "20250701" <= r["date"] <= "20251231"]),
        ("2026P", [r for r in rows if "20260101" <= r["date"] <= "20261231"]),
    ]
    KS = [("現行 k=1.0", 1.0, True), ("k=0.8", 0.8, True), ("k=0.6", 0.6, True),
          ("k=0.4", 0.4, True), ("k=0.2", 0.2, True), ("市場のみ k=0", 0.0, True),
          ("現行 discount off", 1.0, False), ("k=0.4 disc off", 0.4, False)]

    for fname, fr in folds:
        print(f"\n========== {fname} (◎ picks={len(fr)}) ==========")
        print(f"{'config':22s}{'Brier':>8}{'EV>=1.1 n/ret':>18}{'all◎ret':>10}")
        all_pays = [int(r["tan_payout"] or 0) for r in fr]
        all_ret = sum(all_pays) / (100 * len(fr)) if fr else 0
        for label, k, ud in KS:
            b = brier(fr, k, ud)
            n, ret, ci = ret_filter(fr, k, ud, 1.10)
            print(f"{label:22s}{b:>8.4f}{f'{n}/{ret*100:.0f}%':>18}{all_ret*100:>9.0f}%")
        print("  -- EV 較正 (現行 k=1.0): " + " ".join(
            f"[{lo:.1f},{hi:.1f})n{n}={ret*100:.0f}%" for lo, hi, n, ret in ev_buckets(fr, 1.0, True)))
        print("  -- EV 較正 (k=0.4):     " + " ".join(
            f"[{lo:.1f},{hi:.1f})n{n}={ret*100:.0f}%" for lo, hi, n, ret in ev_buckets(fr, 0.4, True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
