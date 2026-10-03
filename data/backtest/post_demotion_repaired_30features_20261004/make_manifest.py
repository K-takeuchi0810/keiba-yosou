"""post-demotion repaired 30-feature の成果物の MANIFEST.json を作る (2026-10-04)。

各ファイルの sha256 と、学習の出自 (コードの SHA・data_version・期間・特徴・best_iteration)、
受理の判定 (comparison_4b_vs_30.json) をまとめる。DB には触れない。

usage (worktree の根で):
    .venv64/Scripts/python.exe data/backtest/post_demotion_repaired_30features_20261004/make_manifest.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERBATIM = {"fundamental_model.txt", "market_offset_model.txt"}     # .gitattributes で -text


def main() -> int:
    files = []
    for p in sorted(HERE.iterdir()):
        if p.name == "MANIFEST.json" or p.is_dir():
            continue
        b = p.read_bytes()
        files.append({
            "file": p.name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
            "line_endings": ("verbatim (-text。LightGBM 自身が書く \\r\\n を含むので変換しない)"
                             if p.name in VERBATIM else
                             "書き出したときのバイト (= git の blob)。autocrlf=true の checkout では CRLF に"
                             "なりうるので、照合は CRLF→LF にしてから"),
        })
    metas = {n: json.loads((HERE / f"{n}.meta.json").read_text(encoding="utf-8"))
             for n in ("fundamental_model", "market_offset_model")}
    comparison = json.loads((HERE / "comparison_4b_vs_30.json").read_text(encoding="utf-8"))
    ev = json.loads((HERE / "post_demotion_market_offset_eval.json").read_text(encoding="utf-8"))
    out = {
        "generation": "post-demotion repaired 30-feature",
        "feature_set": metas["fundamental_model"]["feature_set"],
        "created": "2026-10-04",
        "prereg": "docs/PHASE05_RESULTS.md「post-demotion repaired 30-feature の学習 — 事前固定」(commit 61e2d14、学習の前)",
        "control": "data/backtest/frozen_4b_repaired_31features_20260919/ (4B repaired 31-feature、上書きしていない)",
        "code": {
            "git_sha": metas["fundamental_model"]["git_sha"],
            "dirty_note": ("meta の git_dirty=True は、学習が書き出した predictor/*_model.* 自身が理由 "
                           "(dirty_paths を参照)。コードは 61e2d14 のまま。実行は run_step.py "
                           "(未コミットのまま実行し、このコミットで追加) で config.DB_PATH を本番の DB に向けた"),
            "dirty_paths": {n: m.get("dirty_paths") for n, m in metas.items()},
        },
        "data_version": {n: m["data_version"] for n, m in metas.items()},
        "db_state": {"after_fit": (HERE / "db_state_after_fit.txt").read_text(encoding="utf-8").splitlines(),
                     "after_eval": (HERE / "db_state_after_eval.txt").read_text(encoding="utf-8").splitlines(),
                     "note": "学習の開始時の DB の大きさは fit.log の 1 行目。DB 本体の mtime (10/03 20:00) と "
                             "WAL 0 バイトは学習・評価の前後で不変"},
        "models": {n: {k: m.get(k) for k in ("n_features", "train", "validation", "n_train", "n_valid",
                                             "best_iteration", "audit_columns", "audit_rates",
                                             "audit_rates_by_year")} for n, m in metas.items()},
        "features": metas["fundamental_model"]["features"],
        "features_equal_between_models": metas["fundamental_model"]["features"] == metas["market_offset_model"]["features"],
        "evaluation": {"label": ev["meta"]["label"], "run_index": ev["meta"]["run_index"],
                       "window": [ev["meta"]["from_date"], ev["meta"]["to_date"]],
                       "beta2": ev["primary_conditional_logit"]["coef_correction"],
                       "beta2_ci95": ev["primary_conditional_logit"]["coef_correction_ci95"],
                       "verdict": ev["verdict"]},
        "acceptance": comparison["acceptance"],
        "files": files,
    }
    (HERE / "MANIFEST.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"MANIFEST.json: {len(files)} files, accepted={out['acceptance']['accepted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
