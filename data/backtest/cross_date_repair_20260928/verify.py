"""再生成した 10 日を、builder のコードを使わずに独立に確かめる (読み取りのみ)。

HTML の race ID → 日付の分類 → DB の当日のレース集合 → 出力 CSV の race ID を突き合わせる。
旧成果物がある 7/18・8/08・8/15 は旧/新の差分も出す。
"""
import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROD = Path(r"C:\Users\kizun\dev\keiba-yosou")
OUT = Path(__file__).resolve().parent / "out"
LOG = json.loads((Path(__file__).resolve().parent / "regen_log.json").read_text(encoding="utf-8"))
DB = f"file:{(PROD / 'data' / 'keiba.db').as_posix()}?mode=ro"
RACE_DAYS = ["2026-07-18", "2026-08-08", "2026-08-15", "2026-08-22", "2026-08-29", "2026-09-05", "2026-09-12"]
NO_TARGET = ["2026-06-12", "2026-06-17", "2026-07-03"]
OLD = ["2026-07-18", "2026-08-08", "2026-08-15"]
BLOCK = re.compile(r'<details[^>]*\bid="race-(\d{8})-(\d{2})-(\d{1,2})"[^>]*>(.*?)</details>', re.S)
MARK = re.compile(r'<td class="mark-cell"[^>]*>(.*?)</td>', re.S)
HNUM = re.compile(r'<td class="horse-num[^"]*"[^>]*>\s*(\d+)\s*</td>')


def read_csv(p: Path):
    if not p.exists():
        return None
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def html_races(path: Path):
    text = path.read_text(encoding="utf-8")
    races = []
    for m in BLOCK.finditer(text):
        body = m.group(4).split("<tbody", 1)[1] if "<tbody" in m.group(4) else ""
        body = body.split("</tbody>", 1)[0]
        marks = [re.sub(r"<[^>]+>", "", x).strip() for x in MARK.findall(body)]
        nums = HNUM.findall(body)
        races.append({"date": m.group(1), "track": m.group(2), "rn": int(m.group(3)),
                      "id": f"{m.group(1)}-{m.group(2)}-{int(m.group(3)):02d}",
                      "horses": len(nums), "honmei": marks.count("◎")})
    return races


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def check_day(d: str, conn) -> dict:
    target = d.replace("-", "")
    run = next(r for r in LOG["runs"] if r["date"] == d)
    out = OUT / d
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    c = man["counts"]
    hp = Path(run["html"])
    races = html_races(hp if hp.is_absolute() else PROD / hp)
    tgt = [r for r in races if r["date"] == target]
    frn = [r for r in races if r["date"] != target]
    res = {"date": d, "html": Path(run["html"]).name, "rc": run["rc"], "fail": []}

    def need(cond, msg):
        if not cond:
            res["fail"].append(msg)

    # HTML → manifest
    need(c["html_races_parsed"] == len(races), f"html_races_parsed {c['html_races_parsed']} != {len(races)}")
    need(c["foreign_date_races_dropped"] == len(frn), f"foreign races {c['foreign_date_races_dropped']} != {len(frn)}")
    need(c["foreign_date_predictions_dropped"] == sum(r["horses"] for r in frn),
         f"foreign horses {c['foreign_date_predictions_dropped']} != {sum(r['horses'] for r in frn)}")
    need(sorted(c["foreign_date_race_ids"]) == sorted(r["id"] for r in frn), "foreign_date_race_ids が HTML と違う")
    need(c["predictions"] == sum(r["horses"] for r in tgt), f"predictions {c['predictions']} != target horses {sum(r['horses'] for r in tgt)}")
    need(all(r["honmei"] <= 1 for r in tgt), "HTML の対象日レースに ◎ が 2 頭以上")

    # 出力 CSV の race ID はすべて対象日
    files = {}
    for name in ("predictions", "evaluation_summary", "final_odds", "race_results", "payouts"):
        rows = read_csv(out / f"{name}.csv")
        files[name] = rows
        bad = [r["race_id"] for r in rows if not r["race_id"].startswith(target)]
        need(not bad, f"{name}.csv に対象日以外の race_id: {bad[:3]}")
    preds, summ = files["predictions"], files["evaluation_summary"]
    need(len(preds) == c["predictions"], "predictions.csv の行数と manifest が違う")
    per_race = Counter(r["race_id"] for r in preds if r["mark"] == "◎")
    need(all(v <= 1 for v in per_race.values()), "predictions.csv に ◎ が 2 頭以上のレース")

    # DB の当日のレース集合 (JRA) と HTML の対象日レース集合
    db_races = {f"{target}-{t}-{int(rn):02d}" for t, rn in conn.execute(
        "SELECT track_code, race_num FROM races WHERE race_year=? AND race_month_day=? "
        "AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10", (target[:4], target[4:]))}
    html_tgt = {r["id"] for r in tgt}
    res["db_jra_races"] = len(db_races)
    res["html_target_races"] = len(html_tgt)
    res["html_target_races_with_horses"] = sum(1 for r in tgt if r["horses"])
    need(html_tgt <= db_races or not html_tgt, f"HTML の対象日レースが DB に無い: {sorted(html_tgt - db_races)[:3]}")
    handled = {r["race_id"] for r in summ}
    no_horse = {r["id"] for r in tgt if not r["horses"]}
    need(len(html_tgt) == len(handled) + len(no_horse),
         f"HTML 対象日レース {len(html_tgt)} != 扱ったレース {len(handled)} + 馬の行が無いレース {len(no_horse)}")

    # manifest の評価の合計
    need(c["evaluation_rows_total"] == len(summ), "evaluation_rows_total と summary の行数が違う")
    need(c["evaluation_rows_total"] == c["evaluation_rows_evaluable"] + c["evaluation_rows_excluded"], "total != evaluable + excluded")
    need(sum(c["evaluation_exclusion_reasons"].values()) == c["evaluation_rows_excluded"], "除外理由の合計が excluded と違う")
    need(sum(1 for r in summ if r["evaluable"] in ("True", "true", "1")) == c["evaluation_rows_evaluable"], "evaluable の行数が違う")

    # 金額の不変量
    for r in summ:
        ev = r["evaluable"] in ("True", "true", "1")
        refunded = r["horse_refunded"] in ("True", "true", "1")
        planned, settled, profit = num(r["planned_stake_yen_100unit"]), num(r["settled_stake_yen_100unit"]), num(r["profit_loss_yen_100unit"])
        bet = r["bet_candidate"] in ("True", "true", "1")
        if not bet:
            need(planned == 0, f"{r['race_id']} {r['horse_num']}: 買い候補でないのに planned {planned}")
        if (not ev) or refunded:
            need(settled == 0 and profit == 0, f"{r['race_id']} {r['horse_num']}: 評価外/返還なのに settled {settled} profit {profit}")
        need(settled <= planned, f"{r['race_id']} {r['horse_num']}: settled > planned")

    honmei = [r for r in summ if r["mark"] == "◎"]
    honmei_ev = [r for r in honmei if r["evaluable"] in ("True", "true", "1")]
    hits = [r for r in honmei_ev if str(r["confirmed_order"]).strip() in ("1", "1.0")]
    res.update({
        "counts": {k: (len(v) if isinstance(v, list) else v) for k, v in c.items()},
        "rows": {k: len(v) for k, v in files.items()},
        "honmei_rows": len(honmei), "honmei_evaluable_N": len(honmei_ev), "honmei_hits": len(hits),
        "honmei_hit_rate": (len(hits) / len(honmei_ev)) if honmei_ev else None,
        "planned_stake": sum(num(r["planned_stake_yen_100unit"]) for r in summ),
        "settled_stake": sum(num(r["settled_stake_yen_100unit"]) for r in summ),
        "profit": sum(num(r["profit_loss_yen_100unit"]) for r in summ),
        "refunded_rows": sum(1 for r in summ if r["horse_refunded"] in ("True", "true", "1")),
        "builder_git_sha": man["builder_git_sha"], "builder_git_dirty": man["builder_git_dirty"],
        "source_html_sha256": man["source_html_sha256"],
    })
    return res


def old_metrics(d: str) -> dict:
    base = PROD / "data" / "results" / d
    summ = read_csv(base / "evaluation_summary.csv")
    preds = read_csv(base / "predictions.csv")
    man = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    honmei = [r for r in summ if r["mark"] == "◎"]
    # 旧 builder には evaluable 列が無い。◎ で着順が付いた行を「評価可」とみなす (定義を記録)
    ev = [r for r in honmei if str(r.get("confirmed_order") or "").strip() not in ("", "0")]
    hits = [r for r in ev if str(r["confirmed_order"]).strip() in ("1", "1.0")]
    per_race = Counter(r["race_id"] for r in honmei)
    return {"rows_summary": len(summ), "rows_predictions": len(preds), "honmei_rows": len(honmei),
            "honmei_evaluable_N_old_def": len(ev), "honmei_hits": len(hits),
            "honmei_hit_rate": (len(hits) / len(ev)) if ev else None,
            "races_with_2plus_honmei": sum(1 for v in per_race.values() if v > 1),
            "profit_old": sum(num(r["profit_loss_yen_100unit"]) for r in summ),
            "bet_candidates_old": sum(1 for r in summ if r["bet_candidate"] in ("True", "true", "1")),
            "manifest_builder": man["builder_git_sha"][:7]}


def main():
    conn = sqlite3.connect(DB, uri=True)
    report = {"regen": {k: v for k, v in LOG.items() if k != "runs"}, "days": {}, "old_vs_new": {}}
    all_ok = True
    for d in RACE_DAYS + NO_TARGET:
        r = check_day(d, conn)
        if d in NO_TARGET:
            c = r["counts"]
            nt = {"target_date_html_races": r["html_target_races"],
                  "all_html_races_foreign": c["foreign_date_races_dropped"] == c["html_races_parsed"] > 0,
                  "predictions": c["predictions"], "evaluable_N": c["evaluation_rows_evaluable"],
                  "settled_stake": r["settled_stake"], "profit": r["profit"],
                  "db_derived_rows": {k: r["rows"][k] for k in ("final_odds", "race_results", "payouts")}}
            for k, ok in (("target_date_html_races==0", nt["target_date_html_races"] == 0),
                          ("all_html_races_foreign", nt["all_html_races_foreign"]),
                          ("predictions==0", nt["predictions"] == 0), ("evaluable_N==0", nt["evaluable_N"] == 0),
                          ("stake_profit==0", nt["settled_stake"] == 0 and nt["profit"] == 0)):
                if not ok:
                    r["fail"].append(f"NO_TARGET 条件が不成立: {k}")
            r["no_target_date"] = nt
        report["days"][d] = r
        all_ok &= not r["fail"]
        print(d, "OK" if not r["fail"] else f"FAIL {r['fail'][:3]}", flush=True)
    for d in OLD:
        o, n = old_metrics(d), report["days"][d]
        report["old_vs_new"][d] = {
            "old": o,
            "new": {k: n[k] for k in ("honmei_rows", "honmei_evaluable_N", "honmei_hits", "honmei_hit_rate",
                                      "planned_stake", "settled_stake", "profit", "refunded_rows")}
                   | {"rows_summary": n["rows"]["evaluation_summary"], "rows_predictions": n["rows"]["predictions"],
                      "dropped_races": n["counts"]["foreign_date_races_dropped"],
                      "dropped_horses": n["counts"]["foreign_date_predictions_dropped"]},
        }
    report["all_ok"] = all_ok
    (Path(__file__).resolve().parent / "verify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("all_ok", all_ok)


if __name__ == "__main__":
    main()
