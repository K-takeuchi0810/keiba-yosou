"""post-demotion repaired 30-feature の学習・域外監査・評価を、この worktree のコードで本番 DB に対して実行する。

worktree には data/keiba.db が無い (git 管理外) ので、`config.DB_PATH` を本番の checkout の DB に向ける。
各モジュールは import するときに DB_PATH を取り込むので、import より前に差し替える。
DB への接続は各スクリプトのとおり読み取り専用 (mode=ro)。

usage (worktree の根で):
    .venv64/Scripts/python.exe data/backtest/post_demotion_repaired_30features_20261004/run_step.py <step> [引数...]
    step: fit_fundamental | fit_offset | domain | eval
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
PROD_DB = Path(r"C:\Users\kizun\dev\keiba-yosou\data\keiba.db")

STEPS = {
    "fit_fundamental": ("scripts.fundamental_model", ["--fit"]),
    "fit_offset": ("scripts.market_offset_model", ["--fit"]),
    "domain": ("scripts.feature_domain_audit", []),
    "eval": ("scripts.market_offset_eval", []),
}


def main() -> None:
    step, rest = sys.argv[1], sys.argv[2:]
    module, args = STEPS[step]
    if not PROD_DB.exists():
        raise SystemExit(f"本番 DB が無い: {PROD_DB}")
    sys.path.insert(0, str(WT))
    if "db" in sys.modules:
        raise SystemExit("db が既に import されている (DB_PATH を差し替えられない)")
    import config

    config.DB_PATH = PROD_DB
    import db

    assert db.DB_PATH == PROD_DB, db.DB_PATH
    print(f"[run_step] {step}: {module} {args + rest} / code={WT} / db={PROD_DB}", flush=True)
    sys.argv = [module] + args + rest
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
