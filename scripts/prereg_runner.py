"""事前登録した主検定の runner の共通の純粋な部品 (2026-10-06、Group D の runner から使う)。

Group A (`scripts/group_a_run.py`) と C′ (`scripts/c_prime_run.py`) の runner は、それぞれの主検定の錠が sha256 / blob を固定した **歴史的な記録** として
凍結したまま触らない (Group A の `_check_pinned` は git の状態が不明なときに通る fail-open の写しのまま残っている)。新しい runner はここを使う。
C′ の凍結の前と主検定の後の code-quality のレビューの持ち越し: fail-closed・来歴の own_output を複数のパスに・git の失敗を RunError に。

- `verdict` / `fixed_power`: §8-4 / §8-7 / §8-7b の判定の区分と MDE (定数は事前登録の値)
- `write_json`: 原子的・NaN は null・`allow_nan=False`
- `blob_sha`: git の blob と同じ規則 (改行を LF に正規化)。作業ツリーの autocrlf に依らない
- `provenance`: HEAD・未コミットの変更 (`--untracked-files=all`、自分の出力先は除く)・依存ファイルの blob・版・DB の状態
- `check_pinned`: 主検定の前の照合 (fail-closed: git の状態が不明でも止める、固定のファイルが無ければ止める)
- `lock_is_committed`: 錠が git に追跡されていて、変更が無いこと
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

BETA_TARGET = math.log1p(0.25) / 2.0                # §8-4 / §8-4c-2: β_market = 1 で 2 単位違う 2 頭の相対オッズに 1.25 倍の差
Z_ALPHA_2SIDED_001 = 2.5758293035489004             # 両側 α = 0.01
Z_POWER_080 = 0.8416212335729143                    # 検出力 80%
CRITICAL_MULTIPLIER = Z_ALPHA_2SIDED_001 + Z_POWER_080


class RunError(RuntimeError):
    pass


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob_sha(path: Path) -> str:
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def rel(root: Path, path: Path) -> str | None:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def nan_to_none(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [nan_to_none(v) for v in obj]
    return obj


def write_json(path: Path, obj) -> None:
    """原子的に書く (一時のファイル → replace)。NaN / inf は null にする。"""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(nan_to_none(obj), ensure_ascii=False, indent=1, default=str, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    except FileNotFoundError as e:                  # git が無い環境
        raise RunError(f"git を実行できない: {e}") from e


def provenance(root: Path, dependencies: tuple[str, ...], db_path, argv: list[str] | None = None,
               own_output: str | list[str] | None = None) -> dict:
    """来歴。`own_output` (その実行が書く出力先、repo からの相対。複数可) の未追跡・変更は git_dirty から外す (生の一覧は git_status に残す)。"""
    owns = [o for o in ([own_output] if isinstance(own_output, str) else (own_output or [])) if o]
    head = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    lines = [ln for ln in status.stdout.splitlines() if ln.strip()] if status.returncode == 0 else None

    def own(line: str) -> bool:
        p = line[3:].strip().strip('"').replace("\\", "/")
        return any(p == o.rstrip("/") or p.startswith(o.rstrip("/") + "/") for o in owns)
    dbp = Path(db_path)
    st = dbp.stat() if dbp.exists() else None
    return {"git_sha": head.stdout.strip() if head.returncode == 0 else "unknown",
            "git_dirty": (any(not own(ln) for ln in lines) if lines is not None else None),
            "git_status": lines, "own_output": owns,
            "files_blob_sha1": {f: blob_sha(Path(root) / f) for f in dependencies if (Path(root) / f).exists()},
            "python": platform.python_version(), "numpy": np.__version__,
            "argv": list(argv if argv is not None else sys.argv),
            "db": {"path": str(dbp), "bytes": st.st_size if st else None,
                   "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds") if st else None}}


def check_pinned(now_prov: dict, pinned_files: tuple[str, ...], *sources: tuple[str, dict]) -> dict:
    """主検定の前の照合 (fail-closed)。`sources` は (名前, その時点の来歴) の組。git の状態が不明 (None) でも止める。"""
    if now_prov["git_dirty"] is not False:
        raise RunError(f"作業ツリーに未コミットの変更がある、または git の状態が分からない: {now_prov['git_status']}")
    cur = now_prov["files_blob_sha1"]
    missing = [f for f in pinned_files if f not in cur]
    if missing:
        raise RunError(f"固定のファイルが無い: {missing}")
    bad = {}
    for f in pinned_files:
        for name, prov in sources:
            if prov["files_blob_sha1"].get(f) != cur[f]:
                bad[f"{f} ({name})"] = (prov["files_blob_sha1"].get(f), cur[f])
    if bad:
        raise RunError(f"主検定の前提のファイルが凍結・検出力の時点と違う: {bad}")
    return {"git_sha": now_prov["git_sha"], "pinned_blob_sha1": {f: cur[f] for f in pinned_files}}


def lock_is_committed(root: Path, lock_path: Path) -> bool:
    r = rel(root, lock_path)
    if r is None:
        return False
    tracked = _git(root, "ls-files", "--error-unmatch", r)
    status = _git(root, "status", "--porcelain", "--", r)
    return tracked.returncode == 0 and status.returncode == 0 and not status.stdout.strip()


def fixed_power(se_analytic: float, se_train_boot: float | None, n_train: int, n_target: int) -> dict:
    """§8-7b: MDE = 3.4174 × max(解析の SE, 学習期のブートストラップの SE × √(N_学習 / N_主検定))。MDE > β_target なら判定不能を先に確定。"""
    se_scaled = se_train_boot * math.sqrt(n_train / n_target) if se_train_boot is not None else None
    se_fixed = max(se_analytic, se_scaled) if se_scaled is not None else se_analytic
    m = CRITICAL_MULTIPLIER * se_fixed
    return {"se_analytic_2025": se_analytic, "se_train_boot": se_train_boot, "n_train_races": n_train, "n_target_races": n_target,
            "se_train_scaled": se_scaled, "se_fixed": se_fixed, "critical_multiplier": CRITICAL_MULTIPLIER, "mde": m,
            "beta_target": BETA_TARGET, "inconclusive_by_power": bool(m > BETA_TARGET),
            "status_before_primary": "PRIMARY_INCONCLUSIVE" if m > BETA_TARGET else "PRIMARY_DECIDABLE"}


def verdict(ci: dict, power: dict) -> tuple[str, str]:
    """§8-4: 検出力で判定不能が確定していれば INCONCLUSIVE (MDE の理由を上書きしない) → 区間が無効なら INCONCLUSIVE → 下限 > 0 で PASS。"""
    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")
    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"
    return ("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] > 0 else ("PRIMARY_FAIL", "ci_lower_not_above_zero")
