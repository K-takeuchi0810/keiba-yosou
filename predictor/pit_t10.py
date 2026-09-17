"""T−10 の唯一の選択規則と、その PIT 監査 (憲法 Phase 0.5-1)。

## 規則 (1 本化)

1. 基準時刻は **その時点で認識していた最新の予定発走時刻**。
   結果を知ってから実際の発走時刻で逆算してはいけない。
2. `decision_time = known_start_time − 10 分`
3. 採用するオッズは `data_received_at <= decision_time` を満たす **最新値**。
4. `decision_time` より後のオッズを「近いから」という理由で採用しない。
5. 該当データが無ければ **欠損**。後続値で補完しない。

## 発走時刻変更の扱い

`start_time_changes` は「いつ発表されたか (announced_time)」と
「新しい発走時刻 (new_start_time)」を持つ。ある瞬間 t に我々が知っていた
発走時刻は「t 以前に発表された変更のうち最新のもの」。

決定時刻は発走時刻から決まり、発走時刻は決定時刻に何を知っていたかで決まる
ので循環する。次のように解く:

    S ← 当初の予定発走時刻
    繰り返し:
        T ← S − 10 分
        S' ← T 以前に発表された変更のうち最新の new_start_time (無ければ S)
        S' == S なら終了、そうでなければ S ← S'

例: 当初 15:40 (T=15:30)。15:28 に 15:45 へ変更 → 15:28 ≤ 15:30 なので
既知 → S=15:45, T=15:35。15:35 以前の変更は同じなので確定。
逆に変更の発表が 15:38 なら、15:30 の時点では知らないので T=15:30 のまま。

## 監査

各サンプルについて次を検査する。**違反は黙って除外せず、まず失敗させる**。
黙って除外するとデータ品質の問題が見えなくなる。

- `odds_received_at <= decision_time`
- `odds_observed_at <= decision_time` (提供元の発表時刻。分かる場合のみ)
- `start_time_used` が `decision_time` 時点で既知
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config import PIT_GATE_MINUTES

RACE_KEYS = ("race_year", "race_month_day", "track_code", "kaiji", "nichiji",
             "race_num")


def _parse_hhmm(date8: str, hhmm: str) -> datetime | None:
    raw = (hhmm or "").strip()
    if len(raw) != 4 or not raw.isdigit() or len(date8) != 8 or not date8.isdigit():
        return None
    h, m = int(raw[:2]), int(raw[2:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return datetime(int(date8[:4]), int(date8[4:6]), int(date8[6:]), h, m)


def _parse_announced(date8: str, mmddhhmm: str) -> datetime | None:
    """発表時刻 MMDDHHMM を、そのレース日の年に載せて datetime にする。

    年をまたぐ開催は JRA に無いが、12/31 → 01/01 のような値が来たら None にして
    安全側に倒す (不明な時刻を「既知」と扱わない)。
    """
    raw = (mmddhhmm or "").strip()
    if len(raw) != 8 or not raw.isdigit() or len(date8) != 8:
        return None
    mm, dd, hh, mi = raw[:2], raw[2:4], raw[4:6], raw[6:]
    try:
        dt = datetime(int(date8[:4]), int(mm), int(dd), int(hh), int(mi))
    except ValueError:
        return None
    race_day = datetime(int(date8[:4]), int(date8[4:6]), int(date8[6:]))
    # 発表はレース当日か前日まで。それ以上離れていたら年またぎ等の異常とみなす。
    if not (timedelta(days=-2) <= dt - race_day <= timedelta(days=1)):
        return None
    return dt


@dataclass
class StartTimeHistory:
    """そのレースについて「いつ何を知っていたか」。"""

    scheduled: datetime | None                    # 当初の予定発走時刻
    changes: list[tuple[datetime, datetime]] = field(default_factory=list)
    # (発表時刻, 新しい発走時刻) の昇順

    def known_at(self, moment: datetime) -> datetime | None:
        """moment の時点で認識していた予定発走時刻。"""
        known = self.scheduled
        for announced, new_start in self.changes:
            if announced <= moment:
                known = new_start
            else:
                break
        return known


def start_time_history(conn: sqlite3.Connection, race: dict) -> StartTimeHistory:
    """発走時刻の履歴を組み立てる。

    `races.start_time` は **変更後の現在値** なので、そのままでは「当初の予定」に
    ならない。start_time_changes の最も古い old_start_time があればそれを当初値と
    し、無ければ現在値を当初値とみなす。
    """
    date8 = f"{race.get('race_year', '')}{race.get('race_month_day', '')}"
    rows = conn.execute(
        """SELECT announced_time, new_start_time, old_start_time
             FROM start_time_changes
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
            ORDER BY announced_time""",
        tuple(race.get(k) for k in RACE_KEYS)).fetchall()

    changes: list[tuple[datetime, datetime]] = []
    scheduled = _parse_hhmm(date8, race.get("start_time") or "")
    if rows:
        first_old = _parse_hhmm(date8, str(rows[0][2] or ""))
        if first_old is not None:
            scheduled = first_old
        for announced_time, new_start, _old in rows:
            a = _parse_announced(date8, str(announced_time or ""))
            n = _parse_hhmm(date8, str(new_start or ""))
            if a is not None and n is not None:
                changes.append((a, n))
    return StartTimeHistory(scheduled=scheduled, changes=changes)


def decision_time(conn: sqlite3.Connection, race: dict,
                  gate_minutes: int | None = None) -> tuple[datetime | None,
                                                            datetime | None]:
    """(決定時刻, そのとき認識していた発走時刻) を返す。

    発走時刻が不明なら (None, None)。循環は反復で解く (最大 5 回で収束する)。
    """
    minutes = PIT_GATE_MINUTES if gate_minutes is None else gate_minutes
    hist = start_time_history(conn, race)
    start = hist.scheduled
    if start is None:
        return (None, None)
    for _ in range(5):
        target = start - timedelta(minutes=minutes)
        known = hist.known_at(target)
        if known is None or known == start:
            return (target, start)
        start = known
    return (start - timedelta(minutes=minutes), start)


@dataclass
class T10Market:
    """T−10 時点の市場状態。憲法 Phase 0.5-2 が保存を求める項目を持つ。"""

    race_id: str
    decision_time: str
    start_time_used: str
    odds: dict[str, float]                  # 馬番 → 単勝オッズ (倍)
    implied: dict[str, float]               # 馬番 → T-10 Market Implied Probability
    market_rank: dict[str, int]             # 馬番 → 市場での順位 (1 = 最低オッズ)
    # 正規化前の Σ(1/odds)。**固定オッズ市場の overround とは同義ではない**。
    # JRA はパリミュチュエルで、オッズは投票総額から事後的に決まる。
    # ブックメーカーが利鞘として上乗せするマージンとは成り立ちが違うので、
    # 中立的に「逆オッズの総和」と呼ぶ (2026-09-18 ユーザ指摘)。
    inverse_odds_mass: float
    odds_received_at: str                   # 採用したスナップの受信時刻
    odds_observed_at: str | None            # 提供元が示す発表時刻 (分かる場合)
    n_horses: int
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations and bool(self.implied)


def t10_market(conn: sqlite3.Connection, race: dict,
               gate_minutes: int | None = None) -> T10Market | None:
    """T−10 時点の市場を、唯一の規則で組み立てる。

    データが無ければ None (欠損)。**後続値で補完しない**。
    規則違反があっても None にはせず、violations に入れて返す
    (黙って除外するとデータ品質の問題が見えなくなるため)。
    """
    target, start_used = decision_time(conn, race, gate_minutes)
    if target is None:
        return None
    date8 = f"{race.get('race_year', '')}{race.get('race_month_day', '')}"
    cutoff = target.isoformat(timespec="seconds")

    # `data_received_at <= decision_time` を満たす最新の 1 枚を選ぶ。
    # 「決定時刻に最も近い」ではなく「決定時刻以前で最新」。
    row = conn.execute(
        """SELECT MAX(fetched_at) FROM odds_snapshots
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND fetched_at IS NOT NULL AND fetched_at <= ?""",
        (*[race.get(k) for k in RACE_KEYS], cutoff)).fetchone()
    if row is None or not row[0]:
        return None
    received_at = str(row[0])

    rows = conn.execute(
        """SELECT horse_num, win_odds, announced_at FROM odds_snapshots
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=? AND fetched_at=?
              AND win_odds > 0""",
        (*[race.get(k) for k in RACE_KEYS], received_at)).fetchall()
    if not rows:
        return None

    odds = {str(r[0]).strip(): r[1] / 10.0 for r in rows}
    observed_raw = next((str(r[2]) for r in rows if r[2]), None)

    raw = {h: 1.0 / o for h, o in odds.items() if o > 0}
    inverse_odds_mass = sum(raw.values())
    implied = ({h: v / inverse_odds_mass for h, v in raw.items()}
               if inverse_odds_mass > 0 else {})
    ranked = sorted(odds, key=lambda h: odds[h])
    market_rank = {h: i + 1 for i, h in enumerate(ranked)}

    violations: list[str] = []
    if received_at > cutoff:
        violations.append(
            f"受信時刻 {received_at} が決定時刻 {cutoff} より後")
    observed_dt = _parse_announced(date8, observed_raw or "")
    if observed_raw and observed_dt is None:
        violations.append(f"発表時刻 {observed_raw!r} を解釈できない")
    elif observed_dt is not None and observed_dt > target:
        violations.append(
            f"発表時刻 {observed_dt.isoformat()} が決定時刻 {cutoff} より後")
    hist = start_time_history(conn, race)
    if start_used is not None and hist.known_at(target) != start_used:
        violations.append(
            f"使った発走時刻 {start_used.isoformat()} が決定時刻に既知でない")

    return T10Market(
        race_id="-".join(str(race.get(k)) for k in RACE_KEYS),
        decision_time=cutoff,
        start_time_used=start_used.isoformat(timespec="minutes") if start_used else "",
        odds=odds, implied=implied, market_rank=market_rank,
        inverse_odds_mass=inverse_odds_mass,
        odds_received_at=received_at,
        odds_observed_at=observed_dt.isoformat(timespec="minutes") if observed_dt else None,
        n_horses=len(odds), violations=violations,
    )
