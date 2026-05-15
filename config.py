"""プロジェクト共通設定。

パス・サービスキー等の入口。ハードコード値はここに集約し、
他モジュールはこのモジュールを import する。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")

# 取得・予想生成の中間成果物
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "keiba.db"

# Web 配信用に生成する HTML（プレビュー兼公開元）
WEB_DIST = PROJECT_ROOT / "web" / "dist"

# 公開先（iCloud Drive 配下）。iPhone Files アプリから閲覧。
ICLOUD_PUBLISH_DIR = Path.home() / "iCloudDrive" / "競馬予想"

# JV-Link に渡すソフトウェアID（アプリ識別子）。
# 利用キー（サービスキー）は JV-Link 本体の設定ダイアログで登録済みであることが前提。
JVLINK_SID = os.environ.get("JVLINK_SID", "UNKNOWN")


# データ期間の正規分割 (2026-05-12 5 年分割版)。
# 過去、calibrator の学習窓と filter sweep の評価窓が不明確で in-sample 化が
# 発生していた。以後は **必ずこの 3 期間に従う**:
#   TRAIN      : calibrator fit + weights ハンドチューニング素材。3 年分。
#   TEST       : filter / weight 採用判断、A/B 比較。**TRAIN と必ず disjoint**
#   PRODUCTION : 本番運用 = 当日まで遡って features を構築し予測。
#                副次的に「採用 *決定後*」の HOLDOUT としても扱う。
# 各期間境界は `from <= race_date <= to` の閉区間。
#
# 注意: 過去 win_odds (発走前単勝オッズ) は JV-Data の O1 records 由来で、JV-Link
# は過去履歴を保持しない。当プロジェクトでは 2025-05 から累積開始。よって:
#   - 2024 以前: RA/SE/HR (race info / 出走馬 / 払戻) のみ → calibrator fit OK、
#     ベタ買い回収率 OK、`wl_odds_8_20` 系の buy filter は 0 件評価になる。
#   - 2025+ : 全部揃う → filter sweep 完全動作。
# このため filter_sweep --walk-forward の数値は実質 TEST 期間内 2025 部分が支配的。
DATA_PERIODS: dict[str, dict[str, str]] = {
    "train":      {"from": "20210101", "to": "20231231"},   # 3 年 / calibrator + weights
    "test":       {"from": "20240101", "to": "20251231"},   # 2 年 / 採用判断・A/B
    "production": {"from": "20260101", "to": "20261231"},   # 本番 + HOLDOUT
}


# 買い目フィルタの既定値。アプリ全体で **必ずここを唯一の出典** とする。
# 利用箇所: web/generator.py (公開 HTML 用) / gui/app.py:_is_buy_candidate
#         / scripts/backtest.py (デフォルト引数) / GUI dashboard JS の input value
# この値が変わったら data/backtest/ で新たに rule_version 付きで保存し直すこと
# (過去 backtest と直接比較できなくなるため)。
BUY_FILTER_DEFAULT: dict = {
    # --- 緊急退避状態 (2026-05-15 hold-out 失敗を受けての撤回) ---
    # P12 で採用した `wl5_pop_1_2` は PRODUCTION 2026 hold-out で大暴落 (
    # data/backtest/20260515_201342_tan_p13-production-holdout-filtered.json):
    #   - TEST 2024-25: 659 戦 / 184.0% (CI [116.4%, 266.5%]) / +55,360 円
    #   - PRODUCTION 2026: 115 戦 / 45.1% (CI [20.8%, 75.0%]) / -6,310 円
    # 戦略の出口性能が -139pt 大暴落。場別が逆転:
    #   - 福島 137% → 22.6% / 中山 93.5% → 28.7% / 中京 91.4% → 22.4%
    #   - 一方除外した 阪神 52.5% → 137.2% / 新潟 77.1% → 99.2%
    # Calibration Brier も 0.022 → 0.033 と +50% 悪化 = 大規模 distribution shift。
    #
    # 根本原因 (推定): 馬場改修 / 開催プロモーション変更 / 騎手成績変動などで
    # 「場特性」が 2026 春で大きく変化したため、TEST 2024-2025 で robust だった
    # 場選定が PRODUCTION に転送できなかった。
    #
    # 緊急退避方針: whitelist_grades / whitelist_tracks を空にすることで
    # 「is_whitelisted_race が常に False」=「buy_only に該当する horse がゼロ」に。
    # この状態では予想生成 (◎・○・▲ の印付け) は通常通り行われるが、
    # 「買い候補マーキング (bet_candidate=True)」は誰にも付かない = 自動投入を停止。
    # 本番ベット判断は手動で行う、PRODUCTION 2026 で robust な戦略を再探索するまで。
    "min_ev": None,
    "min_value": None,
    "min_odds": None,
    "max_odds": None,
    "min_popularity": None,
    "max_popularity": None,
    "exclude_confidence": [],
    "max_odds_age_min": 30,
    # ----- 退避モード -----
    # whitelist_mode=True + grades=[] + tracks=[] で is_whitelisted_race が
    # 常に False。buy_only に該当する horse がゼロになる。
    "whitelist_mode": True,
    "whitelist_grades": [],
    "whitelist_tracks": [],
}


def buy_whitelist_enabled() -> bool:
    """環境変数で `whitelist_mode` の既定値を上書き可能にする。"""
    raw = os.environ.get("BET_WHITELIST")
    if raw is None:
        return bool(BUY_FILTER_DEFAULT.get("whitelist_mode", False))
    return raw not in ("0", "false", "False", "")


def is_whitelisted_race(race: dict) -> bool:
    """race (dict) が「ホワイトリスト条件 (重賞 OR 得意競馬場)」を満たすか。

    `whitelist_mode=False` のときは常に True (= 通常運用)。
    呼び出し側は `_is_buy_candidate` 等から横断的にこの関数を使う。
    """
    if not buy_whitelist_enabled():
        return True
    grade = (race.get("grade_code") or "").strip()
    track = (race.get("track_code") or "").strip()
    if grade and grade in BUY_FILTER_DEFAULT["whitelist_grades"]:
        return True
    if track and track in BUY_FILTER_DEFAULT["whitelist_tracks"]:
        return True
    return False


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIST.mkdir(parents=True, exist_ok=True)
    ICLOUD_PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
