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

from jvlink_client.ingest import _split_records
from jvlink_client.parser import HN_LENGTH


def _blod_dirs(root: Path) -> list[Path]:
    return [root / sub for sub in ("BLOD", "blod") if (root / sub).is_dir()]


def _has_hn(path: Path) -> bool:
    """.jvd に HN レコードが 1 件でも含まれるか (CRLF 分割で厳密判定)。"""
    try:
        return any(r[:2] == b"HN" for r in _split_records(path.read_bytes()))
    except Exception:  # noqa: BLE001 — 壊れたファイルは skip
        return False


def _inventory(root: Path) -> dict[str, int]:
    """BLOD 配下 .jvd をレコード種別 (ファイル名先頭2文字) 別に件数集計して可視化する。
    HN(繁殖馬) ファイルが 0 なら BLOD 取得で HN が来ていない = breeding_horses を埋められない。"""
    counts: dict[str, int] = {}
    for d in _blod_dirs(root):
        for f in sorted(d.glob("*.jvd")):
            prefix = f.name[:2].upper()
            counts[prefix] = counts.get(prefix, 0) + 1
    return counts


def _find_blod_file(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    root = Path(__file__).resolve().parent.parent / "data" / "raw"
    # 1) BLOD 配下でファイル名が HN* のもの (JV-Link はレコード種別でファイル名を付ける)
    for d in _blod_dirs(root):
        for f in sorted(d.glob("*.jvd")):
            if f.name[:2].upper() == "HN":
                return f
    # 2) 名前が BT/SK でも中身に HN レコードを含む .jvd を内容走査で探す
    for d in _blod_dirs(root):
        for f in sorted(d.glob("*.jvd")):
            if _has_hn(f):
                return f
    # 3) dataspec 別ディレクトリが無い場合は raw 直下を内容走査
    if root.is_dir():
        for f in sorted(root.rglob("*.jvd")):
            if _has_hn(f):
                return f
    return None


def _dec(b: bytes) -> str:
    return b.decode("cp932", errors="replace").replace("　", "□")  # 全角空白を □ 可視化


def main() -> int:
    ap = argparse.ArgumentParser(description="HN 産地バイト位置 probe")
    ap.add_argument("--file", default=None)
    ap.add_argument("-n", type=int, default=6, help="表示するレコード数")
    args = ap.parse_args()

    # まず BLOD 配下のレコード種別インベントリを出す (HN が来ているかの切り分け)。
    root = Path(__file__).resolve().parent.parent / "data" / "raw"
    inv = _inventory(root)
    if inv:
        print("=== data/raw/BLOD のファイル種別 (先頭2文字=レコード種別) ===")
        for k, v in sorted(inv.items()):
            tag = {"BT": "系統", "HN": "繁殖馬", "SK": "産駒"}.get(k, "?")
            print(f"  {k} ({tag}): {v} ファイル")
        if inv.get("HN", 0) == 0:
            print()
            print("⚠ HN(繁殖馬) ファイルが 0 です。BLOD を取得しても HN が来ていません。")
            print("  breeding_horses は HN からしか埋まらないため、これが traversal_hit=0 の主因です。")
            print("  対処: JVOpen の BLOD 取得で HN が含まれるか確認し、")
            print("        `python -m scripts.bootstrap --dataspecs BLOD` を実行して HN を取得してください。")
            print("        (JRA-VAN のデータ種別設定で『繁殖馬』が有効か、フルデータ契約かも確認)")
        print()

    path = _find_blod_file(args.file)
    if path is None or not path.exists():
        print("HN レコードを含む .jvd が見つかりません。--file で明示してください。")
        print("(例: data/raw/BLOD/HNxxxx.jvd)")
        return 1
    print(f"file: {path}")

    data = path.read_bytes()
    # BLOD の .jvd は BT/HN/SK 等が CRLF 区切りで混在するため、ingest と同じ
    # _split_records (CRLF 分割 + 先頭 NUL 除去) で分割し、'HN' レコードだけ拾う。
    recs = [r for r in _split_records(data) if r[:2] == b"HN"][:args.n]
    if not recs:
        print("HN レコードが見つかりませんでした。別の BLOD .jvd を --file で指定してください。")
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
        # 繁殖番号 (sire/dam) も同方向シフトの疑い — 数字同士で無音誤りするため併記
        # (2026-07-06 data-pipeline MED-1)。10 桁数字が綺麗に出る位置が正。
        print(f"      父繁殖 現行230-239 = '{_dec(rec[229:239])}' / 候補228-237 = '{_dec(rec[227:237])}'")
        print(f"      母繁殖 現行240-249 = '{_dec(rec[239:249])}' / 候補238-247 = '{_dec(rec[237:247])}'")
    print("\nこの出力を貼ってください。産地名が全角で正しく読める開始位置を特定し、")
    print("parse_hn の 205(持込)/206-209(輸入年)/210-229(産地) を修正します。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
