"""PIT (point-in-time) 市場状態の再構成 — live と backtest の共有入口。

改革 R1-1 (docs/REFORM_2026H2_MARKET_RESIDUAL.md 柱 1) の中核。

**なぜ必要か**: 現行の予想は `horse_races.win_odds` (最新 1 枚を UPDATE) を見る。
これは live では「今の最新オッズ」、backtest では「確定オッズ (発走後)」になり、
同じコードが別の情報を見る = train-serve skew の温床だった。実測された歪み:

- 朝 8-9 時生成の実運用: 市場人気加点の発火 0/367、オッズ保有 57.5%
- backtest (repair 適用後): 市場人気加点 1,171 頭発火、オッズ保有 99.7%
- → 「backtest 66.2%」は公開している朝の印の成績ではない (2026-08-22 検出)

本モジュールは「発走 T−n 分の時点で観測可能だった市場」を `odds_snapshots` から
再構成する。cutoff は**発走時刻から逆算**するので、live で何時に実行しても、
後日 backtest で再計算しても**同じ入力**になる (実行時刻に依存しない再現性)。

**fail-closed 規律** (F3 設計 §4.4): PIT 適格スナップショットが無い馬は
オッズを None にする。確定オッズ (odds_fetched_at IS NULL = 発走後) への
フォールバックは禁止 — それをやると発走後情報が発走前判断に混入する。
"""
from __future__ import annotations

import sqlite3

from predictor.pit_gate import pit_cutoff, usable_snapshots

# apply_pit_odds が書き換える列 (呼び出し側が把握できるよう明示)
PIT_OVERWRITTEN_KEYS = ("win_odds", "win_popularity", "odds_fetched_at", "odds_dataspec")


def latest_pit_odds(
    conn: sqlite3.Connection,
    race: dict,
    gate_minutes: int | None = None,
) -> dict[str, dict]:
    """馬番 -> PIT 適格な最新スナップショット。

    `predictor.pit_gate.usable_snapshots` (時刻昇順) を各馬の最後の 1 点に畳む。
    ゲートを通さない odds_snapshots の直読は禁止なので、必ず本関数を経由する。
    """
    out: dict[str, dict] = {}
    for snap in usable_snapshots(conn, race, gate_minutes):
        num = str(snap.get("horse_num") or "").strip()
        if not num:
            continue
        # 昇順なので後勝ちで「cutoff 以前の最新」になる
        out[num] = snap
    return out


def apply_pit_odds(
    conn: sqlite3.Connection,
    race: dict,
    horses: list[dict],
    gate_minutes: int | None = None,
) -> tuple[list[dict], dict]:
    """horses のオッズ列を「発走 T−n 分時点で観測可能だった値」に差し替える。

    Args:
        horses: `scripts.backtest.horses_for_race` 等が返す出走馬 dict のリスト。
                **破壊しない** (浅いコピーを返す)。
    Returns:
        (差し替え後の horses, coverage メタ)

    差し替え規則:
      - PIT 適格スナップがある馬 → その値 (win_odds / win_popularity /
        odds_fetched_at=snapshot 時刻 / odds_dataspec=source)
      - 無い馬 → **オッズを None にする** (fail-closed。確定オッズを流用しない)

    coverage メタは「市場情報がどれだけ観測できていたか」の記録用で、
    予想の解釈と SLO 監視に使う。
    """
    snaps = latest_pit_odds(conn, race, gate_minutes)
    cutoff = pit_cutoff(
        f"{race.get('race_year','')}{race.get('race_month_day','')}",
        race.get("start_time") or "",
        gate_minutes,
    )
    out: list[dict] = []
    covered = 0
    for h in horses:
        h2 = dict(h)
        num = str(h.get("horse_num") or "").strip()
        snap = snaps.get(num)
        if snap is not None and (snap.get("win_odds") or 0) > 0:
            h2["win_odds"] = snap.get("win_odds")
            h2["win_popularity"] = snap.get("win_popularity")
            h2["odds_fetched_at"] = snap.get("fetched_at")
            h2["odds_dataspec"] = snap.get("source")
            covered += 1
        else:
            # fail-closed: 発走後の確定オッズを発走前判断に混ぜない
            h2["win_odds"] = None
            h2["win_popularity"] = None
            h2["odds_fetched_at"] = None
            h2["odds_dataspec"] = None
        out.append(h2)

    total = len(horses)
    meta = {
        "pit_cutoff": cutoff,
        "horses_total": total,
        "horses_with_pit_odds": covered,
        "coverage": round(covered / total, 4) if total else 0.0,
        # レース単位の判定: 1 頭でも観測できていれば「市場情報あり」
        "has_market": covered > 0,
        # 最新スナップの時刻 (観測の鮮度。cutoff との差が実効リード時間)
        "latest_snapshot_at": max(
            (s.get("fetched_at") for s in snaps.values() if s.get("fetched_at")),
            default=None,
        ),
    }
    return out, meta


def summarize_coverage(metas: list[dict]) -> dict:
    """複数レースの coverage メタを集約する (SLO 監視・レポート用)。"""
    n = len(metas)
    with_market = sum(1 for m in metas if m.get("has_market"))
    horses_total = sum(m.get("horses_total") or 0 for m in metas)
    horses_covered = sum(m.get("horses_with_pit_odds") or 0 for m in metas)
    return {
        "races": n,
        "races_with_market": with_market,
        "races_market_rate": round(with_market / n, 4) if n else 0.0,
        "horses_total": horses_total,
        "horses_with_pit_odds": horses_covered,
        "horses_coverage": round(horses_covered / horses_total, 4) if horses_total else 0.0,
    }
