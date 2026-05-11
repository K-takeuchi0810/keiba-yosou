"""仕様書通り 1272 バイトの RA 記録から主要フィールドを抜き出して表示。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
file = ROOT / "data" / "raw" / "RACE" / "RADW2026050320260502112825.jvd"
data = file.read_bytes()
print(f"File size: {len(data)}, /1272 = {len(data) / 1272}")

# 1272 バイト固定で切る
RECORD_LEN = 1272
records = [data[i : i + RECORD_LEN] for i in range(0, len(data), RECORD_LEN)]
print(f"Records: {len(records)}")


def f(rec: bytes, pos: int, length: int) -> bytes:
    return rec[pos - 1 : pos - 1 + length]


def fs(rec: bytes, pos: int, length: int) -> str:
    raw = f(rec, pos, length)
    try:
        return raw.decode("cp932").rstrip()
    except UnicodeDecodeError:
        return raw.decode("cp932", errors="replace").rstrip()


# 何件か見てみる
for idx in (0, 5, 10, 20, 30):
    if idx >= len(records):
        break
    r = records[idx]
    print(f"\n=== record {idx} ===")
    print(f"  種別ID:        {fs(r, 1, 2)}")
    print(f"  データ区分:    {fs(r, 3, 1)}")
    print(f"  作成日:        {fs(r, 4, 8)}")
    print(f"  開催年月日:    {fs(r, 12, 4)}-{fs(r, 16, 4)}")
    print(f"  競馬場:        {fs(r, 20, 2)}")
    print(f"  回/日/R:       {fs(r, 22, 2)}/{fs(r, 24, 2)}/{fs(r, 26, 2)}")
    print(f"  曜日:          {fs(r, 28, 1)}")
    print(f"  特別競走番号:  {fs(r, 29, 4)}")
    print(f"  競走名本題:    {fs(r, 33, 60)!r}")
    print(f"  競走名略称10:  {fs(r, 573, 20)!r}")
    print(f"  グレード:      {fs(r, 615, 1)!r}")
    print(f"  競走種別:      {fs(r, 617, 2)}")
    print(f"  距離:          {fs(r, 698, 4)}m")
    print(f"  トラック:      {fs(r, 706, 2)}")
    print(f"  発走時刻:      {fs(r, 874, 4)}")
    print(f"  登録/出走:     {fs(r, 882, 2)}/{fs(r, 884, 2)}")
    print(f"  天候:          {fs(r, 888, 1)}")
    print(f"  芝/ダート馬場: {fs(r, 889, 1)}/{fs(r, 890, 1)}")
