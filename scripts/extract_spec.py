"""仕様書 PDF からテキスト抽出して docs/extracted/ に保存する開発ヘルパ。

ページ単位で .txt を出すので、grep / Read で参照しやすい。
"""

import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "extracted"
OUT.mkdir(parents=True, exist_ok=True)


def extract(pdf_path: Path) -> None:
    reader = PdfReader(str(pdf_path))
    base = pdf_path.stem
    print(f"{pdf_path.name}: {len(reader.pages)} pages")
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        out_file = OUT / f"{base}_p{i:03d}.txt"
        out_file.write_text(text, encoding="utf-8")


def main() -> None:
    for pdf in DOCS.glob("*.pdf"):
        extract(pdf)
    print(f"wrote {len(list(OUT.glob('*.txt')))} pages to {OUT}")


if __name__ == "__main__":
    main()
