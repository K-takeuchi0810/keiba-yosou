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
import re
import runpy
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_guard import child_pytest_env  # noqa: E402

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


#: 本番側で必ず存在するはずの監視対象。無ければ「監視対象 0 件 = 安全」に化ける。
PRODUCTION_WATCH = ("data/logs", "data/runtime", "data/keiba.db")


def check_production(production_root: Path = PRODUCTION_ROOT) -> list[str]:
    """本番 checkout と監視対象が実在するか。問題があれば理由のリスト。

    本番の場所を取り違えた (checkout を移した・設定がずれた) まま流すと、
    事前検査は合格し、本番の記録は空になり、**枠が黙って何も守らない**
    (2026-09-26 のレビューで実測)。
    """
    production_root = Path(production_root)
    if not production_root.is_dir():
        return [f"本番 checkout が見つからない: {production_root}"]
    return [f"本番の監視対象が無い: {production_root / rel}"
            for rel in PRODUCTION_WATCH if not (production_root / rel).exists()]


def refuses_target(rel: object, copy_root: Path) -> str | None:
    """変異を植えるファイルがコピーの中に収まらなければ、その理由を返す。

    絶対パスや `..` を渡すと、隔離コピーの **外** のファイルを実際に書き換える
    (2026-09-26 のレビューで偽の本番に対して実測。終了後に戻すので静かに通った)。
    「書いてから戻す」は安全策にしない。**書く前に**拒否する。
    """
    if not isinstance(rel, str) or not rel.strip():
        return f"対象パスが空か文字列でない: {rel!r}"
    win = PureWindowsPath(rel)
    if win.drive or win.root or rel.startswith(("/", "\\")) or os.path.isabs(rel):
        return f"対象パスが絶対パス: {rel!r}"
    if any(part == ".." for part in re.split(r"[\\/]+", rel)):
        return f"対象パスに .. がある: {rel!r}"
    target = (Path(copy_root) / rel).resolve()          # ジャンクション越しも解決する
    if not _inside(target, Path(copy_root).resolve()):
        return f"対象パスがコピーの外を指す: {rel!r} -> {target}"
    return None


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
    # DB は「書き込まれたか」だけを見る。本体はサイズと更新時刻、WAL はサイズだけ。
    # WAL の更新時刻は **読むだけ** の接続でも動く (2026-09-26 00:05、別プロジェクトの
    # 常駐プロセスが DB を開いただけで WAL の時刻が変わり、無関係の変異で ABORT した)。
    db = production_root / "data" / "keiba.db"
    if db.exists():
        st = db.stat()
        snap["data/keiba.db"] = (st.st_size, st.st_mtime_ns)
    wal = production_root / "data" / "keiba.db-wal"
    if wal.exists():
        snap["data/keiba.db-wal"] = (wal.stat().st_size, 0)
    return snap


def diff_snapshots(before: dict, after: dict) -> list[str]:
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


@dataclass
class Result:
    name: str
    status: str                       # KILLED / SURVIVED / NOT_APPLIED / REFUSED / ABORTED
    detail: list[str] = field(default_factory=list)


class SandboxError(RuntimeError):
    """止めた理由。`results` はそこまでに流した変異の結果 (途中経過を捨てない)。"""

    def __init__(self, message: str, results: list | None = None):
        super().__init__(message)
        self.results = list(results or [])


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_mutants(copy_root: Path, mutants, tests, *,
                production_root: Path = PRODUCTION_ROOT,
                python: str | None = None) -> list[Result]:
    """変異を 1 つずつ植えて tests を流す。必ず元に戻す。

    本番に変化が出たら SandboxError で止める (残りは流さない)。
    """
    copy_root = Path(copy_root)
    problems = check_production(production_root)
    if problems:
        raise SandboxError("本番の監視を始められない: " + " / ".join(problems))
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
            # 子 pytest の環境は runtime_guard.child_pytest_env で作る (見張りは常に
            # strict)。呼び出し元が週次監視用の off を持っていても、変異の実行には
            # 持ち込まない (環境変数 1 つで枠の内側の防御線まで外れないように)。
            env = child_pytest_env(PYTHONPYCACHEPREFIX=pyc)
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
                 if refuses_target(f, copy_root) is None and (copy_root / f).exists()}
    results: list[Result] = []
    for name, rel, old, new in mutants:
        reason = refuses_target(rel, copy_root) or refuses(new, production_root)
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
            raise SandboxError(f"変異 {name!r} の実行で本番が変わった: {changed}", results)
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
        for r in e.results:
            print(r.status, r.name, *r.detail)
        print(f"ABORT: {e}", file=sys.stderr)
        return 2
    for r in results:
        print(r.status, r.name, *r.detail)
    survived = [r for r in results if r.status in ("SURVIVED", "NOT_APPLIED")]
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
