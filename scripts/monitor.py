r"""Phase 5 (2026-05-13): Brier ドリフト監視と自動再訓練アラート。

直近 N 日の予測 vs 結果から Brier を計算し、訓練時 (`predictor/lgbm_meta.json`
または `predictor/calibrator.json`) の値より一定割合悪化していたら警告。

usage:
    .venv64\Scripts\python.exe -m scripts.monitor --days 30
    .venv64\Scripts\python.exe -m scripts.monitor --days 30 --auto-retrain
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PROJECT_ROOT
from db import open_db
from predictor.calibration import calibration_report
from predictor.rules import predict_race
from scripts.backtest import horses_for_race, list_races

logger = logging.getLogger(__name__)

DEGRADATION_THRESHOLD = 0.20  # baseline Brier 比 +20% で警告

# 採用時に凍結する baseline (本番 pipeline と同一コードパスで計測した
# backtest の calibration.brier_score)。--freeze-baseline で更新する。
BASELINE_FILE = PROJECT_ROOT / "data" / "backtest" / "baseline_brier.json"


def _read_baseline_brier() -> tuple[str, float] | None:
    """ドリフト判定の baseline Brier。

    優先: 採用時に凍結した BASELINE_FILE (measure_recent_brier と同じ
    本番 pipeline = ensemble + calibrated で計測した値)。
    フォールバック: 訓練時メタ (LGBM 単体 / calibrator fit 時) — ただし
    計測コードパスが異なるためドリフト閾値が系統的にずれる
    (2026-06-13 v2 監査指摘。実測で既に +7.9% 下駄があった)。
    """
    if BASELINE_FILE.exists():
        try:
            d = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
            b = d.get("brier_score")
            if b:
                return (f"frozen:{d.get('source', '?')}", float(b))
        except Exception:
            logger.warning("baseline_brier.json の読込に失敗", exc_info=True)
    logger.warning(
        "凍結 baseline (%s) が無いため訓練時メタにフォールバックします。"
        "計測経路が本番 pipeline と異なり閾値がずれるため、採用時の backtest "
        "JSON から `python -m scripts.monitor --freeze-baseline <path>` で"
        "凍結してください。", BASELINE_FILE)
    lgbm_meta = PROJECT_ROOT / "predictor" / "lgbm_meta.json"
    if lgbm_meta.exists():
        try:
            d = json.loads(lgbm_meta.read_text(encoding="utf-8"))
            b = d.get("val_brier")
            if b:
                return ("lgbm.val_brier", float(b))
        except Exception:
            pass
    calib = PROJECT_ROOT / "predictor" / "calibrator.json"
    if calib.exists():
        try:
            d = json.loads(calib.read_text(encoding="utf-8"))
            b = d.get("brier_score")
            if b:
                return ("calibrator.brier_score", float(b))
        except Exception:
            pass
    return None


def measure_recent_brier(days: int) -> dict:
    today = datetime.now().date()
    from_date = (today - timedelta(days=days)).strftime("%Y%m%d")
    to_date = today.strftime("%Y%m%d")
    records: list[dict] = []
    with open_db() as conn:
        races = list_races(conn, from_date, to_date, jra_only=True)
        cache: dict = {}
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            if not any((h.get("confirmed_order") or 0) > 0 for h in horses):
                continue
            try:
                preds = predict_race(horses, conn=conn, race=race, cache=cache)
            except Exception as e:
                logger.warning("predict_race failed: %s", e)
                continue
            horse_by_num = {h.get("horse_num"): h for h in horses}
            for pred in preds:
                horse = horse_by_num.get(pred.horse_num)
                if not horse:
                    continue
                records.append({
                    "probability": pred.win_probability,
                    "actual": 1 if horse.get("confirmed_order") == 1 else 0,
                })
    rep = calibration_report(records)
    return {
        "from_date": from_date,
        "to_date": to_date,
        "n_records": len(records),
        "brier_score": rep.get("brier_score"),
        "log_loss": rep.get("log_loss"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30,
                    help="直近何日分の予測を評価するか (既定 30)")
    ap.add_argument("--threshold", type=float, default=DEGRADATION_THRESHOLD,
                    help="baseline 比悪化率の警告閾値 (既定 0.20 = +20%%)")
    ap.add_argument("--auto-retrain", action="store_true",
                    help="閾値超過時に LightGBM 自動再訓練を kick (.venv64 で実行)")
    ap.add_argument("--freeze-baseline-days", type=int, metavar="N", default=None,
                    help="measure_recent_brier(N日) を baseline_brier.json に凍結して終了。"
                         "戦略/校正の採用時に実行する。週次監視と同一の計測コードパス "
                         "(本番 pipeline の最終 win_probability) で測るのが要点 — "
                         "backtest JSON の calibration.brier は raw_blended ベースで"
                         "経路が異なるため使わない")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.freeze_baseline_days:
        m = measure_recent_brier(args.freeze_baseline_days)
        if not m.get("brier_score") or not m.get("n_records"):
            print(f"ERROR: 計測できる確定レースが無い ({m['from_date']}-{m['to_date']})",
                  file=sys.stderr)
            return 2
        BASELINE_FILE.write_text(json.dumps({
            "brier_score": m["brier_score"],
            "log_loss": m["log_loss"],
            "n_records": m["n_records"],
            "source": "measure_recent_brier (本番 pipeline と同一経路)",
            "period": [m["from_date"], m["to_date"]],
            "frozen_at": datetime.now().isoformat(timespec="seconds"),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"baseline frozen: brier={m['brier_score']:.4f} "
              f"(n={m['n_records']}, {m['from_date']}-{m['to_date']})")
        return 0

    baseline = _read_baseline_brier()
    if not baseline:
        print("ERROR: no baseline Brier found (lgbm_meta.json or calibrator.json)", file=sys.stderr)
        return 2
    src, base_b = baseline
    recent = measure_recent_brier(args.days)
    if recent["brier_score"] is None or recent["n_records"] == 0:
        print(f"WARN: no recent records ({recent['from_date']}-{recent['to_date']})", file=sys.stderr)
        return 1
    drift = (recent["brier_score"] - base_b) / base_b if base_b else 0
    payload = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_source": src,
        "baseline_brier": base_b,
        "recent_period": [recent["from_date"], recent["to_date"]],
        "recent_n": recent["n_records"],
        "recent_brier": recent["brier_score"],
        "recent_logloss": recent["log_loss"],
        "drift_rate": round(drift, 4),
        "threshold": args.threshold,
        "alert": drift > args.threshold,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if payload["alert"]:
        print(
            f"⚠ Brier drift {drift*100:+.1f}% above baseline {base_b:.4f} → "
            f"{recent['brier_score']:.4f} on {recent['n_records']} recent records",
            file=sys.stderr,
        )
        if args.auto_retrain:
            print("=== triggering auto-retrain ===", file=sys.stderr)
            from config import DATA_PERIODS
            cmd = [
                str(PROJECT_ROOT / ".venv64" / "Scripts" / "python.exe"),
                "-m", "scripts.train_lgbm",
                "--from", DATA_PERIODS["train"]["from"],
                "--to", DATA_PERIODS["train"]["to"],
                "--rule-version", f"lgbm-autoretrain-{datetime.now().strftime('%Y%m%d')}",
                "--n-trials", "100",
                "--save",
            ]
            print(" ".join(cmd), file=sys.stderr)
            subprocess.run(cmd, check=False)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
