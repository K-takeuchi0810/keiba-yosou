"""Phase 0.5-5 Group A 専用: raw の RA から競走条件コード (クラス) を抜き出し、凍結した表を作る (2026-10-05)。

仕様: `docs/PHASE05_5_CLASS_EXTRACTION.md`。DB には書かない (raw の読み取りだけ)。共有の `jvlink_client/parser.py` には
足さない (ai-builder が import する経路を変えないため)。parser からはレコードの分割 (`_split_fixed`、private。名前が
変われば最初の呼び出しで AttributeError で止まる) と、レースを特定する項目の読み取り (`parse_ra`) だけを使う。

表は **JRA の全レースの超集合** (障害・中止 `data_div = 9` を含む)。Group A の利用側が平地・`data_div = 7` に絞る。

usage:
    python -m scripts.group_a_class_table probe --raw-dir DIR              # JRA 公式の期待値との突合 (36 レース)
    python -m scripts.group_a_class_table build --raw-dir DIR --out-dir DIR  # 2021-2025 の JRA の表を作って凍結する
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from jvlink_client import parser as P

MAPPING_VERSION = "class_v1"
FROM_DATE, TO_DATE = "20210101", "20251231"
JRA_TRACKS = (1, 10)               # scripts/backfill_corner_orders.py と同じ範囲 (track 01〜10)
# 仕様書「2. レース詳細」項番 28〜32 (1 起点の位置、各 3 バイト)
CODE_POSITIONS = {"c2": 623, "c3": 626, "c4": 629, "c5": 632, "cmin": 635}
# レコードがここまで無ければ止める (track_type_code の位置 706〜707 まで読むため)。raw は CRLF を除いて 1270 バイト
MIN_RECORD_BYTES = 707
# 年齢の欄で「その年齢は出走できない」ことを表す値 (コード表 2007 の 000 = 未設定)
NO_CONDITION = "000"
# canonical class (カテゴリ。数値の大小は仮定しない)。足すときは MAPPING_VERSION を上げ、docs と TARGETS の写像も直す
CANONICAL = {"701": "701", "703": "703", "005": "005", "010": "010", "016": "016", "999": "999"}
HERE = Path(__file__).resolve().parent.parent
PROBE_DIR = HERE / "data" / "backtest" / "group_a_class_20261005"
# 最若年が何歳のとき、どの欄が最若年の欄と同じ値のはずか (TARGETS.md の判定の規則)
AGE_SLOT = {2: "c2", 3: "c3", 4: "c4"}
IDENTITY = ("track_type_code", "distance")   # 同じレースで食い違えば止める項目 (条件コードに加えて)


class ClassTableError(RuntimeError):
    pass


def _code(rec: bytes, pos: int) -> str:
    return rec[pos - 1:pos + 2].decode("ascii", errors="replace")


def is_jra(track_code: str) -> bool:
    return str(track_code).isdigit() and JRA_TRACKS[0] <= int(track_code) <= JRA_TRACKS[1]


def raw_files(raw_dir: Path) -> list[Path]:
    files = sorted(Path(raw_dir).glob("RA*.jvd"))
    if not files:
        raise ClassTableError(f"RA*.jvd が無い: {raw_dir} (--raw-dir を確かめる)")
    return files


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(files: list[Path], from_date: str = FROM_DATE, to_date: str = TO_DATE,
            counts: Counter | None = None) -> dict[str, dict]:
    """{race_id: {codes..., data_divs, files}}。同じレースで条件コード・距離・コースが食い違ったら止める。

    `counts` を渡すと、読んだレコードと飛ばしたレコードの件数を理由ごとに数える (MANIFEST に残す)。
    """
    counts = counts if counts is not None else Counter()
    out: dict[str, dict] = {}
    for f in files:
        for rec in P._split_fixed(f.read_bytes(), P.RA_LENGTH):
            counts["records_read"] += 1
            if len(rec) < MIN_RECORD_BYTES:
                raise ClassTableError(f"{f.name}: 短いレコード ({len(rec)} バイト < {MIN_RECORD_BYTES})")
            if len(rec) < P.RA_LENGTH:
                rec = rec.ljust(P.RA_LENGTH, b"\x00")
            ra = P.parse_ra(rec)
            ymd = f"{ra.year}{ra.month_day}"
            if not ymd.isdigit():
                counts["skipped_non_numeric_date"] += 1
                continue
            if not (from_date <= ymd <= to_date):
                counts["skipped_out_of_range"] += 1
                continue
            if not is_jra(ra.track_code):
                counts["skipped_non_jra"] += 1
                continue
            counts["records_used"] += 1
            codes = {k: _code(rec, pos) for k, pos in CODE_POSITIONS.items()}
            ident = {"track_type_code": ra.track_type_code, "distance": ra.distance}
            rid = ra.race_id
            cur = out.get(rid)
            if cur is None:
                out[rid] = {**codes, **ident, "data_divs": {ra.data_div}, "files": {f.name}}
                continue
            new = {**codes, **ident}
            if any(cur[k] != v for k, v in new.items()):
                raise ClassTableError(f"{rid}: 条件コード / 距離 / コースが食い違う ({sorted(cur['files'])} と {f.name}): "
                                      f"{ {k: cur[k] for k in new} } vs {new}")
            cur["data_divs"].add(ra.data_div)
            cur["files"].add(f.name)
    return out


def canonical_class(cmin: str) -> str:
    if cmin not in CANONICAL:
        raise ClassTableError(f"想定外の最若年条件コード: {cmin!r} (mapping {MAPPING_VERSION})")
    return CANONICAL[cmin]


def _load_expected() -> dict[str, tuple[str, int]]:
    spec = importlib.util.spec_from_file_location("expected_class", PROBE_DIR / "expected_jra_official.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.EXPECTED


def probe(raw_dir: Path) -> dict:
    expected = _load_expected()
    days = {rid[:8] for rid in expected}
    table = extract(raw_files(raw_dir), min(days), max(days))
    rows, bad = [], 0
    for rid, (exp_class, exp_min_age) in sorted(expected.items()):
        got = table.get(rid)
        if got is None:
            rows.append({"race_id": rid, "ok": False, "reason": "raw に無い"})
            bad += 1
            continue
        slot = AGE_SLOT[exp_min_age]
        ok = got["cmin"] == exp_class and got[slot] == got["cmin"]
        bad += 0 if ok else 1
        rows.append({"race_id": rid, "ok": ok, "expected_class": exp_class, "cmin": got["cmin"],
                     "expected_min_age": exp_min_age, f"slot_{slot}": got[slot],
                     "codes": {k: got[k] for k in CODE_POSITIONS}, "files": sorted(got["files"])})
    return {"n": len(expected), "mismatch": bad, "ok": bad == 0, "rows": rows,
            "expected_sha256": sha256(PROBE_DIR / "expected_jra_official.py")}


def git_provenance() -> dict:
    """build を実行した時点の HEAD と、作業ツリーに未コミットの変更があったか (この script と parser に限らず全体)。"""
    def run(*args: str) -> str:
        return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout
    try:
        return {"git_sha": run("rev-parse", "HEAD").strip(),
                "git_dirty": bool(run("status", "--porcelain", "--", ".", ":!data/backtest/group_a_class_*").strip()),
                "parser_sha256": sha256(HERE / "jvlink_client" / "parser.py")}
    except Exception:
        return {"git_sha": "unknown", "git_dirty": None, "parser_sha256": sha256(HERE / "jvlink_client" / "parser.py")}


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


def build(raw_dir: Path, out_dir: Path, argv: list[str] | None = None) -> dict:
    files = raw_files(raw_dir)
    counts: Counter = Counter()
    table = extract(files, counts=counts)
    file_sha = {f.name: sha256(f) for f in files}
    # **全行を検証してから** 書く (想定外のコードで止まったときに半端な表を残さない)
    lines: list[list] = []
    by_year: dict[str, Counter] = {}
    by_year_div7: dict[str, Counter] = {}
    n_age_slot_diff = 0
    for rid in sorted(table):
        t = table[rid]
        cls = canonical_class(t["cmin"])
        if len({t[k] for k in ("c2", "c3", "c4", "c5") if t[k] not in (NO_CONDITION, "   ")}) > 1:
            n_age_slot_diff += 1
        src = sorted(t["files"])
        lines.append([rid, t["c2"], t["c3"], t["c4"], t["c5"], t["cmin"], cls, "".join(sorted(t["data_divs"])),
                      t["track_type_code"], t["distance"], ";".join(src), ";".join(file_sha[s] for s in src)])
        y = rid[:4]
        by_year.setdefault(y, Counter())[cls] += 1
        if "7" in t["data_divs"]:
            by_year_div7.setdefault(y, Counter())[cls] += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["race_id", "c2", "c3", "c4", "c5", "cmin", "canonical_class", "data_divs", "track_type_code",
                "distance", "source_files", "source_sha256"])
    w.writerows(lines)
    path = out_dir / "class_table.csv"
    _write_atomic(path, buf.getvalue())
    manifest = {
        "created_by": "scripts/group_a_class_table.py build", "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "argv": argv, "raw_dir": str(raw_dir), **git_provenance(),
        "script_sha256": sha256(Path(__file__)), "mapping_version": MAPPING_VERSION,
        "range": [FROM_DATE, TO_DATE], "jra_tracks": list(JRA_TRACKS), "code_positions": CODE_POSITIONS,
        "note": "表は JRA の全レースの超集合 (障害・data_div 9 を含む)。利用側が平地・data_div 7 に絞る",
        "n_races": len(table), "record_counts": dict(sorted(counts.items())),
        "counts_by_year_class": {y: dict(c) for y, c in by_year.items()},
        "counts_by_year_class_data_div_7": {y: dict(c) for y, c in by_year_div7.items()},
        "n_races_with_different_age_slot_codes": n_age_slot_diff,
        "raw_files": [{"file": f.name, "sha256": file_sha[f.name]} for f in files],
        "class_table_sha256": sha256(path),
    }
    _write_atomic(out_dir / "MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return manifest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["probe", "build"])
    ap.add_argument("--raw-dir", required=True, help="raw の RACE のディレクトリ (worktree には無いので明示する)")
    ap.add_argument("--out-dir")
    a = ap.parse_args(argv)
    if a.mode == "probe":
        rep = probe(Path(a.raw_dir))
        for r in rep["rows"]:
            print(("OK " if r["ok"] else "NG ") + json.dumps(r, ensure_ascii=False))
        print(f"probe: {rep['n'] - rep['mismatch']}/{rep['n']} 一致 (expected sha256 {rep['expected_sha256']})")
        return 0 if rep["ok"] else 1
    if not a.out_dir:
        ap.error("build には --out-dir が要る")
    m = build(Path(a.raw_dir), Path(a.out_dir), argv=argv)
    print(json.dumps({k: v for k, v in m.items() if k != "raw_files"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
