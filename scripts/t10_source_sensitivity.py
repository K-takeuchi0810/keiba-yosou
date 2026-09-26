"""Phase 0.5-4B の結論が、T−10 市場の取得元 (0B30 / 0B31) でどれだけ動くかを測る。

**これは 4B の再判定ではなく感度分析。** 0B30 と 0B31 のどちらが正しいかは決めない
(docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md 3-bis)。モデル・閾値・評価集合の規則は 4B と
同じものを各系列にそのまま当て、**入力の T−10 市場だけ** を差し替える。

## 系列 (2026-09-26 CHAT で固定)

| 系列 | T−10 市場の出どころ |
|---|---|
| `original_mixed` | DB の odds_snapshots をそのまま (4B と同じ `predictor.pit_t10.t10_market`)。4B の再現の基準 |
| `raw_mixed` | raw の 0B30 + 0B31 から組み直した混合。DB の同じ秒の上書きの影響を除く |
| `raw_0B30` | raw の 0B30 だけ |
| `raw_0B31` | raw の 0B31 だけ (5〜6 月の backfill_0B31 の元データを含む) |
| `matched_same_state` | raw_0B30 と raw_0B31 が T−10 に選ぶ状態が **同じ市場状態** (発表時刻・単勝票数合計・全馬のオッズが一致) のレースだけ |

raw からの選択規則は `t10_market` と同じ: 決定時刻 (発走時刻変更の既知性を含む) 以前に
受信した最新の 1 枚。**受信時刻はファイル名の epoch** (backfill_odds_snapshots と同じ由来)。
raw_mixed で同じ秒に両方がある場合は、単勝票数合計の多い方 (= 後の市場状態) を採り、件数を残す。

## 事前に固定した読み方 (結果を見る前に書いた)

- 判定可能: 鮮度内 (30 分以内) のレース数が original_mixed の 50% 以上。満たさない系列は
  **判定不能** (否定にも肯定にも使わない)
- 「結論が同じ」: 主要仮説の合否・金額の判定 (合格 / 不合格 / 判定不能)・比 ≥ 1.75 が 0 頭か・
  棄却条件の該当、の 4 つがすべて一致
- same_total_discordant / different_state は評価系列に混ぜず、件数・レース数・代表例を監査として出す

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
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("KEIBA_PROD_ROOT") or HERE)
sys.path.insert(0, str(ROOT))

from jvlink_client.ingest import _split_records  # noqa: E402
from jvlink_client.parser import parse_o1  # noqa: E402
from predictor import pit_t10  # noqa: E402
from predictor.pit_t10 import T10Market, _parse_announced, decision_time, start_time_history  # noqa: E402
import scripts.market_offset_eval as moe  # noqa: E402
from predictor.eval_stats import coefficient_ci, conditional_logit, metrics  # noqa: E402

FROM, TO = "20260509", "20260831"          # 4A/4B の評価窓
NAME = re.compile(r"^(0B3[01])_(\d{16})_(\d+)\.jvd$")
SERIES = ("original_mixed", "raw_mixed", "raw_0B30", "raw_0B31", "matched_same_state")
MIN_FRESH_SHARE = 0.5
REF_4B = "data/backtest/20260919_phase05_4B_market_offset.json"


# --- raw の読み込み -----------------------------------------------------------

def load_raw_states() -> tuple[dict, dict]:
    """race_id -> [state]。state = 1 回の取得で得た O1 1 レコード。"""
    states: dict[str, list[dict]] = defaultdict(list)
    info = Counter()
    for spec in ("0B30", "0B31"):
        for p in (ROOT / "data" / "raw" / spec).iterdir():
            m = NAME.match(p.name)
            if not m:
                info[f"{spec}_name_not_matched"] += 1      # 重複名 (".jvd_....jvd") 等
                continue
            day = m.group(2)[:8]
            if not (FROM <= day <= TO):
                continue
            info[f"{spec}_files"] += 1
            epoch = int(m.group(3))
            if int(p.stat().st_mtime) != epoch:
                info[f"{spec}_mtime_differs_from_name"] += 1
            for rec in _split_records(p.read_bytes()):
                if rec[:2] != b"O1":
                    continue
                o = parse_o1(rec)
                votes = rec[927:938].decode("ascii", "replace").strip()
                rid = "-".join((o.year, o.month_day, o.track_code, o.kaiji, o.nichiji, o.race_num))
                states[rid].append({
                    "source": spec, "file": p.name,
                    "received": datetime.fromtimestamp(epoch),
                    "data_div": o.data_div, "announced": o.announced_at or "",
                    "votes": int(votes) if votes.isdigit() else None,
                    "odds": {h: od for h, od, _pop in o.win_odds},
                })
                info[f"{spec}_o1_records"] += 1
    return states, dict(info)


def same_state(a: dict, b: dict) -> bool:
    return (a["announced"] == b["announced"] and a["votes"] == b["votes"]
            and a["odds"] == b["odds"])


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


# --- 系列ごとの T−10 市場 -----------------------------------------------------

class RawSelector:
    def __init__(self, states: dict):
        self.states = states
        self.audit: dict[str, Counter] = defaultdict(Counter)
        self.pairs: dict[str, dict] = {}          # race_id -> 0B30/0B31 の選択と分類

    def _pick(self, rid: str, cutoff: datetime, sources: tuple[str, ...], series: str):
        cands = [s for s in self.states.get(rid, ())
                 if s["source"] in sources and s["received"] <= cutoff and s["odds"]]
        if not cands:
            return None
        latest = max(s["received"] for s in cands)
        top = [s for s in cands if s["received"] == latest]
        if len({s["source"] for s in top}) > 1:
            self.audit[series]["same_second_both_sources"] += 1
        # 同じ秒: 票数合計の多い方 (後の市場状態)。それでも同じなら 0B31 → 0B30 の順で固定
        top.sort(key=lambda s: (s["votes"] or -1, s["source"] == "0B31"), reverse=True)
        return top[0]

    def market(self, series: str):
        def t10(conn, race, gate_minutes=None):
            target, start_used = decision_time(conn, race, gate_minutes)
            if target is None:
                return None
            rid = "-".join(str(race.get(k)) for k in pit_t10.RACE_KEYS)
            s30 = self._pick(rid, target, ("0B30",), "raw_0B30")
            s31 = self._pick(rid, target, ("0B31",), "raw_0B31")
            kind = classify(s30, s31)
            self.pairs[rid] = {"class": kind, "0B30": s30, "0B31": s31}
            if series == "raw_mixed":
                st = self._pick(rid, target, ("0B30", "0B31"), series)
            elif series == "raw_0B30":
                st = s30
            elif series == "raw_0B31":
                st = s31
            else:  # matched_same_state
                self.audit[series][kind] += 1
                if kind != "matched_same_state":
                    return None
                st = dict(s31, received=max(s30["received"], s31["received"]))
            if st is None:
                return None
            self.audit[series][f"selected_{st['source']}"] += 1
            return build_market(conn, race, target, start_used, st)
        return t10


def build_market(conn, race, target, start_used, st) -> T10Market:
    """t10_market と同じ組み立て・同じ違反検査を raw の状態に当てる。"""
    date8 = f"{race.get('race_year', '')}{race.get('race_month_day', '')}"
    cutoff = target.isoformat(timespec="seconds")
    odds = {h.strip(): v / 10.0 for h, v in st["odds"].items() if v > 0}
    raw = {h: 1.0 / o for h, o in odds.items() if o > 0}
    mass = sum(raw.values())
    implied = {h: v / mass for h, v in raw.items()} if mass > 0 else {}
    ranked = sorted(odds, key=lambda h: odds[h])
    received_at = st["received"].isoformat(timespec="seconds")
    violations = []
    if received_at > cutoff:
        violations.append(f"受信時刻 {received_at} が決定時刻 {cutoff} より後")
    observed_dt = _parse_announced(date8, st["announced"])
    if st["announced"] and observed_dt is None:
        violations.append(f"発表時刻 {st['announced']!r} を解釈できない")
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


# --- 指標 --------------------------------------------------------------------

def ratio_stats(samples: list[dict]) -> dict:
    fresh = [s for s in samples if s["lead_min"] <= moe.DEFAULT_MAX_LEAD_MINUTES]
    r = sorted(s["p_offset"] / s["p_t10"] for s in fresh if s["p_t10"] > 0)
    q = (lambda p: r[min(len(r) - 1, int(p * (len(r) - 1) + 0.5))]) if r else (lambda p: None)
    return {"n": len(r), "max": r[-1] if r else None, "p95": q(0.95), "p99": q(0.99),
            "ge_1_25": sum(x >= 1.25 for x in r), "ge_1_75": sum(x >= 1.75 for x in r)}


def summarise(out: dict, samples: list[dict]) -> dict:
    p = out["primary_conditional_logit"]
    fb = out["flat_bet_edge"]
    months = Counter(s["date"][:7] if "-" in s["date"] else s["date"][:6]
                     for s in samples if s["lead_min"] <= moe.DEFAULT_MAX_LEAD_MINUTES)
    return {
        "coverage": {"counts": out["counts"], "all": out["sets"]["all"],
                     "fresh_le_30m": out["sets"]["fresh_t10"],
                     "fresh_horses_by_month": dict(sorted(months.items()))},
        "t10_logloss_fresh": {"market": out["t10_market_fresh_t10"]["log_loss"],
                              "offset": out["offset_fresh_t10"]["log_loss"]},
        "beta_group": {"coef_market": p["coef_market"], "coef_correction": p["coef_correction"],
                       "ci95": p["coef_correction_ci95"], "pass": p["pass"]},
        "rejection_1_price_polynomial": out["rejection_1_price_polynomial"],
        "p_offset_over_p_market": ratio_stats(samples),
        "purchase_criteria": {"edge_pt": moe.BUY_EDGE_PT, "n_bets": fb["n_bets"],
                              "testable": fb["testable"], "money_pass": out["money_pass"]},
        "verdict": out["verdict"],
    }


def conclusion_key(s: dict) -> tuple:
    v = s["verdict"]
    return (v["primary"], v["money"], s["p_offset_over_p_market"]["ge_1_75"] == 0,
            tuple(v["rejected_by"]))


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"出力先が空でない (上書きしない): {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 評価期間の特徴は系列によらず同じなので 1 回だけ作る (系列ごとの違いは市場だけ)
    real_build = moe.build_dataset
    cache: dict = {}

    def cached_build(f, t):
        if (f, t) not in cache:
            cache[(f, t)] = real_build(f, t)
        return cache[(f, t)]
    moe.build_dataset = cached_build

    print("raw を読み込み中 ...", flush=True)
    states, raw_info = load_raw_states()
    sel = RawSelector(states)
    results, per_series_samples = {}, {}
    real_t10 = moe.t10_market
    for name in SERIES:
        print(f"=== {name} ===", flush=True)
        moe.t10_market = real_t10 if name == "original_mixed" else sel.market(name)
        try:
            out = moe.run(FROM, TO, run_index=0)
        finally:
            moe.t10_market = real_t10
        samples = out.pop("_samples")
        per_series_samples[name] = samples
        results[name] = {"summary": summarise(out, samples), "full": out}

    # 補助: 集合の違い (coverage) と市場の値の違いを分ける。original_mixed と各系列の
    # **両方で鮮度内** のレースだけで、同じ指標を並べる (結果を見る前に追加を決めた)
    lead = moe.DEFAULT_MAX_LEAD_MINUTES
    base_rows = [s for s in per_series_samples["original_mixed"] if s["lead_min"] <= lead]
    base_races = {s["race_id"] for s in base_rows}
    common = {}
    for name in SERIES[1:]:
        rows = [s for s in per_series_samples[name] if s["lead_min"] <= lead]
        races = base_races & {s["race_id"] for s in rows}
        if len(races) < 30:
            common[name] = {"n_races": len(races), "skipped": "共通のレースが 30 未満"}
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
        a = {(s["race_id"], s["horse_num"]): s["p_t10"] for s in base_rows if s["race_id"] in races}
        b = {(s["race_id"], s["horse_num"]): s["p_t10"] for s in rows if s["race_id"] in races}
        same_mkt = sum(1 for r in races if all(abs(a[k] - b.get(k, -1)) < 1e-12
                                                for k in a if k[0] == r))
        common[name] = {"n_races": len(races), "races_with_identical_t10_market": same_mkt, **pair}

    base_fresh = results["original_mixed"]["summary"]["coverage"]["fresh_le_30m"]["n_races"]
    base_key = conclusion_key(results["original_mixed"]["summary"])
    for name, r in results.items():
        s = r["summary"]
        s["judgeable"] = s["coverage"]["fresh_le_30m"]["n_races"] >= MIN_FRESH_SHARE * base_fresh
        s["same_conclusion_as_original_mixed"] = (
            conclusion_key(s) == base_key if s["judgeable"] else None)

    # 0B30 と 0B31 の T−10 の選択の分類 (評価系列には混ぜない監査)
    by_class = defaultdict(list)
    for rid, p in sorted(sel.pairs.items()):
        by_class[p["class"]].append(rid)

    def brief(st):
        return None if st is None else {
            "source": st["source"], "file": st["file"], "received": st["received"].isoformat(),
            "announced": st["announced"], "votes": st["votes"], "n_horses": len(st["odds"])}
    audit = {k: {"n_races": len(v), "examples": [
        {"race_id": rid, "0B30": brief(sel.pairs[rid]["0B30"]), "0B31": brief(sel.pairs[rid]["0B31"])}
        for rid in v[:3]]} for k, v in sorted(by_class.items())}

    # 4B 成果物との照合 (original_mixed が 4B を再現するか)
    ref = json.loads((ROOT / REF_4B).read_text(encoding="utf-8"))
    om = results["original_mixed"]["full"]
    repro = {
        "ref": REF_4B,
        "sets_equal": ref["sets"] == om["sets"],
        "beta_ref": ref["primary_conditional_logit"]["coef_correction"],
        "beta_now": om["primary_conditional_logit"]["coef_correction"],
        "logloss_offset_ref": ref["offset_fresh_t10"]["log_loss"],
        "logloss_offset_now": om["offset_fresh_t10"]["log_loss"],
    }

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "Phase 0.5-4B の T−10 市場の取得元に対する感度分析 (再判定ではない)",
        "window": [FROM, TO], "series": list(SERIES),
        "script": "scripts/t10_source_sensitivity.py",
        "script_git_sha": git("-C", str(HERE), "rev-parse", "HEAD"),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "prod_root": str(ROOT), "prod_git_sha": git("-C", str(ROOT), "rev-parse", "HEAD"),
        "model": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
            "predictor/market_offset_model.txt", "predictor/market_offset_model.meta.json",
            "predictor/fundamental_model.txt", "predictor/fundamental_model.meta.json")},
        "db_snapshot": results["original_mixed"]["full"]["meta"],
        "raw_received_at_origin": "ファイル名の epoch (backfill_odds_snapshots と同じ)。mtime との食い違い件数は raw_info",
        "raw_info": raw_info,
        "raw_mixed_tie_rule": "同じ秒に両方の取得元がある場合は単勝票数合計の多い方、同数なら 0B31",
        "pit_rule": "received <= decision_time (predictor.pit_t10.decision_time、発走時刻変更の既知性込み)",
        "fixed_reading_rules": {
            "judgeable": f"鮮度内レース数 >= original_mixed の {MIN_FRESH_SHARE:.0%}",
            "same_conclusion": "主要仮説の合否 / 金額判定 / 比>=1.75 が 0 頭か / 棄却条件 の 4 つが一致"},
        "selection_audit_counts": {k: dict(v) for k, v in sel.audit.items()},
        "reproduction_of_4B": repro,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "series_summary.json").write_text(json.dumps(
        {k: v["summary"] for k, v in results.items()}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "series_full.json").write_text(json.dumps(
        {k: v["full"] for k, v in results.items()}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "common_fresh_set.json").write_text(json.dumps(
        common, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for name, rows in per_series_samples.items():
        with open(out_dir / f"samples_{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    (out_dir / "selection_classes.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"reproduction_of_4B": repro,
                      "series": {k: {"fresh_races": v["summary"]["coverage"]["fresh_le_30m"]["n_races"],
                                     "beta": v["summary"]["beta_group"]["coef_correction"],
                                     "ci": v["summary"]["beta_group"]["ci95"],
                                     "judgeable": v["summary"]["judgeable"],
                                     "same": v["summary"]["same_conclusion_as_original_mixed"]}
                                 for k, v in results.items()},
                      "classes": {k: v["n_races"] for k, v in audit.items()},
                      "common_fresh_set": common},
                     ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
