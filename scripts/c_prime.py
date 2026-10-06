"""Phase 0.5-5 Group C′ — 展開 × メンバー構成 (脚質コード版) の特徴の計算 (2026-10-06)。

仕様: `docs/PHASE05_5_PREREG.md` §8-4 / §8-4c / §8-4c-2 / §8-6 / §8-6b、`docs/PHASE05_5_EXPLORATION.md` の C′-0〜C′-3。
ここにあるのは計算の部品だけで、どの年を読むかは呼び出し側 (`scripts/c_prime_explore.py`) が決める。

- 各馬の脚質は **対象日より前の日** の走の `leg_quality_code` (1〜4) だけから決める。対象レース自身の値は絶対に使わない
  (レース後に確定する値。`predictor/pit_view.py` の POST_RACE_COLUMNS)。同じ日の他のレースも使わない
- 窓は [対象日 − 365 日, 対象日 − 1 日]、直近 5 走の最頻値、同数なら最頻値の中で最も新しい走に現れた値
- 市場の列は `predictor.race_market.market_feature` (log) だけを `predictor.market_clogit` 経由で使う (§8-6b)。
  Group A の市場の関数 (logit の仕様) は使わない
- 標準化は pooled within-race SD (§8-4c-2): ddof 0・1 レース 1 票・分散 0 のレースも含む・市場の重みは使わない。
  欠損はレース内の欠損でない行の平均で埋める
"""
from __future__ import annotations

import hashlib
import math
import platform
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np

from config import guard_analysis_window
from predictor import market_clogit as mc
from predictor import race_market as rm
from predictor.eval_stats import conditional_logit

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "keiba.db"

PRIMARY_YEAR = 2025                 # 主検定の年。推定には渡さない
WINDOW_DAYS = 365
HISTORY_RUNS = 5
STYLE_CODES = ("1", "2", "3", "4")  # 1 = 逃 / 2 = 先 / 3 = 差 / 4 = 追
FRONT = ("1", "2")
BACK = ("3", "4")
OBSTACLE_FROM = 51                  # track_type_code がこれ以上なら障害 (§8-4b-2 と同じ)
TURF_CODES = range(10, 23)
DIRT_CODES = range(23, 30)
COMPONENTS = ("style_x_pace_fit", "front_competition_signed")
Z_DIRECTION = 2.0                   # 成分の |z| の最大がこれ未満なら「向きの定まらない合成」(台帳 C′-3)
STD_SUFFIX = "_std"


class CPrimeError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------------- 読み込み

def day_ordinal(ymd: str) -> int:
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])).toordinal()


def flat_surface(track_type_code) -> str | None:
    """'T' / 'D' / None (障害)。平地の範囲で未知のコードは止める (黙って落とさない)。"""
    try:
        tt = int(track_type_code)
    except (TypeError, ValueError):
        raise CPrimeError(f"track_type_code を解釈できない: {track_type_code!r}") from None
    if tt >= OBSTACLE_FROM:
        return None
    if tt in TURF_CODES:
        return "T"
    if tt in DIRT_CODES:
        return "D"
    raise CPrimeError(f"平地の未知の track_type_code: {track_type_code!r}")


@dataclass
class Run:
    race_id: str
    ymd: str
    ordinal: int
    horse: str
    horse_num: str
    abnormal: str
    finish: int
    win_odds: float            # 倍。0 以下は価格なし
    leg: str                   # 脚質コード (この走の結果。履歴としてだけ使う)


@dataclass
class Race:
    race_id: str
    ymd: str
    ordinal: int
    runs: list = field(default_factory=list)


def load_races(max_year: int, *, min_year: int = 2021, db_path: Path | str = DB_PATH,
               allow_primary_year: bool = False, primary_purpose: str | None = None,
               primary_year_history_only: bool = False) -> tuple[dict[str, Race], Counter]:
    """JRA (01〜10)・確定 (`data_div = 7`)・平地のレースと走。**探索は 2024 年以前だけ** (2025 は主検定の年)。

    `primary_year_history_only=True` (検出力の計算): 主検定の年の行は、履歴に要る列 (日付・馬・馬番・異常コード・脚質コード) だけを読み、
    着順とオッズは SQL の段で NULL にする (対象レースの結果を読まないことを、行ではなく SQL で保証する)。
    """
    if max_year >= PRIMARY_YEAR and not allow_primary_year:
        raise CPrimeError(f"探索で {PRIMARY_YEAR} 年以降を読もうとした (max_year={max_year})")
    if allow_primary_year and not primary_purpose:
        raise CPrimeError("主検定の年を読むときは primary_purpose (目的) を書く")
    from_date, to_date, _sealed = guard_analysis_window(f"{min_year}0101", f"{max_year}1231", context="c_prime.load_races")
    if primary_year_history_only:
        result_cols = (f"CASE WHEN CAST(h.race_year AS INTEGER) >= {PRIMARY_YEAR} THEN NULL ELSE h.confirmed_order END, "
                       f"CASE WHEN CAST(h.race_year AS INTEGER) >= {PRIMARY_YEAR} THEN NULL ELSE h.win_odds END")
    else:
        result_cols = "h.confirmed_order, h.win_odds"
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
        f"""SELECT h.race_year||h.race_month_day, h.track_code, h.kaiji, h.nichiji, h.race_num, r.track_type_code,
                  h.horse_num, h.blood_register_num, h.abnormal_code, {result_cols}, h.leg_quality_code
             FROM horse_races h
             JOIN races r ON r.race_year = h.race_year AND r.race_month_day = h.race_month_day
              AND r.track_code = h.track_code AND r.kaiji = h.kaiji AND r.nichiji = h.nichiji AND r.race_num = h.race_num
            WHERE (h.race_year||h.race_month_day) BETWEEN ? AND ?
              AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
              AND r.data_div = '7' AND h.horse_num NOT IN ('', '00')
            ORDER BY 1, h.track_code, h.race_num, h.horse_num""", (from_date, to_date)).fetchall()
    finally:
        conn.close()
    stats: Counter = Counter()
    races: dict[str, Race] = {}
    for ymd, tc, ka, ni, rn, tt, hn, bn, abn, fin, odds, leg in rows:
        if flat_surface(tt) is None:
            stats["skip_obstacle_rows"] += 1
            continue
        rid = f"{ymd}_{tc}_{ka}_{ni}_{rn}"
        race = races.get(rid)
        if race is None:
            race = races[rid] = Race(rid, ymd, day_ordinal(ymd))
        try:
            finish = int(fin or 0)
        except (TypeError, ValueError):
            finish = 0
        race.runs.append(Run(rid, ymd, race.ordinal, str(bn or "").strip(), str(hn).strip(), str(abn or "").strip(),
                             finish, (odds or 0) / 10.0, str(leg or "").strip()))
        stats["rows"] += 1
    stats["races"] = len(races)
    return races, stats


# ---------------------------------------------------------------------------------------------------- 脚質の履歴

def style_history(races: dict[str, Race]) -> dict[str, list[tuple[int, str, str]]]:
    """馬ごとの (日の序数, race_id, 脚質コード)。脚質コード 1〜4 の走だけ、日付の古い順。"""
    hist: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for race in races.values():
        for run in race.runs:
            if run.horse and run.leg in STYLE_CODES:
                hist[run.horse].append((run.ordinal, run.race_id, run.leg))
    for h in hist.values():
        h.sort()
    return hist


def style_of(history: list[tuple[int, str, str]], target_ordinal: int) -> str | None:
    """対象日より前の日の、365 日以内の直近 5 走の最頻値。同数なら最頻値の中で最も新しい走に現れた値。無ければ None。"""
    window = [e for e in history if target_ordinal - WINDOW_DAYS <= e[0] <= target_ordinal - 1]
    recent = window[-HISTORY_RUNS:]
    if not recent:
        return None
    counts = Counter(leg for _, _, leg in recent)
    top = max(counts.values())
    modes = {leg for leg, n in counts.items() if n == top}
    for _, _, leg in reversed(recent):
        if leg in modes:
            return leg
    raise CPrimeError("最頻値が見つからない")      # 到達しない


def experience_index(races: dict[str, Race]) -> dict[str, list[int]]:
    """馬ごとの走った日の序数 (返還の対象を除く、脚質コードの有無によらない)。経験の数の診断用。"""
    out: dict[str, list[int]] = defaultdict(list)
    for race in races.values():
        for run in race.runs:
            if run.horse and not rm.is_refunded(run.abnormal):
                out[run.horse].append(run.ordinal)
    for v in out.values():
        v.sort()
    return out


def runs_in_window(days: list[int], target_ordinal: int) -> int:
    return sum(target_ordinal - WINDOW_DAYS <= d <= target_ordinal - 1 for d in days)


# ---------------------------------------------------------------------------------------------------- 成分

def race_components(styles: dict[str, str | None]) -> dict[str, dict[str, float]]:
    """選択集合の馬の脚質 (None = 不明) から、馬ごとの 2 成分 (不明なら NaN、既知 0 頭のレースは全頭 NaN)。"""
    known = {h: s for h, s in styles.items() if s is not None}
    n_known = len(known)
    out = {h: {c: math.nan for c in COMPONENTS} for h in styles}
    if n_known == 0:
        return out
    n1 = sum(s == "1" for s in known.values())
    n2 = sum(s == "2" for s in known.values())
    pace = (n1 + 0.5 * n2) / n_known
    for h, s in known.items():
        out[h]["style_x_pace_fit"] = -pace if s in FRONT else pace
        same_others = sum(t == s for t in known.values()) - 1
        out[h]["front_competition_signed"] = -float(same_others) if s in FRONT else 0.0
    return out


def target_rows(races: dict[str, Race], years: tuple[int, ...], history: dict, experience: dict,
                counts: Counter, exclusions: list[dict]) -> list[dict]:
    """対象レースの標本 (選択集合の馬ごとに 1 行)。P_market は §8-6 の選択集合の中で正規化し直した値。"""
    out = []
    for race in sorted(races.values(), key=lambda r: r.race_id):
        year = int(race.ymd[:4])
        if year not in years:
            continue
        counts["target_races_seen"] += 1
        winners = [x for x in race.runs if x.finish == 1]
        if len(winners) != 1:
            counts["drop_dead_heat_or_no_winner"] += 1
            continue
        abnormal = {x.horse_num: x.abnormal for x in race.runs}
        market = {x.horse_num: x.win_odds for x in race.runs if x.win_odds > 0}
        sel = rm.choice_rows([{"horse_num": x.horse_num, "won": int(x.finish == 1)} for x in race.runs],
                             abnormal, {"final": market})
        if isinstance(sel, rm.Excluded):
            counts[f"excluded:{sel.reason}"] += 1
            exclusions.append({"race_id": race.race_id, "reason": sel.reason, "horses": list(sel.horses)})
            continue
        cs, _kept = sel
        by_num = {x.horse_num: x for x in race.runs}
        styles = {h: (style_of(history.get(by_num[h].horse, []), race.ordinal) if by_num[h].horse else None)
                  for h in cs.choice}
        comps = race_components(styles)
        for h in cs.choice:
            run = by_num[h]
            out.append({"race_id": race.race_id, "year": year, "horse_num": h, "horse": run.horse,
                        "won": int(run.finish == 1), "p_market": cs.implied["final"][h], "style": styles[h] or "",
                        "n_runs_365": runs_in_window(experience.get(run.horse, []), race.ordinal) if run.horse else 0,
                        **comps[h]})
            counts["style_unknown_rows" if styles[h] is None else "style_known_rows"] += 1
        if cs.refunded:
            counts["refunded_runners_excluded"] += len(cs.refunded)
        counts["target_races_used"] += 1
    return out


# ---------------------------------------------------------------------------------------------------- 標準化 (§8-4c-2)

def _by_race(rows: list[dict]) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    return by


def within_sd(rows: list[dict], col: str) -> dict:
    """pooled within-race SD: レースごとの ddof 0 の分散を、欠損でない行が 1 頭以上あるレースで 1 レース 1 票に平均した値の平方根。"""
    v = []
    for rs in _by_race(rows).values():
        x = np.array([r[col] for r in rs if not math.isnan(r[col])], dtype=float)
        if len(x):
            v.append(float(((x - x.mean()) ** 2).mean()))
    if not v:
        raise CPrimeError(f"{col}: 欠損でない行が無い")
    sd = math.sqrt(sum(v) / len(v))
    if not sd > 0:
        raise CPrimeError(f"{col}: pooled within-race SD が 0 (レース内で値が変わらない)")
    return {"sd": sd, "n_races": len(v), "n_races_zero_variance": int(sum(x == 0.0 for x in v))}


def within_share(rows: list[dict], col: str) -> float:
    """ANOVA 型のレース内の変動の割合 (診断): Σ_r Σ_i (x − x̄_r)² / Σ_r Σ_i (x − x̄)²。欠損でない行だけ。"""
    xs, within = [], 0.0
    for rs in _by_race(rows).values():
        x = np.array([r[col] for r in rs if not math.isnan(r[col])], dtype=float)
        if len(x):
            within += float(((x - x.mean()) ** 2).sum())
            xs.append(x)
    allx = np.concatenate(xs) if xs else np.array([])
    total = float(((allx - allx.mean()) ** 2).sum()) if len(allx) else 0.0
    return within / total if total > 0 else math.nan


def standardize(rows: list[dict], col: str, sd: float, out_col: str) -> None:
    """x / sd。欠損はレース内の欠損でない行の (標準化した) 平均で埋め、欠損でない行が 0 のレースは全頭 0。"""
    for rs in _by_race(rows).values():
        known = [r[col] / sd for r in rs if not math.isnan(r[col])]
        fill = sum(known) / len(known) if known else 0.0
        for r in rs:
            r[out_col] = fill if math.isnan(r[col]) else r[col] / sd


# ---------------------------------------------------------------------------------------------------- 合成・推定

def clogit_with_se(rows: list[dict], cols: list[str]) -> dict:
    """`[market_feature] + cols` の条件付きロジットの係数と、ヘッセ行列からの SE (選択には使わない、記録と z のため)。"""
    data = mc.add_market_feature(rows)
    allcols = [mc.MARKET_COL, *cols]
    beta, ok = conditional_logit(data, allcols, with_status=True)
    if not ok:
        raise CPrimeError(f"条件付きロジットが収束しなかった ({allcols})")
    b = np.array(beta, dtype=float)
    info = np.zeros((len(allcols), len(allcols)))
    for rs in _by_race(data).values():
        if sum(r["won"] for r in rs) != 1:
            continue
        X = np.array([[r[c] for c in allcols] for r in rs], dtype=float)
        u = X @ b
        p = np.exp(u - u.max())
        p /= p.sum()
        m = p @ X
        info += (X * p[:, None]).T @ X - np.outer(m, m)
    try:
        se = np.sqrt(np.diag(np.linalg.inv(info)))
    except np.linalg.LinAlgError as e:
        raise CPrimeError(f"情報行列が特異 ({allcols})") from e
    return {"cols": allcols, "beta": [float(x) for x in b], "se": [float(x) for x in se],
            "z": [float(x / s) for x, s in zip(b, se)]}


def check_est_years(years) -> None:
    if any(int(y) >= PRIMARY_YEAR for y in years):
        raise CPrimeError(f"推定に {PRIMARY_YEAR} 年以降の行を渡した: {sorted(set(years))}")


def fit_composite(fit_rows: list[dict]) -> dict:
    """推定期間の行で、成分の σ_within・合成の重み (逆符号は 0)・S の σ_within を決める (§8-4c-2、C′-0)。"""
    check_est_years({r["year"] for r in fit_rows})
    rows = [dict(r) for r in fit_rows]
    comp_sd = {}
    for c in COMPONENTS:
        comp_sd[c] = within_sd(rows, c)
        standardize(rows, c, comp_sd[c]["sd"], c + STD_SUFFIX)
    fit = clogit_with_se(rows, [c + STD_SUFFIX for c in COMPONENTS])
    raw = dict(zip(COMPONENTS, fit["beta"][1:]))
    weights = {c: (b if b > 0 else 0.0) for c, b in raw.items()}       # 期待される符号はどちらも正 (§8-4c)
    if not any(w > 0 for w in weights.values()):
        raise CPrimeError(f"両方の成分が期待と逆の符号 (重みがすべて 0): {raw}。合成は作れない (台帳 C′-0)")
    for r in rows:
        r["S_raw"] = sum(weights[c] * r[c + STD_SUFFIX] for c in COMPONENTS)
    s_sd = within_sd(rows, "S_raw")
    zmax = max(abs(z) for z in fit["z"][1:])
    single = {}                                      # 判定に使わない記録: 成分ごとの単独の当てはめ (共線性の読み分け、レビュー ddc12b6)
    for c in COMPONENTS:
        try:
            one = clogit_with_se(rows, [c + STD_SUFFIX])
            single[c] = {"beta": one["beta"][1], "z": one["z"][1]}
        except CPrimeError as e:
            single[c] = {"error": str(e)}
    return {"single_component_fits": single,
            "component_within_corr": within_race_corr(rows, *[c + STD_SUFFIX for c in COMPONENTS]),"years": sorted({r["year"] for r in fit_rows}), "component_sd": comp_sd, "fit": fit,
            "raw_coefficients": raw, "weights": weights, "s_sd": s_sd,
            "component_z_max": zmax, "direction_undetermined": bool(zmax < Z_DIRECTION),
            "n_races": len(_by_race(rows)), "n_rows": len(rows)}


def apply_composite(rows: list[dict], comp: dict) -> list[dict]:
    """凍結した σ・重みで S を作った行のコピー (推定し直さない)。"""
    out = [dict(r) for r in rows]
    for c in COMPONENTS:
        standardize(out, c, comp["component_sd"][c]["sd"], c + STD_SUFFIX)
    for r in out:
        r["S"] = sum(comp["weights"][c] * r[c + STD_SUFFIX] for c in COMPONENTS) / comp["s_sd"]["sd"]
    return out


# ---------------------------------------------------------------------------------------------------- 診断

def variance_decomposition(rows: list[dict], col: str = "S") -> dict:
    """S の分散の分解 (外部の指示者の要求、診断): 全体 / レース間 / レース内 / 市場で重み付けたレース内 / 市場の列とのレース内の相関。"""
    x = np.array([r[col] for r in rows], dtype=float)
    total = float(x.var())
    within_ss, between_ss, mw_within, sxx, syy, sxy = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    by = _by_race(rows)
    for rs in by.values():
        xr = np.array([r[col] for r in rs], dtype=float)
        within_ss += float(((xr - xr.mean()) ** 2).sum())
        between_ss += len(xr) * float((xr.mean() - x.mean()) ** 2)
        p = np.array([r["p_market"] for r in rs], dtype=float)
        z = np.array([rm.market_feature(q) for q in p])
        dx, dz = xr - p @ xr, z - p @ z
        mw_within += float(p @ dx ** 2)
        sxx += float(p @ dx ** 2)
        syy += float(p @ dz ** 2)
        sxy += float(p @ (dx * dz))
    n = len(x)
    return {"total_var": total, "between_var": between_ss / n, "within_var": within_ss / n,
            "within_share": within_ss / (within_ss + between_ss) if within_ss + between_ss > 0 else math.nan,
            "market_weighted_within_var_per_race": mw_within / len(by),
            "within_race_market_weighted_corr_with_market": sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else math.nan}


def within_race_corr(rows: list[dict], a: str, b: str) -> float:
    """レース内で中心化した 2 列の相関 (等重み)。"""
    da, db = [], []
    for rs in _by_race(rows).values():
        xa = np.array([r[a] for r in rs], dtype=float)
        xb = np.array([r[b] for r in rs], dtype=float)
        da.extend(xa - xa.mean())
        db.extend(xb - xb.mean())
    da, db = np.array(da), np.array(db)
    den = math.sqrt(float(da @ da) * float(db @ db))
    return float(da @ db) / den if den > 0 else math.nan


# ---------------------------------------------------------------------------------------------------- 来歴

DEPENDENCIES = ("scripts/c_prime.py", "scripts/c_prime_explore.py", "scripts/c_prime_run.py", "predictor/market_clogit.py",
                "predictor/race_market.py", "predictor/eval_stats.py", "scripts/group_a_stats.py", "config.py", "db.py",
                "docs/PHASE05_5_PREREG.md", "docs/PHASE05_5_EXPLORATION.md")


def blob_sha(path: Path) -> str:
    """git の blob と同じ規則の hash (改行を LF に正規化してから)。作業ツリーの改行 (autocrlf) に依らない (§8-6b)。"""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def provenance(db_path, argv: list[str] | None = None, own_output: str | None = None) -> dict:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    lines = [ln for ln in status.stdout.splitlines() if ln.strip()] if status.returncode == 0 else None

    def own(line: str) -> bool:
        path = line[3:].strip().strip('"').replace("\\", "/")
        return bool(own_output) and path.startswith(own_output.rstrip("/") + "/")
    dbp = Path(db_path)
    st = dbp.stat() if dbp.exists() else None
    return {"git_sha": head.stdout.strip() if head.returncode == 0 else "unknown",
            "git_dirty": (any(not own(ln) for ln in lines) if lines is not None else None),
            "git_status": lines, "own_output": own_output,
            "files_blob_sha1": {f: blob_sha(ROOT / f) for f in DEPENDENCIES if (ROOT / f).exists()},
            "python": platform.python_version(), "numpy": np.__version__,
            "argv": list(argv if argv is not None else sys.argv),
            "db": {"path": str(dbp), "bytes": st.st_size if st else None,
                   "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds") if st else None}}
