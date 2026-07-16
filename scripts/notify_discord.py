"""Best-effort Discord webhook notification shared by scheduled jobs."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from config import PROJECT_ROOT


WEBHOOK_FILE = PROJECT_ROOT / "data" / "discord_webhook.txt"


def _post_webhook(url: str, text: str) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps({"content": text}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "keiba-yosou-bot/1.0",
        },
        method="POST",
    )
    urllib.request.urlopen(request, timeout=15).read()


def notify_discord(text: str, webhook_file: Path = WEBHOOK_FILE) -> bool:
    """Send one message without allowing notification failure to stop the job."""
    try:
        url = webhook_file.read_text(encoding="utf-8").strip()
        if not url:
            raise ValueError("webhook is empty")
        _post_webhook(url, text)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"WARN: Discord notification failed: {exc}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    notify_discord(args.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
