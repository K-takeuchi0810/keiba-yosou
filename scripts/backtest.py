"""指定期間のレースで予想を実行し、的中率・回収率を計算する。

usage:
    python -m scripts.backtest --from 20240101 --to 20241231
    python -m scripts.backtest --from 20240101 --to 20241231 --bet fuku

買い目戦略:
    tan  : ◎ (印 1 位) を単勝 100 円
    fuku : ◎ (印 1 位) を複勝 100 円
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

from db import open_db
from predictor.calibration import (
    calibration_report,
    fit_bin_calibrator,
    fit_isotonic_calibrator,
)
from predictor.rules import is_tentative, predict_race


def _snapshot_meta() -> dict:
    """backtest 実行時の calibrator / LGBM / git の version snapshot を返す。

    P17 A2 Step 0 (2026-05-17): backtest JSON top-level に `meta` フィールドを
    保存し、「この backtest 結果は どの calibrator と LGBM で出した数値か」
    を後追いで再現可能にする。validation-process-auditor の S1 1st review
    での指摘 (rule_version は管理されているが配下バージョンが追跡できない)
    への対応。
    """
    root = Path(__file__).resolve().parent.parent
    meta: dict = {}
    # calibrator
    try:
        cal = json.loads((root / "predictor" / "calibrator.json").read_text(encoding="utf-8"))
        meta["calibrator_type"] = cal.get("type")
        meta["calibrator_rule_version"] = cal.get("rule_version")
        meta["calibrator_generated_at"] = cal.get("generated_at")
        meta["calibrator_trained_from"] = cal.get("trained_from")
        meta["calibrator_trained_to"] = cal.get("trained_to")
        meta["calibrator_source_count"] = cal.get("source_count")
    except (OSError, json.JSONDecodeError):
        meta["calibrator_type"] = None
    # LGBM
    try:
        lgbm = json.loads((root / "predictor" / "lgbm_meta.json").read_text(encoding="utf-8"))
        meta["lgbm_rule_version"] = lgbm.get("rule_version")
        meta["lgbm_generated_at"] = lgbm.get("generated_at")
        meta["lgbm_trained_from"] = lgbm.get("trained_from")
        meta["lgbm_trained_to"] = lgbm.get("trained_to")
        meta["lgbm_val_brier"] = lgbm.get("val_brier")
    except (OSError, json.JSONDecodeError):
        meta["lgbm_rule_version"] = None
    # git
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).strip().decode("ascii")
        meta["git_sha"] = sha
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        meta["git_sha"] = None
    return meta


def buy_filter_from_generator() -> dict:
    """買い目フィルタの既定値を取得する。

    出典は `config.BUY_FILTER_DEFAULT` 単一。`min_ev` `min_value` は
    None (= 制約なし) を許容するため、float 変換時に None を温存する。
    """
    from config import BUY_FILTER_DEFAULT

    def _maybe_float(v):
        return float(v) if v is not None else None

    return {
        "min_odds": _maybe_float(BUY_FILTER_DEFAULT.get("min_odds")),
        "max_odds": _maybe_float(BUY_FILTER_DEFAULT.get("max_odds")),
        "min_value": _maybe_float(BUY_FILTER_DEFAULT.get("min_value")),
        "min_ev": _maybe_float(BUY_FILTER_DEFAULT.get("min_ev")),
        "min_kelly": _maybe_float(BUY_FILTER_DEFAULT.get("min_kelly")),
        "max_predicted_p": _maybe_float(BUY_FILTER_DEFAULT.get("max_predicted_p")),
        "min_popularity": BUY_FILTER_DEFAULT.get("min_popularity"),
        "max_popularity": BUY_FILTER_DEFAULT.get("max_popularity"),
        "exclude_confidence": list(BUY_FILTER_DEFAULT.get("exclude_confidence") or []),
    }


def distance_bucket_label(distance: int | None) -> str:
    """RA.distance を 4 バケットに集約 (predictor/_distance_bucket と揃える)。"""
    d = distance or 0
    if d <= 1400:
        return "sprint"
    if d <= 1800:
        return "mile"
    if d <= 2200:
        return "middle"
    return "long"


def race_class_label(grade_code: str | None) -> str:
    """RA.grade_code をバックテスト集計用クラスにマップ。

    JV-Data 2003 グレードコード:
      A=G1, B=G2, C=G3, D=重賞以外, E=リステッド/OP特別, F=重賞,
      G=J·G1, H=J·G2, I=J·G3, L=リステッド (新)
    今回は予想精度の弱点 (OP/重賞) を切り出すために以下に集約:
      graded  : A,B,C,F (中央平地重賞)
      jraded  : G,H,I (障害重賞)
      op      : D,E,L (リステッド/オープン特別)
      cond    : それ以外 (条件戦・未勝利・新馬・1 勝クラス〜3 勝クラス)
    """
    g = (grade_code or "").strip()
    if g in ("A", "B", "C", "F"):
        return "graded"
    if g in ("G", "H", "I"):
        return "jraded"
    if g in ("D", "E", "L"):
        return "op"
    return "cond"


def list_races(
    conn,
    from_date: str,
    to_date: str,
    jra_only: bool = True,
    min_distance: int | None = None,
    max_distance: int | None = None,
) -> list[dict]:
    """jra_only=True なら中央場 (track_code 01-10) のみ。
    地方場と海外は JV-Data の RACE dataspec で払戻が来ないので除外しないと
    回収率が引きずり落とされる。
    """
    sql = """
        SELECT * FROM races
        WHERE (race_year || race_month_day) BETWEEN ? AND ?
    """
    if jra_only:
        sql += " AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10 "
    params: list = [from_date, to_date]
    if min_distance is not None:
        sql += " AND distance >= ? "
        params.append(min_distance)
    if max_distance is not None:
        sql += " AND distance <= ? "
        params.append(max_distance)
    sql += " ORDER BY race_year, race_month_day, track_code, race_num "
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def horses_for_race(conn, race: dict) -> list[dict]:
    """1 レースの出走馬を返す。horse_num が空 / "00" のプレースホルダ行は除外。

    JV-Data 上で出馬表確定前は SE レコードに馬番が入らない / "00" のことが
    あるが、表示・予想・回収率計算のいずれにも有害なので根元で弾く。
    """
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND horse_num IS NOT NULL
              AND TRIM(horse_num) != ''
              AND horse_num != '00'
            ORDER BY CAST(horse_num AS INTEGER)
            """,
            (
                race["race_year"], race["race_month_day"], race["track_code"],
                race["kaiji"], race["nichiji"], race["race_num"],
            ),
        ).fetchall()
    ]


def get_payout(conn, race: dict, horse_num: str, bet_type: str) -> int:
    """馬番が的中していれば払戻金を返す、外れなら 0。

    payouts テーブルは 1 レース 1 行で、同着考慮で配当 1〜3 (単勝) / 1〜5 (複勝) を持つ。
    horse_num の払戻があるかを順に照合する。
    """
    row = conn.execute(
        """
        SELECT * FROM payouts
        WHERE race_year=? AND race_month_day=? AND track_code=?
          AND kaiji=? AND nichiji=? AND race_num=?
        """,
        (
            race["race_year"], race["race_month_day"], race["track_code"],
            race["kaiji"], race["nichiji"], race["race_num"],
        ),
    ).fetchone()
    if not row:
        return 0
    row = dict(row)
    if bet_type == "tan":
        for i in (1, 2, 3):
            if row.get(f"tan_horse_num{i}") == horse_num:
                return row.get(f"tan_payout{i}") or 0
    elif bet_type == "fuku":
        for i in (1, 2, 3, 4, 5):
            if row.get(f"fuku_horse_num{i}") == horse_num:
                return row.get(f"fuku_payout{i}") or 0
    return 0


def _empty_bet_stats() -> dict:
    return {
        "bets": 0,
        "hits": 0,
        "bet_total": 0,
        "return_total": 0,
        "_payouts": [],
        "_stakes": [],
    }


def _add_bet(stats: dict, payout: int) -> None:
    stats["bets"] += 1
    stats["bet_total"] += 100
    stats["_stakes"].append(100)
    stats["_payouts"].append(payout if payout > 0 else 0)
    if payout > 0:
        stats["hits"] += 1
        stats["return_total"] += payout


def _finish_bet_stats(stats: dict) -> dict:
    """終了処理: hit_rate / return_rate / profit + Phase 4 (2026-05-13) CI を計算。

    n=41 戦 4 ヒット (旧 wl_odds_8_20 採用判断) の点推定 116.1% は CI 下限が
    8% / 上限 224% と幅広く、本番投入判断に不適。Wilson 95% CI と
    bootstrap return rate CI を必ず添えるようにする。
    """
    from predictor.stats import wilson_ci, bootstrap_return_rate
    bets = stats["bets"]
    bet_total = stats["bet_total"]
    payouts = stats.pop("_payouts", []) or []
    stakes = stats.pop("_stakes", []) or []
    hit_lo, hit_hi = wilson_ci(stats["hits"], bets) if bets else (0.0, 0.0)
    if bets and payouts and stakes:
        ret_point, ret_lo, ret_hi = bootstrap_return_rate(payouts, stakes, n_resample=1000)
    else:
        ret_point, ret_lo, ret_hi = (0.0, 0.0, 0.0)
    return {
        **stats,
        "hit_rate": (stats["hits"] / bets) if bets else 0,
        "return_rate": (stats["return_total"] / bet_total) if bet_total else 0,
        "profit": stats["return_total"] - bet_total,
        "hit_rate_ci95": [round(hit_lo, 4), round(hit_hi, 4)],
        "return_rate_ci95": [round(ret_lo, 4), round(ret_hi, 4)],
    }


def _matches_buy_filter(
    pred,
    horse: dict,
    tentative: bool,
    spec: dict | None,
    race: dict | None = None,
) -> bool:
    """買い目フィルタ判定。S7-α-2 (2026-05-18) で `predictor.filter.is_buy_candidate` に集約。

    spec=None の場合は False (backtest の `--no-filter-from-config` モード等で
    spec を渡さない場合、フィルタ通過させない既存仕様を維持)。
    spec ありの場合は集約関数に委譲。判定ロジック差異は集約モジュールで吸収。

    `pred.mark` は backtest 経路では存在しないので、ここでは集約関数の
    「rank==1 + mark あり + 非 tentative」のうち mark チェックを skip 相当に。
    既存挙動 (rank==1 + 非 tentative のみ) を維持するため、別経路で集約関数を
    呼ぶ前に rank/tentative を pre-check する。
    """
    if not spec:
        return False
    # 既存 backtest は pred.mark が空でも rank==1 なら通していた。
    # 集約関数は mark 必須なので、ここで rank/tentative のみ事前判定し、
    # 集約関数の mark チェックを bypass するために mark を一時付与しない形で
    # 呼ぶことはせず、集約関数の本体を直接呼ぶ。
    # ただ実態として predict_race の preds[0] は mark を持つので、mark 必須は問題なし。
    from predictor.filter import is_buy_candidate
    return is_buy_candidate(pred, horse, tentative, race=race, filter_spec=spec)


def run_backtest(
    from_date: str,
    to_date: str,
    bet_type: str = "tan",
    skip_tentative: bool = True,
    jra_only: bool = True,
    min_odds: float | None = None,
    max_odds: float | None = None,
    min_popularity: int | None = None,
    max_popularity: int | None = None,
    filter_from_config: bool = False,
    min_value: float | None = None,
    min_ev: float | None = None,
    min_distance: int | None = None,
    max_distance: int | None = None,
    db_path: str | Path | None = None,
    progress_every: int = 200,
) -> dict:
    started = time.time()
    buy_filter = buy_filter_from_generator() if filter_from_config else None
    if buy_filter is not None:
        if min_odds is not None:
            buy_filter["min_odds"] = min_odds
        if max_odds is not None:
            buy_filter["max_odds"] = max_odds
        if min_value is not None:
            buy_filter["min_value"] = min_value
        if min_ev is not None:
            buy_filter["min_ev"] = min_ev
    with open_db(db_path) if db_path else open_db() as conn:
        races = list_races(
            conn,
            from_date,
            to_date,
            jra_only=jra_only,
            min_distance=min_distance,
            max_distance=max_distance,
        )

        n_total_races = len(races)
        n_no_horses = 0
        n_no_pick = 0
        n_filtered = 0
        n_tentative_skipped = 0
        n_bet = 0
        n_hit = 0
        total_bet = 0
        total_return = 0
        all_stats = _empty_bet_stats()
        buy_only_stats = _empty_bet_stats()
        # 重賞ホワイトリスト単独 (EV/Odds フィルタ無視) で◎単勝ベタ買いした
        # 場合の集計。「whitelist だけで控除率超えるか」を測るための指標。
        whitelist_only_stats = _empty_bet_stats()
        calibration_records: list[dict] = []
        confidence_stats: dict[str, dict] = defaultdict(_empty_bet_stats)
        # 会場別ブレイクダウン (track_code → [bet, return, hits])
        track_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        # グレード別 (graded/op/cond/jraded) ブレイクダウン
        class_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        # 距離バケット別 (sprint/mile/middle/long) ブレイクダウン
        bucket_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        feature_cache: dict = {}

        for i, race in enumerate(races, 1):
            if progress_every and i % progress_every == 0:
                elapsed = time.time() - started
                rate = i / elapsed if elapsed > 0 else 0
                print(
                    f"  [{i}/{n_total_races}] {rate:.1f} races/s ...",
                    file=sys.stderr,
                    flush=True,
                )

            horses = horses_for_race(conn, race)
            if not horses:
                n_no_horses += 1
                continue

            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            tentative = is_tentative(preds)
            if skip_tentative and tentative:
                n_tentative_skipped += 1
                continue

            top = next((p for p in preds if p.rank == 1 and p.mark), None)
            if not top:
                n_no_pick += 1
                continue

            top_horse = next((h for h in horses if h.get("horse_num") == top.horse_num), None)
            if not top_horse:
                n_no_pick += 1
                continue
            horse_by_num = {h.get("horse_num"): h for h in horses}
            for pred in preds:
                horse = horse_by_num.get(pred.horse_num)
                if not horse:
                    continue
                # P17 A2 c1 (2026-05-17): calibrator fit 入力を切替え。
                # 旧: `pred.win_probability` (= investment_probability、
                #     calibrator + market_blend + odds_discount 適用後、race 内非正規化)
                # 新: `pred.raw_blended_probability` (= LGBM blend 直後、calibrator
                #     適用前、race 内 Σ=1 正規化済)
                # 旧 win_probability は `investment_probability` フィールドに保持
                # (後方互換・後追い分析用)。
                calibration_records.append(
                    {
                        "probability": pred.raw_blended_probability,
                        "investment_probability": pred.win_probability,
                        "actual": 1 if horse.get("confirmed_order") == 1 else 0,
                        "confidence": pred.confidence,
                    }
                )
            payout = get_payout(conn, race, top.horse_num, bet_type)
            _add_bet(all_stats, payout)
            _add_bet(confidence_stats[top.confidence], payout)
            if _matches_buy_filter(top, top_horse, tentative, buy_filter, race=race):
                _add_bet(buy_only_stats, payout)
            # 重賞ホワイトリスト単独 (EV/Odds 等のフィルタ無視) でのベタ買い結果。
            # 暫定だけは除外。BET_WHITELIST=0 のときは is_whitelisted_race が
            # 常に True を返すので、この集計は all_stats と同等になる。
            from config import is_whitelisted_race  # 循環回避のため局所 import
            if not tentative and is_whitelisted_race(race):
                _add_bet(whitelist_only_stats, payout)
            if top_horse:
                odds = (top_horse.get("win_odds") or 0) / 10.0
                popularity = top_horse.get("win_popularity") or 0
                if min_odds is not None and (odds <= 0 or odds < min_odds):
                    n_filtered += 1
                    continue
                if max_odds is not None and (odds <= 0 or odds > max_odds):
                    n_filtered += 1
                    continue
                if min_popularity is not None and (popularity <= 0 or popularity < min_popularity):
                    n_filtered += 1
                    continue
                if max_popularity is not None and (popularity <= 0 or popularity > max_popularity):
                    n_filtered += 1
                    continue

            n_bet += 1
            total_bet += 100
            tcode = race["track_code"]
            cclass = race_class_label(race.get("grade_code"))
            bucket = distance_bucket_label(race.get("distance"))
            track_stats[tcode][0] += 100
            class_stats[cclass][0] += 100
            bucket_stats[bucket][0] += 100
            if payout > 0:
                n_hit += 1
                total_return += payout
                track_stats[tcode][1] += payout
                track_stats[tcode][2] += 1
                class_stats[cclass][1] += payout
                class_stats[cclass][2] += 1
                bucket_stats[bucket][1] += payout
                bucket_stats[bucket][2] += 1

    elapsed = time.time() - started
    all_stats = _finish_bet_stats(all_stats)
    buy_only_stats = _finish_bet_stats(buy_only_stats)
    whitelist_only_stats = _finish_bet_stats(whitelist_only_stats)
    by_confidence = {
        k: _finish_bet_stats(v)
        for k, v in sorted(confidence_stats.items())
    }
    meta = _snapshot_meta()
    # 評価期間が calibrator の fit 期間と重なる場合は in-sample 評価として
    # 明示フラグを立てる (2026-06-13 v2 監査: 2025val 評価が calibrator fit
    # 期間 (2025 通年) 内で行われ「独立 dataset」と誤認されていた)。
    # Brier 等の calibration 指標は in-sample では証拠力が無い。
    calibration_in_sample = False
    ctf, ctt = meta.get("calibrator_trained_from"), meta.get("calibrator_trained_to")
    if ctf and ctt and from_date <= str(ctt) and str(ctf) <= to_date:
        calibration_in_sample = True
        logger.warning(
            "評価期間 %s-%s は calibrator fit 期間 %s-%s と重複しています。"
            "calibration 指標 (Brier 等) は in-sample であり証拠力がありません。",
            from_date, to_date, ctf, ctt)
    return {
        "from_date": from_date,
        "to_date": to_date,
        "bet_type": bet_type,
        "elapsed_sec": round(elapsed, 1),
        # P17 A2 Step 0: 実行時の calibrator / LGBM / git_sha を snapshot。
        # backtest 結果単体で「どの校正器・モデルで出した数字か」を再現可能。
        "meta": meta,
        "calibration_in_sample": calibration_in_sample,
        "races_total": n_total_races,
        "races_no_horses": n_no_horses,
        "races_no_pick": n_no_pick,
        "races_filtered": n_filtered,
        "races_tentative_skipped": n_tentative_skipped,
        "races_bet": n_bet,
        "hits": n_hit,
        "hit_rate": (n_hit / n_bet) if n_bet else 0,
        "bet_total": total_bet,
        "return_total": total_return,
        "return_rate": (total_return / total_bet) if total_bet else 0,
        "all_bets": all_stats["bets"],
        "all_hits": all_stats["hits"],
        "all_hit_rate": all_stats["hit_rate"],
        "all_return_total": all_stats["return_total"],
        "all_return_rate": all_stats["return_rate"],
        "all_hit_rate_ci95": all_stats.get("hit_rate_ci95"),
        "all_return_rate_ci95": all_stats.get("return_rate_ci95"),
        "buy_only_bets": buy_only_stats["bets"],
        "buy_only_hits": buy_only_stats["hits"],
        "buy_only_hit_rate": buy_only_stats["hit_rate"],
        "buy_only_return_total": buy_only_stats["return_total"],
        "buy_only_return_rate": buy_only_stats["return_rate"],
        # Phase 4 (2026-05-13): Wilson hit_rate / bootstrap return_rate の 95% CI。
        # n が小さいほど CI 広く、点推定だけでの本番投入判断を防ぐ。
        "buy_only_hit_rate_ci95": buy_only_stats.get("hit_rate_ci95"),
        "buy_only_return_rate_ci95": buy_only_stats.get("return_rate_ci95"),
        # ホワイトリスト単独 (EV/Odds フィルタ無視) で◎単勝ベタ買いの結果。
        # config.BUY_FILTER_DEFAULT.whitelist_tracks の場 (現 07=中京 / 09=阪神)
        # で重賞のみ買ったときの結果。「特定 2 場の重賞ベタ買いで勝てるか」の指標。
        "whitelist_only_bets": whitelist_only_stats["bets"],
        "whitelist_only_hits": whitelist_only_stats["hits"],
        "whitelist_only_hit_rate": whitelist_only_stats["hit_rate"],
        "whitelist_only_return_total": whitelist_only_stats["return_total"],
        "whitelist_only_return_rate": whitelist_only_stats["return_rate"],
        "whitelist_only_hit_rate_ci95": whitelist_only_stats.get("hit_rate_ci95"),
        "whitelist_only_return_rate_ci95": whitelist_only_stats.get("return_rate_ci95"),
        "calibration": calibration_report(calibration_records),
        "calibrator": fit_bin_calibrator(calibration_records),
        "_calibration_records": calibration_records,  # 内部用 (--save 時には除外したい)
        "by_confidence": by_confidence,
        "filters": {
            "min_odds": min_odds,
            "max_odds": max_odds,
            "min_popularity": min_popularity,
            "max_popularity": max_popularity,
            "min_distance": min_distance,
            "max_distance": max_distance,
        },
        "buy_filter": buy_filter,
        "by_track": {
            tc: {
                "bet": v[0],
                "return": v[1],
                "hits": v[2],
                "return_rate": (v[1] / v[0]) if v[0] else 0,
            }
            for tc, v in sorted(track_stats.items())
        },
        "by_class": {
            cc: {
                "bet": v[0],
                "return": v[1],
                "hits": v[2],
                "return_rate": (v[1] / v[0]) if v[0] else 0,
            }
            for cc, v in sorted(class_stats.items())
        },
        "by_bucket": {
            b: {
                "bet": v[0],
                "return": v[1],
                "hits": v[2],
                "return_rate": (v[1] / v[0]) if v[0] else 0,
            }
            for b, v in sorted(bucket_stats.items())
        },
    }


def format_report(r: dict) -> str:
    lines = []
    lines.append("==== バックテスト結果 ====")
    lines.append(f"期間:           {r['from_date']} 〜 {r['to_date']}")
    lines.append(f"買い目:         ◎{r['bet_type']} 100 円固定")
    lines.append(f"処理時間:       {r['elapsed_sec']} 秒")
    lines.append("")
    lines.append(f"対象レース:     {r['races_total']:,}")
    lines.append(f"  出走馬不足:   {r['races_no_horses']:,}")
    lines.append(f"  暫定スキップ: {r['races_tentative_skipped']:,}")
    lines.append(f"  ◎付かず:      {r['races_no_pick']:,}")
    lines.append(f"  条件外:        {r.get('races_filtered', 0):,}")
    lines.append(f"  実際に賭けた: {r['races_bet']:,}")
    lines.append("")
    lines.append(f"的中数:         {r['hits']:,}")
    lines.append(f"的中率:         {r['hit_rate'] * 100:.1f} %")
    lines.append(f"投資総額:       {r['bet_total']:,} 円")
    lines.append(f"払戻総額:       {r['return_total']:,} 円")
    lines.append(f"回収率:         {r['return_rate'] * 100:.1f} %")
    lines.append(f"収支:           {r['return_total'] - r['bet_total']:+,} 円")
    lines.append("")
    lines.append("運用別:")
    lines.append(
        f"  ベタ買い:   {r.get('all_bets', 0):,} 点  的中 {r.get('all_hits', 0):,}  "
        f"回収率 {r.get('all_return_rate', 0) * 100:.1f}%"
    )
    lines.append(
        f"  絞り運用:   {r.get('buy_only_bets', 0):,} 点  的中 {r.get('buy_only_hits', 0):,}  "
        f"回収率 {r.get('buy_only_return_rate', 0) * 100:.1f}%"
    )
    lines.append(
        f"  WL単独:     {r.get('whitelist_only_bets', 0):,} 点  的中 {r.get('whitelist_only_hits', 0):,}  "
        f"回収率 {r.get('whitelist_only_return_rate', 0) * 100:.1f}%  (重賞+WL場ベタ買い)"
    )
    cal = r.get("calibration") or {}
    if cal.get("count"):
        lines.append("")
        lines.append(
            f"確率校正:       Brier {cal.get('brier_score')}  LogLoss {cal.get('log_loss')}  "
            f"n={cal.get('count'):,}"
        )
    if r.get("by_confidence"):
        lines.append("")
        lines.append("confidence別:")
        for name, v in r["by_confidence"].items():
            lines.append(
                f"  {name}: {v['bets']:,} 点  的中 {v['hits']:,} "
                f"({v['hit_rate'] * 100:.1f}%)  回収率 {v['return_rate'] * 100:.1f}%"
            )
    if r["by_track"]:
        lines.append("")
        lines.append("会場別:")
        for tc, v in r["by_track"].items():
            n_bet = v["bet"] // 100
            hit_rate = (v["hits"] / n_bet) if n_bet else 0
            lines.append(
                f"  場{tc}: {n_bet:,} 戦  的中 {v['hits']:,} ({hit_rate * 100:.1f}%)  "
                f"回収率 {v['return_rate'] * 100:.1f}%"
            )
    if r.get("by_class"):
        labels = {
            "graded": "G1/G2/G3",
            "op":     "L/OP特",
            "jraded": "障害重賞",
            "cond":   "条件戦等",
        }
        lines.append("")
        lines.append("クラス別:")
        for cc, v in r["by_class"].items():
            n_bet = v["bet"] // 100
            hit_rate = (v["hits"] / n_bet) if n_bet else 0
            label = labels.get(cc, cc)
            lines.append(
                f"  {label:<10} {n_bet:>5,} 戦  的中 {v['hits']:>4,} ({hit_rate * 100:5.1f}%)  "
                f"回収率 {v['return_rate'] * 100:5.1f}%"
            )
    if r.get("by_bucket"):
        bucket_labels = {
            "sprint": "短距離 <=1400",
            "mile":   "マイル <=1800",
            "middle": "中距離 <=2200",
            "long":   "長距離 >2200",
        }
        order = ["sprint", "mile", "middle", "long"]
        lines.append("")
        lines.append("距離別:")
        for b in order:
            v = r["by_bucket"].get(b)
            if not v:
                continue
            n_bet = v["bet"] // 100
            hit_rate = (v["hits"] / n_bet) if n_bet else 0
            label = bucket_labels.get(b, b)
            lines.append(
                f"  {label:<14} {n_bet:>5,} 戦  的中 {v['hits']:>4,} ({hit_rate * 100:5.1f}%)  "
                f"回収率 {v['return_rate'] * 100:5.1f}%"
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    ap.add_argument("--bet", default="tan", choices=["tan", "fuku"])
    ap.add_argument(
        "--include-tentative", action="store_true",
        help="暫定（予想根拠不足）レースもベット対象にする",
    )
    ap.add_argument(
        "--all-tracks", action="store_true",
        help="地方場・海外含めて評価（payouts 未取得分は外れ扱いになるので注意）",
    )
    ap.add_argument("--min-odds", type=float, default=None)
    ap.add_argument("--max-odds", type=float, default=None)
    ap.add_argument(
        "--no-filter-from-config",
        action="store_true",
        help="buy_only_* の集計を無効化する (P0-4 以降は config の買い目フィルタが既定 ON)",
    )
    ap.add_argument("--min-value", type=float, default=None)
    ap.add_argument("--min-ev", type=float, default=None)
    ap.add_argument("--min-popularity", type=int, default=None)
    ap.add_argument("--max-popularity", type=int, default=None)
    ap.add_argument("--min-distance", type=int, default=None)
    ap.add_argument("--max-distance", type=int, default=None)
    ap.add_argument("--db", default=None, help="SQLite DB path")
    ap.add_argument(
        "--save", action="store_true",
        help="data/backtest/<timestamp>.json に結果を保存",
    )
    ap.add_argument("--save-calibrator", action="store_true")
    ap.add_argument(
        "--calibrator-type", choices=["bin", "isotonic"], default="bin",
        help="--save-calibrator 時の校正アルゴリズム。isotonic は単調制約付き "
             "(Phase 3 / 2026-05-13 追加、scikit-learn 必須)",
    )
    ap.add_argument(
        "--rule-version", default="v1",
        help="保存時のルールバージョン名 (例: v1, v2-track-condition)",
    )
    ap.add_argument(
        "--save-records",
        action="store_true",
        help="_calibration_records を data/backtest/<ts>_<rule>_records.json に保存。"
             "P17 A2 c2-b の refit_calibrator.py で Isotonic fit の入力に使う。",
    )
    args = ap.parse_args()

    result = run_backtest(
        args.from_date, args.to_date, args.bet,
        skip_tentative=not args.include_tentative,
        jra_only=not args.all_tracks,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        min_popularity=args.min_popularity,
        max_popularity=args.max_popularity,
        filter_from_config=not args.no_filter_from_config,
        min_value=args.min_value,
        min_ev=args.min_ev,
        min_distance=args.min_distance,
        max_distance=args.max_distance,
        db_path=args.db,
    )
    print(format_report(result))

    if args.save:
        out_dir = Path(__file__).resolve().parent.parent / "data" / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "-all" if args.no_filter_from_config else "-filtered"
        out = out_dir / f"{ts}_{args.bet}_{args.rule_version}{suffix}.json"
        # 巨大な _calibration_records (10 万行レベル) は JSON 保存対象外
        saveable = {k: v for k, v in result.items() if not k.startswith("_")}
        out.write_text(
            json.dumps({"rule_version": args.rule_version, **saveable},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nsaved: {out}")
        if args.save_records:
            # P17 A2 c2-a (2026-05-17): _calibration_records を別ファイルに保存し、
            # 後追いで Isotonic fit (scripts.refit_calibrator) に流せるようにする。
            # 各 record は {probability, investment_probability, actual, confidence}
            # を持つ (probability は raw_blended_probability、c1 以降の意味)。
            records_out = out_dir / f"{ts}_{args.bet}_{args.rule_version}_records.json"
            records_out.write_text(
                json.dumps({
                    "rule_version": args.rule_version,
                    "from_date": args.from_date,
                    "to_date": args.to_date,
                    "meta": result.get("meta", {}),
                    "records": result["_calibration_records"],
                }, ensure_ascii=False),  # indent なし (records が数万-10万行のため)
                encoding="utf-8",
            )
            print(f"records saved: {records_out}  n={len(result['_calibration_records'])}")
    if args.save_calibrator:
        out = Path(__file__).resolve().parent.parent / "predictor" / "calibrator.json"
        # 後追い監査用に「いつ・何のデータで fit したか」を必ず記録する
        # (2026-05-12 まで欠落、再現性不能だったため)
        if args.calibrator_type == "isotonic":
            calib_obj = fit_isotonic_calibrator(result["_calibration_records"])
        else:
            calib_obj = result["calibrator"]
        calib_with_meta = {
            **calib_obj,
            "trained_from": args.from_date,
            "trained_to": args.to_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rule_version": args.rule_version,
            "calibrator_type": args.calibrator_type,
        }
        out.write_text(
            json.dumps(calib_with_meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            f"calibrator saved: {out} type={args.calibrator_type} "
            f"trained {args.from_date}-{args.to_date}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
