"""Phase 0.5-5 Group A の実行: 凍結 (freeze) → 検出力の固定 (power) → 主検定 (primary) (2026-10-06)。

仕様: `docs/PHASE05_5_PREREG.md` §8-4 / §8-4b / §8-4b-2 / §8-4b-3 / §8-6 / §8-7 / §8-7b、`docs/PHASE05_5_EXPLORATION.md` (E1b / E2b)。

    python -m scripts.group_a_run freeze  --db <db> --spec S1V1W0 --out <dir>       # 学習期 2022-2024 だけ
    python -m scripts.group_a_run power   --db <db> --frozen <dir> --out <dir>      # 2025 の対象レースの結果を読まない
    python -m scripts.group_a_run primary --db <db> --frozen <dir> --power <power.json> --out <dir>   # 1 回だけ

- freeze: E1b の規則の選択と `--spec` が一致しなければ止める。補正テーブル・標準化・合成の重みを 2022-2024 で推定して凍結する
- power: 凍結物を読み込むだけ (再推定しない)。β を推定しない
- primary: 出力先に結果が既にあれば止める (主検定は 1 回)。区間は `primary_block_ci` (99%、5000、seed 20261004)。
  valid を先に判定し、検出力で判定不能が確定していれば、β と区間に関係なく `PRIMARY_INCONCLUSIVE`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from predictor import eval_stats as es
from scripts import group_a as g
from scripts import group_a_power as pw
from scripts import group_a_stats as st

EST_YEARS = (2022, 2023, 2024)
PRIMARY_YEARS = (2025,)
COLS = ["logit_p_market", "S"]
BOOT_N = 1000                      # §8-7b: 学習期のブートストラップ
BOOT_SEED = 20261004
BOOT_MAX_DISCARD_FRAC = 0.01
FROZEN_FILE = "frozen_tables.json"
MANIFEST_FILE = "MANIFEST.json"
POWER_FILE = "power.json"
PRIMARY_FILE = "primary_result.json"
SIDE_FILE = "primary_side_records.json"
LOCK_FILE = "PRIMARY_LOCK.json"     # 凍結物のディレクトリに置く。主検定を始めた時点で書く (途中で落ちても残る)
# 主検定の前に、凍結の時点と一致しなければならない依存ファイル (探索台帳は追記が続くので外す)
PINNED_FILES = ("scripts/group_a.py", "scripts/group_a_power.py", "scripts/group_a_run.py", "scripts/group_a_stats.py",
                "predictor/eval_stats.py", "config.py", "db.py",
                "data/backtest/group_a_class_20261005/class_table.csv", "docs/PHASE05_5_PREREG.md")


class RunError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rel(path: Path) -> str | None:
    try:
        return Path(path).resolve().relative_to(g.ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _nan_to_none(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_nan_to_none(v) for v in obj]
    return obj


def _write_json(path: Path, obj) -> None:
    """原子的に書く。NaN / inf は null にする (標準の JSON で読めるように)。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_nan_to_none(obj), ensure_ascii=False, indent=1, default=str, allow_nan=False),
                   encoding="utf-8")
    tmp.replace(path)


def history_digest(races: dict, years) -> dict:
    """指定の年の走の内容の sha256 (凍結の時点と、検出力・主検定の時点で、履歴の DB の中身が同じことの照合用)。"""
    h = hashlib.sha256()
    n = 0
    for rid in sorted(r for r in races if int(r[:4]) in years):
        for x in races[rid].runs:
            h.update(f"{rid}|{x.horse}|{x.horse_num}|{x.abnormal}|{x.finish}|{x.sec_per_km!r}|{x.burden_kg!r}|{x.win_odds!r}\n"
                     .encode("utf-8"))
            n += 1
    return {"years": sorted(years), "runs": n, "sha256": h.hexdigest()}


def missing_by_year(rows: list[dict]) -> dict:
    out: dict = {}
    for y in sorted({r["year"] for r in rows}):
        rs = [r for r in rows if r["year"] == y]
        out[str(y)] = {c: float(np.mean([math.isnan(r[c]) for r in rs])) for c in g.COMPONENTS}
        out[str(y)]["S_all_missing"] = float(np.mean([all(math.isnan(r[c]) for c in g.COMPONENTS) for r in rs]))
    return out


def clip_audit(rstats: Counter, years: tuple) -> dict:
    """年 × クラス × 年齢の区分ごとの評価値のある走と、遅い側・速い側の clip の件数と率 (監査用、採否の基準にしない)。"""
    agg: dict = defaultdict(lambda: {"rated": 0, "clipped_slow": 0, "clipped_fast": 0})
    for k, v in rstats.items():
        if not k.startswith("group|"):
            continue
        _, y, c, a, state = k.split("|")
        if int(y) in years:
            agg[f"{y}|{c}|{a}"][state] += v
    for d in agg.values():
        d["slow_rate"] = d["clipped_slow"] / d["rated"] if d["rated"] else None
        d["fast_rate"] = d["clipped_fast"] / d["rated"] if d["rated"] else None
    return dict(sorted(agg.items()))


def unrated_races_by_track(races: dict, par: g.ParModel, years: tuple) -> dict:
    """基準 (セル) が無いので評価値を持たないレースの、年 × 競馬場ごとの件数。"""
    out: Counter = Counter()
    for r in races.values():
        if int(r.ymd[:4]) in years and math.isnan(par.base(r)):
            out[f"{r.ymd[:4]}|{r.track}"] += 1
    return dict(sorted(out.items()))


def choice_set_contract(rows: list[dict], counts: Counter) -> dict:
    """§8-6 の選択集合の契約の記録: 除いた馬・レースの数と、レースごとの市場の確率の和。"""
    by: dict = defaultdict(float)
    for r in rows:
        by[r["race_id"]] += r["p_market"]
    dev = max((abs(s - 1.0) for s in by.values()), default=0.0)
    return {"counts": dict(counts), "n_races": len(by), "n_rows": len(rows), "max_abs_prob_sum_dev": dev}


# ---------------------------------------------------------------------------------------------------- freeze

def run_freeze(db: str, spec_name: str, out: Path, e1b: Path, argv: list[str]) -> dict:
    started = _now()
    sel = json.loads(Path(e1b).read_text(encoding="utf-8"))["selection"]["selected"]
    if sel != spec_name:
        raise RunError(f"--spec {spec_name} は E1b の規則の選択 {sel} と違う")
    spec = next((s for s in (g.Spec(a, b, c) for a in g.SPEC_AXES["scale"] for b in g.SPEC_AXES["variant"]
                             for c in g.SPEC_AXES["weight"]) if s.name == spec_name), None)
    if spec is None:
        raise RunError(f"未知の候補: {spec_name}")
    out.mkdir(parents=True, exist_ok=True)
    races, load_stats = g.load_races(max(EST_YEARS), db_path=db)
    tables = g.fit_tables(races, spec, EST_YEARS)
    ratings, rstats = g.rate_runs(races, tables)
    counts: Counter = Counter()
    rows = g.target_samples(races, EST_YEARS, ratings, counts)
    g.add_market_logit(rows)
    comp = g.fit_composite(rows)
    g.apply_composite(rows, comp)
    contract = choice_set_contract(rows, counts)
    packed = st.pack(rows, COLS)
    beta_pk, ok_pk = st.clogit_packed(packed)
    beta_es, ok_es = es.conditional_logit(rows, COLS, with_status=True)
    if not (ok_pk and ok_es) or max(abs(a - b) for a, b in zip(beta_pk, beta_es)) > 1e-8:
        raise RunError(f"配列版と eval_stats の条件付きロジットが一致しない: {beta_pk} vs {beta_es}")
    hess = g.clogit_with_se(rows, COLS)
    t0 = time.time()
    vals, discarded = es._block_resample(rows, st.make_beta_stat(packed, "S"), BOOT_N, BOOT_SEED)
    boot = {"n_boot": BOOT_N, "seed": BOOT_SEED, "unit": "race", "statistic": "beta_S of logit_p_market + S (frozen S)",
            "n_valid": len(vals), "n_discarded": discarded, "max_discard": math.floor(BOOT_MAX_DISCARD_FRAC * BOOT_N + 1e-9),
            "seconds": round(time.time() - t0, 1)}
    boot["se"] = float(np.std(vals, ddof=1)) if discarded <= boot["max_discard"] and len(vals) > 1 else None
    # 判定に使わない記録: 学習期の leave-one-year-out (残りの 2 年で補正テーブル・重みを推定し、外した年で β の符号)
    loyo = {}
    for y in EST_YEARS:
        rest = tuple(x for x in EST_YEARS if x != y)
        try:
            t_y = g.fit_tables(races, spec, rest)
            r_y, _ = g.rate_runs(races, t_y)
            c1, c2 = Counter(), Counter()
            fit_y = g.target_samples(races, rest, r_y, c1)
            ev_y = g.target_samples(races, (y,), r_y, c2)
            g.add_market_logit(fit_y)
            g.add_market_logit(ev_y)
            comp_y = g.fit_composite(fit_y)
            g.apply_composite(ev_y, comp_y)
            res = g.clogit_with_se(ev_y, COLS)
            loyo[str(y)] = {"est_years": list(rest), "beta_S": res["beta"][1], "se_S": res["se"][1],
                            "sign": (None if math.isnan(res["beta"][1]) else int(np.sign(res["beta"][1]))),
                            "weights": comp_y["weights"]}
        except g.GroupAError as e:                    # 判定に使わない記録なので、fold の失敗は記録して続ける
            loyo[str(y)] = {"est_years": list(rest), "error": str(e)}
    payload = g.freeze_payload(tables, comp)
    _write_json(out / FROZEN_FILE, payload)
    manifest = {
        "kind": "group_a_freeze", "started_at": started, "ended_at": _now(),
        "provenance": g.provenance(db, argv, own_output=_rel(out)),
        "spec": spec_name, "est_years": list(EST_YEARS), "e1b_selection_file": str(e1b), "e1b_selected": sel,
        "frozen_file": FROZEN_FILE, "frozen_sha256": _sha(out / FROZEN_FILE), "payload_version": payload["payload_version"],
        "load_stats": dict(load_stats), "par_counts": tables.par.counts, "n_variants": len(tables.variants),
        "history_digest": history_digest(races, (2021,) + EST_YEARS),
        "choice_set": contract, "n_train_races": contract["n_races"],
        "missing_by_year": missing_by_year(rows),
        "clip_audit": clip_audit(rstats, (2021,) + EST_YEARS),
        "rating_totals": {k: v for k, v in rstats.items() if not k.startswith("group|")},
        "unrated_races_by_year_track": unrated_races_by_track(races, tables.par, (2021,) + EST_YEARS),
        "kyoto_cells": {f"{c[0]}|{c[1]}|{c[2]}": (list(lv) if lv is not None else None)
                        for c, lv in sorted(tables.par.cell_level.items(), key=str) if c[0] == "08"},
        "train_in_sample": {"beta": beta_es, "hessian_se": hess["se"], "note": "学習期の in-sample の値 (判定に使わない)"},
        "bootstrap": boot, "leave_one_year_out": loyo,
        "corr_S_market_within_race": _within_corr(rows, "S", "logit_p_market"),
        "estimator": {"conditional_logit": "predictor.eval_stats.conditional_logit (damped Newton, step cap 2, tol 1e-9, max 100)",
                      "packed": "scripts.group_a_stats.clogit_packed (同じアルゴリズム、一致をテストと実行時に確認)"},
    }
    _write_json(out / MANIFEST_FILE, manifest)
    return manifest


def _within_corr(rows, a, b) -> float:
    by: dict = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    xs, ys = [], []
    for rs in by.values():
        if len(rs) < 2:
            continue
        ma = sum(r[a] for r in rs) / len(rs)
        mb = sum(r[b] for r in rs) / len(rs)
        xs += [r[a] - ma for r in rs]
        ys += [r[b] - mb for r in rs]
    return float(np.corrcoef(xs, ys)[0, 1]) if len(xs) > 2 else math.nan


def _check_history(races: dict, man: dict) -> None:
    d = history_digest(races, tuple(man["history_digest"]["years"]))
    if d != man["history_digest"]:
        raise RunError(f"2021-2024 の履歴が凍結の時点と違う (DB が変わった): {d} vs {man['history_digest']}")


def _check_pinned(man: dict, power: dict) -> dict:
    """主検定の前提: 作業ツリーに未コミットの変更が無く、固定する依存ファイルの sha256 が凍結・検出力の時点と同じ。"""
    now = g.provenance(man["provenance"]["db"]["path"], ["check"])
    if now["git_dirty"]:
        raise RunError(f"作業ツリーに未コミットの変更がある: {now['git_status']}")
    bad = {}
    for f in PINNED_FILES:
        cur = now["files_sha256"].get(f)
        for name, src in (("freeze", man["provenance"]["files_sha256"]), ("power", power["provenance"]["files_sha256"])):
            if src.get(f) != cur:
                bad[f"{f} ({name})"] = (src.get(f), cur)
    if bad:
        raise RunError(f"主検定の前提のファイルが凍結・検出力の時点と違う: {bad}")
    return {"git_sha": now["git_sha"], "pinned": {f: now["files_sha256"][f] for f in PINNED_FILES}}


def _load_frozen(frozen: Path) -> tuple[dict, dict]:
    man = json.loads((frozen / MANIFEST_FILE).read_text(encoding="utf-8"))
    if _sha(frozen / FROZEN_FILE) != man["frozen_sha256"]:
        raise RunError("凍結物の sha256 が MANIFEST と違う")
    payload = json.loads((frozen / FROZEN_FILE).read_text(encoding="utf-8"))
    return man, payload


# ---------------------------------------------------------------------------------------------------- power

def run_power(db: str, frozen: Path, out: Path, argv: list[str]) -> dict:
    started = _now()
    man, payload = _load_frozen(frozen)
    out.mkdir(parents=True, exist_ok=True)
    races, load_stats = g.load_races(max(PRIMARY_YEARS), db_path=db, allow_primary_year=True,
                                     primary_purpose="power: 2025 の過去走の時計を S の履歴として読む (対象レースの結果は対象の行に付けない)")
    _check_history(races, man)
    tables, comp = g.tables_from_payload(payload, races)
    ratings, _ = g.rate_runs(races, tables)
    del races                                        # 以降、対象レースは allow-list の読み込みだけ
    targets = pw.load_target_fields(max(PRIMARY_YEARS), db)
    counts: Counter = Counter()
    rows = pw.outcome_blind_rows(targets, ratings, counts)
    g.add_market_logit(rows)
    g.apply_composite(rows, comp)
    fisher = pw.fisher_se_at_null(rows)
    boot_se = man["bootstrap"]["se"]
    fixed = (pw.fixed_power(fisher["se"], boot_se, man["n_train_races"], fisher["n_races"]) if boot_se is not None
             else {**pw.fixed_power(fisher["se"], 0.0, man["n_train_races"], fisher["n_races"]), "se_train_boot": None,
                   "note": "学習期のブートストラップの SE が NA なので解析の SE だけ (§8-7b)"})
    result = {
        "kind": "group_a_power", "started_at": started, "ended_at": _now(),
        "provenance": g.provenance(db, argv, own_output=_rel(out)),
        "frozen_sha256": man["frozen_sha256"], "frozen_manifest_sha256": _sha(frozen / MANIFEST_FILE),
        "load_stats_history": dict(load_stats), "target_counts": dict(counts),
        "fisher": fisher, "power": fixed, "purchase_count_at_beta_target": pw.purchase_count_at_target(rows),
        "missing_by_year": missing_by_year(rows), "n_rows": len(rows),
        "note": "対象レース自身の結果は読んでいない (allow-list の読み込み、行に won なし)。β は推定していない",
    }
    _write_json(out / POWER_FILE, result)
    return result


# ---------------------------------------------------------------------------------------------------- primary

def _history_with_finish(races: dict) -> dict:
    """{馬: [(日の通し番号, 着順, 人気)]} (判定に使わない記録用。人気は返還を除いた馬のオッズの順位、同値は平均)。"""
    out: dict = defaultdict(list)
    for r in sorted(races.values(), key=lambda x: x.ymd):
        choice = [x for x in r.runs if x.abnormal not in g.REFUNDED and x.win_odds > 0]
        odds = [x.win_odds for x in choice]
        for x in choice:
            pop = sum(o < x.win_odds for o in odds) + (sum(o == x.win_odds for o in odds) + 1) / 2.0
            if x.horse:
                out[x.horse].append((x.ordinal, float(x.finish) if x.finish > 0 else math.nan, pop))
    return out


def _attach_last_run(rows: list[dict], hist: dict) -> None:
    for row in rows:
        t = g.day_ordinal(row["race_id"][:8])
        h = hist.get(row["horse"], [])
        i = bisect_left(h, (t, -math.inf, -math.inf))
        lo = bisect_left(h, (t - g.WINDOW_DAYS, -math.inf, -math.inf))
        row["last_finish"] = h[i - 1][1] if i > 0 else math.nan
        row["last_popularity"] = h[i - 1][2] if i > 0 else math.nan
        row["starts_365"] = float(i - lo)


def _target_ages(db: str, year: int) -> dict:
    conn = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    rows = conn.execute("""SELECT race_year||race_month_day||'_'||track_code||'_'||kaiji||'_'||nichiji||'_'||race_num, horse_num, age
                             FROM horse_races WHERE race_year = ?""", (str(year),)).fetchall()
    conn.close()
    out = {}
    for rid, hn, age in rows:
        try:
            out[(rid, str(hn).strip())] = float(age) if age not in (None, "", 0, "0") else math.nan
        except (TypeError, ValueError):
            out[(rid, str(hn).strip())] = math.nan
    return out


def _residualised(rows: list[dict], x: str) -> list[dict]:
    """S を x で残差化した版 (x が欠損の行は x の平均で埋める)。最小二乗は 2025 の行の S と x だけ (結果は使わない)。"""
    xs = np.array([r[x] for r in rows])
    fill = np.nanmean(xs)
    xs = np.where(np.isnan(xs), fill, xs)
    s = np.array([r["S"] for r in rows])
    A = np.column_stack([np.ones_like(xs), xs])
    coef, *_ = np.linalg.lstsq(A, s, rcond=None)
    res = s - A @ coef
    return [{**r, "S_res": float(v)} for r, v in zip(rows, res)]


def verdict(ci: dict, power: dict) -> tuple[str, str]:
    """§8-4: valid を先に見る → 検出力で判定不能が確定していれば INCONCLUSIVE → 下限 > 0 なら PASS、そうでなければ FAIL。"""
    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"
    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", "mde_above_beta_target"
    return ("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] > 0 else ("PRIMARY_FAIL", "ci_lower_not_above_zero")


def run_primary(db: str, frozen: Path, power_path: Path, out: Path, argv: list[str],
                rerun_reason: str | None = None) -> dict:
    """主検定。凍結物のディレクトリの錠 (LOCK_FILE) で 1 回だけに限る。錠は 2025 の結果を読む前に書く (途中で落ちても残る)。

    再実行は、実行の前に欠陥を特定して記録した場合だけ (§8-4)。`rerun_reason` を書くと run_index を 1 つ進めて走る。
    """
    man, payload = _load_frozen(frozen)
    power = json.loads(Path(power_path).read_text(encoding="utf-8"))
    if power["frozen_sha256"] != man["frozen_sha256"] or power.get("frozen_manifest_sha256") != _sha(frozen / MANIFEST_FILE):
        raise RunError("検出力の結果が別の凍結物から作られている")
    lock_path = frozen / LOCK_FILE
    previous = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else None
    if previous is not None and not rerun_reason:
        raise RunError(f"主検定は既に始まっている (錠 {lock_path}、run_index {previous['run_index']})。主検定は 1 回だけ")
    pinned = _check_pinned(man, power)
    run_index = (previous["run_index"] + 1) if previous else 1
    started = _now()
    out.mkdir(parents=True, exist_ok=True)
    history = (previous.get("history", []) + [previous]) if previous else []
    _write_json(lock_path, {"run_index": run_index, "started_at": started, "out": str(out), "rerun_reason": rerun_reason,
                            "frozen_sha256": man["frozen_sha256"], "power_sha256": _sha(power_path), **pinned,
                            "history": history})
    races, load_stats = g.load_races(max(PRIMARY_YEARS), db_path=db, allow_primary_year=True,
                                     primary_purpose=f"primary: Group A の主検定 (run_index {run_index})")
    _check_history(races, man)
    tables, comp = g.tables_from_payload(payload, races)
    ratings, _ = g.rate_runs(races, tables)
    counts: Counter = Counter()
    rows = g.target_samples(races, PRIMARY_YEARS, ratings, counts)
    refunded = sum(1 for r in races.values() if r.ymd[:4] == "2025" for x in r.runs if x.abnormal in g.REFUNDED)
    g.add_market_logit(rows)
    g.apply_composite(rows, comp)
    contract = choice_set_contract(rows, counts)
    contract["refunded_runners_in_2025_races"] = refunded
    beta, ok = es.conditional_logit(rows, COLS, with_status=True)
    packed = st.pack(rows, COLS)
    beta_pk, ok_pk = st.clogit_packed(packed)
    if ok != ok_pk or (ok and max(abs(a - b) for a, b in zip(beta, beta_pk)) > 1e-8):
        raise RunError(f"配列版と eval_stats の条件付きロジットが一致しない: {beta_pk} vs {beta}")
    t0 = time.time()
    ci = es.primary_block_ci(rows, st.make_beta_stat(packed, "S"), level=es.PRIMARY_CI_LEVEL)
    ci_seconds = round(time.time() - t0, 1)
    if (ci["level"], ci["n_boot"], ci["seed"]) != (es.PRIMARY_CI_LEVEL, es.PRIMARY_N_BOOT, es.PRIMARY_SEED):
        raise RunError(f"主検定の区間の設定が事前登録と違う: {ci}")
    hess = g.clogit_with_se(rows, COLS)
    cat, reason = verdict(ci, power["power"])
    z = pw.Z_ALPHA_2SIDED_001
    result = {
        "kind": "group_a_primary", "run_index": run_index, "rerun_reason": rerun_reason,
        "started_at": started, "ended_at": _now(),
        "provenance": g.provenance(db, argv, own_output=_rel(out)), "pinned": pinned,
        "frozen_sha256": man["frozen_sha256"], "power_sha256": _sha(power_path),
        "load_stats": dict(load_stats), "choice_set": contract,
        "n_races_power_minus_primary": power["fisher"]["n_races"] - contract["n_races"],
        "beta": {"market": beta[0], "S": beta[1], "converged": ok},
        "ci_99": ci, "ci_seconds": ci_seconds,
        "wald_diagnostic": {"se_hessian": hess["se"][1], "lo": beta[1] - z * hess["se"][1], "hi": beta[1] + z * hess["se"][1],
                            "note": "診断だけ。判定に使わない"},
        "power": power["power"], "category": cat, "category_reason": reason,
    }
    _write_json(out / PRIMARY_FILE, result)          # 判定までを先に書く (判定に使わない記録で落ちても残る)
    try:
        side = _side_records(races, rows, db)
    except Exception as e:                           # 判定に使わない記録の失敗は、判定を変えずに記録だけする
        side = {"error": f"{type(e).__name__}: {e}"}
    _write_json(out / SIDE_FILE, {"run_index": run_index, "primary_file": PRIMARY_FILE, **side})
    return {**result, "side_records_not_for_decision": side}


def _side_records(races: dict, rows: list[dict], db: str) -> dict:
    """§8-4 の判定に使わない記録 (2025 で 1 回だけ)。"""
    hist = _history_with_finish(races)
    _attach_last_run(rows, hist)
    ages = _target_ages(db, max(PRIMARY_YEARS))
    matched = 0
    for r in rows:
        r["age"] = ages.get((r["race_id"], r["horse_num"]), math.nan)
        matched += not math.isnan(r["age"])
    side = {"rho_S_market_within_race": _within_corr(rows, "S", "logit_p_market"),
            "corr_S_starts_365_within_race": _within_corr(rows, "S", "starts_365"),
            "corr_S_age_within_race": _within_corr([r for r in rows if not math.isnan(r["age"])], "S", "age"),
            "age_matched_rows": matched, "n_rows": len(rows)}
    for x in ("last_finish", "last_popularity"):
        rr = _residualised(rows, x)
        res = g.clogit_with_se(rr, ["logit_p_market", "S_res"])
        side[f"beta_S_residualised_on_{x}"] = {"beta": res["beta"][1], "se": res["se"][1], "converged": res["converged"],
                                               "x_missing_rows": int(sum(math.isnan(r[x]) for r in rows)),
                                               "note": "残差化はレース間を含む pooled の最小二乗 (x の欠損は平均で埋める)"}
    return side


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--db", required=True); f.add_argument("--spec", required=True); f.add_argument("--out", required=True)
    f.add_argument("--e1b", default=str(g.ROOT / "data" / "backtest" / "group_a_20261005" / "e1b" / "cross_results.json"))
    p = sub.add_parser("power")
    p.add_argument("--db", required=True); p.add_argument("--frozen", required=True); p.add_argument("--out", required=True)
    q = sub.add_parser("primary")
    q.add_argument("--db", required=True); q.add_argument("--frozen", required=True); q.add_argument("--power", required=True)
    q.add_argument("--out", required=True)
    q.add_argument("--rerun-reason", help="再実行のときだけ。実行の前に特定して記録した欠陥 (§8-4)")
    a = ap.parse_args(argv)
    full = ["group_a_run", *argv]
    if a.cmd == "freeze":
        m = run_freeze(a.db, a.spec, Path(a.out), Path(a.e1b), full)
        print(json.dumps({k: m[k] for k in ("spec", "frozen_sha256", "n_train_races", "bootstrap", "leave_one_year_out",
                                            "train_in_sample")}, ensure_ascii=False, indent=1, default=str))
    elif a.cmd == "power":
        r = run_power(a.db, Path(a.frozen), Path(a.out), full)
        print(json.dumps({"power": r["power"], "fisher_se": r["fisher"]["se"], "rho": r["fisher"]["rho_within_race_market_weighted"],
                          "purchase": r["purchase_count_at_beta_target"]}, ensure_ascii=False, indent=1))
    else:
        r = run_primary(a.db, Path(a.frozen), Path(a.power), Path(a.out), full, rerun_reason=a.rerun_reason)
        print(json.dumps({k: r[k] for k in ("beta", "ci_99", "category", "category_reason")}, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
