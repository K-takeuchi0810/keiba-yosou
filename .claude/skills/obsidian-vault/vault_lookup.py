"""Obsidian 保管庫 (競馬) をノート本文を開かずに引く。

使い方:
  python .claude/skills/obsidian-vault/vault_lookup.py 通過順位 脚質   # 名前・タグ・要点に全語を含むノートの要点
  python .claude/skills/obsidian-vault/vault_lookup.py --body leg_code  # 本文も探し、該当行を 3 行まで添える
  python .claude/skills/obsidian-vault/vault_lookup.py --status 撤回     # 状態で絞る (確定/暫定/撤回/進行中)
  python .claude/skills/obsidian-vault/vault_lookup.py --list           # フォルダごとのノート名だけ

保管庫の場所は環境変数 KEIBA_VAULT で上書きできる。
"""
import argparse
import os
import pathlib
import re
import sys

VAULT = pathlib.Path(
    os.environ.get("KEIBA_VAULT", r"C:\Users\kizun\Documents\Obsidian Vault\競馬")
)


def parse(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, body = "", text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            meta, body = parts[1], parts[2]
    field = lambda k: (re.search(rf"^{k}:\s*(.+)$", meta, re.M) or [None, ""])[1].strip()
    summary = []
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if "[!summary]" in line:
            for nxt in lines[i + 1:]:
                if not nxt.startswith(">"):
                    break
                summary.append(nxt.lstrip("> ").strip())
            break
    return {
        "name": path.stem,
        "folder": path.parent.name,
        "tags": field("tags"),
        "state": field("状態"),
        "date": field("日付"),
        "summary": " ".join(s for s in summary if s),
        "body": body,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("words", nargs="*", help="すべてを含むノートを返す (大文字小文字は区別しない)")
    ap.add_argument("--body", action="store_true", help="本文も検索し、該当行を添える")
    ap.add_argument("--status", help="状態で絞る")
    ap.add_argument("--list", action="store_true", help="ノート名の一覧だけ")
    ap.add_argument("--max", type=int, default=15, help="最大件数 (既定 15)")
    args = ap.parse_args()

    if not VAULT.is_dir():
        print(f"保管庫が見つからない: {VAULT}", file=sys.stderr)
        return 2
    notes = [parse(p) for p in sorted(VAULT.rglob("*.md"))]

    if args.list:
        for folder in sorted({n["folder"] for n in notes}):
            names = [n["name"] for n in notes if n["folder"] == folder]
            print(f"## {folder} ({len(names)})\n" + " / ".join(names))
        return 0

    words = [w.lower() for w in args.words]
    hits = []
    for n in notes:
        if args.status and n["state"] != args.status:
            continue
        head = f"{n['name']} {n['tags']} {n['summary']}".lower()
        hay = head + " " + n["body"].lower() if args.body else head
        if all(w in hay for w in words):
            n["head_hit"] = all(w in head for w in words)
            hits.append(n)
    # 名前・要点で一致したものを先に、何でも載っている索引は後ろに
    hits.sort(key=lambda n: (not n["head_hit"], n["folder"] == "00 索引"))

    for n in hits[: args.max]:
        state = f" [{n['state']} {n['date']}]".rstrip() if n["state"] else ""
        print(f"■ {n['folder']}/{n['name']}{state}")
        print(f"  {n['summary'] or '(要点なし)'}")
        if args.body and words:
            shown = 0
            for line in n["body"].splitlines():
                low = line.lower()
                if any(w in low for w in words) and "[!summary]" not in line and not line.startswith(">"):
                    print(f"  … {line.strip()[:160]}")
                    shown += 1
                    if shown == 3:
                        break
    rest = len(hits) - args.max
    print(f"-- {len(hits)} 件" + (f" (うち {rest} 件は省略、--max で増やす)" if rest > 0 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
