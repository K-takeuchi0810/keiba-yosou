"""Copy retained iCloud prediction snapshots into the repository archive.

Dry-run is the default. Pass ``--execute`` to copy; source files are never removed.
Files with a SHA-256 already present under the same date are skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from config import PROJECT_ROOT


SNAPSHOT_RE = re.compile(r"^index_(\d{8})_\d{6}_\d{6}\.html$")
DEFAULT_SOURCE = Path.home() / "iCloudDrive" / "競馬予想" / "snapshots"
DEFAULT_RESULTS = PROJECT_ROOT / "data" / "results"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_snapshots(
    source_dir: Path, results_root: Path, *, execute: bool = False
) -> dict:
    copied: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    planned: Counter[str] = Counter()

    for source in sorted(source_dir.glob("index_*.html")):
        match = SNAPSHOT_RE.match(source.name)
        if not match or not source.is_file():
            continue
        raw_date = match.group(1)
        date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        date_dir = results_root / date
        archive_dir = date_dir / "archive"
        source_hash = sha256_of(source)
        existing = next(
            (
                candidate for candidate in date_dir.rglob("*.html")
                if candidate.is_file() and sha256_of(candidate) == source_hash
            ),
            None,
        ) if date_dir.exists() else None
        if existing:
            skipped[date] += 1
            print(f"SKIP {source.name}: duplicate of {existing}")
            continue

        destination = archive_dir / source.name
        if destination.exists():
            destination = archive_dir / f"{source.stem}_{source_hash[:8]}.html"
        planned[date] += 1
        if execute:
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied[date] += 1
            print(f"COPY {source} -> {destination}")
        else:
            print(f"DRY-RUN {source} -> {destination}")

    return {
        "planned": dict(planned),
        "copied": dict(copied),
        "skipped": dict(skipped),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.source.exists():
        print(f"snapshot directory not found: {args.source}", file=sys.stderr)
        return 1
    summary = archive_snapshots(
        args.source.resolve(), args.results_root.resolve(), execute=args.execute
    )
    print(f"summary: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
