"""Phase 0.5-5 Group D の実行: 凍結 (freeze) → 検出力の固定 (power) → 錠 (arm) → 主検定 (primary) (2026-10-06)。

仕様: `docs/PHASE05_5_PREREG.md` §8-4 / §8-4d / §8-4c-2 / §8-6 / §8-6b / §8-7 / §8-7b / §8-8、台帳 D-0〜D-3。共通の部品は `scripts/prereg_runner.py`。

**2026-10-06 の決定で Group D の主検定は実行しない** (`BLOCKED_BY_IDENTIFIABILITY` / `PRIMARY_NOT_RUN`、`docs/PHASE05_5_GROUP_D_RESULT.md`)。
freeze 以降を走らせる前に族の状態 (`docs/PHASE05_5_FAMILY_STATUS.md`) と事前登録の追補を確認すること。このスクリプトは実装と変異の記録として残す。

    python -m scripts.group_d_run freeze  --db <db> --out <dir>
    python -m scripts.group_d_run power   --db <db> --frozen <dir> --out <dir>
    python -m scripts.group_d_run arm     --db <db> --frozen <dir> --power <power.json>
    python -m scripts.group_d_run primary --db <db> --frozen <dir> --power <power.json> --out <dir>

- 主検定のモデルは `[market_feature, class_move, S_std]` (市場の列は market_clogit / race_market.market_feature)
- 検出力: 2025 の対象レースは allow-list の SQL だけで読み、行に won は付けない。前走の評価値と要求水準の履歴には、対象日より前の日の走の時計・着順を
  読む (Group A と同じ原則。外部の指示者の決定 2026-10-05)。2025 の履歴の digest を記録し、錠と主検定の開始の印の前に照合する
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from config import guard_analysis_window
from db import REFUNDED_ABNORMAL_CODES
from predictor import eval_stats as es
from predictor import market_clogit as mc
from predictor import race_market as rm
from scripts import c_prime as cp
from scripts import group_a as ga
from scripts import group_a_stats as st
from scripts import group_d as gd
from scripts import prereg_runner as pr

ROOT = Path(__file__).resolve().parent.parent
EST_YEARS = (2022, 2023, 2024)
PRIMARY_YEAR = gd.PRIMARY_YEAR
COLS = [mc.MARKET_COL, "class_move_filled", "S_std"]
BOOT_N = 1000
BOOT_SEED = 20261004
BOOT_MAX_DISCARD_FRAC = 0.01
FROZEN_FILE = "frozen_group_d.json"
MANIFEST_FILE = "MANIFEST.json"
POWER_FILE = "power.json"
PRIMARY_FILE = "primary_result.json"
SIDE_FILE = "primary_side_records.json"
LOCK_FILE = "PRIMARY_LOCK.json"
STARTED_FILE = "PRIMARY_RUN_{}_STARTED.json"
PAYLOAD_VERSION = "group_d_payload_v1"
DEPENDENCIES = ("scripts/group_d.py", "scripts/group_d_run.py", "scripts/group_a.py", "scripts/c_prime.py", "scripts/prereg_runner.py",
                "predictor/market_clogit.py", "predictor/race_market.py", "predictor/eval_stats.py", "scripts/group_a_stats.py",
                "config.py", "db.py", "docs/PHASE05_5_PREREG.md", "data/backtest/group_a_class_20261005/class_table.csv")
PINNED_FILES = DEPENDENCIES
# Group A の凍結物の形 (`group_a.freeze_payload`) を評価値の補正テーブルの入れ物として使う。D は Group A の合成を使わないので空にする
_EMPTY_COMPOSITE = {"standardizer": {}, "raw_weights": {}, "weights": {}, "zeroed": [], "S_standardizer": [0.0, 1.0]}

_REFUND_SQL = ", ".join(f"'{c}'" for c in sorted(REFUNDED_ABNORMAL_CODES))
REFUND_PROXY_CODE = sorted(REFUNDED_ABNORMAL_CODES)[0]
TARGET_SELECT = (
    ("h.race_year", "race_year"), ("h.race_month_day", "race_month_day"), ("h.track_code", "track_code"),
    ("h.kaiji", "kaiji"), ("h.nichiji", "nichiji"), ("h.race_num", "race_num"), ("r.track_type_code", "track_type_code"),
    ("h.horse_num", "horse_num"), ("h.blood_register_num", "blood_register_num"),
    (f"CASE WHEN h.abnormal_code IN ({_REFUND_SQL}) THEN 1 ELSE 0 END", "is_refunded"), ("h.win_odds", "win_odds"),
)
TARGET_COLUMNS = tuple(alias for _, alias in TARGET_SELECT)
FORBIDDEN_COLUMNS = ("confirmed_order", "finish_order", "finish_time", "final_3f", "same_finish", "time_diff", "corner_order",
                     "mining", "payout", "popularity", "leg_quality", "starter_count", "horse_weight", "weight_change", "last3f", "front3f")


def constants() -> dict:
    return {"window_days": gd.WINDOW_DAYS, "min_requirement_races": gd.MIN_REQUIREMENT_RACES, "level": gd.LEVEL, "spec": gd.SPEC.name}


def history_digest(races: dict, years) -> dict:
    """指定の年の走の内容 (評価値と要求水準の材料: 時計・着順・斤量・返還・オッズ) の sha256。"""
    h = hashlib.sha256()
    n = 0
    for rid in sorted(r for r in races if int(r[:4]) in years):
        for x in races[rid].runs:
            h.update(f"{rid}|{x.horse}|{x.horse_num}|{x.abnormal}|{x.finish}|{x.sec_per_km!r}|{x.burden_kg!r}|{x.win_odds!r}\n".encode("utf-8"))
            n += 1
    return {"years": sorted(years), "runs": n, "sha256": h.hexdigest()}


def fisher_se_at_null(rows: list[dict]) -> dict:
    """仮定 β_market = 1・β_move = 0・β_S = 0 (勝つ確率 = P_market) での `(market_feature, class_move, S_std)` の情報行列から、S のシューア補元の SE。"""
    if any("won" in r for r in rows):
        raise pr.RunError("検出力の計算の行に勝ちの列がある")
    by = mc.check_canonical(rows)
    info = np.zeros((3, 3))
    for rs in by.values():
        p_market = {r["horse_num"]: r["p_market"] for r in rs}
        p_null = rm.p_new(p_market, {h: 0.0 for h in p_market}, 1.0, 0.0)
        p = np.array([p_null[r["horse_num"]] for r in rs])
        X = np.array([[rm.market_feature(r["p_market"]), r["class_move_filled"], r["S_std"]] for r in rs], dtype=float)
        m = p @ X
        info += (X * p[:, None]).T @ X - np.outer(m, m)
    try:
        inv = np.linalg.inv(info)
    except np.linalg.LinAlgError as e:
        raise pr.RunError("情報行列が特異") from e
    nuis = info[:2, :2]
    schur = float(info[2, 2] - info[2, :2] @ np.linalg.solve(nuis, info[:2, 2]))
    return {"se": float(math.sqrt(inv[2, 2])), "n_races": len(by), "info": info.tolist(), "var_s_within": float(info[2, 2]),
            "schur_complement": schur, "assumption": "beta_market=1, beta_move=0, beta_S=0 (win probability = P_market)"}


# ---------------------------------------------------------------------------------------------------- freeze

def run_freeze(db: str, out: Path, argv: list[str]) -> dict:
    started = pr.now()
    if (out / FROZEN_FILE).exists() or (out / LOCK_FILE).exists():
        raise pr.RunError(f"凍結物か錠が既にある (上書きしない): {out}")
    out.mkdir(parents=True, exist_ok=True)
    races, load_stats = ga.load_races(max(EST_YEARS), min_year=2021, db_path=db)
    tables = ga.fit_tables(races, gd.SPEC, EST_YEARS)
    history = gd.run_ratings(races, tables)
    req = gd.Requirements(races, gd.winner_ratings(races, history))
    counts, exclusions = Counter(), []
    rows = gd.target_rows(races, EST_YEARS, history, req, counts, exclusions)
    scale = gd.fit_scale(rows)
    srows = mc.add_market_feature(gd.standardize_and_fill(rows, scale["sd"]))
    beta_es, ok_es = es.conditional_logit(srows, COLS, with_status=True)
    packed = st.pack(srows, COLS)
    beta_pk, ok_pk = st.clogit_packed(packed)
    if not (ok_es and ok_pk) or max(abs(a - b) for a, b in zip(beta_es, beta_pk)) > 1e-8:
        raise pr.RunError(f"配列版と eval_stats の条件付きロジットが一致しない: {beta_pk} vs {beta_es}")
    t0 = time.time()
    vals, discarded = es._block_resample(srows, st.make_beta_stat(packed, "S_std"), BOOT_N, BOOT_SEED)
    boot = {"n_boot": BOOT_N, "seed": BOOT_SEED, "unit": "race", "statistic": "beta_S of [market_feature, class_move, S_std]",
            "n_valid": len(vals), "n_discarded": discarded, "max_discard": math.floor(BOOT_MAX_DISCARD_FRAC * BOOT_N + 1e-9),
            "seconds": round(time.time() - t0, 1)}
    boot["se"] = float(np.std(vals, ddof=1)) if discarded <= boot["max_discard"] and len(vals) > 1 else None
    loyo = {}
    for y in EST_YEARS:                               # 判定に使わない記録
        rest = tuple(x for x in EST_YEARS if x != y)
        t_y = ga.fit_tables(races, gd.SPEC, rest)
        h_y = gd.run_ratings(races, t_y)
        r_y = gd.Requirements(races, gd.winner_ratings(races, h_y))
        fit_y = gd.target_rows(races, rest, h_y, r_y, Counter(), [])
        ev_y = gd.target_rows(races, (y,), h_y, r_y, Counter(), [])
        sd_y = gd.fit_scale(fit_y)["sd"]
        res = gd.clogit(gd.standardize_and_fill(ev_y, sd_y))
        loyo[str(y)] = {"est_years": list(rest), "beta_S": res["beta"][2], "se_S": res["se"][2], "sign": int(np.sign(res["beta"][2]))}
    payload = {"payload_version": PAYLOAD_VERSION, "constants": constants(), "S_scale": scale,
               "rating_tables": ga.freeze_payload(tables, _EMPTY_COMPOSITE)}
    pr.write_json(out / FROZEN_FILE, payload)
    manifest = {
        "kind": "group_d_freeze", "started_at": started, "ended_at": pr.now(),
        "provenance": pr.provenance(ROOT, DEPENDENCIES, db, argv, own_output=pr.rel(ROOT, out)),
        "est_years": list(EST_YEARS), "frozen_file": FROZEN_FILE, "frozen_sha256": pr.sha256(out / FROZEN_FILE),
        "load_stats": dict(load_stats), "history_digest": history_digest(races, (2021,) + EST_YEARS),
        "counts": dict(counts), "exclusions": exclusions, "n_train_races": len({r["race_id"] for r in rows}),
        "train_in_sample": {"beta": beta_es, "cols": COLS, "note": "学習期の in-sample (判定に使わない)"},
        "bootstrap": boot, "leave_one_year_out": loyo,
        "S_variance_decomposition_train": cp.variance_decomposition(srows, "S_std"),
        "S_vs_class_move_within_corr_train": cp.within_race_corr(srows, "S_std", "class_move_filled"),
    }
    pr.write_json(out / MANIFEST_FILE, manifest)
    return manifest


def _load_frozen(frozen: Path) -> tuple[dict, dict]:
    man = json.loads((frozen / MANIFEST_FILE).read_text(encoding="utf-8"))
    if pr.sha256(frozen / FROZEN_FILE) != man["frozen_sha256"]:
        raise pr.RunError("凍結物の sha256 が MANIFEST と違う")
    payload = json.loads((frozen / FROZEN_FILE).read_text(encoding="utf-8"))
    if payload.get("payload_version") != PAYLOAD_VERSION:
        raise pr.RunError(f"凍結物の版が違う: {payload.get('payload_version')}")
    if payload["constants"] != json.loads(json.dumps(constants())):
        raise pr.RunError("凍結物の定数が今のコードと違う")
    return man, payload


def _check_history(races: dict, man: dict) -> None:
    d = history_digest(races, tuple(man["history_digest"]["years"]))
    if d != man["history_digest"]:
        raise pr.RunError(f"2021-2024 の履歴が凍結の時点と違う (DB が変わった): {d} vs {man['history_digest']}")


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
        raise pr.RunError(f"対象レースの SQL に結果の列が入っている: {bad}")
    if "*" in low:
        raise pr.RunError("対象レースの SQL に * がある")
    return sql


def load_target_fields(year: int, db_path) -> dict[str, list[dict]]:
    guard_analysis_window(f"{year}0101", f"{year}1231", context="group_d_run.load_target_fields")
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        cur = conn.execute(target_sql(), (str(year),))
        names = tuple(d[0] for d in cur.description)
        if names != TARGET_COLUMNS:
            raise pr.RunError(f"対象レースの返る列が allow-list と違う: {names}")
        rows = cur.fetchall()
    finally:
        conn.close()
    out: dict[str, list[dict]] = defaultdict(list)
    for (ry, rmd, tc, ka, ni, rn, tt, hn, bn, refunded, odds) in rows:
        if ga.is_obstacle(tt):
            continue
        surface = ga.surface_of(tt)
        if surface is None:
            raise pr.RunError(f"{ry}{rmd}_{tc}_{ka}_{ni}_{rn}: 平地の未知の track_type_code {tt!r}")
        rid = f"{ry}{rmd}_{tc}_{ka}_{ni}_{rn}"
        out[rid].append({"race_id": rid, "ymd": f"{ry}{rmd}", "surface": surface, "horse": str(bn or "").strip(),
                         "horse_num": str(hn).strip(), "refunded": bool(refunded), "win_odds": float(odds or 0) / 10.0})
    return dict(out)


def outcome_blind_rows(targets: dict, classes: dict, races_hist: dict, history: dict, req: gd.Requirements,
                       counts: Counter, exclusions: list[dict]) -> list[dict]:
    """選択集合 (§8-6) の行。won を持たない。前走の評価値と要求水準は対象日より前の日の履歴だけ (`gd.previous_run` / `Requirements`)。"""
    out = []
    for rid in sorted(targets):
        runners = targets[rid]
        counts["target_races_seen"] += 1
        cls = classes.get(rid, (None, None))[0]
        if cls not in gd.LEVEL:
            raise pr.RunError(f"{rid}: 想定外の canonical class {cls!r}")
        cs = rm.build_choice_set({x["horse_num"]: (REFUND_PROXY_CODE if x["refunded"] else "0") for x in runners},
                                 {"final": {x["horse_num"]: x["win_odds"] for x in runners if x["win_odds"] > 0}})
        if isinstance(cs, rm.Excluded):
            counts[f"excluded:{cs.reason}"] += 1
            exclusions.append({"race_id": rid, "reason": cs.reason, "horses": list(cs.horses)})
            continue
        t = ga.day_ordinal(runners[0]["ymd"])
        by_num = {x["horse_num"]: x for x in runners}
        rows = []
        for h in cs.choice:
            horse = by_num[h]["horse"]
            prev = gd.previous_run(history.get(horse, []), t) if horse else None
            row = {"race_id": rid, "year": int(rid[:4]), "horse_num": h, "p_market": cs.implied["final"][h],
                   "S_raw": math.nan, "class_move": math.nan, "has_prev": prev is not None}
            if prev is not None:
                pday, prid, prating = prev
                prace = races_hist[prid]
                requirement = req(prace.cls, prace.surface, pday)
                if not math.isnan(requirement):
                    row["S_raw"] = prating - requirement
                    row["class_move"] = float(gd.LEVEL[cls] - gd.LEVEL[prace.cls])
            rows.append(row)
        if not any(not math.isnan(r["S_raw"]) for r in rows):
            counts[f"excluded:{gd.EXCLUDE_ALL_MISSING}"] += 1
            exclusions.append({"race_id": rid, "reason": gd.EXCLUDE_ALL_MISSING, "horses": [r["horse_num"] for r in rows]})
            continue
        counts["target_races_used"] += 1
        out.extend(rows)
    return out


def primary_year_history_digest(races: dict, year: int) -> dict:
    """2025 の履歴の材料 (評価値・要求水準に使う、対象日より前の日の走の時計・着順など) の sha256。検出力と主検定の間の DB の変化を止める。"""
    return {**history_digest(races, (year,)), "year": year}


def run_power(db: str, frozen: Path, out: Path, argv: list[str]) -> dict:
    started = pr.now()
    man, payload = _load_frozen(frozen)
    out.mkdir(parents=True, exist_ok=True)
    races, load_stats = ga.load_races(PRIMARY_YEAR, min_year=2021, db_path=db, allow_primary_year=True,
                                      primary_purpose="power: 2025 の対象日より前の日の走を、前走の評価値と要求水準の履歴として読む (対象の行に結果は付けない)")
    _check_history(races, man)
    tables, _ = ga.tables_from_payload(payload["rating_tables"], races)
    history = gd.run_ratings(races, tables)
    req = gd.Requirements(races, gd.winner_ratings(races, history))
    primary_history = primary_year_history_digest(races, PRIMARY_YEAR)
    races_hist = {rid: r for rid, r in races.items()}   # レースの属性 (クラス・芝ダ) だけを引く
    targets = load_target_fields(PRIMARY_YEAR, db)
    counts, exclusions = Counter(), []
    raw_rows = outcome_blind_rows(targets, ga.load_class_table(), races_hist, history, req, counts, exclusions)
    del races
    rows = gd.standardize_and_fill(raw_rows, payload["S_scale"]["sd"])
    fisher = fisher_se_at_null(rows)
    power = pr.fixed_power(fisher["se"], man["bootstrap"]["se"], man["n_train_races"], fisher["n_races"])
    buys = mc.ratio_buys_at(rows, 1.0, pr.BETA_TARGET, s_col="S_std")
    n_races = fisher["n_races"]
    per100 = 100.0 * len(buys) / n_races if n_races else math.nan
    result = {
        "kind": "group_d_power", "started_at": started, "ended_at": pr.now(),
        "provenance": pr.provenance(ROOT, DEPENDENCIES, db, argv, own_output=pr.rel(ROOT, out)),
        "frozen_sha256": man["frozen_sha256"], "frozen_manifest_sha256": pr.sha256(frozen / MANIFEST_FILE),
        "load_stats_history": dict(load_stats), "target_counts": dict(counts), "exclusions": exclusions,
        "primary_year_history_digest": primary_history, "fisher": fisher, "power": power,
        "purchase_projection": {"assumption": "beta_market=1, beta_move=0, beta_S=beta_target (2025 の推定値は使わない)",
                                "counting": "predictor.market_clogit.ratio_buys_at(rows, 1.0, beta_target)",
                                "n_horses": len(buys), "n_races": n_races, "per_100_races": per100},
        "S_variance_decomposition_2025": cp.variance_decomposition(rows, "S_std"), "n_rows": len(rows),
        "observed_rate": sum(not math.isnan(r["S_raw"]) for r in rows) / len(rows) if rows else math.nan,
        "note": "対象レース自身の結果は読んでいない (allow-list の読み込み、行に won なし)。β は推定していない",
    }
    pr.write_json(out / POWER_FILE, result)
    return result


# ---------------------------------------------------------------------------------------------------- arm / primary

def _frozen_and_power(frozen: Path, power_path: Path) -> tuple[dict, dict, dict]:
    man, payload = _load_frozen(frozen)
    power = json.loads(Path(power_path).read_text(encoding="utf-8"))
    if power["frozen_sha256"] != man["frozen_sha256"] or power.get("frozen_manifest_sha256") != pr.sha256(frozen / MANIFEST_FILE):
        raise pr.RunError("検出力の結果が別の凍結物から作られている")
    return man, payload, power


def _check_pinned(man: dict, power: dict) -> dict:
    now = pr.provenance(ROOT, DEPENDENCIES, man["provenance"]["db"]["path"], ["check"])
    return pr.check_pinned(now, PINNED_FILES, ("freeze", man["provenance"]), ("power", power["provenance"]))


def _check_histories_before_reading_results(db: str, man: dict, power: dict) -> None:
    """2021-2024 と 2025 の履歴が凍結・検出力の時点と同じか (開始の印の前に。照合で止まっても run_index を消費しない)。"""
    races, _ = ga.load_races(PRIMARY_YEAR, min_year=2021, db_path=db, allow_primary_year=True,
                             primary_purpose="arm / primary の前の履歴の照合")
    _check_history(races, man)
    if primary_year_history_digest(races, PRIMARY_YEAR) != power["primary_year_history_digest"]:
        raise pr.RunError("2025 の履歴が検出力の計算の時点と違う (DB が変わった)")


def run_arm(db: str, frozen: Path, power_path: Path, argv: list[str], rerun_reason: str | None = None) -> dict:
    man, _payload, power = _frozen_and_power(frozen, power_path)
    lock_path = frozen / LOCK_FILE
    previous = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else None
    if previous is not None and not rerun_reason:
        raise pr.RunError(f"主検定の錠が既にある ({lock_path}、run_index {previous['run_index']})。主検定は 1 回だけ")
    pinned = _check_pinned(man, power)
    _check_histories_before_reading_results(db, man, power)
    run_index = (previous["run_index"] + 1) if previous else 1
    lock = {"run_index": run_index, "armed_at": pr.now(), "argv": argv, "rerun_reason": rerun_reason,
            "frozen_sha256": man["frozen_sha256"], "power_sha256": pr.sha256(power_path), **pinned,
            "history": (previous.get("history", []) + [previous]) if previous else []}
    pr.write_json(lock_path, lock)
    return lock


def run_primary(db: str, frozen: Path, power_path: Path, out: Path, argv: list[str]) -> dict:
    man, payload, power = _frozen_and_power(frozen, power_path)
    lock_path = frozen / LOCK_FILE
    if not lock_path.exists():
        raise pr.RunError("主検定の錠が無い (先に arm で錠を書き、git にコミットする)")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if not pr.lock_is_committed(ROOT, lock_path):
        raise pr.RunError(f"主検定の錠が git にコミットされていない ({lock_path})")
    if lock["frozen_sha256"] != man["frozen_sha256"] or lock["power_sha256"] != pr.sha256(power_path):
        raise pr.RunError("錠が別の凍結物・検出力のもの")
    run_index = lock["run_index"]
    started_path = frozen / STARTED_FILE.format(run_index)
    if started_path.exists():
        raise pr.RunError(f"run_index {run_index} の主検定は既に始まっている ({started_path})")
    if (out / PRIMARY_FILE).exists():
        raise pr.RunError(f"主検定の結果が出力先に既にある (上書きしない): {out}")
    pinned = _check_pinned(man, power)
    if pinned["pinned_blob_sha1"] != lock["pinned_blob_sha1"]:
        raise pr.RunError("固定したファイルが錠を書いた時点と違う")
    _check_histories_before_reading_results(db, man, power)
    started = pr.now()
    out.mkdir(parents=True, exist_ok=True)
    pr.write_json(started_path, {"run_index": run_index, "started_at": started, "out": str(out), "argv": argv})
    races, load_stats = ga.load_races(PRIMARY_YEAR, min_year=2021, db_path=db, allow_primary_year=True,
                                      primary_purpose=f"primary: Group D の主検定 (run_index {run_index})")
    _check_history(races, man)
    tables, _ = ga.tables_from_payload(payload["rating_tables"], races)
    history = gd.run_ratings(races, tables)
    req = gd.Requirements(races, gd.winner_ratings(races, history))
    counts, exclusions = Counter(), []
    raw_rows = gd.target_rows(races, (PRIMARY_YEAR,), history, req, counts, exclusions)
    rows = gd.standardize_and_fill(raw_rows, payload["S_scale"]["sd"])
    srows = mc.add_market_feature(rows)
    beta, ok = es.conditional_logit(srows, COLS, with_status=True)
    packed = st.pack(srows, COLS)
    beta_pk, ok_pk = st.clogit_packed(packed)
    if ok != ok_pk or (ok and max(abs(a - b) for a, b in zip(beta, beta_pk)) > 1e-8):
        raise pr.RunError(f"配列版と eval_stats の条件付きロジットが一致しない: {beta_pk} vs {beta}")
    t0 = time.time()
    ci = es.primary_block_ci(srows, st.make_beta_stat(packed, "S_std"), level=es.PRIMARY_CI_LEVEL)
    ci_seconds = round(time.time() - t0, 1)
    if (ci["level"], ci["n_boot"], ci["seed"]) != (es.PRIMARY_CI_LEVEL, es.PRIMARY_N_BOOT, es.PRIMARY_SEED):
        raise pr.RunError(f"主検定の区間の設定が事前登録と違う: {ci}")
    hess = gd.clogit(rows)
    cat, reason = pr.verdict(ci, power["power"])
    z = pr.Z_ALPHA_2SIDED_001
    result = {
        "kind": "group_d_primary", "run_index": run_index, "rerun_reason": lock.get("rerun_reason"),
        "started_at": started, "ended_at": pr.now(),
        "provenance": pr.provenance(ROOT, DEPENDENCIES, db, argv, own_output=[pr.rel(ROOT, out), pr.rel(ROOT, started_path)]),
        "pinned": pinned, "frozen_sha256": man["frozen_sha256"], "power_sha256": pr.sha256(power_path),
        "load_stats": dict(load_stats), "counts": dict(counts), "exclusions": exclusions,
        "n_races": len({r["race_id"] for r in rows}), "n_rows": len(rows),
        "n_races_power_minus_primary": power["fisher"]["n_races"] - len({r["race_id"] for r in rows}),
        "beta": {"market": beta[0], "class_move": beta[1], "S": beta[2], "converged": ok}, "ci_99": ci, "ci_seconds": ci_seconds,
        "wald_diagnostic": {"se_hessian": hess["se"][2], "lo": beta[2] - z * hess["se"][2], "hi": beta[2] + z * hess["se"][2],
                            "note": "診断だけ。判定に使わない"},
        "power": power["power"], "category": cat, "category_reason": reason,
        "after_primary": "config.CONSUMED_WINDOWS に 20250101-20251231 / 'phase05_5 group_d primary run_index N' を追記する (reused consumed validation window)",
    }
    pr.write_json(out / PRIMARY_FILE, result)
    try:
        side = _side_records(raw_rows, rows, beta, payload["S_scale"]["sd"])
    except Exception as e:                           # 判定に使わない記録の失敗は判定を変えない
        side = {"error": f"{type(e).__name__}: {e}"}
    pr.write_json(out / SIDE_FILE, {"run_index": run_index, "primary_file": PRIMARY_FILE, **side})
    return {**result, "side_records_not_for_decision": side}


def _side_records(raw_rows: list[dict], rows: list[dict], beta: list[float], s_sd: float) -> dict:
    """§8-4d の診断 (判定に使わない、2025 で 1 回だけ)。"""
    side = {"S_variance_decomposition": cp.variance_decomposition(rows, "S_std"),
            "S_vs_class_move_within_corr": cp.within_race_corr(rows, "S_std", "class_move_filled"),
            "gap_to_current_class_equivalence": gd.gap_equivalence(raw_rows, s_sd)}
    inter = [{**r, "S_x_move": r["S_std"] * r["class_move_filled"]} for r in rows]
    fit = cp.clogit_with_se(inter, ["class_move_filled", "S_std", "S_x_move"])
    side["S_x_move"] = {"beta": fit["beta"][3], "z": fit["z"][3]}
    by_move = defaultdict(int)
    for r in raw_rows:
        if not math.isnan(r["class_move"]):
            by_move[int(r["class_move"])] += 1
    side["class_move_distribution"] = dict(sorted(by_move.items()))
    # 金額の診断の集合 (§8-6b): p_new の S の列に β_move·class_move + β_S·S_std を渡す (単一の P_new の関数のまま)。2025 の確定市場での件数の記録
    lin = [{k: v for k, v in r.items() if k != "won"} | {"lin": beta[1] * r["class_move_filled"] + beta[2] * r["S_std"]} for r in rows]
    side["diagnostic_sets_final_market_2025"] = {
        "full": len(mc.ratio_buys_at(lin, beta[0], 1.0, s_col="lin")),
        "market_recalibration_only": len(mc.ratio_buys_at(lin, beta[0], 0.0, s_col="lin")),
        "s_correction_only": len(mc.ratio_buys_at(rows_no_won(rows), 1.0, beta[2], s_col="S_std"))}
    return side


def rows_no_won(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if k != "won"} for r in rows]


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
    full = ["group_d_run", *argv]
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
        print(json.dumps({"power": r["power"], "fisher_se": r["fisher"]["se"], "purchase": r["purchase_projection"]}, ensure_ascii=False, indent=1))
    elif a.cmd == "arm":
        lock = run_arm(a.db, Path(a.frozen), Path(a.power), full, rerun_reason=a.rerun_reason)
        print(json.dumps({k: lock[k] for k in ("run_index", "armed_at", "frozen_sha256", "power_sha256", "git_sha")}, ensure_ascii=False, indent=1))
    else:
        r = run_primary(a.db, Path(a.frozen), Path(a.power), Path(a.out), full)
        print(json.dumps({k: r[k] for k in ("beta", "ci_99", "category", "category_reason")}, ensure_ascii=False, indent=1, default=str))
        print("次: " + r["after_primary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
