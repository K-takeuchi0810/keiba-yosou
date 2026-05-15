"""リスク管理 / 賭金最適化 (Phase 7 / 2026-05-16)。

提供する 2 つのレイヤ:

1. Kelly fraction 賭金サイズ算出:
   - kelly_fraction(win_prob, odds) -> 最適賭金比率 f*
   - kelly_size(f*, bankroll, mode) -> 円単位の賭金
   - 推奨運用は 1/4 Kelly (f* / 4) で variance を抑える

2. Drawdown tracker:
   - DrawdownTracker: 直近 N レースの累積収支を SQLite に記録
   - bet_size_multiplier(): drawdown 比例で 0.5〜1.0 のスケーラを返す
   - エスカレーション制御: 連敗 + 累積 -X%% で自動サスペンド

使い方:
    from predictor.risk import kelly_fraction, kelly_size, DrawdownTracker

    f = kelly_fraction(win_prob=0.20, odds=8.0)  # = 0.0857
    bet = kelly_size(f, bankroll=10000, mode="quarter")  # 1/4 Kelly: 214 円

    tracker = DrawdownTracker()
    multiplier = tracker.bet_size_multiplier()  # 0.5-1.0
    final_bet = int(bet * multiplier)
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# Kelly fraction
# ============================================================


def kelly_fraction(win_prob: float, odds: float) -> float:
    """Kelly の最適賭金比率 f* = (p × (b+1) - 1) / b

    引数:
        win_prob: 予想勝率 [0, 1]
        odds: 払戻倍率 (= ペイアウト除算込み、単勝 5 倍なら 5.0)
    戻り:
        f* ∈ [0, 1]。負値は 0 にクリップ (= 賭けない)
    """
    if win_prob <= 0 or win_prob >= 1 or odds <= 1:
        return 0.0
    b = odds - 1.0
    edge = win_prob * (b + 1.0) - 1.0   # = win_prob × odds - 1 (EV - 1)
    if edge <= 0:
        return 0.0
    return min(1.0, edge / b)


def kelly_size(
    f_star: float,
    bankroll: float,
    mode: str = "quarter",
    max_pct: float = 0.05,
    round_unit: int = 100,
) -> int:
    """Kelly fraction を円単位の賭金に変換。

    引数:
        f_star: kelly_fraction() の戻り値
        bankroll: 現在の bankroll (円)
        mode: "full" / "half" / "quarter" (= 1/4 Kelly、推奨)
        max_pct: bankroll の最大 X%% を上限とする safety cap (default 5%%)
        round_unit: 賭金丸め単位 (default 100 = 100 円単位)
    """
    if f_star <= 0:
        return 0
    multiplier = {"full": 1.0, "half": 0.5, "quarter": 0.25}.get(mode, 0.25)
    raw = f_star * multiplier * bankroll
    capped = min(raw, bankroll * max_pct)
    return max(0, int(round(capped / round_unit)) * round_unit)


# ============================================================
# Drawdown tracker (連敗時 / 累積マイナス時の自動賭金縮小)
# ============================================================


_DRAWDOWN_SCHEMA = """
CREATE TABLE IF NOT EXISTS bet_history (
    placed_at      TEXT NOT NULL,
    race_id        TEXT NOT NULL,
    horse_num      TEXT NOT NULL,
    bet_size_yen   INTEGER NOT NULL,
    payout_yen     INTEGER DEFAULT 0,
    settled        INTEGER DEFAULT 0,
    PRIMARY KEY (race_id, horse_num)
);
CREATE INDEX IF NOT EXISTS idx_bet_history_placed
    ON bet_history (placed_at DESC);
"""


class DrawdownTracker:
    """直近の累積収支から賭金スケーラを算出。

    SQLite に bet_history テーブルを持ち、各賭金 + 結果を記録。
    bet_size_multiplier() は次の 2 段階制御を返す:

    - 直近 30 日累積 ROI が -10%% 〜 -20%% の範囲: 線形に 1.0 → 0.5
    - 直近 30 日累積 ROI が -20%% 未満: 0.5 固定 (最低保険)
    - 直近 30 日累積 ROI が 0%% 以上: 1.0 (フルサイズ)

    連敗単独でも警告: 直近 10 戦で 8 連敗以上 → multiplier 0.5 強制。
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        from config import DATA_DIR
        self.db_path = Path(db_path) if db_path else DATA_DIR / "bet_history.db"
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_DRAWDOWN_SCHEMA)

    def record_bet(
        self,
        race_id: str,
        horse_num: str,
        bet_size_yen: int,
        placed_at: str | None = None,
    ) -> None:
        """新規ベット記録 (race_id × horse_num で重複防止)。"""
        ts = placed_at or datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO bet_history "
                "(placed_at, race_id, horse_num, bet_size_yen) VALUES (?, ?, ?, ?)",
                (ts, race_id, horse_num, bet_size_yen),
            )

    def settle_bet(
        self,
        race_id: str,
        horse_num: str,
        payout_yen: int,
    ) -> None:
        """結果確定後に payout を記録。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE bet_history SET payout_yen=?, settled=1 "
                "WHERE race_id=? AND horse_num=?",
                (payout_yen, race_id, horse_num),
            )

    def recent_roi(self, days: int = 30) -> tuple[float, int]:
        """直近 N 日の (ROI, n_bets)。確定済のみ集計。"""
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT SUM(bet_size_yen), SUM(payout_yen), COUNT(*) "
                "FROM bet_history WHERE settled=1 AND placed_at >= ?",
                (since,),
            ).fetchone()
        if not row or not row[0]:
            return (0.0, 0)
        stake, payout, n = int(row[0]), int(row[1] or 0), int(row[2])
        return ((payout - stake) / stake if stake else 0.0, n)

    def recent_losses(self, last_n: int = 10) -> int:
        """直近 N 戦の連敗カウント (確定済のみ)。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT payout_yen FROM bet_history WHERE settled=1 "
                "ORDER BY placed_at DESC LIMIT ?",
                (last_n,),
            ).fetchall()
        return sum(1 for r in rows if not r[0] or r[0] == 0)

    def bet_size_multiplier(self) -> float:
        """drawdown / 連敗を反映した賭金スケーラ [0.5, 1.0]。

        Phase 7 仕様:
        - 直近 30 日 ROI が 0%% 以上: 1.0 (フル)
        - ROI -10%% 未満: 線形に 1.0 → 0.5 (-20%% で 0.5)
        - ROI -20%% 未満: 0.5 固定
        - 直近 10 戦で 8 敗以上: 0.5 強制 (連敗保護)
        """
        roi, n = self.recent_roi(days=30)
        if n < 5:
            return 1.0   # サンプル少 (= 退避明け / 開始期) はフルでもよい
        # 連敗トリガー
        losses = self.recent_losses(last_n=10)
        if losses >= 8:
            return 0.5
        # ROI 線形
        if roi >= 0:
            return 1.0
        if roi <= -0.20:
            return 0.5
        # -0.10 〜 -0.20 → 1.0 → 0.5 線形
        # roi=-0.10 → 1.0, roi=-0.20 → 0.5
        # ratio = (roi + 0.10) / -0.10 = (0.10 - |roi|) / 0.10... easier:
        # multiplier = 1.0 + (roi + 0.10) / 0.10 * (-0.5)
        # = 1.0 - 5 * (roi + 0.10)
        # at roi=-0.10: 1.0 - 0 = 1.0
        # at roi=-0.15: 1.0 - 0.25 = 0.75
        # at roi=-0.20: 1.0 - 0.50 = 0.5
        # ↑ roi が負の符号で間違える可能性 → 慎重に書く
        if roi > -0.10:
            return 1.0
        # roi ∈ [-0.20, -0.10) の線形
        return 0.5 + (roi + 0.20) / 0.10 * 0.5

    def should_suspend(self, monthly_threshold: float = -0.30) -> bool:
        """月次累積 ROI が threshold を下回ったらサスペンド推奨を返す。"""
        roi, n = self.recent_roi(days=30)
        return n >= 10 and roi <= monthly_threshold
