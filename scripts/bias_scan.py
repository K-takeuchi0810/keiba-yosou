"""層別 特徴量バイアス検証ツール。

同じ競馬場・同じ馬場状態でも、開催が進む (nichiji が進む) ・雨が降る等で
レース傾向は変わる。現行は weights.json も LGBM も「全レース一律」なので、
こうしたセグメント差が均されて系統的バイアスになっている疑いがある。

本ツールはレースを以下の軸で層別し、各セグメントで
  calibration gap = mean(予想勝率) - 実勝率  (符号付き)
を Wilson CI とサンプル数ゲート付きで算出し、「どこに本物のバイアスが
あるか」を bias_severity = |gap| * sqrt(effective_n) 降順でランキング表示する。

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
加えて厳選 2 軸クロス (track×condition / surface×condition / track×meet /
track×kaiji / surface×weather_wet)。

== subject (pick / all) の使い分け ==
  - pick (既定): ◎ 1 頭 / レース。「◎ を出し続けた場合の実害」を測る。
    1 レース 1 レコードなので Wilson CI / return bootstrap が統計的に妥当。
  - all: 全馬全レコード。スコアリング全体の reliability を見る。ただし
    1 レース内は「誰か 1 頭が 1 着」の制約で actual が完全相関するため、
    有効サンプル数は馬行数ではなく **レース数 (n_races)**。Wilson CI を馬行
    n で出すと過度に狭くなる (偽陽性増)。よって all モードでは gap の有意
    判定は出さず (None)、bias_severity も sqrt(n_races) で計算し、return 系
    指標は「全馬買い」が戦略でないため出さない。reliability の点推定専用。
  pick に偏りがあり all に無ければ「◎選択ロジック固有のバイアス」、両方に
  あれば「スコアリング自体のバイアス」と切り分けられる。

== 次フェーズ (セグメント別重み付け) の前提条件 ==
重み付けの変更は本ツールでは行わない (診断のみ)。CLAUDE.md の過適合警告
(P12 崩壊) に従い、ranked セルを重み変更の根拠に使う前に必ず
  (1) 多重比較を考慮しても有意 (本ツールは ~150 セルを単独検定するため
      期待偽陽性が出力ヘッダに表示される。Bonferroni 等で再評価せよ)、
  (2) 2024 と 2025 の独立期間で再現、
  (3) holdout 通過、
の 3 条件を確認すること。SIG* は単期間の統計的有意を示すだけで、重み変更
の十分条件ではない。
TODO (type-A 移行時): pick の gap 有意判定は mean_pred を定数扱いし実勝率の
Wilson CI と比較する近似。重み変更の足切りに使う際は mean_pred の標準誤差も
合成した two-proportion 的検定へ格上げすること (2026-06-30 検証監査指摘)。

== 解釈上の注意 ==
- mean_pred は race 内 Σ=1 正規化済の確率の平均なので、平均出走頭数 (avg_field)
  に依存する (小頭数セルほど機械的に高い)。avg_field が大きく異なるセル間で
  生 gap を直接比較すると頭数効果をバイアスと誤認しうる。次フェーズで
  segment 間比較する際は field 層別 (近い avg_field 同士) で見ること。
- return 系指標は単勝 (tan) のみ。複勝 (fuku) のセグメント別 calibration を
  診断したい場合は get_payout(..., "fuku") 経路の追加が必要 (将来拡張)。

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
from predictor.rules import is_tentative, predict_race
from predictor.stats import bootstrap_return_rate, wilson_ci
from scripts.backtest import (
    popularity_config,
    race_odds_untrusted,
    snapshot_meta,
    distance_bucket_label,
    get_payout,
    horses_for_race,
    list_races,
)
from web.codes import track_name, track_type

# gap がこの値以上なら "大きい" 偏りとして SIG* 表示 (有意 かつ 実用的に無視できない)
MATERIAL_GAP = 0.03

# 馬場状態コード -> ASCII 安定キー (JSON キー兼ソート用)。表示は _DISPLAY。
_CONDITION_KEYS = {"1": "firm", "2": "good", "3": "yielding", "4": "soft"}
# 天候コード -> ASCII 安定キー。
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
        # 障害は芝・ダート両区間。"0"/空は未設定なので、有効な方を採用
        # ("0" は truthy 文字列なので or 連結だと誤って "0" を拾う点に注意)。
        turf_c = (race.get("turf_condition") or "").strip()
        dirt_c = (race.get("dirt_condition") or "").strip()
        code = turf_c if turf_c in _CONDITION_KEYS else dirt_c
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
    """開催進行。nichiji (開催内の日) を early/mid/late に集約。

    JRA の 1 開催は通常 6〜12 日 (土日 × 3〜6 週)。馬場は開催が進むほど内が
    荒れ外差し有利に傾くので、序盤 (1-2 日目) / 中盤 (3-5 日目) / 終盤 (6 日目
    以降) の 3 段で「進行に伴う傾向シフト」を捉える。バケット内の単調ドリフト
    は別軸 day_of_meet (nichiji 生値) で観察する。
    """
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
    "track_x_condition": ("track", "condition"),    # 同一場で馬場が変わる仮説
    "surface_x_condition": ("surface", "condition"),
    "track_x_meet": ("track", "meet"),              # 場ごとの開催進行ドリフト
    "track_x_kaiji": ("track", "kaiji"),            # 春/秋・仮柵位置で変わる同一場
    "surface_x_weather_wet": ("surface", "weather_wet"),  # 雨仮説
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
    """1 セグメントの蓄積器。

    calibration 統計は **streaming 集計** (件数/Σp/勝数/Σ二乗誤差) で持ち、
    subject=all の 2 年全馬行 (数十万レコード) でも list を溜めずメモリ一定にする
    (2026-06-30 data-pipeline 監査指摘)。return 用の払戻系列は pick subject のみ
    (1 レース 1 件) なので list のままで軽量。

    n_races は「このセルに寄与したレース数」= all モードの有効サンプルサイズ。
    全軸がレース単位属性 (track/surface/condition/…) なので、1 レースは各軸の
    ちょうど 1 セルに丸ごと入る。よって add_race を 1 レース 1 回呼べばよい。
    """

    __slots__ = ("n", "sum_prob", "wins", "sum_sq_err", "top3", "warn_n",
                 "payouts_trusted", "stakes_trusted", "n_trusted", "n_races", "field_sum")

    def __init__(self) -> None:
        self.n = 0
        self.sum_prob = 0.0
        self.wins = 0
        self.sum_sq_err = 0.0   # Σ(p - y)^2 → Brier
        self.top3 = 0
        self.warn_n = 0         # feature_warnings 付きレコード数 (品質セグメント診断)
        self.payouts_trusted: list[int] = []
        self.stakes_trusted: list[int] = []
        self.n_trusted = 0
        self.n_races = 0
        self.field_sum = 0

    def add_race(self, field_size: int) -> None:
        """レース単位の寄与 (1 レース 1 回)。有効 n と平均出走頭数を蓄積。"""
        self.n_races += 1
        self.field_sum += field_size

    def add(self, prob: float, actual: int, top3: bool, payout: int, odds_trusted: bool,
            has_warning: bool = False) -> None:
        """レコード単位の寄与 (pick は 1/レース、all は 1/馬)。"""
        p = max(0.0, min(1.0, float(prob)))  # calibration_report と同じクランプ
        y = 1 if actual else 0
        self.n += 1
        self.sum_prob += p
        self.wins += y
        self.sum_sq_err += (p - y) ** 2
        self.top3 += int(top3)
        if has_warning:
            self.warn_n += 1
        if odds_trusted:
            self.payouts_trusted.append(payout)
            self.stakes_trusted.append(100)
            self.n_trusted += 1


def summarize_cell(cell: Cell, min_n: int, subject: str) -> dict:
    n = cell.n
    wins = cell.wins
    mean_pred = cell.sum_prob / n if n else 0.0
    actual_rate = wins / n if n else 0.0
    gap = mean_pred - actual_rate
    lo, hi = wilson_ci(wins, n)

    # 有効サンプルサイズ: pick は 1 レース 1 行なので n。all はレース内相関で
    # 有効 n がレース数に縮むので n_races。ゲート/severity に effective_n を使う。
    effective_n = cell.n_races if subject == "all" else n

    # gap の有意判定は pick のみ。all は馬行 Wilson CI が過度に狭く偽陽性源に
    # なるため出さない (None) — reliability 点推定専用。
    if subject == "all":
        gap_significant: bool | None = None
    else:
        gap_significant = n > 0 and (mean_pred < lo or mean_pred > hi)

    # Brier は streaming の Σ(p-y)^2 / n。calibration_report と同一定義 (clamp 済 p)。
    brier = round(cell.sum_sq_err / n, 6) if n else None

    # return は pick のみ (1 bet/レースで bootstrap が妥当)。all は「全馬買い」
    # が戦略でなく、馬単位 bootstrap も race 内相関を無視するため出さない。
    if subject == "pick" and cell.n_trusted:
        ret_point, ret_lo, ret_hi = bootstrap_return_rate(cell.payouts_trusted, cell.stakes_trusted)
    else:
        ret_point = ret_lo = ret_hi = None

    avg_field = round(cell.field_sum / cell.n_races, 1) if cell.n_races else 0.0
    qualifies = effective_n >= min_n
    return {
        "n": n,
        "n_races": cell.n_races,
        "n_trusted": cell.n_trusted,
        "effective_n": effective_n,
        "avg_field": avg_field,
        "mean_pred": round(mean_pred, 4),
        "actual_rate": round(actual_rate, 4),
        "calibration_gap": round(gap, 4),
        "ci_lo": round(lo, 4),
        "ci_hi": round(hi, 4),
        "gap_significant": gap_significant,
        "bias_severity": round(abs(gap) * math.sqrt(effective_n), 4) if qualifies else None,
        "brier": brier,
        "win_pct": round(wins / n * 100, 1) if n else 0.0,
        "top3_pct": round(cell.top3 / n * 100, 1) if n else 0.0,
        # feature_warnings 付きレコードの数と率。gap が大きいセルの説明仮説
        # 「そのセグメントは特徴量欠損 (leg_quality 等) が多いだけでは」を即検証できる。
        "warn_n": cell.warn_n,
        "warn_pct": round(cell.warn_n / n * 100, 1) if n else 0.0,
        "return_pct": round(ret_point * 100, 1) if ret_point is not None else None,
        "return_ci": [round(ret_lo * 100, 1), round(ret_hi * 100, 1)] if ret_point is not None else None,
        "status": "ok" if qualifies else "insufficient",
    }


def severity_tag(cell_stats: dict) -> str:
    if not cell_stats["gap_significant"]:  # None or False
        return ""
    return "SIG*" if abs(cell_stats["calibration_gap"]) >= MATERIAL_GAP else "sig"


# ---------------------------------------------------------------------------
# メイン走査
# ---------------------------------------------------------------------------
def run_scan(conn, from_date: str, to_date: str, subject: str, axes: list[str],
             enable_cross: bool, min_n: int, min_n_cross: int,
             odds_gate: bool, include_tentative: bool) -> dict:
    pop_cfg = popularity_config()
    max_age = pop_cfg.get("max_snapshot_age_min")
    cross_specs = CROSS_SPECS if enable_cross else {}

    axis_cells: dict[str, dict[str, Cell]] = {a: defaultdict(Cell) for a in axes}
    cross_cells: dict[str, dict[str, Cell]] = {c: defaultdict(Cell) for c in cross_specs}
    global_cell = Cell()

    n_races = n_skip_tentative = n_no_winner = n_no_horses = n_odds_untrusted = 0
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

        odds_trusted = (not odds_gate) or (not race_odds_untrusted(horses, race, max_age))
        if not odds_trusted:
            n_odds_untrusted += 1
        surface = surface_key(race)
        field_size = len(horses)

        # レコード化: (prob, actual, top3, payout, has_warning)。subject で対象を切替。
        records: list[tuple[float, int, bool, int, bool]] = []
        if subject == "pick":
            if not include_tentative and is_tentative(preds):
                n_skip_tentative += 1
                continue
            top = preds[0]
            actual = 1 if top.horse_num == actual_win["horse_num"] else 0
            records.append((top.raw_blended_probability, actual,
                            top.horse_num in actual_top3,
                            get_payout(conn, race, top.horse_num, "tan"),
                            bool(getattr(top, "feature_warnings", None))))
        else:  # all
            for p in preds:
                actual = 1 if p.horse_num == actual_win["horse_num"] else 0
                records.append((p.raw_blended_probability, actual,
                                p.horse_num in actual_top3,
                                get_payout(conn, race, p.horse_num, "tan"),
                                bool(getattr(p, "feature_warnings", None))))
        if not records:
            continue
        n_races += 1

        # 全軸がレース単位属性なのでキーは 1 レース 1 回計算 (高速)。
        axis_keys = {a: AXIS_FUNCS[a](race, surface) for a in axes}
        cross_keys = {c: f"{AXIS_FUNCS[a1](race, surface)}|{AXIS_FUNCS[a2](race, surface)}"
                      for c, (a1, a2) in cross_specs.items()}

        # レース単位の寄与 (有効 n / 平均頭数) を 1 回ずつ。
        global_cell.add_race(field_size)
        for a in axes:
            axis_cells[a][axis_keys[a]].add_race(field_size)
        for c in cross_specs:
            cross_cells[c][cross_keys[c]].add_race(field_size)

        # レコード単位の寄与。
        for prob, actual, top3, payout, has_warn in records:
            global_cell.add(prob, actual, top3, payout, odds_trusted, has_warn)
            for a in axes:
                axis_cells[a][axis_keys[a]].add(prob, actual, top3, payout, odds_trusted, has_warn)
            for c in cross_specs:
                cross_cells[c][cross_keys[c]].add(prob, actual, top3, payout, odds_trusted, has_warn)

    # 集計
    global_stats = summarize_cell(global_cell, min_n=0, subject=subject)
    axes_out = {a: {k: summarize_cell(c, min_n, subject) for k, c in cells.items()}
                for a, cells in axis_cells.items()}
    cross_out = {c: {k: summarize_cell(cell, min_n_cross, subject) for k, cell in cells.items()}
                 for c, cells in cross_cells.items()}

    # 全軸ランキング (status=ok のみ、bias_severity 降順)。pick は有意セルのみ、
    # all は有意判定不可なので effective_n ゲートを通った全セル。
    ranked: list[dict] = []
    for group_name, cells in list(axes_out.items()) + list(cross_out.items()):
        for key, st in cells.items():
            if st["status"] != "ok":
                continue
            if subject == "pick" and not st["gap_significant"]:
                continue
            ranked.append({
                "axis": group_name, "cell": key, "n": st["n"],
                "effective_n": st["effective_n"],
                "calibration_gap": st["calibration_gap"],
                "bias_severity": st["bias_severity"],
                "gap_significant": st["gap_significant"],
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
        "n_no_horses": n_no_horses,
        "n_odds_untrusted": n_odds_untrusted,
        "n_cells_tested": sum(len(v) for v in axes_out.values()) + sum(len(v) for v in cross_out.values()),
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
        f"  {display_cell(axis, key):<10} n={st['n']:>5}(nr={st['n_races']:>5} tr={st['n_trusted']:>5}) "
        f"fld={st['avg_field']:>4} pred={st['mean_pred']:.3f} "
        f"actual={st['actual_rate']:.3f} gap={st['calibration_gap']:+.3f} "
        f"CI[{st['ci_lo']:.3f}-{st['ci_hi']:.3f}] {severity_tag(st):<4} "
        f"brier={st['brier']} win={st['win_pct']}% {ret}"
    )


def print_report(result: dict, top: int) -> None:
    g = result["global"]
    subject = result["subject"]
    print("=" * 78)
    print(f"BIAS SCAN  {result['from_date']}-{result['to_date']}  subject={subject}")
    print(f"  races={result['n_races_scanned']} skip_tentative={result['n_skip_tentative']} "
          f"odds_untrusted={result['n_odds_untrusted']} min_n={result['min_n']} "
          f"min_n_cross={result['min_n_cross']}")
    print("  ⚠ TEST=2年。細セルはノイズ。信用するのは gap_significant(SIG*/sig) かつ n>=min_n のみ。")
    if result.get("calibration_in_sample"):
        print("  ⚠ calibration_in_sample=True — 評価期間が calibrator fit 期間と重複。Brier/gap は in-sample。")
    if subject == "all":
        print("  ⚠ subject=all: n は馬行数。レース内相関で有効 n はレース数(nr)。Wilson CI は")
        print("     過度に狭く有意判定は出さない。bias_severity は sqrt(nr) 基準。reliability 点推定専用。")
    print(f"  GLOBAL REF: pred={g['mean_pred']:.3f} actual={g['actual_rate']:.3f} "
          f"gap={g['calibration_gap']:+.3f} CI[{g['ci_lo']:.3f}-{g['ci_hi']:.3f}] "
          f"n={g['n']} nr={g['n_races']} fld={g['avg_field']}")
    print("=" * 78)

    # 全軸ランキング
    n_cells = result.get("n_cells_tested", 0)
    print("\n### MOST BIASED CELLS (全軸, bias_severity 降順, qualifying のみ)")
    print(f"  ⚠ 多重比較未補正: 約{n_cells}セル×α=0.05 → 期待偽陽性 ~{n_cells * 0.05:.0f} セル。")
    print("     SIG*/sig の単期間判断は禁止。重み変更は 2024/2025 独立再現 + holdout 通過後のみ。")
    if not result["ranked"]:
        print("  (有意な偏りセルなし)")
    for r in result["ranked"][:top]:
        print(f"  [{r['axis']}] {display_cell(r['axis'], r['cell'])}: "
              f"gap={r['calibration_gap']:+.3f} n={r['n']} eff_n={r['effective_n']} "
              f"severity={r['bias_severity']}")

    # 軸ごと
    for axis, cells in result["axes"].items():
        ok = {k: v for k, v in cells.items() if v["status"] == "ok"}
        insuf = {k: v for k, v in cells.items() if v["status"] == "insufficient"}
        print(f"\nAXIS: {axis} (ok={len(ok)} insufficient={len(insuf)})")
        for key, st in sorted(ok.items(), key=lambda kv: kv[1]["bias_severity"] or 0, reverse=True)[:top]:
            print(_fmt_cell_line(axis, key, st))
        if insuf:
            tags = ", ".join(f"{display_cell(axis, k)}(n={v['n']},eff={v['effective_n']})"
                             for k, v in sorted(insuf.items()))
            print(f"  INSUFFICIENT: {tags}")

    # クロス
    for cname, cells in result.get("cross", {}).items():
        ok = {k: v for k, v in cells.items() if v["status"] == "ok"}
        print(f"\nCROSS: {cname} (ok={len(ok)} / {len(cells)} cells, min_n_cross={result['min_n_cross']})")
        a1, a2 = CROSS_SPECS[cname]
        for key, st in sorted(ok.items(), key=lambda kv: kv[1]["bias_severity"] or 0, reverse=True)[:top]:
            k1, k2 = key.split("|", 1)
            label = f"{display_cell(a1, k1)}×{display_cell(a2, k2)}"
            print(f"  {label:<14} n={st['n']:>5} eff={st['effective_n']:>5} "
                  f"gap={st['calibration_gap']:+.3f} CI[{st['ci_lo']:.3f}-{st['ci_hi']:.3f}] {severity_tag(st)}")


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
    if not args.save:
        logger.warning("--save なし: meta(git_sha/calibrator版)/結果が揮発し後から再現できません。")

    with (open_db(args.db) if args.db else open_db()) as conn:
        result = run_scan(
            conn, args.from_date, args.to_date, args.subject, axes,
            args.cross, args.min_n, args.min_n_cross, args.odds_gate,
            args.include_tentative,
        )

    # in-sample 判定 (calibrator fit 窓との重複)
    meta = snapshot_meta()
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
        # 原子書き込み: 中断による corrupt JSON を防ぐため tmp に書いて rename。
        tmp_path = out_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.rename(out_path)
        print(f"\nsaved: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
