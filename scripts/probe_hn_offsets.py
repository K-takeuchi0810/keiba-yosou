"""HN (繁殖馬マスタ) の産地/輸入年/持込区分のバイト位置を実 .jvd で突き止める。

2026-07-06 実 DB 検証で産地 (205-229 と仮定) が「先頭欠け + 末尾に隣接フィールド
混入」= オフセット誤りと判明。正しい位置を確定するため、生レコードの 195-250 バイト
付近を複数の候補幅で cp932 デコードして目視できるようにする。

出力を Claude に貼れば、産地フィールドの正しい開始位置・幅を特定して parse_hn を
修正できる。

usage:
    .venv32/Scripts/python.exe -m scripts.probe_hn_offsets
    .venv32/Scripts/python.exe -m scripts.probe_hn_offsets --file data/raw/BLOD/xxxx.jvd -n 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jvlink_client.parser import HN_LENGTH


def _find_blod_file(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    root = Path(__file__).resolve().parent.parent / "data" / "raw"
    for sub in ("BLOD", "blod"):
        d = root / sub
        if d.is_dir():
            files = sorted(d.glob("*.jvd"))
            if files:
                return files[0]
    # dataspec 別ディレクトリが無い場合は raw 直下から HN を含む .jvd を探す
    if root.is_dir():
        for f in sorted(root.rglob("*.jvd")):
            head = f.read_bytes()[:2]
            if head == b"HN":
                return f
    return None


def _dec(b: bytes) -> str:
    return b.decode("cp932", errors="replace").replace("　", "□")  # 全角空白を □ 可視化


def main() -> int:
    ap = argparse.ArgumentParser(description="HN 産地バイト位置 probe")
    ap.add_argument("--file", default=None)
    ap.add_argument("-n", type=int, default=6, help="表示するレコード数")
    args = ap.parse_args()

    path = _find_blod_file(args.file)
    if path is None or not path.exists():
        print("BLOD/HN の .jvd が見つかりません。--file で明示してください。")
        print("(例: data/raw/BLOD/ 配下の .jvd)")
        return 1
    print(f"file: {path}")

    data = path.read_bytes()
    # HN は 251 byte 固定 + CRLF。レコード先頭 2 byte が 'HN' のものを拾う。
    recs = []
    step = HN_LENGTH
    i = 0
    while i + HN_LENGTH <= len(data) and len(recs) < args.n:
        rec = data[i:i + HN_LENGTH]
        if rec[:2] == b"HN":
            recs.append(rec)
            i += HN_LENGTH
            # CRLF スキップ
            while i < len(data) and data[i:i + 1] in (b"\r", b"\n"):
                i += 1
        else:
            i += 1
    if not recs:
        print("HN レコードが取れませんでした (先頭 2byte が 'HN' の固定長で分割不可)。")
        return 1

    print(f"\n=== 各レコードの馬名 (41-76) と 195-250 バイト領域 (1-indexed) ===")
    print("□ = 全角空白 (パディング)。産地名の実際の開始位置と幅を目視で特定する。\n")
    for k, rec in enumerate(recs):
        name = _dec(rec[40:76]).rstrip("□ ")
        print(f"[{k}] 馬名={name}")
        # 1-indexed 195..250 を 1 バイトごとに位置付きで (全角境界を見るため 2 通り)
        seg = rec[194:250]  # 0-indexed 194 = 1-indexed 195
        print(f"    195-250 raw = {_dec(seg)}")
        # 候補: 現行 (誤) 210-229、および -2 シフト 208-227、-4 シフト 206-225
        print(f"      現行 210-229(20) = '{_dec(rec[209:229])}'")
        print(f"      候補 208-227(20) = '{_dec(rec[207:227])}'")
        print(f"      候補 206-225(20) = '{_dec(rec[205:225])}'")
        print(f"      候補 209-228(20) = '{_dec(rec[208:228])}'")
        # 数字フィールド候補 (持込区分/輸入年) の周辺
        print(f"      201-210 = '{_dec(rec[200:210])}'  (毛色203-204/性別201/品種202 の後)")
    print("\nこの出力を貼ってください。産地名が全角で正しく読める開始位置を特定し、")
    print("parse_hn の 205(持込)/206-209(輸入年)/210-229(産地) を修正します。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
