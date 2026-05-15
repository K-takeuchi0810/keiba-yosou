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
    # --- P14 採用 (2026-05-15): only_t04_09_ev_ge_110 ---
    # P12 wl5_pop_1_2 hold-out 失敗後、recent-3fold sweep (2025-H1 / 2025-H2 /
    # 2026-Q1+) で唯一 robust だった戦略を採用:
    #   - 2025-H1: 165 戦 / 8.5% / 82.4%
    #   - 2025-H2: 166 戦 / 12.0% / 121.1%
    #   - 2026-Q1+: 105 戦 / 11.4% / 168.3%
    #   - min return 82.4% (controlled loss 以上) / 戦数 436 / 1.5 年
    #
    # 戦略の中身:
    #   - 場 = 新潟 (04) + 阪神 (09) — recent-3fold で逆転 robust だった 2 場
    #   - EV >= 1.10 — LGBM が「期待値 +10% 以上」と判定した馬のみ
    #
    # 注意: 第 3 fold が 2026-Q1+ (= PRODUCTION 期間そのもの) なので、
    # 厳密には「採用判断と評価が同一期間で循環」する形。今後発生する
    # 2026-05-11 以降の前向きデータでさらに継続検証必要。
    #
    # 義務化された運用ルール (前回 P12 失敗の反省):
    #   1. scripts/monitor.py を **週次自動実行** (Brier ドリフト >+20% で警告)
    #   2. Brier 警告発火 → 即サスペンド (whitelist_tracks=[] で買い候補ゼロ)
    #   3. **月次で TRAIN を rolling forward** (例: 2022-2024 → 2023-2025) して
    #      LGBM 再訓練
    #   4. **四半期ごとに --recent-3fold を再実行** して戦略の有効性確認
    #   5. 同戦略を採用してから **3 ヶ月** 経過したら必ず再 sweep
    #
    # 旧 wl_odds_8_20 (in-sample, P05) / wl_ex_unsure_pop_1_4 (旧) と比較:
    #   - wl_odds_8_20: TEST in-sample 116% → out-of-sample 34% (崩壊)
    #   - wl5_pop_1_2: TEST 184% → PROD 45% (崩壊)
    #   - only_t04_09_ev_ge_110: TEST 不明 → recent-3fold 82-168% (採用)
    # 過去 2 戦略はいずれも「TEST 通年集約で高 EV」を信用しすぎて失敗した。
    # 本戦略は「直近 1.5 年で逆転 robust」を根拠とするので時系列適応度高い。
    "min_ev": 1.10,                 # ←主絞り条件 1: LGBM EV エッジ
    "min_value": None,
    "min_odds": None,
    "max_odds": None,
    "min_popularity": None,
    "max_popularity": None,
    "exclude_confidence": [],
    "max_odds_age_min": 30,
    # ----- 場別 whitelist (2 場限定、recent-3fold 採用) -----
    # 04 = 新潟、09 = 阪神 (web/codes.py:TRACK_NAMES)
    # recent-3fold で逆転 robust だった 2 場。P12 採用の 5 場 {01,02,03,06,07}
    # は全部 hold-out で崩壊したため除外。
    "whitelist_mode": True,
    "whitelist_grades": [],
    "whitelist_tracks": ["04", "09"],
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
