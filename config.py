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
    # --- 既定値の根拠 (P0-4 walk-forward sweep) ---
    # scripts/filter_sweep.py --walk-forward の結果、複数の robust なフィルタが検出:
    #   - wl_odds_8_20 (= whitelist + Odds 8-20): 74戦/103.5% (design) / 41戦/116.1% (eval)
    #   - wl_ex_unsure_pop_1_4 (= whitelist + 信頼度除外 + 1-4 人気): 166戦/86.3% / 105戦/89.0% ★採用
    #   - wl_odds_2_5 (= 重賞+中山+京都 で 2-5 倍本命): 259戦/80.7% / 180戦/84.2%
    # サンプル豊富 (271 戦) で両期間とも控除率超え + 既存の信頼度判定と
    # 整合する `wl_ex_unsure_pop_1_4` を採用。EV / 内部バリューはモデルが
    # 校正できていないため実質無効化 (0.0)。Odds 帯は 1〜100 で実質無効化し、
    # 代わりに人気帯 (1-4) と信頼度除外で絞る。
    # None は「制約なし」を意味する (= 負値も許容)。0.0 だと負の EV が排除される。
    "min_ev": None,
    "min_value": None,
    "min_odds": 1.0,
    "max_odds": 100.0,
    "min_popularity": 1,           # 単勝 1 〜 N 人気
    "max_popularity": 4,           # ←ここがメインの絞り条件
    "exclude_confidence": ["暫定", "混戦", "接戦"],   # 信頼度ラベルでこれらは買わない
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
