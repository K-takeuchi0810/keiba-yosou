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
    # --- 既定値の根拠 (Phase 6 LGBM v4 + walk-forward 3-fold, 2026-05-15 更新) ---
    # data/backtest/20260514_sweep_phase6_v4.csv の 69 filter × 3 fold sweep で
    # **`wl5_pop_1_2`** が圧倒的勝者として浮上:
    #   - 2023: 199 戦 / 17.6% / 117.6%
    #   - 2024: 187 戦 / 16.6% / 195.5%
    #   - 2025: 259 戦 / 16.2% / 240.5%
    #   - min return 117.6% (全 3 fold +100% 維持) / 年間 ~215 戦
    #
    # 旧採用 `wl_odds_8_20` は LGBM ensemble 時点でも 2024 で 2.3% に崩壊し
    # in-sample artifact 確定。代わりに本戦略は:
    #   - **5 場 (LGBM v4 で robust な札幌/函館/福島/中山/中京)** に限定
    #   - **1-2 人気** に限定 (本命厚切り)
    #   - 重賞限定は削除 (場フィルタで十分絞れる)
    #
    # 構造的特徴:
    # - JRA 単勝控除率 80% を全 3 fold で +37.6pt 以上超え、構造的天井突破
    # - 戦数 645 / 3 年で Wilson CI が狭く統計的有意
    # - 重賞限定でないので戦数十分かつ noise 耐性あり
    # - LGBM v4 が `jockey_track_top3_rate` (場別騎手相性) を強く活用しているため
    #
    # 旧 wl_odds_8_20 採用との交替で「+100% を毎月安定」が現実的に到達可能。
    # ただし PRODUCTION 2026 の hold-out 検証は本番投入前に必須。
    "min_ev": None,
    "min_value": None,
    "min_odds": None,              # popularity で絞るため odds 制約は解除
    "max_odds": None,
    "min_popularity": 1,           # ←主絞り条件 1: 1-2 人気のみ
    "max_popularity": 2,
    "exclude_confidence": [],
    "max_odds_age_min": 30,
    # ----- 場別ホワイトリスト (LGBM v4 + 3-fold robust 5 場) -----
    # whitelist_tracks の場コードは web/codes.py 準拠 (JV-Data 2001 場コード):
    #   01=札幌 / 02=函館 / 03=福島 / 04=新潟 / 05=東京 / 06=中山 /
    #   07=中京 / 08=京都 / 09=阪神 / 10=小倉
    # 採用 5 場 {01, 02, 03, 06, 07} は LGBM v4 ensemble での 2023-2025 各年
    # 場別 EVAL で安定 robust なものを選定 (data/backtest/20260514_sweep_phase6_v4.csv)。
    # `whitelist_grades` を空にしているのは「場フィルタだけで絞る」設計。
    # 重賞限定にすると戦数激減 (645 → ~50) で CI が広がる。
    "whitelist_mode": True,
    "whitelist_grades": [],
    "whitelist_tracks": ["01", "02", "03", "06", "07"],
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
