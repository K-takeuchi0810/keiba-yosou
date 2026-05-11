"""JVRead の戻り値タプル各要素を検査して、buf と filename の位置を特定する一回限りの調査スクリプト。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import win32com.client

jv = win32com.client.Dispatch("JVDTLab.JVLink.1")
jv.JVInit("UNKNOWN")
jv.JVOpen("RACE", "20260501000000", 4, 0, 0, "")

for i in range(3):
    r = jv.JVRead("", 110000, "")
    print(f"--- read {i} ---")
    print(f"len={len(r)} rc={r[0]}")
    for j, v in enumerate(r):
        if isinstance(v, str):
            ascii_only = v[:60].encode("ascii", errors="replace")
            print(f"  [{j}] str len={len(v)} preview={ascii_only!r}")
        else:
            print(f"  [{j}] {type(v).__name__}={v!r}")

jv.JVClose()
