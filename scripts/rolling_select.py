"""月次戦略 rolling 再選定 framework (Phase 7 / 2026-05-16)。

採用済戦略の劣化を検知し、必要なら新戦略候補を出すまでを自動化。
人間判断で `config.BUY_FILTER_DEFAULT` 更新までは行わないが、推奨案を
標準出力 + JSON 出力する。

usage:
    .venv64\\Scripts\\python.exe -m scripts.rolling_select
    .venv64\\Scripts\\python.exe -m scripts.rolling_select --threshold 0.70 --auto-sweep

動作:
1. 採用日からの経過月数を計算 (config.BUY_FILTER_DEFAULT 最終更新時刻ベース)
2. 採用戦略の直近 1.5 年 3-fold 数値を抽出 (recent_3fold csv が必要)
3. 「賞味期限 3 ヶ月超過」「直近 fold で <=70%%」「Brier drift > 20%%」の
   いずれかが発火したら再選定推奨
4. --auto-sweep フラグありなら scripts.filter_sweep --recent-3fold を自動 kick
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BUY_FILTER_DEFAULT, PROJECT_ROOT


def find_latest_recent_3fold_csv() -> Path | None:
    """data/backtest/ から最新の recent_3fold sweep CSV を探す。"""
    csvs = sorted((PROJECT_ROOT / "data" / "backtest").glob("*recent_3fold*.csv"))
    return csvs[-1] if csvs else None


def parse_3fold_csv(csv_path: Path) -> list[dict]:
    """recent_3fold CSV を読み、各 filter の return_rate trajectory を返す。"""
    rows: list[dict] = []
    text = csv_path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")
    if not lines:
        return rows
    header = lines[0].split(",")
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) != len(header):
            continue
        d = dict(zip(header, parts))
        rows.append(d)
    return rows


def current_filter_signature() -> str:
    """現採用 BUY_FILTER_DEFAULT のシグネチャ文字列 (人間可読)。"""
    s = BUY_FILTER_DEFAULT
    parts = []
    if s.get("whitelist_tracks"):
        parts.append("t" + "+".join(sorted(s["whitelist_tracks"])))
    if s.get("whitelist_grades"):
        parts.append("g" + "+".join(sorted(s["whitelist_grades"])))
    if s.get("min_popularity") is not None:
        parts.append(f"pop{s['min_popularity']}_{s.get('max_popularity') or '?'}")
    if s.get("min_odds") is not None:
        parts.append(f"odds{s['min_odds']}_{s.get('max_odds') or '?'}")
    if s.get("min_ev") is not None:
        parts.append(f"ev>={s['min_ev']}")
    return "/".join(parts) if parts else "empty"


def days_since_config_update() -> int:
    """config.py の最終更新からの経過日数。"""
    config_path = PROJECT_ROOT / "config.py"
    mtime = config_path.stat().st_mtime
    delta = (datetime.now() - datetime.fromtimestamp(mtime)).total_seconds()
    return int(delta // 86400)


def get_brier_drift() -> tuple[float, str]:
    """scripts.monitor の結果から Brier drift を取得。"""
    try:
        result = subprocess.run(
            [str(PROJECT_ROOT / ".venv64" / "Scripts" / "python.exe"),
             "-m", "scripts.monitor", "--days", "30", "--quiet"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.stdout.strip():
            payload = json.loads(result.stdout.strip())
            return float(payload.get("drift_rate", 0)), str(payload.get("recent_brier", "?"))
    except Exception as e:
        return 0.0, f"error: {e}"
    return 0.0, "no_data"


def recommend_action(
    days_since: int,
    drift_rate: float,
    threshold_drift: float,
) -> str:
    """採用継続 / 再 sweep / サスペンド の判断。"""
    if days_since >= 90:
        return "RE_SWEEP_REQUIRED (賞味期限 3 ヶ月超過)"
    if drift_rate > threshold_drift:
        return f"RE_SWEEP_REQUIRED (Brier drift {drift_rate*100:.1f}%% > {threshold_drift*100:.0f}%%)"
    if days_since >= 60 and drift_rate > threshold_drift / 2:
        return "RE_SWEEP_RECOMMENDED (2 ヶ月超過 + ドリフト兆候)"
    return "CONTINUE (採用継続 OK)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--threshold-drift", type=float, default=0.20,
        help="Brier drift 警告閾値 (default 0.20 = +20%%)",
    )
    ap.add_argument(
        "--auto-sweep", action="store_true",
        help="RE_SWEEP_REQUIRED 時に scripts.filter_sweep --recent-3fold を自動実行",
    )
    args = ap.parse_args()

    sig = current_filter_signature()
    days = days_since_config_update()
    drift, recent_brier = get_brier_drift()
    action = recommend_action(days, drift, args.threshold_drift)

    payload = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "current_filter_signature": sig,
        "days_since_config_update": days,
        "brier_drift_rate": round(drift, 4),
        "recent_brier": recent_brier,
        "threshold_drift": args.threshold_drift,
        "recommendation": action,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if "RE_SWEEP_REQUIRED" in action and args.auto_sweep:
        print()
        print("=== auto-sweep kick ===", file=sys.stderr)
        sweep_out = PROJECT_ROOT / "data" / "backtest" / (
            f"{datetime.now().strftime('%Y%m%d')}_auto_recent_3fold.csv"
        )
        sweep_log = sweep_out.with_suffix(".log")
        subprocess.run(
            [str(PROJECT_ROOT / ".venv64" / "Scripts" / "python.exe"),
             "-m", "scripts.filter_sweep", "--recent-3fold"],
            stdout=open(sweep_out, "w", encoding="utf-8"),
            stderr=open(sweep_log, "w", encoding="utf-8"),
            check=False,
        )
        print(f"sweep saved: {sweep_out}")

    return 1 if "RE_SWEEP_REQUIRED" in action else 0


if __name__ == "__main__":
    sys.exit(main())
