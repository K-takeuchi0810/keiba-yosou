"""本番の dry-run のレポートを、Scratch B の固定値と手順書 (RESULT_SCRATCH_B.md 確定版の 6) で照合する (読み取りのみ)。

使い方: python check_prod_dryrun.py prod_dryrun_<SHA>.json
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = {"raw_records_used": 309_865, "raw_keys": 262_113, "planned_updates": 262_113, "db_rows": 262_885,
            "null_remaining_after": 772, "nonnull_before": 0, "raw_keys_not_in_db": 0}

scratch = json.loads((HERE / "scratch_b_backfill_report.json").read_text(encoding="utf-8"))
prod = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ok = True

s_files = {f["file"]: f for f in scratch["raw_files"]}
p_files = {f["file"]: f for f in prod["raw_files"]}
missing = sorted(set(s_files) - set(p_files))
sha_diff = sorted(n for n in set(s_files) & set(p_files) if s_files[n]["sha256"] != p_files[n]["sha256"])
extra = sorted(set(p_files) - set(s_files))
print(f"(a) scratch_b files {len(s_files)} / prod files {len(p_files)} / missing {len(missing)} / sha mismatch {len(sha_diff)}")
ok &= not missing and not sha_diff and len(s_files) == 335

bad_extra = []
for n in extra:
    m = re.match(r"SE..(\d{8})(\d{14})\.jvd$", n)
    if not m or m.group(1) <= "20260630":
        bad_extra.append(n)
    print(f"(b) extra {n}  name_date={m.group(1) if m else None}  se_records={p_files[n].get('se_records')}")
print(f"(b) extra files {len(extra)} / not after 20260630: {len(bad_extra)}")
ok &= not bad_extra

for k, v in EXPECTED.items():
    hit = prod.get(k) == v
    ok &= hit
    print(f"(c) {k}: {prod.get(k)} (expected {v}) {'OK' if hit else 'MISMATCH'}")
acc = prod.get("acceptance_planned", {}).get("ok") is True
ok &= acc
print(f"(c) acceptance_planned.ok: {acc}")
print(f"result={prod.get('result')} apply={prod.get('apply')}")
ok &= prod.get("result") == "dry_run"
print("ALL_OK" if ok else "STOP: do not request approval")
sys.exit(0 if ok else 1)
