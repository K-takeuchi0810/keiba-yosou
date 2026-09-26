"""Phase 0.5-4B の結論が、T−10 市場の取得元 (0B30 / 0B31) でどれだけ動くかを測る。

**これは 4B の再判定ではなく、明示的な感度分析 (robustness analysis)。** 事前登録された
確認的な検定ではない。0B30 と 0B31 のどちらが正しいかは決めない
(docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md 3-bis)。モデル・閾値・評価集合の規則は 4B と
同じものを各系列にそのまま当て、**入力の T−10 市場だけ** を差し替える。

## 系列 (2026-09-26 CHAT で固定。main 491d2e6 の監査文書 3-bis に登録済み)

| 系列 | T−10 市場の出どころ |
|---|---|
| `original_mixed` | DB の odds_snapshots をそのまま (本番の `predictor.pit_t10.t10_market`)。4B の再現の基準 |
| `raw_mixed` | raw の 0B30 + 0B31 から組み直した混合。DB の同じ秒の上書きの影響を除く |
| `raw_0B30` | raw の 0B30 だけ |
| `raw_0B31` | raw の 0B31 だけ (5〜6 月の backfill_0B31 の元データを含む) |
| `matched_same_state` | raw_0B30 と raw_0B31 が T−10 に選ぶ状態が **同じ市場状態** (発表時刻・単勝票数合計・全馬のオッズが一致) のレースだけ |

## raw の扱い (本番の取り込みと同じ意味にする)

- 受信時刻: 本番の fetched_at の由来に合わせる。backfill (`scripts/backfill_odds_snapshots.py`、
  0B31 の 2026-06-28 以前) は **ファイル名の epoch**、ライブの取り込み (`jvlink_client/ingest.py`)
  は **ファイルの mtime** (秒未満切り捨て)。取り込まれなかった 7 月前半もライブの規則で扱う
- odds > 0 の馬が 1 頭もいない O1 は、本番では行を作らない (`db.insert_odds_snapshot`) ので
  「存在しない」とみなす。選択は `t10_market` と同じ「決定時刻以前で受信が最新の 1 枚」で、
  **それより前の枚へは遡らない**
- raw_mixed で同じ秒に両方ある場合は単勝票数合計の多い方 (後の市場状態)、同数なら 0B31
- 組み立て (`build_market`) は `t10_market` の写しなので、**起動時に評価窓の全レースで
  本番と等価かを確かめ、1 件でも違えば止める** (production equivalence gate)

## 読み方 (2026-09-26 CHAT。当初の 50% 閾値は事前固定を git で証明できないため格下げ)

coverage の閾値そのものを感度の対象にし、40 / 45 / 50 / 55% で各系列が判定対象になるか、
主要仮説・棄却条件・比 ≥ 1.75・購入条件が original_mixed と同じかを並べる。
「結論が同じ」= 主要仮説の合否 / 金額の判定 / 比 ≥ 1.75 が 0 頭か / 棄却条件、の 4 つが一致。
same_total_discordant / different_state は評価系列に混ぜず、監査として別に出す。

usage (成果物は既存の 4A/4B と別名。既存 JSON は上書きしない):
    KEIBA_PROD_ROOT=C:/Users/kizun/dev/keiba-yosou \
    .venv64/Scripts/python.exe scripts/t10_source_sensitivity.py --out-dir data/backtest/src_sensitivity_20260926
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("KEIBA_PROD_ROOT") or HERE).resolve()
sys.path.insert(0, str(ROOT))

import jvlink_client.ingest as ingest_mod  # noqa: E402
import jvlink_client.parser as parser_mod  # noqa: E402
from jvlink_client.ingest import _split_records  # noqa: E402
from jvlink_client.parser import parse_o1  # noqa: E402
from predictor import eval_stats, pit_t10  # noqa: E402
from predictor.eval_stats import block_boot, coefficient_ci, conditional_logit, metrics  # noqa: E402
from predictor.pit_t10 import T10Market, _parse_announced, decision_time, start_time_history  # noqa: E402
import scripts.market_offset_eval as moe  # noqa: E402

# KEIBA_PROD_ROOT で解決したつもりが、別の checkout のコードで走っていないこと
PROD_MODULES = {"market_offset_eval": moe, "pit_t10": pit_t10, "eval_stats": eval_stats,
                "ingest": ingest_mod, "parser": parser_mod}
for _name, _mod in PROD_MODULES.items():
    if not Path(_mod.__file__).resolve().is_relative_to(ROOT):
        raise SystemExit(f"{_name} が {ROOT} の外から読み込まれた: {_mod.__file__}")

FROM, TO = "20260509", "20260831"          # 4A/4B の評価窓
NAME = re.compile(r"^(0B3[01])_(\d{16})_(\d+)\.jvd$")
SERIES = ("original_mixed", "raw_mixed", "raw_0B30", "raw_0B31", "matched_same_state")
COVERAGE_THRESHOLDS = (0.40, 0.45, 0.50, 0.55)
# backfill_odds_snapshots.py の在庫の最終日。これ以前の 0B31 は epoch、以後はライブの mtime
BACKFILL_LAST_DAY = "20260628"
# JV-Data4901 p.15 O1 項番 20「単勝票数合計」位置 928 (1 始まり)・11 バイト・百円単位。
# parser の O1Odds に無い項目なので、ここで切り出す (0 始まりで 927:938)
WIN_VOTES_SLICE = slice(927, 938)
# 共通集合での比較を行う最小レース数。当てはめが安定する目安として実行前に置いた値
# (統計的な根拠のある下限ではない)
MIN_COMMON_RACES = 30
REF_4B = "data/backtest/20260919_phase05_4B_market_offset.json"


# --- raw の読み込み -----------------------------------------------------------

def raw_received(spec: str, day: str, epoch: int, mtime: float) -> tuple[datetime, str]:
    """本番の fetched_at と同じ由来の受信時刻。"""
    if spec == "0B31" and day <= BACKFILL_LAST_DAY:
        return datetime.fromtimestamp(epoch), "epoch_backfill"
    # ingest.py: datetime.fromtimestamp(st_mtime).isoformat(timespec="seconds") = 秒未満切り捨て
    return datetime.fromtimestamp(mtime).replace(microsecond=0), "mtime_live"


def load_raw_states() -> tuple[dict, dict]:
    """race_id -> [state]。state = 1 回の取得で得た O1 1 レコード。"""
    states: dict[str, list[dict]] = defaultdict(list)
    info = Counter()
    for spec in ("0B30", "0B31"):
        for p in (ROOT / "data" / "raw" / spec).iterdir():
            m = NAME.match(p.name)
            if not m:
                info[f"{spec}_name_not_matched"] += 1      # 0 バイトの重複名 (".jvd_....jvd")
                if p.stat().st_size:
                    info[f"{spec}_name_not_matched_nonempty"] += 1
                continue
            day = m.group(2)[:8]
            if not (FROM <= day <= TO):
                continue
            info[f"{spec}_files"] += 1
            epoch = int(m.group(3))
            mtime = p.stat().st_mtime
            received, origin = raw_received(spec, day, epoch, mtime)
            info[f"{spec}_{origin}"] += 1
            if int(mtime) != epoch:
                info[f"{spec}_mtime_differs_from_name"] += 1
            for rec in _split_records(p.read_bytes()):
                if rec[:2] != b"O1":
                    continue
                o = parse_o1(rec)
                odds = {h.strip(): od for h, od, _pop in o.win_odds}   # parse_o1 は odds > 0 だけ
                if not odds:
                    info[f"{spec}_o1_without_positive_odds_treated_absent"] += 1
                    continue
                votes = rec[WIN_VOTES_SLICE].decode("ascii", "replace").strip()
                rid = "-".join((o.year, o.month_day, o.track_code, o.kaiji, o.nichiji, o.race_num))
                states[rid].append({
                    "source": spec, "file": p.name, "received": received,
                    "received_origin": origin, "received_epoch": datetime.fromtimestamp(epoch),
                    "data_div": o.data_div, "announced": o.announced_at or "",
                    "votes": int(votes) if votes.isdigit() else None, "odds": odds,
                })
                info[f"{spec}_o1_records"] += 1
    return states, dict(info)


def classify(a: dict | None, b: dict | None) -> str:
    if a is None or b is None:
        return "one_source_missing"
    if a["announced"] != b["announced"]:
        return "different_announced"
    if a["votes"] != b["votes"]:
        return "different_state"
    if a["odds"] != b["odds"]:
        return "same_total_discordant"
    return "matched_same_state"


def pick(states, cutoff: datetime, sources: tuple[str, ...], key: str = "received"):
    """決定時刻以前で受信が最新の 1 枚。同じ秒に複数あれば票数合計の多い方、同数なら 0B31。

    t10_market と同じく、最新の枚より前へは遡らない。戻り値 (state | None, 同秒に両取得元か)。
    """
    cands = [s for s in states if s["source"] in sources and s[key] <= cutoff]
    if not cands:
        return None, False
    latest = max(s[key] for s in cands)
    top = [s for s in cands if s[key] == latest]
    tie = len({s["source"] for s in top}) > 1
    top.sort(key=lambda s: (s["votes"] if s["votes"] is not None else -1, s["source"] == "0B31"),
             reverse=True)
    return top[0], tie


# --- T10Market の組み立て (t10_market の写し。起動時に本番と等価かを確かめる) ---------

def build_market(conn, race, target, start_used, received_at: str,
                 odds_tenths: dict[str, int], observed_raw: str | None) -> T10Market:
    date8 = f"{race.get('race_year', '')}{race.get('race_month_day', '')}"
    cutoff = target.isoformat(timespec="seconds")
    odds = {h: v / 10.0 for h, v in odds_tenths.items()}
    raw = {h: 1.0 / o for h, o in odds.items() if o > 0}
    mass = sum(raw.values())
    implied = {h: v / mass for h, v in raw.items()} if mass > 0 else {}
    ranked = sorted(odds, key=lambda h: odds[h])
    violations = []
    if received_at > cutoff:
        violations.append(f"受信時刻 {received_at} が決定時刻 {cutoff} より後")
    observed_dt = _parse_announced(date8, observed_raw or "")
    if observed_raw and observed_dt is None:
        violations.append(f"発表時刻 {observed_raw!r} を解釈できない")
    elif observed_dt is not None and observed_dt > target:
        violations.append(f"発表時刻 {observed_dt.isoformat()} が決定時刻 {cutoff} より後")
    hist = start_time_history(conn, race)
    if start_used is not None and hist.known_at(target) != start_used:
        violations.append(f"使った発走時刻 {start_used.isoformat()} が決定時刻に既知でない")
    return T10Market(
        race_id="-".join(str(race.get(k)) for k in pit_t10.RACE_KEYS),
        decision_time=cutoff,
        start_time_used=start_used.isoformat(timespec="minutes") if start_used else "",
        odds=odds, implied=implied, market_rank={h: i + 1 for i, h in enumerate(ranked)},
        inverse_odds_mass=mass, odds_received_at=received_at,
        odds_observed_at=observed_dt.isoformat(timespec="minutes") if observed_dt else None,
        n_horses=len(odds), violations=violations)


def db_market(conn, race, gate_minutes=None) -> tuple[T10Market | None, dict | None]:
    """DB の行を build_market に通す (t10_market と同じ SQL で 1 枚を選ぶ)。出自も返す。"""
    target, start_used = decision_time(conn, race, gate_minutes)
    if target is None:
        return None, None
    key = [race.get(k) for k in pit_t10.RACE_KEYS]
    cutoff = target.isoformat(timespec="seconds")
    row = conn.execute(
        """SELECT MAX(fetched_at) FROM odds_snapshots
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND fetched_at IS NOT NULL AND fetched_at <= ?""", (*key, cutoff)).fetchone()
    if row is None or not row[0]:
        return None, None
    received_at = str(row[0])
    rows = conn.execute(
        """SELECT horse_num, win_odds, announced_at FROM odds_snapshots
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=? AND fetched_at=?
              AND win_odds > 0""", (*key, received_at)).fetchall()
    if not rows:
        return None, None
    srcs = sorted({r[0] for r in conn.execute(
        """SELECT source FROM odds_snapshots WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=? AND fetched_at=?""", (*key, received_at))})
    m = build_market(conn, race, target, start_used, received_at,
                     {str(r[0]).strip(): r[1] for r in rows},
                     next((str(r[2]) for r in rows if r[2]), None))
    return m, {"source": "+".join(srcs), "received_at": received_at,
               "received_origin": "db", "total_votes": None,
               "announced": m.odds_observed_at}


def production_equivalence(conn, races: list[dict]) -> dict:
    """評価窓の全レースで db_market == 本番 t10_market を確かめる。1 件でも違えば止める。"""
    mismatched = []
    n_none = 0
    for race in races:
        prod = pit_t10.t10_market(conn, race)
        mine, _ = db_market(conn, race)
        if prod is None and mine is None:
            n_none += 1
            continue
        if prod is None or mine is None or asdict(prod) != asdict(mine):
            mismatched.append("-".join(str(race.get(k)) for k in pit_t10.RACE_KEYS))
    out = {"production_equivalence_checked_races": len(races),
           "production_equivalence_both_none": n_none,
           "production_equivalence_mismatched_races": len(mismatched),
           "production_equivalence_mismatch_examples": mismatched[:10]}
    if mismatched:
        raise SystemExit(f"build_market が本番の t10_market と一致しない: {out}")
    return out


# --- 系列ごとの T−10 市場 -----------------------------------------------------

class RawSelector:
    def __init__(self, states: dict):
        self.states = states
        self.audit: dict[str, Counter] = defaultdict(Counter)
        self.pairs: dict[str, dict] = {}          # race_id -> 0B30/0B31 の選択と分類
        self.chosen: dict[str, dict[str, dict]] = defaultdict(dict)   # series -> race_id -> 出自

    def market(self, series: str):
        def t10(conn, race, gate_minutes=None):
            target, start_used = decision_time(conn, race, gate_minutes)
            if target is None:
                return None
            rid = "-".join(str(race.get(k)) for k in pit_t10.RACE_KEYS)
            st_all = self.states.get(rid, ())
            s30, _ = pick(st_all, target, ("0B30",))
            s31, _ = pick(st_all, target, ("0B31",))
            kind = classify(s30, s31)
            self.pairs[rid] = {"class": kind, "0B30": s30, "0B31": s31}
            if series == "raw_mixed":
                st, tie = pick(st_all, target, ("0B30", "0B31"))
                if tie:
                    self.audit[series]["same_second_both_sources"] += 1
                alt, _ = pick(st_all, target, ("0B30", "0B31"), key="received_epoch")
            elif series in ("raw_0B30", "raw_0B31"):
                src = series[4:]
                st = s30 if src == "0B30" else s31
                alt, _ = pick(st_all, target, (src,), key="received_epoch")
            else:  # matched_same_state
                self.audit[series][kind] += 1
                if kind != "matched_same_state":
                    return None
                st = dict(s31, received=max(s30["received"], s31["received"]),
                          source="0B30=0B31")
                alt = st
            if (st or {}).get("file") != (alt or {}).get("file"):
                self.audit[series]["selection_differs_if_epoch_used"] += 1
            if st is None:
                return None
            self.audit[series][f"selected_{st['source']}_{st['received_origin']}"] += 1
            received_at = st["received"].isoformat(timespec="seconds")
            self.chosen[series][rid] = {"source": st["source"], "received_at": received_at,
                                        "received_origin": st["received_origin"],
                                        "total_votes": st["votes"], "announced": st["announced"]}
            return build_market(conn, race, target, start_used, received_at,
                                st["odds"], st["announced"] or None)
        return t10


# --- 指標 --------------------------------------------------------------------

def is_fresh(s: dict) -> bool:
    return s["lead_min"] <= moe.DEFAULT_MAX_LEAD_MINUTES


def ratio_stats(samples: list[dict]) -> dict:
    fresh = [s for s in samples if is_fresh(s)]
    r = sorted(s["p_offset"] / s["p_t10"] for s in fresh if s["p_t10"] > 0)
    q = (lambda p: r[min(len(r) - 1, int(p * (len(r) - 1) + 0.5))]) if r else (lambda p: None)
    return {"n": len(r), "max": r[-1] if r else None, "p95": q(0.95), "p99": q(0.99),
            "ge_1_25": sum(x >= 1.25 for x in r), "ge_1_75": sum(x >= 1.75 for x in r)}


def summarise(out: dict, samples: list[dict]) -> dict:
    p = out["primary_conditional_logit"]
    fb = out["flat_bet_edge"]
    months = Counter(str(s["date"]).replace("-", "")[:6] for s in samples if is_fresh(s))
    return {
        "coverage": {"counts": out["counts"], "all": out["sets"]["all"],
                     "fresh_le_30m": out["sets"]["fresh_t10"],
                     "fresh_horses_by_month": dict(sorted(months.items()))},
        "t10_logloss_fresh": {"market": out["t10_market_fresh_t10"]["log_loss"],
                              "offset": out["offset_fresh_t10"]["log_loss"]},
        "t10_logloss_all": {"market": out["t10_market_all"]["log_loss"],
                            "offset": out["offset_all"]["log_loss"]},
        "beta_group": {"coef_market": p["coef_market"], "coef_correction": p["coef_correction"],
                       "ci95": p["coef_correction_ci95"], "pass": p["pass"]},
        "rejection_1_price_polynomial": out["rejection_1_price_polynomial"],
        "rejection_2_stale_only_win": out["rejection_2_stale_only_win"],
        "p_offset_over_p_market": ratio_stats(samples),
        "purchase_criteria": {"edge_pt": moe.BUY_EDGE_PT, "n_bets": fb["n_bets"],
                              "testable": fb["testable"], "money_pass": out["money_pass"]},
        "verdict": out["verdict"],
    }


def conclusion_parts(s: dict) -> dict:
    v = s["verdict"]
    return {"primary_pass": v["primary"], "money": v["money"],
            "ratio_ge_1_75_zero": s["p_offset_over_p_market"]["ge_1_75"] == 0,
            "rejected_by": list(v["rejected_by"])}


def threshold_table(summaries: dict) -> dict:
    """coverage の閾値ごとに、各系列が判定対象か・結論が original_mixed と同じか。"""
    base = summaries["original_mixed"]
    base_n = base["coverage"]["fresh_le_30m"]["n_races"]
    base_parts = conclusion_parts(base)
    table = {}
    for thr in COVERAGE_THRESHOLDS:
        row = {}
        for name, s in summaries.items():
            n = s["coverage"]["fresh_le_30m"]["n_races"]
            parts = conclusion_parts(s)
            judged = n >= thr * base_n
            row[name] = {"fresh_races": n, "share": round(n / base_n, 4), "judged": judged,
                         "same_conclusion": (parts == base_parts) if judged else None,
                         "differs_in": [k for k in parts if parts[k] != base_parts[k]] if judged else None}
        table[f"{int(thr * 100)}%"] = row
    return {"base_fresh_races": base_n, "base_conclusion": base_parts, "by_threshold": table,
            "conclusion_parts": {k: conclusion_parts(s) for k, s in summaries.items()}}


def paired_delta_beta(base_rows: list[dict], rows: list[dict], races: set) -> dict:
    """同じレースを塊として再抽出した Δβ₂ (系列 − original_mixed) の 95% 区間。"""
    tagged = ([dict(s, _tag="a") for s in base_rows if s["race_id"] in races]
              + [dict(s, _tag="b") for s in rows if s["race_id"] in races])
    cols = ["z_t10", "margin"]

    def stat(draw):
        a = [s for s in draw if s["_tag"] == "a"]
        b = [s for s in draw if s["_tag"] == "b"]
        try:
            return float(conditional_logit(b, cols)[1] - conditional_logit(a, cols)[1])
        except Exception:
            return None
    point = stat(tagged)
    lo, hi = block_boot(tagged, stat, n_boot=moe.N_BOOT_PRIMARY)
    return {"delta_beta": point, "ci95": [lo, hi], "n_boot": moe.N_BOOT_PRIMARY,
            "method": "race-block bootstrap (eval_stats.block_boot, SEED 固定)"}


def common_set_comparison(per_series_samples: dict) -> dict:
    """集合の違い (coverage) と市場の値の違いを分ける: original_mixed と両方で鮮度内のレース。"""
    base_rows = [s for s in per_series_samples["original_mixed"] if is_fresh(s)]
    base_races = {s["race_id"] for s in base_rows}
    common = {}
    for name in SERIES[1:]:
        rows = [s for s in per_series_samples[name] if is_fresh(s)]
        races = base_races & {s["race_id"] for s in rows}
        if len(races) < MIN_COMMON_RACES:
            common[name] = {"n_races": len(races), "skipped": f"共通のレースが {MIN_COMMON_RACES} 未満"}
            continue
        pair = {}
        for label, src in (("original_mixed", base_rows), (name, rows)):
            sub = [s for s in src if s["race_id"] in races]
            beta = conditional_logit(sub, ["z_t10", "margin"])
            lo, hi = coefficient_ci(sub, ["z_t10", "margin"], 1, n_boot=moe.N_BOOT_PRIMARY)
            pair[label] = {"n_horses": len(sub), "beta": beta[1], "ci95": [lo, hi],
                           "logloss_market": metrics(sub, "p_t10")["log_loss"],
                           "logloss_offset": metrics(sub, "p_offset")["log_loss"],
                           "ratio": ratio_stats(sub),
                           "edge_gt_5pt": sum(s["edge"] > moe.BUY_EDGE_PT for s in sub)}
        a = defaultdict(dict)
        b = defaultdict(dict)
        for s in base_rows:
            if s["race_id"] in races:
                a[s["race_id"]][s["horse_num"]] = s["p_t10"]
        for s in rows:
            if s["race_id"] in races:
                b[s["race_id"]][s["horse_num"]] = s["p_t10"]
        differing = sorted(r for r in races if a[r].keys() != b[r].keys()
                           or any(abs(a[r][h] - b[r][h]) > 1e-12 for h in a[r]))
        by_month = Counter(r.split("-")[1][:2] for r in differing)
        common[name] = {"n_races": len(races),
                        "races_with_identical_t10_market": len(races) - len(differing),
                        "races_with_different_t10_market": len(differing),
                        "different_races_by_month": dict(sorted(by_month.items())),
                        "paired_delta_beta": paired_delta_beta(base_rows, rows, races), **pair}
    return common


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def run_series(name: str, sel: RawSelector, real_t10, prov: dict) -> tuple[dict, list[dict]]:
    if name == "original_mixed":
        def t10(conn, race, gate_minutes=None):
            m = real_t10(conn, race, gate_minutes)       # 本番そのもの。出自は別に記録
            _, info = db_market(conn, race, gate_minutes)
            if m is not None and info is not None:
                prov[m.race_id] = info
            return m
        moe.t10_market = t10
    else:
        moe.t10_market = sel.market(name)
    try:
        out = moe.run(FROM, TO, run_index=0)
    finally:
        moe.t10_market = real_t10
    return out, out.pop("_samples")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"出力先が空でない (上書きしない): {out_dir}")

    real_build, real_t10 = moe.build_dataset, moe.t10_market
    cache: dict = {}

    def cached_build(f, t):
        if (f, t) not in cache:
            cache[(f, t)] = real_build(f, t)
        return cache[(f, t)]

    conn = sqlite3.connect(f"file:{moe.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    races = [dict(r) for r in conn.execute(
        """SELECT * FROM races WHERE (race_year||race_month_day) BETWEEN ? AND ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""", (FROM, TO))]
    print(f"本番の t10_market との等価性を {len(races)} レースで確認中 ...", flush=True)
    equivalence = production_equivalence(conn, races)
    conn.close()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("raw を読み込み中 ...", flush=True)
    states, raw_info = load_raw_states()
    sel = RawSelector(states)
    results, per_series_samples = {}, {}
    db_prov: dict[str, dict] = {}
    moe.build_dataset = cached_build    # 評価期間の特徴は系列によらず同じなので 1 回だけ作る
    try:
        for name in SERIES:
            print(f"=== {name} ===", flush=True)
            out, samples = run_series(name, sel, real_t10, db_prov)
            per_series_samples[name] = samples
            results[name] = {"summary": summarise(out, samples), "full": out}
    finally:
        moe.build_dataset = real_build

    summaries = {k: v["summary"] for k, v in results.items()}
    thresholds = threshold_table(summaries)
    common = common_set_comparison(per_series_samples)

    by_class = defaultdict(list)
    for rid, p in sorted(sel.pairs.items()):
        by_class[p["class"]].append(rid)

    def brief(st):
        return None if st is None else {
            "source": st["source"], "file": st["file"], "received": st["received"].isoformat(),
            "received_origin": st["received_origin"], "announced": st["announced"],
            "votes": st["votes"], "n_horses": len(st["odds"])}
    audit = {k: {"n_races": len(v), "examples": [
        {"race_id": rid, "0B30": brief(sel.pairs[rid]["0B30"]), "0B31": brief(sel.pairs[rid]["0B31"])}
        for rid in v[:3]]} for k, v in sorted(by_class.items())}

    ref = json.loads((ROOT / REF_4B).read_text(encoding="utf-8"))
    om = results["original_mixed"]["full"]
    repro = {"ref": REF_4B, "sets_equal": ref["sets"] == om["sets"],
             "beta_ref": ref["primary_conditional_logit"]["coef_correction"],
             "beta_now": om["primary_conditional_logit"]["coef_correction"],
             "logloss_offset_ref": ref["offset_fresh_t10"]["log_loss"],
             "logloss_offset_now": om["offset_fresh_t10"]["log_loss"]}

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "Phase 0.5-4B の T−10 市場の取得元に対する感度分析 (再判定でも確認的検定でもない)",
        "window": [FROM, TO], "series": list(SERIES),
        "script": "scripts/t10_source_sensitivity.py",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "worktree_head_at_run": git("-C", str(HERE), "rev-parse", "HEAD"),
        "worktree_porcelain_at_run": git("-C", str(HERE), "status", "--porcelain"),
        "production_root": str(ROOT),
        "production_module_git_head": git("-C", str(ROOT), "rev-parse", "HEAD"),
        "production_tracked_changes_at_run": git("-C", str(ROOT), "status", "--porcelain",
                                                 "--untracked-files=no"),
        "production_module_path": {k: str(Path(m.__file__).resolve()) for k, m in PROD_MODULES.items()},
        **equivalence,
        "model": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
            "predictor/market_offset_model.txt", "predictor/market_offset_model.meta.json",
            "predictor/fundamental_model.txt", "predictor/fundamental_model.meta.json")},
        "db_snapshot": om["meta"],
        "raw_received_at_origin": (f"0B31 で {BACKFILL_LAST_DAY} 以前 = ファイル名の epoch (backfill と同じ)、"
                                   "それ以外 = ファイルの mtime 秒未満切り捨て (ライブの ingest と同じ)"),
        "raw_absent_rule": "odds > 0 の馬が 0 頭の O1 は本番で行を作らないので存在しないとみなす",
        "raw_info": raw_info,
        "raw_mixed_tie_rule": "同じ秒に両方の取得元がある場合は単勝票数合計の多い方、同数なら 0B31",
        "pit_rule": "received <= decision_time (predictor.pit_t10.decision_time、発走時刻変更の既知性込み)",
        "reading": ("coverage 閾値 40/45/50/55% の感度として読む。50% は事前固定を git で証明できない"
                    "ため判定の根拠にしない (2026-09-26 CHAT)"),
        "consumed_windows_note": ("strategy_dev 窓 (20260509〜20260831) を追加で観察した。"
                                  "config.CONSUMED_WINDOWS への反映は JST ブランチ解凍後"),
        "selection_audit_counts": {k: dict(v) for k, v in sel.audit.items()},
        "reproduction_of_4B": repro,
    }
    dump = lambda obj: json.dumps(obj, ensure_ascii=False, indent=1, default=str)  # noqa: E731
    (out_dir / "manifest.json").write_text(dump(manifest), encoding="utf-8")
    (out_dir / "series_summary.json").write_text(dump(summaries), encoding="utf-8")
    (out_dir / "series_full.json").write_text(dump({k: v["full"] for k, v in results.items()}), encoding="utf-8")
    (out_dir / "coverage_threshold_sensitivity.json").write_text(dump(thresholds), encoding="utf-8")
    (out_dir / "common_fresh_set.json").write_text(dump(common), encoding="utf-8")
    (out_dir / "selection_classes.json").write_text(dump(audit), encoding="utf-8")
    prov_cols = ["t10_source", "t10_received_at", "t10_received_origin", "t10_total_votes",
                 "t10_announced"]
    for name, rows in per_series_samples.items():
        chosen = db_prov if name == "original_mixed" else sel.chosen[name]
        with open(out_dir / f"samples_{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) + prov_cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                c = chosen.get(r["race_id"], {})
                w.writerow({**r, **{f"t10_{k}": c.get(k) for k in (
                    "source", "received_at", "received_origin", "total_votes", "announced")}})
    print(dump({"reproduction_of_4B": repro, "equivalence": equivalence,
                "thresholds": {t: {k: (v["judged"], v["same_conclusion"]) for k, v in row.items()}
                               for t, row in thresholds["by_threshold"].items()},
                "classes": {k: v["n_races"] for k, v in audit.items()},
                "common": {k: {x: v.get(x) for x in ("n_races", "races_with_different_t10_market",
                                                     "different_races_by_month", "paired_delta_beta")}
                           for k, v in common.items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
