"""変異テストを **本番に届かない場所だけ** で流すための枠 (2026-09-25)。

## なぜ要るか

変異テスト (欠陥をわざと植えてテストが落ちるかを見る) は、この repo では
何度も本番に届きかけた:

- 2026-09-21: subagent が本番 checkout の `jst.py` に「前日を返す」変異を残した
- 2026-09-25: `git archive` で取り出した隔離コピーで流したのに、変異の中身が
  「bat の cd 先を本番 checkout に戻す」ものだったため、テストが bat を動かす
  たびに本番へ cd し、本番の `data/logs` に 3 回書き込んだ

「気を付ける」では止まらないので、ここで機械的に止める:

1. **流す前**: コピーが本番 checkout の外にあるか、`.git` が無いか、本番 DB への
   リンクや webhook ファイルを持っていないか。1 つでも駄目なら何も流さない
2. **変異ごと**: 植える文字列が本番のパス・本番 DB・Discord webhook を含むなら、
   その変異は流さない (REFUSED)。行き先は存在しないダミーパスにして書き直す
3. **変異ごと (後)**: 本番の `data/logs` / `data/runtime` / DB に変化が出たら、
   そこで全体を止める (ABORTED)

## 使い方

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec <spec.py>

spec には `MUTANTS = [(名前, 相対パス, 置換前, 置換後), ...]` と
`TESTS = ["tests/...", ...]` を書く。隔離コピーは

    git archive <sha> | tar -x -C <本番の外のディレクトリ>

で作り、`.venv64` だけは本物へのジャンクションにしてよい。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import runpy
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: 本番 checkout。Task Scheduler が毎朝読むツリー。
PRODUCTION_ROOT = Path(r"C:\Users\kizun\dev\keiba-yosou")

#: コピーの中でリンクにしてよいもの (Python の実行環境だけ)。
ALLOWED_LINKS = {".venv64", ".venv32"}

WEBHOOK_MARKERS = ("discord.com/api/webhooks", "discordapp.com/api/webhooks")


def _norm(p: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def _is_link(p: Path) -> bool:
    """シンボリックリンクと Windows のジャンクションの両方を見る。"""
    if p.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction and is_junction(p))


def _inside(child: Path, parent: Path) -> bool:
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def check_sandbox(copy_root: Path, production_root: Path = PRODUCTION_ROOT) -> list[str]:
    """隔離コピーとして使ってよいか。問題があれば理由のリストを返す (空なら可)。"""
    problems: list[str] = []
    copy_root = Path(copy_root)
    if not copy_root.is_dir():
        return [f"コピーが無い: {copy_root}"]
    if _inside(copy_root, production_root):
        problems.append(f"コピーが本番 checkout の中にある: {copy_root}")
    if _inside(production_root, copy_root):
        problems.append(f"コピーが本番 checkout を含んでいる: {copy_root}")
    if (copy_root / ".git").exists():
        problems.append("コピーに .git がある (git archive で取り出したものを使う)")
    if (copy_root / "data" / "discord_webhook.txt").exists():
        problems.append("コピーに data/discord_webhook.txt がある (実際に通知が飛ぶ)")
    db = copy_root / "data" / "keiba.db"
    prod_db = production_root / "data" / "keiba.db"
    if db.exists() or _is_link(db):
        if _is_link(db):
            problems.append("コピーの data/keiba.db がリンク (本番 DB に書き込みうる)")
        elif prod_db.exists() and os.path.samefile(db, prod_db):
            problems.append("コピーの data/keiba.db が本番 DB と同じファイル (ハードリンク)")
    for dirpath, dirnames, filenames in os.walk(copy_root):
        here = Path(dirpath)
        for name in list(dirnames) + filenames:
            p = here / name
            if not _is_link(p):
                continue
            rel = p.relative_to(copy_root).as_posix()
            if rel in ALLOWED_LINKS:
                dirnames[:] = [d for d in dirnames if d != name]   # 中には入らない
                continue
            problems.append(f"許可していないリンク: {rel}")
            if name in dirnames:
                dirnames.remove(name)
    return problems


def production_markers(production_root: Path = PRODUCTION_ROOT) -> list[str]:
    """変異の文字列に含まれていたら流さない語 (本番のパスと webhook)。"""
    root = str(production_root)
    variants = {root, root.replace("\\", "/"), root.replace("\\", "\\\\"),
                root.replace("\\", "/").replace("C:", "/c", 1)}
    return sorted(variants) + list(WEBHOOK_MARKERS)


def refuses(new_text: str, production_root: Path = PRODUCTION_ROOT) -> str | None:
    """植える文字列が本番を指していれば、その理由を返す。"""
    low = new_text.lower()
    for m in production_markers(production_root):
        if m.lower() in low:
            return f"変異が本番を指す文字列を含む: {m!r}"
    return None


def snapshot_production(production_root: Path = PRODUCTION_ROOT) -> dict:
    """本番の運用ログ置き場と DB の状態 (名前・サイズ・更新時刻)。"""
    snap: dict[str, tuple[int, int]] = {}
    for rel in ("data/logs", "data/runtime"):
        d = production_root / rel
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file():
                    st = p.stat()
                    snap[p.relative_to(production_root).as_posix()] = (
                        st.st_size, st.st_mtime_ns)
    for rel in ("data/keiba.db", "data/keiba.db-wal"):
        p = production_root / rel
        if p.exists():
            st = p.stat()
            snap[rel] = (st.st_size, st.st_mtime_ns)
    return snap


def diff_snapshots(before: dict, after: dict) -> list[str]:
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


@dataclass
class Result:
    name: str
    status: str                       # KILLED / SURVIVED / NOT_APPLIED / REFUSED / ABORTED
    detail: list[str] = field(default_factory=list)


class SandboxError(RuntimeError):
    pass


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_mutants(copy_root: Path, mutants, tests, *,
                production_root: Path = PRODUCTION_ROOT,
                python: str | None = None) -> list[Result]:
    """変異を 1 つずつ植えて tests を流す。必ず元に戻す。

    本番に変化が出たら SandboxError で止める (残りは流さない)。
    """
    copy_root = Path(copy_root)
    problems = check_sandbox(copy_root, production_root)
    if problems:
        raise SandboxError("隔離コピーとして使えない: " + " / ".join(problems))
    py = python or sys.executable

    def _pytest():
        # バイトコードは実行ごとに新しい置き場へ。Python は .pyc の有効性を
        # 「ソースの更新時刻 (秒) とサイズ」で見るので、`+` → `-` のように
        # サイズの変わらない変異を同じ 1 秒のうちに植えると、古い .pyc が
        # そのまま使われて変異が「生存」に見える (2026-09-25 に実際に起きた)。
        import tempfile

        with tempfile.TemporaryDirectory(prefix="mut-pyc-") as pyc:
            env = {**os.environ, "PYTHONPYCACHEPREFIX": pyc,
                   "PYTHONIOENCODING": "utf-8"}
            return subprocess.run(
                [py, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests],
                cwd=copy_root, capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env)

    # 変異を植える前に、同じ環境で緑であることを確かめる。赤いテストがあると
    # どの変異も「撃墜」に見え、後ろのテストが 1 本も走らない (2026-09-25 実例:
    # 出力のエンコーディング依存で落ちる 1 本が、後ろの 9 変異の結果を隠した)。
    before = snapshot_production(production_root)
    baseline = _pytest()
    changed = diff_snapshots(before, snapshot_production(production_root))
    if changed:
        raise SandboxError(f"変異なしの実行で本番が変わった: {changed}")
    if baseline.returncode != 0:
        failed = [l for l in baseline.stdout.splitlines()
                  if l.startswith(("FAILED", "ERROR"))]
        raise SandboxError(f"変異なしでテストが赤い (結果が信用できない): {failed[:3]}")

    originals = {f: _digest(copy_root / f) for f in {m[1] for m in mutants}
                 if (copy_root / f).exists()}
    results: list[Result] = []
    for name, rel, old, new in mutants:
        reason = refuses(new, production_root)
        if reason:
            results.append(Result(name, "REFUSED", [reason]))
            continue
        p = copy_root / rel
        orig = p.read_bytes()
        text = orig.decode("utf-8")
        if "\r\n" in text and "\n" in old and "\r\n" not in old:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        if text.count(old) != 1:
            results.append(Result(name, "NOT_APPLIED", [f"一致 {text.count(old)} 件"]))
            continue
        before = snapshot_production(production_root)
        try:
            p.write_bytes(text.replace(old, new).encode("utf-8"))
            r = _pytest()
        finally:
            p.write_bytes(orig)
        changed = diff_snapshots(before, snapshot_production(production_root))
        if changed:
            results.append(Result(name, "ABORTED", changed))
            raise SandboxError(f"変異 {name!r} の実行で本番が変わった: {changed}")
        failed = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "ERROR"))]
        results.append(Result(name, "KILLED" if r.returncode else "SURVIVED", failed[:1]))
    after = {f: _digest(copy_root / f) for f in originals}
    if after != originals:
        raise SandboxError("変異を元に戻せていないファイルがある")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--copy", required=True, help="隔離コピー (git archive で取り出したもの)")
    ap.add_argument("--spec", required=True, help="MUTANTS と TESTS を定義した .py")
    args = ap.parse_args()

    spec = runpy.run_path(args.spec)
    try:
        results = run_mutants(Path(args.copy), spec["MUTANTS"], spec["TESTS"])
    except SandboxError as e:
        print(f"ABORT: {e}", file=sys.stderr)
        return 2
    for r in results:
        print(r.status, r.name, *r.detail)
    survived = [r for r in results if r.status in ("SURVIVED", "NOT_APPLIED")]
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
