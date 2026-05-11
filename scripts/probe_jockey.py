"""SE レコードのジョッキーコード/名前まわりの bytes を確認する。"""

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
files = sorted((ROOT / "data" / "raw" / "RACE").glob("SEDW*.jvd"))
if not files:
    print("no SEDW files")
    sys.exit(1)
data = files[-1].read_bytes()
print(f"file: {files[-1].name}, size: {len(data)}, /555 = {len(data) / 555}")

# CRLF で分割した場合の record 長分布
records_by_crlf = [r for r in data.split(b"\r\n") if r]
from collections import Counter
print(f"records by CRLF: {len(records_by_crlf)}")
print(f"length distribution: {Counter(len(r) + 2 for r in records_by_crlf).most_common(5)}")

rec = data[:555]
print(f"record 0 length: 555")

print()
print("=== offsets 0-50 (header + race id + horse fields start) ===")
print(f"hex:    {rec[0:50].hex()}")
print(f"decode: {rec[0:50].decode('cp932', errors='replace')!r}")
print()
print("=== offsets 250-310 (around horse weight + jockey) ===")
print(f"hex:    {rec[250:310].hex()}")
print(f"decode: {rec[250:310].decode('cp932', errors='replace')!r}")
print()
print("=== offsets 285-340 (around jockey fields) ===")
print(f"hex:    {rec[285:340].hex()}")
print(f"decode: {rec[285:340].decode('cp932', errors='replace')!r}")
print()
# Spec (1-indexed): 28=ブリンカー(295,1), 29=予備(296,1), 30=jockey_code(297,5),
# 31=変更前jockey_code(302,5), 32=jockey_short_name(307,8)
# Convert to 0-indexed: 294, 295, 296, 301, 306
print(f"ブリンカー[295,1] (0-idx 294): {rec[294:295]!r}")
print(f"予備[296,1] (0-idx 295): {rec[295:296]!r}")
print(f"jockey_code[297,5] (0-idx 296-300): {rec[296:301]!r} = {rec[296:301].decode('cp932', errors='replace')!r}")
print(f"prev_jockey_code[302,5] (0-idx 301-305): {rec[301:306]!r}")
print(f"jockey_short_name[307,8] (0-idx 306-313): {rec[306:314]!r} -> {rec[306:314].decode('cp932', errors='replace')!r}")
