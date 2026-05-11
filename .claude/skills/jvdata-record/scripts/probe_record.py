"""raw ファイルの先頭バイトを観察してレコード種別とレコード長を推定する。

新しいレコード種別のパーサを追加する前に、実物のバイト列が想定と合うかを
確認するためのヘルパ。

Usage:
    python -m .claude.skills.jvdata-record.scripts.probe_record <path>
    python scripts/probe_record.py <path>

出力:
    - ファイルサイズ
    - 先頭 64 バイトの hex / ascii / sjis 表示
    - CRLF を含むか
    - 先頭 2 バイト (= レコード種別 ID 候補)
    - CRLF 分割後の 1 レコード目の長さ (= レコード長候補)
"""

from __future__ import annotations

import sys
from pathlib import Path


def hex_dump(data: bytes, width: int = 16) -> str:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        try:
            asciipart = chunk.decode("ascii", errors="replace")
        except Exception:
            asciipart = ""
        asciipart = "".join(c if 0x20 <= ord(c) < 0x7F else "." for c in asciipart)
        lines.append(f"{i:04x}  {hexpart:<{width * 3}}  {asciipart}")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: probe_record.py <path-to-jvd-file>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    data = path.read_bytes()
    size = len(data)

    print(f"file:  {path}")
    print(f"size:  {size:,} bytes")
    print()

    if size == 0:
        print("(empty file)")
        return 0

    print("--- head 64 bytes (hex) ---")
    print(hex_dump(data[:64]))
    print()

    # レコード種別 ID 候補
    head_id = data[:2].decode("ascii", errors="replace")
    print(f"record_type (head 2 bytes): {head_id!r}")

    # CRLF 分割
    has_crlf = b"\r\n" in data
    print(f"contains CRLF: {has_crlf}")
    if has_crlf:
        parts = [r for r in data.split(b"\r\n") if r]
        print(f"crlf-split records: {len(parts)}")
        if parts:
            r0 = parts[0]
            print(f"first record length: {len(r0)} bytes (= candidate RECORD_LENGTH)")
            print(f"first record id:    {r0[:2].decode('ascii', errors='replace')!r}")
            # サンプル: 2 番目以降のレコードと長さが揃っているか
            lengths = sorted({len(r) for r in parts[:200]})
            print(f"length distribution (first 200 recs): {lengths}")
    else:
        # CRLF が無いなら全体が 1 レコードか、改行抜きで連結されているか
        print("no CRLF separator. either single-record file or concatenated records.")

    # SJIS 試読
    try:
        head_text = data[:128].decode("cp932", errors="replace")
        print()
        print("--- head 128 bytes as cp932 ---")
        print(repr(head_text))
    except Exception as e:
        print(f"cp932 decode failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
