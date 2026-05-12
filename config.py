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


# 買い目フィルタの既定値。アプリ全体で **必ずここを唯一の出典** とする。
# 利用箇所: web/generator.py (公開 HTML 用) / gui/app.py:_is_buy_candidate
#         / scripts/backtest.py (デフォルト引数) / GUI dashboard JS の input value
# この値が変わったら data/backtest/ で新たに rule_version 付きで保存し直すこと
# (過去 backtest と直接比較できなくなるため)。
BUY_FILTER_DEFAULT: dict = {
    # --- 既定値の根拠 (P0-4 walk-forward sweep, 2026-05-12 更新) ---
    # `scripts/filter_sweep.py --walk-forward` を 2 期間 (design 2025/06-12 / eval
    # 2026/01-04) で再計測し、両期間とも控除率 80% を超えるフィルタを sweep。
    # 主要結果 (data/backtest/20260512_walk_forward_v2.csv):
    #   - wl_odds_8_20          : 74戦/103.5% (design) / 41戦/116.1% (eval) ★採用
    #   - wl_odds_8_20_pop_4_8  : 67戦/101.2% / 37戦/128.6% (戦数最少だが上振れ大)
    #   - wl_ex_unsure_pop_1_4  : 166戦/86.3% / 105戦/89.0% (旧採用、+100% 未達)
    #   - wl_odds_2_5           : 259戦/80.7% / 180戦/84.2%
    # 旧採用の `wl_ex_unsure_pop_1_4` は両期間 80%+ ロバストだが +100% に届かず
    # 控除率 -13% 確定運用。+100% 圏を狙う `wl_odds_8_20` に切替。
    # 戦数 115 (両期間合計) でサンプル少だが、両期間とも +100% を出すロバスト性
    # を優先。`pop_4_8` 重ね掛けは EVAL 上振れ大だが DESIGN +1.2% でギリのため見送り。
    # 信頼度除外 (exclude_confidence) は 8-20 帯では `picks` がほぼ消失する
    # (sweep の `wl_odds_8_20_ex_unsure` が 17/7 戦, 65%/0% に崩壊) ため解除。
    # 人気帯 (popularity) も解除し、Odds 帯 8-20 のみで絞る。
    # None は「制約なし」を意味する (= 負値も許容)。0.0 だと負の EV が排除される。
    "min_ev": None,
    "min_value": None,
    "min_odds": 8.0,               # ←ここが主絞り条件 (wl_odds_8_20 採用)
    "max_odds": 20.0,
    "min_popularity": None,        # popularity 制約は解除 (Odds 帯で代替)
    "max_popularity": None,
    "exclude_confidence": [],      # 8-20 帯では混戦ラベル不可避なので解除
    "max_odds_age_min": 30,
    # ----- 重賞ホワイトリストモード -----
    "whitelist_mode": True,
    "whitelist_grades": ["A", "B", "C", "F"],   # G1=A / G2=B / G3=C / 重賞=F
    "whitelist_tracks": ["07", "09"],            # 中山 / 京都
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
