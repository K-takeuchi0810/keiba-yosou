"""Phase 0.5-5 Group A 専用: raw の RA から競走条件コード (クラス) を抜き出し、凍結した表を作る (2026-10-05)。

仕様: `docs/PHASE05_5_CLASS_EXTRACTION.md`。DB には書かない (raw の読み取りだけ)。共有の `jvlink_client/parser.py` には
足さない (ai-builder が import する経路を変えないため)。レコードの分割と、レースを特定する項目の読み取りだけ parser を使う。

usage:
    python -m scripts.group_a_class_table probe [--raw-dir DIR]     # JRA 公式の期待値との突合 (36 レース)
    python -m scripts.group_a_class_table build --out-dir DIR [--raw-dir DIR]   # 2021-2025 の JRA の表を作って凍結する
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import config
from jvlink_client import parser as P

MAPPING_VERSION = "class_v1"
FROM_DATE, TO_DATE = "20210101", "20251231"
JRA_TRACKS = (1, 10)
# 仕様書「2. レース詳細」項番 28〜32 (1 起点の位置、各 3 バイト)
CODE_POSITIONS = {"c2": 623, "c3": 626, "c4": 629, "c5": 632, "cmin": 635}
# canonical class (カテゴリ。数値の大小は仮定しない)
CANONICAL = {"701": "701", "703": "703", "005": "005", "010": "010", "016": "016", "999": "999"}
HERE = Path(__file__).resolve().parent.parent
PROBE_DIR = HERE / "data" / "backtest" / "group_a_class_20261005"
# 最若年が何歳のとき、どの欄が最若年の欄と同じ値のはずか (TARGETS.md の判定の規則)
AGE_SLOT = {2: "c2", 3: "c3", 4: "c4"}


class ClassTableError(RuntimeError):
    pass


def _code(rec: bytes, pos: int) -> str:
    return rec[pos - 1:pos + 2].decode("ascii", errors="replace")


def race_id(ra) -> str:
    return f"{ra.year}{ra.month_day}_{ra.track_code}_{ra.kaiji}_{ra.nichiji}_{ra.race_num}"


def is_jra(track_code: str) -> bool:
    return str(track_code).isdigit() and JRA_TRACKS[0] <= int(track_code) <= JRA_TRACKS[1]


def raw_files(raw_dir: Path) -> list[Path]:
    return sorted(Path(raw_dir).glob("RA*.jvd"))


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(files: list[Path], from_date: str = FROM_DATE, to_date: str = TO_DATE) -> dict[str, dict]:
    """{race_id: {codes..., data_divs, files}}。同じレースで条件コードが食い違ったら止める。"""
    out: dict[str, dict] = {}
    for f in files:
        for rec in P._split_fixed(f.read_bytes(), P.RA_LENGTH):
            if len(rec) < P.RA_LENGTH:
                rec = rec.ljust(P.RA_LENGTH, b"\x00")
            ra = P.parse_ra(rec)
            ymd = f"{ra.year}{ra.month_day}"
            if not ymd.isdigit() or not (from_date <= ymd <= to_date) or not is_jra(ra.track_code):
                continue
            codes = {k: _code(rec, pos) for k, pos in CODE_POSITIONS.items()}
            rid = race_id(ra)
            cur = out.get(rid)
            if cur is None:
                out[rid] = {**codes, "data_divs": {ra.data_div}, "files": {f.name},
                            "track_type_code": ra.track_type_code, "distance": ra.distance}
                continue
            if any(cur[k] != v for k, v in codes.items()):
                raise ClassTableError(f"{rid}: 条件コードが食い違う ({cur['files']} と {f.name}): "
                                      f"{ {k: cur[k] for k in codes} } vs {codes}")
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
        ok_class = got["cmin"] == exp_class
        ok_slot = got[slot] == got["cmin"]
        ok = ok_class and ok_slot
        bad += 0 if ok else 1
        rows.append({"race_id": rid, "ok": ok, "expected_class": exp_class, "cmin": got["cmin"],
                     "expected_min_age": exp_min_age, f"slot_{slot}": got[slot],
                     "codes": {k: got[k] for k in CODE_POSITIONS}, "files": sorted(got["files"])})
    return {"n": len(expected), "mismatch": bad, "ok": bad == 0, "rows": rows,
            "expected_sha256": sha256(PROBE_DIR / "expected_jra_official.py")}


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "-C", str(HERE), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def build(raw_dir: Path, out_dir: Path) -> dict:
    files = raw_files(raw_dir)
    table = extract(files)
    out_dir.mkdir(parents=True, exist_ok=True)
    file_sha = {f.name: sha256(f) for f in files}
    path = out_dir / "class_table.csv"
    n_age_slot_diff = 0
    counts: dict[str, dict[str, int]] = {}
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["race_id", "c2", "c3", "c4", "c5", "cmin", "canonical_class", "data_divs", "track_type_code",
                    "distance", "source_files", "source_sha256"])
        for rid in sorted(table):
            t = table[rid]
            cls = canonical_class(t["cmin"])
            nonzero = {t[k] for k in ("c2", "c3", "c4", "c5") if t[k] not in ("000", "   ")}
            if len(nonzero) > 1:
                n_age_slot_diff += 1
            src = sorted(t["files"])
            w.writerow([rid, t["c2"], t["c3"], t["c4"], t["c5"], t["cmin"], cls, "".join(sorted(t["data_divs"])),
                        t["track_type_code"], t["distance"], ";".join(src), ";".join(file_sha[s] for s in src)])
            y = rid[:4]
            counts.setdefault(y, {}).setdefault(cls, 0)
            counts[y][cls] += 1
    manifest = {
        "created_by": "scripts/group_a_class_table.py build", "git_sha": _git_sha(),
        "script_sha256": sha256(Path(__file__)), "mapping_version": MAPPING_VERSION,
        "range": [FROM_DATE, TO_DATE], "jra_tracks": list(JRA_TRACKS), "code_positions": CODE_POSITIONS,
        "n_races": len(table), "counts_by_year_class": counts,
        "n_races_with_different_age_slot_codes": n_age_slot_diff,
        "raw_files": [{"file": f.name, "sha256": file_sha[f.name]} for f in files],
        "class_table_sha256": sha256(path),
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["probe", "build"])
    ap.add_argument("--raw-dir", default=str(Path(config.PROJECT_ROOT) / "data" / "raw" / "RACE"))
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
    m = build(Path(a.raw_dir), Path(a.out_dir))
    print(json.dumps({k: v for k, v in m.items() if k != "raw_files"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
