"""records JSON を入力に Isotonic calibrator を fit し、predictor/calibrator.json を置換する。

P17 A2 c2-b (2026-05-17) で新規追加。Phase A2 (Isotonic 化) のフロー:

  1. scripts.backtest --save --save-records --from <s> --to <e> --rule-version <v>
     → records JSON (各馬の raw_blended_probability + actual) を保存
  2. python -m scripts.refit_calibrator <records_path>
     → records から Isotonic を fit
     → 旧 predictor/calibrator.json を .bak にバックアップ
     → 新 predictor/calibrator.json (type=isotonic) として書き出し

usage:
    python -m scripts.refit_calibrator data/backtest/<ts>_<rule>_records.json

P17 A2 c1 後に collect された records (records[i]["probability"] が
raw_blended_probability、race-internal Σ=1 で正規化済) を入力にするのが
正しい使い方。古い records (c1 前、investment_probability ベース) を
入力に使うと、本番予測経路と入力分布が一致せず校正が機能しない。

依存:
  - .venv64 (scikit-learn 必須、fit_isotonic_calibrator が IsotonicRegression を使う)
  - 入力 records JSON: scripts.backtest --save-records で生成された形式
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from predictor.calibration import fit_isotonic_calibrator
from predictor.rules import RULES_VERSION


CALIBRATOR_PATH = Path(__file__).resolve().parent.parent / "predictor" / "calibrator.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("records_path", help="scripts.backtest --save-records が生成した records JSON のパス")
    ap.add_argument(
        "--rule-version", default=None,
        help="新 calibrator.json に記録する rule_version。"
             "省略時は records JSON の rule_version + '_isotonic' を使う",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="fit のみ行い calibrator.json は置換しない (検証用)",
    )
    args = ap.parse_args()

    records_path = Path(args.records_path)
    if not records_path.exists():
        print(f"records file not found: {records_path}", file=sys.stderr)
        return 1

    data = json.loads(records_path.read_text(encoding="utf-8"))
    records = data.get("records") or []
    if not records:
        print("records is empty; nothing to fit", file=sys.stderr)
        return 1

    print(f"loaded {len(records)} records from {records_path}")
    print(f"  source rule_version: {data.get('rule_version')}")
    print(f"  source period: {data.get('from_date')} - {data.get('to_date')}")
    print(f"  source meta calibrator: {data.get('meta', {}).get('calibrator_rule_version')}")
    print(f"  source meta lgbm: {data.get('meta', {}).get('lgbm_rule_version')}")
    print(f"  source meta git_sha: {(data.get('meta', {}).get('git_sha') or '')[:12]}")

    # Isotonic fit
    iso = fit_isotonic_calibrator(records)
    n_knots = len(iso.get("x_knots") or [])
    print(f"isotonic fit: source_count={iso.get('source_count')} knots={n_knots} "
          f"brier={iso.get('brier_score')} logloss={iso.get('log_loss')}")

    rule_version = args.rule_version or f"{data.get('rule_version', 'unknown')}_isotonic"
    calib_with_meta = {
        **iso,
        "trained_from": data.get("from_date"),
        "trained_to": data.get("to_date"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rule_version": rule_version,
        # fit 時点の予想ルール版。predictor.rules._load_calibrator が現行
        # RULES_VERSION と照合し、不一致なら「旧 mapping を別分布に適用」警告を出す。
        "expected_rules_version": RULES_VERSION,
        "calibrator_type": "isotonic",
        # 後追い再現用に元 records の出自を残す
        "source_records_meta": data.get("meta", {}),
    }

    if args.dry_run:
        print("--dry-run: calibrator.json は置換しない")
        print("=== resulting calibrator.json content ===")
        print(json.dumps({k: v for k, v in calib_with_meta.items() if k not in ("x_knots", "y_knots")},
                        indent=2, ensure_ascii=False))
        print(f"  (x_knots: {n_knots} entries, y_knots: {n_knots} entries omitted)")
        return 0

    # backup existing calibrator.json
    if CALIBRATOR_PATH.exists():
        bak = CALIBRATOR_PATH.with_suffix(".json.bak")
        bak.write_bytes(CALIBRATOR_PATH.read_bytes())
        print(f"backup: {bak}")

    CALIBRATOR_PATH.write_text(
        json.dumps(calib_with_meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"calibrator replaced: {CALIBRATOR_PATH}")
    print(f"  type=isotonic  rule_version={rule_version}")
    print(f"  trained {data.get('from_date')} - {data.get('to_date')}  n={iso.get('source_count')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
