"""Phase 0.5-5 Group C′ の実行: 凍結 (freeze) → 検出力の固定 (power) → 錠 (arm) → 主検定 (primary) (2026-10-06)。

仕様: `docs/PHASE05_5_PREREG.md` §8-4 / §8-4c / §8-4c-2 / §8-6 / §8-6b / §8-7 / §8-7b / §8-8、台帳 C′-0〜C′-3。

    python -m scripts.c_prime_run freeze  --db <db> --out <dir>                                  # 学習期 2022-2024 だけ
    python -m scripts.c_prime_run power   --db <db> --frozen <dir> --out <dir>                   # 2025 の対象レースの結果を読まない
    python -m scripts.c_prime_run arm     --db <db> --frozen <dir> --power <power.json>          # 錠を書く → git にコミット
    python -m scripts.c_prime_run primary --db <db> --frozen <dir> --power <power.json> --out <dir>   # 1 回だけ

- 市場の列は `predictor.market_clogit` (log P_market) だけ。条件付きロジットの列は `[market_feature, S]`
- 固定のファイルの照合は git の blob (改行を正規化した値、§8-6b)
- primary: 錠が git にコミットされていなければ止める。2025 の結果を読む前に開始の印を書く。区間は `primary_block_ci` (99%)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from config import guard_analysis_window
from db import REFUNDED_ABNORMAL_CODES
from predictor import eval_stats as es
from predictor import market_clogit as mc
from predictor import race_market as rm
from scripts import c_prime as cp
from scripts import group_a_stats as st          # 汎用の配列版の条件付きロジット (eval_stats と同じアルゴリズム、市場の変換は持たない)


class RunError(RuntimeError):
    pass


EST_YEARS = (2022, 2023, 2024)
PRIMARY_YEAR = cp.PRIMARY_YEAR
COLS = [mc.MARKET_COL, "S"]
BETA_TARGET = math.log1p(0.25) / 2.0             # §8-4c-2: β_market = 1 で S が 2 単位違う 2 頭の相対オッズに 1.25 倍の差
CRITICAL_MULTIPLIER = 2.5758293035489004 + 0.8416212335729143   # z_{0.995} + z_{0.80}
BOOT_N = 1000                                    # §8-7b
BOOT_SEED = 20261004
BOOT_MAX_DISCARD_FRAC = 0.01
FROZEN_FILE = "frozen_composite.json"
MANIFEST_FILE = "MANIFEST.json"
POWER_FILE = "power.json"
PRIMARY_FILE = "primary_result.json"
SIDE_FILE = "primary_side_records.json"
LOCK_FILE = "PRIMARY_LOCK.json"
STARTED_FILE = "PRIMARY_RUN_{}_STARTED.json"
PINNED_FILES = ("scripts/c_prime.py", "scripts/c_prime_run.py", "predictor/market_clogit.py", "predictor/race_market.py",
                "predictor/eval_stats.py", "scripts/group_a_stats.py", "config.py", "db.py", "docs/PHASE05_5_PREREG.md")
_missing = [f for f in PINNED_FILES if f not in cp.DEPENDENCIES]
if _missing:
    raise RunError(f"PINNED_FILES が c_prime.DEPENDENCIES に無い: {_missing}")

# 検出力の計算で対象レースから読んでよい列 (allow-list)。返る列の名前の完全一致を実行時に確かめる
_REFUND_SQL = ", ".join(f"'{c}'" for c in sorted(REFUNDED_ABNORMAL_CODES))       # 単一の出典は db
TARGET_SELECT = (
    ("h.race_year", "race_year"), ("h.race_month_day", "race_month_day"), ("h.track_code", "track_code"),
    ("h.kaiji", "kaiji"), ("h.nichiji", "nichiji"), ("h.race_num", "race_num"), ("r.track_type_code", "track_type_code"),
    ("h.horse_num", "horse_num"), ("h.blood_register_num", "blood_register_num"),
    (f"CASE WHEN h.abnormal_code IN ({_REFUND_SQL}) THEN 1 ELSE 0 END", "is_refunded"),   # 返還の真偽だけ (4 / 5 / 7 は出さない)
    ("h.win_odds", "win_odds"),
)
TARGET_COLUMNS = tuple(alias for _, alias in TARGET_SELECT)
FORBIDDEN_COLUMNS = ("confirmed_order", "finish_order", "finish_time", "final_3f", "same_finish", "time_diff",
                     "corner_order", "mining", "payout", "popularity", "leg_quality", "starter_count",
                     "horse_weight", "weight_change", "last3f", "front3f")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rel(path: Path) -> str | None:
    try:
        return Path(path).resolve().relative_to(cp.ROOT.resolve()).as_posix()
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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_nan_to_none(obj), ensure_ascii=False, indent=1, default=str, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def history_digest(races: dict, years) -> dict:
    """指定の年の走の内容 (脚質コードを含む) の sha256。凍結と検出力・主検定の時点で履歴の DB が同じことの照合用。"""
    h = hashlib.sha256()
    n = 0
    for rid in sorted(r for r in races if int(r[:4]) in years):
        for x in races[rid].runs:
            h.update(f"{rid}|{x.horse}|{x.horse_num}|{x.abnormal}|{x.finish}|{x.win_odds!r}|{x.leg}\n".encode("utf-8"))
            n += 1
    return {"years": sorted(years), "runs": n, "sha256": h.hexdigest()}


def choice_set_contract(rows: list[dict], counts: Counter, exclusions: list[dict]) -> dict:
    by: dict = defaultdict(float)
    for r in rows:
        by[r["race_id"]] += r["p_market"]
    return {"counts": dict(counts), "n_races": len(by), "n_rows": len(rows), "exclusions": exclusions,
            "max_abs_prob_sum_dev": max((abs(s - 1.0) for s in by.values()), default=0.0)}


def _with_market(rows: list[dict]) -> list[dict]:
    return mc.add_market_feature(rows)


def _beta_both(rows_m: list[dict]) -> tuple[list[float], bool, st.Packed]:
    """eval_stats と配列版の条件付きロジットの一致を確かめて β を返す。"""
    beta_es, ok_es = es.conditional_logit(rows_m, COLS, with_status=True)
    packed = st.pack(rows_m, COLS)
    beta_pk, ok_pk = st.clogit_packed(packed)
    if ok_es != ok_pk or (ok_es and max(abs(a - b) for a, b in zip(beta_es, beta_pk)) > 1e-8):
        raise RunError(f"配列版と eval_stats の条件付きロジットが一致しない: {beta_pk} vs {beta_es}")
    return beta_es, ok_es, packed


# ---------------------------------------------------------------------------------------------------- freeze

def run_freeze(db: str, out: Path, argv: list[str]) -> dict:
    started = _now()
    out.mkdir(parents=True, exist_ok=True)
    races, load_stats = cp.load_races(max(EST_YEARS), min_year=2021, db_path=db)
    history, experience = cp.style_history(races), cp.experience_index(races)
    counts, exclusions = Counter(), []
    rows = cp.target_rows(races, EST_YEARS, history, experience, counts, exclusions)
    comp = cp.fit_composite(rows)
    srows = _with_market(cp.apply_composite(rows, comp))
    beta, ok, packed = _beta_both(srows)
    hess = cp.clogit_with_se(cp.apply_composite(rows, comp), ["S"])
    t0 = time.time()
    vals, discarded = es._block_resample(srows, st.make_beta_stat(packed, "S"), BOOT_N, BOOT_SEED)
    boot = {"n_boot": BOOT_N, "seed": BOOT_SEED, "unit": "race", "statistic": "beta_S of market_feature + S (frozen S)",
            "n_valid": len(vals), "n_discarded": discarded, "max_discard": math.floor(BOOT_MAX_DISCARD_FRAC * BOOT_N + 1e-9),
            "seconds": round(time.time() - t0, 1)}
    boot["se"] = float(np.std(vals, ddof=1)) if discarded <= boot["max_discard"] and len(vals) > 1 else None
    loyo = {}
    for y in EST_YEARS:                               # 判定に使わない記録: 残りの 2 年で σ・重みを推定し、外した年で β の符号
        rest = tuple(x for x in EST_YEARS if x != y)
        try:
            c_y = cp.fit_composite([r for r in rows if r["year"] in rest])
            res = cp.clogit_with_se(cp.apply_composite([r for r in rows if r["year"] == y], c_y), ["S"])
            loyo[str(y)] = {"est_years": list(rest), "beta_S": res["beta"][1], "se_S": res["se"][1],
                            "sign": int(np.sign(res["beta"][1])), "weights": c_y["weights"]}
        except cp.CPrimeError as e:
            loyo[str(y)] = {"est_years": list(rest), "error": str(e)}
    payload = {"payload_version": "c_prime_payload_v1", "composite": comp, "components": list(cp.COMPONENTS),
               "constants": {"window_days": cp.WINDOW_DAYS, "history_runs": cp.HISTORY_RUNS, "style_codes": list(cp.STYLE_CODES)}}
    _write_json(out / FROZEN_FILE, payload)
    manifest = {
        "kind": "c_prime_freeze", "started_at": started, "ended_at": _now(),
        "provenance": cp.provenance(db, argv, own_output=_rel(out)),
        "est_years": list(EST_YEARS), "frozen_file": FROZEN_FILE, "frozen_sha256": _sha(out / FROZEN_FILE),
        "load_stats": dict(load_stats), "history_digest": history_digest(races, (2021,) + EST_YEARS),
        "choice_set": choice_set_contract(rows, counts, exclusions), "n_train_races": len({r["race_id"] for r in rows}),
        "train_in_sample": {"beta": beta, "converged": ok, "hessian_se": hess["se"], "note": "学習期の in-sample (判定に使わない)"},
        "bootstrap": boot, "leave_one_year_out": loyo,
        "S_variance_decomposition_train": cp.variance_decomposition(srows, "S"),
        "S_vs_n_runs_365_within_corr_train": cp.within_race_corr(srows, "S", "n_runs_365"),
        "component_within_share_train": {c: cp.within_share(rows, c) for c in cp.COMPONENTS},
        "estimator": {"conditional_logit": "predictor.eval_stats.conditional_logit", "packed": "scripts.group_a_stats.clogit_packed",
                      "market_column": "predictor.race_market.market_feature (log)"},
    }
    _write_json(out / MANIFEST_FILE, manifest)
    return manifest


def _load_frozen(frozen: Path) -> tuple[dict, dict]:
    man = json.loads((frozen / MANIFEST_FILE).read_text(encoding="utf-8"))
    if _sha(frozen / FROZEN_FILE) != man["frozen_sha256"]:
        raise RunError("凍結物の sha256 が MANIFEST と違う")
    payload = json.loads((frozen / FROZEN_FILE).read_text(encoding="utf-8"))
    if payload.get("payload_version") != "c_prime_payload_v1":
        raise RunError(f"凍結物の版が違う: {payload.get('payload_version')}")
    if payload["constants"] != {"window_days": cp.WINDOW_DAYS, "history_runs": cp.HISTORY_RUNS, "style_codes": list(cp.STYLE_CODES)}:
        raise RunError("凍結物の定数が今のコードと違う")
    return man, payload


def _check_history(races: dict, man: dict) -> None:
    d = history_digest(races, tuple(man["history_digest"]["years"]))
    if d != man["history_digest"]:
        raise RunError(f"2021-2024 の履歴が凍結の時点と違う (DB が変わった): {d} vs {man['history_digest']}")


# ---------------------------------------------------------------------------------------------------- power

def target_sql() -> str:
    sql = f"""SELECT {', '.join(f'{expr} AS {alias}' for expr, alias in TARGET_SELECT)}
                FROM horse_races h
                JOIN races r ON r.race_year = h.race_year AND r.race_month_day = h.race_month_day
                 AND r.track_code = h.track_code AND r.kaiji = h.kaiji AND r.nichiji = h.nichiji AND r.race_num = h.race_num
               WHERE h.race_year = ? AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
                 AND r.data_div = '7' AND h.horse_num NOT IN ('', '00')
               ORDER BY 1, 2, 3, 6, 8"""
    low = sql.lower()
    bad = [c for c in FORBIDDEN_COLUMNS if c in low]
    if bad:
        raise RunError(f"対象レースの SQL に結果の列が入っている: {bad}")
    if "*" in low:
        raise RunError("対象レースの SQL に * がある")
    return sql


def load_target_fields(year: int, db_path) -> dict[str, list[dict]]:
    """対象レース (JRA・確定・平地) の選択集合の材料だけを読む。結果の列 (着順・脚質コード・異常コードの生の値) は読まない。"""
    guard_analysis_window(f"{year}0101", f"{year}1231", context="c_prime_run.load_target_fields")
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    cur = conn.execute(target_sql(), (str(year),))
    names = tuple(d[0] for d in cur.description)
    if names != TARGET_COLUMNS:
        conn.close()
        raise RunError(f"対象レースの返る列が allow-list と違う: {names}")
    rows = cur.fetchall()
    conn.close()
    out: dict[str, list[dict]] = defaultdict(list)
    for (ry, rmd, tc, ka, ni, rn, tt, hn, bn, refunded, odds) in rows:
        if cp.flat_surface(tt) is None:
            continue
        rid = f"{ry}{rmd}_{tc}_{ka}_{ni}_{rn}"
        out[rid].append({"race_id": rid, "ymd": f"{ry}{rmd}", "horse": str(bn or "").strip(), "horse_num": str(hn).strip(),
                         "refunded": bool(refunded), "win_odds": float(odds or 0) / 10.0})
    return dict(out)


def outcome_blind_rows(targets: dict, history: dict, experience: dict, counts: Counter, exclusions: list[dict]) -> list[dict]:
    """選択集合 (§8-6) の行。`won` を持たない (勝ち馬の数も見ないので、同着のレースも含む)。"""
    out = []
    for rid in sorted(targets):
        runners = targets[rid]
        counts["target_races_seen"] += 1
        cs = rm.build_choice_set({x["horse_num"]: ("3" if x["refunded"] else "0") for x in runners},
                                 {"final": {x["horse_num"]: x["win_odds"] for x in runners if x["win_odds"] > 0}})
        if isinstance(cs, rm.Excluded):
            counts[f"excluded:{cs.reason}"] += 1
            exclusions.append({"race_id": rid, "reason": cs.reason, "horses": list(cs.horses)})
            continue
        ordinal = cp.day_ordinal(runners[0]["ymd"])
        by_num = {x["horse_num"]: x for x in runners}
        styles = {h: (cp.style_of(history.get(by_num[h]["horse"], []), ordinal) if by_num[h]["horse"] else None) for h in cs.choice}
        comps = cp.race_components(styles)
        for h in cs.choice:
            out.append({"race_id": rid, "year": int(rid[:4]), "horse_num": h, "p_market": cs.implied["final"][h],
                        "style": styles[h] or "",
                        "n_runs_365": cp.runs_in_window(experience.get(by_num[h]["horse"], []), ordinal), **comps[h]})
        counts["refunded_runners"] += len(cs.refunded)
        counts["target_races_used"] += 1
    return out


def fixed_power(se_analytic: float, se_train_boot: float | None, n_train: int, n_target: int) -> dict:
    se_scaled = se_train_boot * math.sqrt(n_train / n_target) if se_train_boot is not None else None
    se_fixed = max(se_analytic, se_scaled) if se_scaled is not None else se_analytic
    m = CRITICAL_MULTIPLIER * se_fixed
    return {"se_analytic_2025": se_analytic, "se_train_boot": se_train_boot, "n_train_races": n_train, "n_target_races": n_target,
            "se_train_scaled": se_scaled, "se_fixed": se_fixed, "critical_multiplier": CRITICAL_MULTIPLIER, "mde": m,
            "beta_target": BETA_TARGET, "inconclusive_by_power": bool(m > BETA_TARGET),
            "rule": "MDE > beta_target なら、主検定は結果に関係なく PRIMARY_INCONCLUSIVE (§8-4)。主検定は 1 回実行して記録する"}


def run_power(db: str, frozen: Path, out: Path, argv: list[str]) -> dict:
    started = _now()
    man, payload = _load_frozen(frozen)
    out.mkdir(parents=True, exist_ok=True)
    races, load_stats = cp.load_races(PRIMARY_YEAR, min_year=2021, db_path=db, allow_primary_year=True,
                                      primary_purpose="power: 2025 の対象日より前の走の脚質コードを履歴として読む (対象の行に結果を付けない)")
    _check_history(races, man)
    history, experience = cp.style_history(races), cp.experience_index(races)
    del races                                        # 以降、対象レースは allow-list の読み込みだけ
    targets = load_target_fields(PRIMARY_YEAR, db)
    counts, exclusions = Counter(), []
    rows = cp.apply_composite(outcome_blind_rows(targets, history, experience, counts, exclusions), payload["composite"])
    fisher = mc.fisher_se_at_null(rows)
    power = fixed_power(fisher["se"], man["bootstrap"]["se"], man["n_train_races"], fisher["n_races"])
    buys = mc.ratio_buys_at(rows, 1.0, BETA_TARGET)  # §8-8: 正規化した P_new の比で数える (S ≥ 2 の目安は使わない)
    n_races = fisher["n_races"]
    per100 = 100.0 * len(buys) / n_races if n_races else math.nan
    result = {
        "kind": "c_prime_power", "started_at": started, "ended_at": _now(),
        "provenance": cp.provenance(db, argv, own_output=_rel(out)),
        "frozen_sha256": man["frozen_sha256"], "frozen_manifest_sha256": _sha(frozen / MANIFEST_FILE),
        "load_stats_history": dict(load_stats), "target_counts": dict(counts), "exclusions": exclusions,
        "fisher": fisher, "power": power,
        "purchase_projection": {"assumption": "beta_market=1, beta_S=beta_target (2025 の推定値は使わない)",
                                "counting": "predictor.market_clogit.ratio_buys_at(rows, 1.0, beta_target)",
                                "n_horses": len(buys), "n_races": n_races, "per_100_races": per100,
                                "races_for_100": (100 / per100 * 100) if per100 > 0 else None,
                                "races_for_1500": (1500 / per100 * 100) if per100 > 0 else None},
        "S_variance_decomposition_2025": cp.variance_decomposition(rows, "S"),
        "n_rows": len(rows), "style_unknown_rate": sum(not r["style"] for r in rows) / len(rows) if rows else math.nan,
        "note": "対象レース自身の結果は読んでいない (allow-list の読み込み、行に won なし)。β は推定していない",
    }
    _write_json(out / POWER_FILE, result)
    return result


# ---------------------------------------------------------------------------------------------------- arm / primary

def _check_pinned(man: dict, power: dict) -> dict:
    now = cp.provenance(man["provenance"]["db"]["path"], ["check"])
    if now["git_dirty"]:
        raise RunError(f"作業ツリーに未コミットの変更がある: {now['git_status']}")
    bad = {}
    for f in PINNED_FILES:
        cur = now["files_blob_sha1"].get(f)
        for name, src in (("freeze", man["provenance"]["files_blob_sha1"]), ("power", power["provenance"]["files_blob_sha1"])):
            if src.get(f) != cur:
                bad[f"{f} ({name})"] = (src.get(f), cur)
    if bad:
        raise RunError(f"主検定の前提のファイルが凍結・検出力の時点と違う: {bad}")
    return {"git_sha": now["git_sha"], "pinned_blob_sha1": {f: now["files_blob_sha1"][f] for f in PINNED_FILES}}


def _frozen_and_power(frozen: Path, power_path: Path) -> tuple[dict, dict, dict]:
    man, payload = _load_frozen(frozen)
    power = json.loads(Path(power_path).read_text(encoding="utf-8"))
    if power["frozen_sha256"] != man["frozen_sha256"] or power.get("frozen_manifest_sha256") != _sha(frozen / MANIFEST_FILE):
        raise RunError("検出力の結果が別の凍結物から作られている")
    return man, payload, power


def run_arm(db: str, frozen: Path, power_path: Path, argv: list[str], rerun_reason: str | None = None) -> dict:
    man, _payload, power = _frozen_and_power(frozen, power_path)
    lock_path = frozen / LOCK_FILE
    previous = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else None
    if previous is not None and not rerun_reason:
        raise RunError(f"主検定の錠が既にある ({lock_path}、run_index {previous['run_index']})。主検定は 1 回だけ")
    pinned = _check_pinned(man, power)
    hist_races, _ = cp.load_races(max(EST_YEARS), min_year=2021, db_path=db)
    _check_history(hist_races, man)
    del hist_races
    run_index = (previous["run_index"] + 1) if previous else 1
    lock = {"run_index": run_index, "armed_at": _now(), "argv": argv, "rerun_reason": rerun_reason,
            "frozen_sha256": man["frozen_sha256"], "power_sha256": _sha(power_path), **pinned,
            "history": (previous.get("history", []) + [previous]) if previous else []}
    _write_json(lock_path, lock)
    return lock


def _lock_is_committed(lock_path: Path) -> bool:
    rel = _rel(lock_path)
    if rel is None:
        return False
    tracked = subprocess.run(["git", "-C", str(cp.ROOT), "ls-files", "--error-unmatch", rel], capture_output=True, text=True)
    status = subprocess.run(["git", "-C", str(cp.ROOT), "status", "--porcelain", "--", rel], capture_output=True, text=True)
    return tracked.returncode == 0 and status.returncode == 0 and not status.stdout.strip()


def verdict(ci: dict, power: dict) -> tuple[str, str]:
    """§8-4: 検出力で判定不能が確定していれば INCONCLUSIVE (MDE の理由を上書きしない) → 区間が無効なら INCONCLUSIVE → 下限 > 0 で PASS。"""
    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")
    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"
    return ("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] > 0 else ("PRIMARY_FAIL", "ci_lower_not_above_zero")


def run_primary(db: str, frozen: Path, power_path: Path, out: Path, argv: list[str]) -> dict:
    man, payload, power = _frozen_and_power(frozen, power_path)
    lock_path = frozen / LOCK_FILE
    if not lock_path.exists():
        raise RunError("主検定の錠が無い (先に arm で錠を書き、git にコミットする)")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if not _lock_is_committed(lock_path):
        raise RunError(f"主検定の錠が git にコミットされていない ({lock_path})")
    if lock["frozen_sha256"] != man["frozen_sha256"] or lock["power_sha256"] != _sha(power_path):
        raise RunError("錠が別の凍結物・検出力のもの")
    run_index = lock["run_index"]
    started_path = frozen / STARTED_FILE.format(run_index)
    if started_path.exists():
        raise RunError(f"run_index {run_index} の主検定は既に始まっている ({started_path})")
    pinned = _check_pinned(man, power)
    if pinned["pinned_blob_sha1"] != lock["pinned_blob_sha1"]:
        raise RunError("固定したファイルが錠を書いた時点と違う")
    started = _now()
    out.mkdir(parents=True, exist_ok=True)
    _write_json(started_path, {"run_index": run_index, "started_at": started, "out": str(out), "argv": argv})
    races, load_stats = cp.load_races(PRIMARY_YEAR, min_year=2021, db_path=db, allow_primary_year=True,
                                      primary_purpose=f"primary: Group C′ の主検定 (run_index {run_index})")
    _check_history(races, man)
    history, experience = cp.style_history(races), cp.experience_index(races)
    counts, exclusions = Counter(), []
    rows = cp.apply_composite(cp.target_rows(races, (PRIMARY_YEAR,), history, experience, counts, exclusions),
                              payload["composite"])
    srows = _with_market(rows)
    beta, ok, packed = _beta_both(srows)
    t0 = time.time()
    ci = es.primary_block_ci(srows, st.make_beta_stat(packed, "S"), level=es.PRIMARY_CI_LEVEL)
    ci_seconds = round(time.time() - t0, 1)
    if (ci["level"], ci["n_boot"], ci["seed"]) != (es.PRIMARY_CI_LEVEL, es.PRIMARY_N_BOOT, es.PRIMARY_SEED):
        raise RunError(f"主検定の区間の設定が事前登録と違う: {ci}")
    hess = cp.clogit_with_se(rows, ["S"])
    cat, reason = verdict(ci, power["power"])
    z = 2.5758293035489004
    result = {
        "kind": "c_prime_primary", "run_index": run_index, "rerun_reason": lock.get("rerun_reason"),
        "started_at": started, "ended_at": _now(),
        "provenance": cp.provenance(db, argv, own_output=_rel(out)), "pinned": pinned,
        "frozen_sha256": man["frozen_sha256"], "power_sha256": _sha(power_path),
        "load_stats": dict(load_stats), "choice_set": choice_set_contract(rows, counts, exclusions),
        "n_races_power_minus_primary": power["fisher"]["n_races"] - len({r["race_id"] for r in rows}),
        "beta": {"market": beta[0], "S": beta[1], "converged": ok}, "ci_99": ci, "ci_seconds": ci_seconds,
        "wald_diagnostic": {"se_hessian": hess["se"][1], "lo": beta[1] - z * hess["se"][1], "hi": beta[1] + z * hess["se"][1],
                            "note": "診断だけ。判定に使わない"},
        "power": power["power"], "category": cat, "category_reason": reason,
    }
    _write_json(out / PRIMARY_FILE, result)
    try:
        side = _side_records(rows, beta)
    except Exception as e:                           # 判定に使わない記録の失敗は、判定を変えずに記録だけする
        side = {"error": f"{type(e).__name__}: {e}"}
    _write_json(out / SIDE_FILE, {"run_index": run_index, "primary_file": PRIMARY_FILE, **side})
    return {**result, "side_records_not_for_decision": side}


def _side_records(rows: list[dict], beta: list[float]) -> dict:
    """§8-4 / §8-6b の判定に使わない記録 (2025 で 1 回だけ)。"""
    side = {"S_variance_decomposition": cp.variance_decomposition(rows, "S"),
            "S_vs_n_runs_365_within_corr": cp.within_race_corr(rows, "S", "n_runs_365")}
    # S を脚質の指示 (逃・先 = −1、差・追 = +1、不明 = 0) で残差化した版 (pace と無関係な「先行・差し」の市場の偏りの切り分け)
    ind = np.array([(-1.0 if r["style"] in cp.FRONT else 1.0 if r["style"] in cp.BACK else 0.0) for r in rows])
    s = np.array([r["S"] for r in rows])
    A = np.column_stack([np.ones_like(ind), ind])
    coef, *_ = np.linalg.lstsq(A, s, rcond=None)
    res_rows = [{**r, "S_res": float(v)} for r, v in zip(rows, s - A @ coef)]
    side["beta_S_residualised_on_style_indicator"] = {**cp.clogit_with_se(res_rows, ["S_res"]),
                                                      "note": "pooled の最小二乗で残差化 (2025 の中の in-sample の操作)"}
    # style_rarity_in_race: 同じ脚質コードの馬の、既知の馬に占める割合の逆数 (不明はレース内の平均で埋める)
    by = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    rr = []
    for rs in by.values():
        known = [r["style"] for r in rs if r["style"]]
        vals = {st_: len(known) / known.count(st_) for st_ in set(known)}
        fill = (sum(vals[r["style"]] for r in rs if r["style"]) / len(known)) if known else 0.0
        rr.extend({**r, "style_rarity_in_race": vals.get(r["style"], fill) if r["style"] else fill} for r in rs)
    side["beta_style_rarity_in_race"] = cp.clogit_with_se(rr, ["style_rarity_in_race"])
    # 金額の試験の診断の集合 (§8-6b。2025 の確定市場での件数の記録で、金額の判定ではない)
    try:
        unit = mc.fit_s_given_unit_market(rows)["beta_s_given_unit_market"]
    except mc.MarketClogitError as e:
        unit = None
        side["fit_s_given_unit_market_error"] = str(e)
    no_won = [{k: v for k, v in r.items() if k != "won"} for r in rows]
    side["diagnostic_sets_final_market_2025"] = mc.diagnostic_sets(no_won, beta[0], beta[1], beta_s_given_unit_market=unit)
    return side


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--db", required=True); f.add_argument("--out", required=True)
    p = sub.add_parser("power")
    p.add_argument("--db", required=True); p.add_argument("--frozen", required=True); p.add_argument("--out", required=True)
    am = sub.add_parser("arm")
    am.add_argument("--db", required=True); am.add_argument("--frozen", required=True); am.add_argument("--power", required=True)
    am.add_argument("--rerun-reason")
    q = sub.add_parser("primary")
    q.add_argument("--db", required=True); q.add_argument("--frozen", required=True); q.add_argument("--power", required=True)
    q.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    full = ["c_prime_run", *argv]
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if a.cmd == "freeze":
        m = run_freeze(a.db, Path(a.out), full)
        print(json.dumps({k: m[k] for k in ("frozen_sha256", "n_train_races", "bootstrap", "leave_one_year_out", "train_in_sample")},
                         ensure_ascii=False, indent=1, default=str))
    elif a.cmd == "power":
        r = run_power(a.db, Path(a.frozen), Path(a.out), full)
        print(json.dumps({"power": r["power"], "fisher_se": r["fisher"]["se"], "rho": r["fisher"]["rho_within_race_market_weighted"],
                          "purchase": r["purchase_projection"]}, ensure_ascii=False, indent=1))
    elif a.cmd == "arm":
        lock = run_arm(a.db, Path(a.frozen), Path(a.power), full, rerun_reason=a.rerun_reason)
        print(json.dumps({k: lock[k] for k in ("run_index", "armed_at", "frozen_sha256", "power_sha256", "git_sha")},
                         ensure_ascii=False, indent=1))
    else:
        r = run_primary(a.db, Path(a.frozen), Path(a.power), Path(a.out), full)
        print(json.dumps({k: r[k] for k in ("beta", "ci_99", "category", "category_reason")}, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
