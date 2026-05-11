"""RAMM ファイルが何のレコードを含むか調べる。"""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
files = sorted((ROOT / "data" / "raw" / "RACE").glob("RAMM*.jvd"))
if not files:
    print("RAMM file not found")
    sys.exit(1)

f = files[0]
data = f.read_bytes()
print(f"file: {f.name} size: {len(data)}")

# CRLF で区切ってレコード ID を抽出
records = [r for r in data.split(b"\r\n") if r]
ids = Counter(r[:2].decode("latin-1", errors="replace") for r in records)
lengths = Counter(len(r) + 2 for r in records)
print(f"records: {len(records)}")
print(f"record IDs: {ids.most_common()}")
print(f"record lengths (incl CRLF): {lengths.most_common(10)}")

# 最初の数レコードのバイト先頭を表示
for i, r in enumerate(records[:3]):
    print(f"\nrec {i}: id={r[:2].decode('latin-1', errors='replace')!r} len={len(r) + 2}")
    print(f"  hex: {r[:80].hex()}")
