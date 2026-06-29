"""層別 特徴量バイアス検証ツール。

同じ競馬場・同じ馬場状態でも、開催が進む (nichiji が進む) ・雨が降る等で
レース傾向は変わる。現行は weights.json も LGBM も「全レース一律」なので、
こうしたセグメント差が均されて系統的バイアスになっている疑いがある。

本ツールはレースを以下の軸で層別し、各セグメントで
  calibration gap = mean(予想勝率) - 実勝率  (符号付き)
を Wilson CI とサンプル数ゲート付きで算出し、「どこに本物のバイアスが
あるか」を bias_severity = |gap| * sqrt(n) 降順でランキング表示する。

  - track       競馬場
  - surface     芝 / ダート / 障害
  - distance    sprint/mile/middle/long
  - condition   馬場状態 (良/稍重/重/不良, サーフェス依存)
  - weather     天候 6 値
  - weather_wet 晴曇 vs 雨 (粗 2 値, 「雨」仮説用)
  - meet        開催進行 early/mid/late (nichiji 由来)
  - day_of_meet 開催日 生値 (バケット内ドリフトを隠さない)
  - kaiji       開催回 生値 (春/秋の同一場を分離)
  - month       月 01..12
  - season      winter/spring/summer/autumn
加えて厳選 2 軸クロス (track×condition / surface×condition /
track×meet / surface×weather_wet)。

重み付けの変更は行わない (診断のみ)。CLAUDE.md の過適合警告 (P12 崩壊) に
従い、ranked セルが有意かつ複数期間で再現するのを確認してから次フェーズで
重み付けを判断する。

usage:
    python -m scripts.bias_scan                         # 既定 TEST 2024-2025
    python -m scripts.bias_scan --from 20250101 --to 20250131
    python -m scripts.bias_scan --subject all --save --rule-version bias-baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

from config import DATA_PERIODS
from db import open_db
from predictor.calibration import calibration_report
from predictor.rules import is_tentative, predict_race
from predictor.stats import bootstrap_return_rate, wilson_ci
from scripts.backtest import (
    _popularity_config,
    _race_odds_untrusted,
    _snapshot_meta,
    distance_bucket_label,
    get_payout,
    horses_for_race,
    list_races,
)
from web.codes import ground_name, track_name, track_type, weather_name

# gap がこの値以上なら "大きい" 偏りとして SIG* 表示 (有意 かつ 実用的に無視できない)
MATERIAL_GAP = 0.03

# 馬場状態コード -> ASCII 安定キー (JSON キー兼ソート用)。表示は ground_name。
_CONDITION_KEYS = {"1": "firm", "2": "good", "3": "yielding", "4": "soft"}
# 天候コード -> ASCII 安定キー。表示は weather_name。
_WEATHER_KEYS = {
    "1": "clear", "2": "cloudy", "3": "light_rain",
    "4": "rain", "5": "light_snow", "6": "snow",
}
# 雨仮説用の粗 2 値。晴/曇 = dry、小雨/雨/雪 = wet。
_WET_CODES = {"3", "4", "5", "6"}
_DRY_CODES = {"1", "2"}


# ---------------------------------------------------------------------------
# セグメントキー導出 (race dict + surface を受け、ASCII 安定な短い文字列を返す)
# ---------------------------------------------------------------------------
def surface_key(race: dict) -> str:
    jp = track_type(race.get("track_type_code") or "")
    return {"芝": "turf", "ダート": "dirt", "障害": "jump"}.get(jp, "other")


def condition_key(race: dict, surface: str) -> str:
    """馬場状態。芝なら turf_condition、ダートなら dirt_condition を選択。

    障害は芝・ダート両区間を走るため populated な方をフォールバック採用。
    """
    if surface == "turf":
        code = race.get("turf_condition")
    elif surface == "dirt":
        code = race.get("dirt_condition")
    else:
        code = race.get("turf_condition") or race.get("dirt_condition")
    return _CONDITION_KEYS.get((code or "").strip(), "unknown")


def weather_key(race: dict) -> str:
    return _WEATHER_KEYS.get((race.get("weather_code") or "").strip(), "unknown")


def weather_wet_key(race: dict) -> str:
    code = (race.get("weather_code") or "").strip()
    if code in _WET_CODES:
        return "wet"
    if code in _DRY_CODES:
        return "dry"
    return "unknown"


def meet_progress_key(race: dict) -> str:
    """開催進行。nichiji (開催内の日, 通常 01..12) を early/mid/late に。"""
    try:
        nd = int((race.get("nichiji") or "0").strip())
    except ValueError:
        return "unknown"
    if nd <= 0:
        return "unknown"
    if nd <= 2:
        return "early"
    if nd <= 5:
        return "mid"
    return "late"


def day_of_meet_key(race: dict) -> str:
    nd = (race.get("nichiji") or "").strip()
    return nd.zfill(2) if nd else "unknown"


def kaiji_key(race: dict) -> str:
    k = (race.get("kaiji") or "").strip()
    return k.zfill(2) if k else "unknown"


def month_key(race: dict) -> str:
    md = (race.get("race_month_day") or "").strip()
    return md[:2] if len(md) >= 2 else "unknown"


def season_key(race: dict) -> str:
    mk = month_key(race)
    if mk == "unknown":
        return "unknown"
    m = int(mk)
    if m in (12, 1, 2):
        return "winter"
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    return "autumn"


def track_key(race: dict) -> str:
    return (race.get("track_code") or "").strip() or "unknown"


# axis 名 -> (race, surface) を受けてキーを返す関数
AXIS_FUNCS = {
    "track": lambda r, s: track_key(r),
    "surface": lambda r, s: s,
    "distance": lambda r, s: distance_bucket_label(r.get("distance")),
    "condition": lambda r, s: condition_key(r, s),
    "weather": lambda r, s: weather_key(r),
    "weather_wet": lambda r, s: weather_wet_key(r),
    "meet": lambda r, s: meet_progress_key(r),
    "day_of_meet": lambda r, s: day_of_meet_key(r),
    "kaiji": lambda r, s: kaiji_key(r),
    "month": lambda r, s: month_key(r),
    "season": lambda r, s: season_key(r),
}
ALL_AXES = list(AXIS_FUNCS)

# 厳選 2 軸クロス (全直積はセル枯れ=ノイズなので禁止)。"|" 区切りキー。
CROSS_SPECS = {
    "track_x_condition": ("track", "condition"),
    "surface_x_condition": ("surface", "condition"),
    "track_x_meet": ("track", "meet"),
    "surface_x_weather_wet": ("surface", "weather_wet"),
}

# 表示用ラベル (ASCII キー -> 人間可読)。コンソール専用、JSON は ASCII キーのまま。
_DISPLAY = {
    "turf": "芝", "dirt": "ダート", "jump": "障害", "other": "他",
    "firm": "良", "good": "稍重", "yielding": "重", "soft": "不良",
    "clear": "晴", "cloudy": "曇", "light_rain": "小雨",
    "rain": "雨", "light_snow": "小雪", "snow": "雪",
    "dry": "乾", "wet": "湿", "early": "序盤", "mid": "中盤", "late": "終盤",
}


def display_cell(axis: str, key: str) -> str:
    if axis == "track":
        return track_name(key)
    return _DISPLAY.get(key, key)


# ---------------------------------------------------------------------------
# セル集計
# ---------------------------------------------------------------------------
class Cell:
    """1 セグメントの蓄積器。calibration は全レコード、return はオッズ信頼分のみ。"""

    __slots__ = ("probs", "actuals", "top3", "payouts_trusted", "stakes_trusted", "n_trusted")

    def __init__(self) -> None:
        self.probs: list[float] = []
        self.actuals: list[int] = []
        self.top3 = 0
        self.payouts_trusted: list[int] = []
        self.stakes_trusted: list[int] = []
        self.n_trusted = 0

    def add(self, prob: float, actual: int, top3: bool, payout: int, odds_trusted: bool) -> None:
        self.probs.append(prob)
        self.actuals.append(actual)
        self.top3 += int(top3)
        if odds_trusted:
            self.payouts_trusted.append(payout)
            self.stakes_trusted.append(100)
            self.n_trusted += 1


def summarize_cell(cell: Cell, min_n: int) -> dict:
    n = len(cell.probs)
    wins = sum(cell.actuals)
    mean_pred = sum(cell.probs) / n if n else 0.0
    actual_rate = wins / n if n else 0.0
    gap = mean_pred - actual_rate
    lo, hi = wilson_ci(wins, n)
    gap_significant = n > 0 and (mean_pred < lo or mean_pred > hi)
    brier = calibration_report(
        [{"probability": p, "actual": a} for p, a in zip(cell.probs, cell.actuals)]
    )["brier_score"]
    # return (オッズ信頼分のみ)
    if cell.n_trusted:
        ret_point, ret_lo, ret_hi = bootstrap_return_rate(cell.payouts_trusted, cell.stakes_trusted)
    else:
        ret_point = ret_lo = ret_hi = None
    return {
        "n": n,
        "n_trusted": cell.n_trusted,
        "mean_pred": round(mean_pred, 4),
        "actual_rate": round(actual_rate, 4),
        "calibration_gap": round(gap, 4),
        "ci_lo": round(lo, 4),
        "ci_hi": round(hi, 4),
        "gap_significant": gap_significant,
        "bias_severity": round(abs(gap) * math.sqrt(n), 4) if n >= min_n else None,
        "brier": brier,
        "win_pct": round(wins / n * 100, 1) if n else 0.0,
        "top3_pct": round(cell.top3 / n * 100, 1) if n else 0.0,
        "return_pct": round(ret_point * 100, 1) if ret_point is not None else None,
        "return_ci": [round(ret_lo * 100, 1), round(ret_hi * 100, 1)] if ret_point is not None else None,
        "status": "ok" if n >= min_n else "insufficient",
    }


def severity_tag(cell_stats: dict) -> str:
    if not cell_stats["gap_significant"]:
        return ""
    return "SIG*" if abs(cell_stats["calibration_gap"]) >= MATERIAL_GAP else "sig"


# ---------------------------------------------------------------------------
# メイン走査
# ---------------------------------------------------------------------------
def run_scan(conn, from_date: str, to_date: str, subject: str, axes: list[str],
             enable_cross: bool, min_n: int, min_n_cross: int,
             odds_gate: bool, include_tentative: bool) -> dict:
    pop_cfg = _popularity_config()
    max_age = pop_cfg.get("max_snapshot_age_min")

    axis_cells: dict[str, dict[str, Cell]] = {a: defaultdict(Cell) for a in axes}
    cross_cells: dict[str, dict[str, Cell]] = (
        {c: defaultdict(Cell) for c in CROSS_SPECS} if enable_cross else {}
    )
    global_cell = Cell()

    n_races = n_skip_tentative = n_no_winner = n_no_horses = 0
    feature_cache: dict = {}

    races = list_races(conn, from_date, to_date, jra_only=True, require_confirmed=True)
    for race in races:
        horses = horses_for_race(conn, race)
        if not horses:
            n_no_horses += 1
            continue
        actual_win = next((h for h in horses if h.get("confirmed_order") == 1), None)
        if not actual_win:
            n_no_winner += 1
            continue
        actual_top3 = {h["horse_num"] for h in horses if h.get("confirmed_order") in (1, 2, 3)}
        preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
        if not preds:
            continue

        odds_trusted = (not odds_gate) or (not _race_odds_untrusted(horses, race, max_age))
        surface = surface_key(race)
        n_races += 1

        # レコード化: (prob, actual, top3, payout)
        records: list[tuple[float, int, bool, int]] = []
        if subject == "pick":
            if not include_tentative and is_tentative(preds):
                n_skip_tentative += 1
                continue
            top = preds[0]
            actual = 1 if top.horse_num == actual_win["horse_num"] else 0
            top3 = top.horse_num in actual_top3
            payout = get_payout(conn, race, top.horse_num, "tan")
            records.append((top.raw_blended_probability, actual, top3, payout))
        else:  # all
            for p in preds:
                actual = 1 if p.horse_num == actual_win["horse_num"] else 0
                top3 = p.horse_num in actual_top3
                payout = get_payout(conn, race, p.horse_num, "tan")
                records.append((p.raw_blended_probability, actual, top3, payout))

        for prob, actual, top3, payout in records:
            global_cell.add(prob, actual, top3, payout, odds_trusted)
            for axis in axes:
                key = AXIS_FUNCS[axis](race, surface)
                axis_cells[axis][key].add(prob, actual, top3, payout, odds_trusted)
            for cname, (a1, a2) in (CROSS_SPECS.items() if enable_cross else []):
                k1 = AXIS_FUNCS[a1](race, surface)
                k2 = AXIS_FUNCS[a2](race, surface)
                cross_cells[cname][f"{k1}|{k2}"].add(prob, actual, top3, payout, odds_trusted)

    # 集計
    global_stats = summarize_cell(global_cell, min_n=0)
    axes_out: dict[str, dict[str, dict]] = {}
    for axis, cells in axis_cells.items():
        axes_out[axis] = {key: summarize_cell(c, min_n) for key, c in cells.items()}
    cross_out: dict[str, dict[str, dict]] = {}
    for cname, cells in cross_cells.items():
        cross_out[cname] = {key: summarize_cell(c, min_n_cross) for key, c in cells.items()}

    # 全軸ランキング (qualifying セルのみ, bias_severity 降順)
    ranked: list[dict] = []
    for axis, cells in axes_out.items():
        for key, st in cells.items():
            if st["status"] == "ok" and st["gap_significant"]:
                ranked.append({
                    "axis": axis, "cell": key, "n": st["n"],
                    "calibration_gap": st["calibration_gap"],
                    "bias_severity": st["bias_severity"],
                    "gap_significant": True,
                })
    for cname, cells in cross_out.items():
        for key, st in cells.items():
            if st["status"] == "ok" and st["gap_significant"]:
                ranked.append({
                    "axis": cname, "cell": key, "n": st["n"],
                    "calibration_gap": st["calibration_gap"],
                    "bias_severity": st["bias_severity"],
                    "gap_significant": True,
                })
    ranked.sort(key=lambda r: r["bias_severity"] or 0, reverse=True)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "subject": subject,
        "min_n": min_n,
        "min_n_cross": min_n_cross,
        "odds_gate": odds_gate,
        "n_races_scanned": n_races,
        "n_skip_tentative": n_skip_tentative,
        "n_no_winner": n_no_winner,
        "global": global_stats,
        "axes": axes_out,
        "cross": cross_out,
        "ranked": ranked,
    }


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------
def _fmt_cell_line(axis: str, key: str, st: dict) -> str:
    ret = f"ret={st['return_pct']}%" if st["return_pct"] is not None else "ret=n/a"
    return (
        f"  {display_cell(axis, key):<10} n={st['n']:>5} pred={st['mean_pred']:.3f} "
        f"actual={st['actual_rate']:.3f} gap={st['calibration_gap']:+.3f} "
        f"CI[{st['ci_lo']:.3f}-{st['ci_hi']:.3f}] {severity_tag(st):<4} "
        f"brier={st['brier']} win={st['win_pct']}% {ret}"
    )


def print_report(result: dict, top: int) -> None:
    g = result["global"]
    print("=" * 78)
    print(f"BIAS SCAN  {result['from_date']}-{result['to_date']}  subject={result['subject']}")
    print(f"  races={result['n_races_scanned']} skip_tentative={result['n_skip_tentative']} "
          f"min_n={result['min_n']} min_n_cross={result['min_n_cross']}")
    print("  ⚠ TEST=2年。細セルはノイズ。信用するのは gap_significant(SIG*/sig) かつ n>=min_n のみ。")
    print(f"  GLOBAL REF: pred={g['mean_pred']:.3f} actual={g['actual_rate']:.3f} "
          f"gap={g['calibration_gap']:+.3f} CI[{g['ci_lo']:.3f}-{g['ci_hi']:.3f}] n={g['n']}")
    print("=" * 78)

    # 全軸ランキング
    print("\n### MOST BIASED CELLS (全軸, bias_severity 降順, qualifying のみ)")
    if not result["ranked"]:
        print("  (有意な偏りセルなし)")
    for r in result["ranked"][:top]:
        print(f"  [{r['axis']}] {display_cell(r['axis'], r['cell'])}: "
              f"gap={r['calibration_gap']:+.3f} n={r['n']} severity={r['bias_severity']}")

    # 軸ごと
    for axis, cells in result["axes"].items():
        ok = {k: v for k, v in cells.items() if v["status"] == "ok"}
        insuf = {k: v for k, v in cells.items() if v["status"] == "insufficient"}
        print(f"\nAXIS: {axis} (ok={len(ok)} insufficient={len(insuf)})")
        for key, st in sorted(ok.items(), key=lambda kv: kv[1]["bias_severity"] or 0, reverse=True)[:top]:
            print(_fmt_cell_line(axis, key, st))
        if insuf:
            tags = ", ".join(f"{display_cell(axis, k)}(n={v['n']})" for k, v in sorted(insuf.items()))
            print(f"  INSUFFICIENT: {tags}")

    # クロス
    for cname, cells in result.get("cross", {}).items():
        ok = {k: v for k, v in cells.items() if v["status"] == "ok"}
        print(f"\nCROSS: {cname} (ok={len(ok)} / {len(cells)} cells, min_n_cross={result['min_n_cross']})")
        for key, st in sorted(ok.items(), key=lambda kv: kv[1]["bias_severity"] or 0, reverse=True)[:top]:
            k1, k2 = key.split("|", 1)
            a1, a2 = CROSS_SPECS[cname]
            label = f"{display_cell(a1, k1)}×{display_cell(a2, k2)}"
            print(f"  {label:<14} n={st['n']:>5} gap={st['calibration_gap']:+.3f} "
                  f"CI[{st['ci_lo']:.3f}-{st['ci_hi']:.3f}] {severity_tag(st)}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="層別 特徴量バイアス検証")
    ap.add_argument("--from", dest="from_date", default=DATA_PERIODS["test"]["from"])
    ap.add_argument("--to", dest="to_date", default=DATA_PERIODS["test"]["to"])
    ap.add_argument("--db", default=None)
    ap.add_argument("--subject", choices=["pick", "all"], default="pick")
    ap.add_argument("--axes", default="all", help=f"カンマ区切り or all: {','.join(ALL_AXES)}")
    ap.add_argument("--no-cross", dest="cross", action="store_false", default=True)
    ap.add_argument("--min-n", type=int, default=50)
    ap.add_argument("--min-n-cross", type=int, default=100)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--include-tentative", action="store_true")
    ap.add_argument("--no-odds-gate", dest="odds_gate", action="store_false", default=True)
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--rule-version", default="bias-scan")
    args = ap.parse_args()

    if args.axes == "all":
        axes = list(ALL_AXES)
    else:
        axes = [a.strip() for a in args.axes.split(",") if a.strip()]
        bad = [a for a in axes if a not in AXIS_FUNCS]
        if bad:
            raise SystemExit(f"未知の軸: {bad}. 選択肢: {ALL_AXES}")

    tf, tt = DATA_PERIODS["train"]["from"], DATA_PERIODS["train"]["to"]
    if args.from_date <= tt and tf <= args.to_date:
        logger.warning(
            "評価期間 %s-%s は TRAIN 期間 %s-%s と重複しています。calibration gap が "
            "in-sample になり証拠力が落ちます。", args.from_date, args.to_date, tf, tt)

    with (open_db(args.db) if args.db else open_db()) as conn:
        result = run_scan(
            conn, args.from_date, args.to_date, args.subject, axes,
            args.cross, args.min_n, args.min_n_cross, args.odds_gate,
            args.include_tentative,
        )

    # in-sample 判定 (calibrator fit 窓との重複)
    meta = _snapshot_meta()
    ctf, ctt = meta.get("calibrator_trained_from"), meta.get("calibrator_trained_to")
    calibration_in_sample = bool(ctf and ctt and args.from_date <= str(ctt) and str(ctf) <= args.to_date)
    if calibration_in_sample:
        logger.warning("評価期間が calibrator fit 期間 %s-%s と重複。Brier 等は in-sample。", ctf, ctt)
    result["meta"] = meta
    result["calibration_in_sample"] = calibration_in_sample
    result["rule_version"] = args.rule_version

    print_report(result, args.top)

    if args.save:
        out_dir = Path(__file__).resolve().parent.parent / "data" / "bias_scan"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{stamp}_{args.rule_version}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nsaved: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
