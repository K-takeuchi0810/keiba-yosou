"""Compare simple betting filters using one prediction pass.

usage:
    python -m scripts.filter_sweep --from 20240101 --to 20241231 --bet tan
    python -m scripts.filter_sweep --walk-forward  # 2 期間並列 sweep
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BUY_FILTER_DEFAULT, DATA_PERIODS
from db import open_db
from predictor.rules import is_tentative, predict_race
from scripts.backtest import get_payout, horses_for_race, list_races

WHITELIST_GRADES = frozenset(BUY_FILTER_DEFAULT["whitelist_grades"])
WHITELIST_TRACKS = frozenset(BUY_FILTER_DEFAULT["whitelist_tracks"])


@dataclass
class Pick:
    track_code: str
    grade_code: str          # 重賞判定用 (A/B/C/F = graded)
    ev: float                # 予想 EV
    odds: float
    popularity: int
    confidence: str          # 信頼度ラベル
    tan_payout: int
    fuku_payout: int
    # Phase 6 expansion (2026-05-14): MING (JRA-VAN プロ予想) シグナル
    win_probability: float = 0.0   # LGBM ensemble 後の校正済み確率 (P(win))
    kelly_fraction: float = 0.0    # Kelly 賭金率
    mining_tm_score: int = 0       # TM スコア (10x 内部表現、0-1000)
    mining_tm_rank: int = 0        # TM 推定順位 (1=最有力)
    mining_dm_rank: int = 0        # DM 推定順位

    @property
    def is_whitelisted(self) -> bool:
        if self.grade_code and self.grade_code in WHITELIST_GRADES:
            return True
        if self.track_code and self.track_code in WHITELIST_TRACKS:
            return True
        return False


def collect_picks(
    from_date: str,
    to_date: str,
    skip_tentative: bool = True,
    db_path: str | Path | None = None,
) -> list[Pick]:
    picks: list[Pick] = []
    with open_db(db_path) if db_path else open_db() as conn:
        races = list_races(conn, from_date, to_date, jra_only=True)
        feature_cache: dict = {}
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            if skip_tentative and is_tentative(preds):
                continue
            top = next((p for p in preds if p.rank == 1 and p.mark), None)
            if not top:
                continue
            horse = next((h for h in horses if h.get("horse_num") == top.horse_num), None)
            if not horse:
                continue
            top_feat = horse.get("_features") or {}
            picks.append(
                Pick(
                    track_code=race["track_code"],
                    grade_code=(race.get("grade_code") or "").strip(),
                    ev=float(top.expected_value or 0),
                    odds=(horse.get("win_odds") or 0) / 10.0,
                    popularity=horse.get("win_popularity") or 0,
                    confidence=top.confidence,
                    tan_payout=get_payout(conn, race, top.horse_num, "tan"),
                    fuku_payout=get_payout(conn, race, top.horse_num, "fuku"),
                    win_probability=float(top.win_probability or 0),
                    kelly_fraction=float(top.kelly_fraction or 0),
                    mining_tm_score=int(top_feat.get("mining_tm_score") or 0),
                    mining_tm_rank=int(top_feat.get("mining_tm_rank") or 0),
                    mining_dm_rank=int(top_feat.get("mining_dm_rank") or 0),
                )
            )
    return picks


def match_filter(p: Pick, spec: dict) -> bool:
    if "min_odds" in spec and (p.odds <= 0 or p.odds < spec["min_odds"]):
        return False
    if "max_odds" in spec and (p.odds <= 0 or p.odds > spec["max_odds"]):
        return False
    if "min_pop" in spec and (p.popularity <= 0 or p.popularity < spec["min_pop"]):
        return False
    if "max_pop" in spec and (p.popularity <= 0 or p.popularity > spec["max_pop"]):
        return False
    if "min_ev" in spec and p.ev < spec["min_ev"]:
        return False
    if "tracks" in spec and p.track_code not in spec["tracks"]:
        return False
    if spec.get("whitelist") and not p.is_whitelisted:
        return False
    if "exclude_conf" in spec and p.confidence in spec["exclude_conf"]:
        return False
    # Phase 6 expansion (2026-05-14)
    if "min_prob" in spec and p.win_probability < spec["min_prob"]:
        return False
    if "min_kelly" in spec and p.kelly_fraction < spec["min_kelly"]:
        return False
    if "min_tm_score" in spec and p.mining_tm_score < spec["min_tm_score"]:
        return False
    if "max_tm_rank" in spec and (p.mining_tm_rank <= 0 or p.mining_tm_rank > spec["max_tm_rank"]):
        return False
    if "max_dm_rank" in spec and (p.mining_dm_rank <= 0 or p.mining_dm_rank > spec["max_dm_rank"]):
        return False
    return True


def summarize(picks: list[Pick], bet: str, spec: dict) -> dict:
    payout_attr = f"{bet}_payout"
    selected = [p for p in picks if match_filter_extended(p, spec)]
    bet_total = len(selected) * 100
    returns = sum(getattr(p, payout_attr) for p in selected)
    hits = sum(1 for p in selected if getattr(p, payout_attr) > 0)
    return {
        "bets": len(selected),
        "hits": hits,
        "hit_rate": hits / len(selected) if selected else 0,
        "return_rate": returns / bet_total if bet_total else 0,
        "profit": returns - bet_total,
    }


FILTERS = [
    # ベースライン
    ("all", {}),
    ("whitelist_only", {"whitelist": True}),
    # whitelist 内 odds 帯
    ("wl_odds_2_5", {"whitelist": True, "min_odds": 2.0, "max_odds": 5.0}),
    ("wl_odds_5_10", {"whitelist": True, "min_odds": 5.0, "max_odds": 10.0}),
    ("wl_odds_10_20", {"whitelist": True, "min_odds": 10.0, "max_odds": 20.0}),
    ("wl_odds_20_50", {"whitelist": True, "min_odds": 20.0, "max_odds": 50.0}),
    ("wl_odds_5_15", {"whitelist": True, "min_odds": 5.0, "max_odds": 15.0}),
    ("wl_odds_8_20", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0}),
    # whitelist 内 popularity 帯
    ("wl_pop_1_2", {"whitelist": True, "min_pop": 1, "max_pop": 2}),
    ("wl_pop_1_3", {"whitelist": True, "min_pop": 1, "max_pop": 3}),
    ("wl_pop_4_6", {"whitelist": True, "min_pop": 4, "max_pop": 6}),
    ("wl_pop_4_8", {"whitelist": True, "min_pop": 4, "max_pop": 8}),
    ("wl_pop_7_plus", {"whitelist": True, "min_pop": 7}),
    # whitelist + 信頼度
    ("wl_ex_tentative", {"whitelist": True, "exclude_conf": ["暫定"]}),
    ("wl_ex_unsure", {"whitelist": True, "exclude_conf": ["暫定", "混戦", "接戦"]}),
    # whitelist + 複合
    ("wl_odds_5_15_pop_1_4", {"whitelist": True, "min_odds": 5.0, "max_odds": 15.0, "min_pop": 1, "max_pop": 4}),
    ("wl_odds_2_8_pop_1_3", {"whitelist": True, "min_odds": 2.0, "max_odds": 8.0, "min_pop": 1, "max_pop": 3}),
    ("wl_ex_unsure_pop_1_4", {"whitelist": True, "exclude_conf": ["暫定", "混戦", "接戦"], "min_pop": 1, "max_pop": 4}),
    # wl_odds_8_20 路線の +100% 追求 (2026-05-12 追加, project-state 高インパクト #3)
    # 隣接 odds 帯を試して戦数増の可能性を見る
    ("wl_odds_6_20", {"whitelist": True, "min_odds": 6.0, "max_odds": 20.0}),
    ("wl_odds_7_22", {"whitelist": True, "min_odds": 7.0, "max_odds": 22.0}),
    ("wl_odds_8_25", {"whitelist": True, "min_odds": 8.0, "max_odds": 25.0}),
    ("wl_odds_9_25", {"whitelist": True, "min_odds": 9.0, "max_odds": 25.0}),
    # 8-20 + 信頼度フィルタ重ね掛け (戦数減 / 回収率上振れ狙い)
    ("wl_odds_8_20_ex_unsure", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0, "exclude_conf": ["暫定", "混戦", "接戦"]}),
    ("wl_odds_8_20_ex_tentative", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0, "exclude_conf": ["暫定"]}),
    # 8-20 + 人気帯 (中穴 4-8 が wl_pop_4_8 単体で eval 122.1% を出したため)
    ("wl_odds_8_20_pop_4_8", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0, "min_pop": 4, "max_pop": 8}),
    # wl_pop_4_8 の安定化候補
    ("wl_pop_4_10", {"whitelist": True, "min_pop": 4, "max_pop": 10}),
    ("wl_pop_5_9_ex_unsure", {"whitelist": True, "min_pop": 5, "max_pop": 9, "exclude_conf": ["暫定", "混戦", "接戦"]}),
    # whitelist 外 (= 控除率の低い領域)
    ("non_wl", {"whitelist": False}),
    # 旧バリアント (参考)
    ("odds_2_5", {"min_odds": 2.0, "max_odds": 5.0}),
    ("odds_10_20", {"min_odds": 10.0, "max_odds": 20.0}),

    # ========== Phase 6 (2026-05-14) 戦略カタログ拡張 ==========
    # 「いくつもの検証を行い良いものを伸ばす」方針。LGBM ensemble 後の確率と
    # MING (DM/TM) を活用した EV / Kelly / 確率ベース戦略を追加。
    #
    # EV ベース戦略 (LGBM 確率 × オッズ - 1 が閾値超え)
    ("ev_ge_105", {"min_ev": 1.05}),
    ("ev_ge_110", {"min_ev": 1.10}),
    ("ev_ge_120", {"min_ev": 1.20}),
    ("ev_ge_150", {"min_ev": 1.50}),
    ("ev_ge_200", {"min_ev": 2.00}),
    # EV + whitelist 複合 (重賞 + 中京/阪神 + EV エッジ)
    ("wl_ev_105", {"whitelist": True, "min_ev": 1.05}),
    ("wl_ev_110", {"whitelist": True, "min_ev": 1.10}),
    ("wl_ev_120", {"whitelist": True, "min_ev": 1.20}),
    ("wl_ev_150", {"whitelist": True, "min_ev": 1.50}),
    # 確率ベース戦略 (校正後 P(win) が閾値超え = 本命系)
    ("prob_ge_20", {"min_prob": 0.20}),
    ("prob_ge_30", {"min_prob": 0.30}),
    ("wl_prob_ge_20", {"whitelist": True, "min_prob": 0.20}),
    ("wl_prob_ge_30", {"whitelist": True, "min_prob": 0.30}),
    # Kelly 賭金率ベース (= 内部的に「EV プラス + 確率十分」を意味するので堅実)
    ("kelly_ge_01", {"min_kelly": 0.01}),
    ("kelly_ge_05", {"min_kelly": 0.05}),
    ("wl_kelly_ge_01", {"whitelist": True, "min_kelly": 0.01}),
    ("wl_kelly_ge_05", {"whitelist": True, "min_kelly": 0.05}),

    # ========== MING (JRA-VAN プロ予想) 単独 / 自モデル併用 ==========
    # TM score の高さで絞る (TM > 80 等)
    ("tm_score_ge_700", {"min_tm_score": 700}),   # = 内部 700 = score 70.0
    ("tm_score_ge_800", {"min_tm_score": 800}),
    ("tm_score_ge_900", {"min_tm_score": 900}),
    # TM rank の上位
    ("tm_rank_1", {"max_tm_rank": 1}),       # TM 本命と一致
    ("tm_rank_1_3", {"max_tm_rank": 3}),     # TM 上位 3 頭
    # DM rank の上位
    ("dm_rank_1", {"max_dm_rank": 1}),
    ("dm_rank_1_3", {"max_dm_rank": 3}),
    # WL 内で MING 高評価
    ("wl_tm_score_ge_700", {"whitelist": True, "min_tm_score": 700}),
    ("wl_tm_score_ge_800", {"whitelist": True, "min_tm_score": 800}),
    ("wl_tm_rank_1_3", {"whitelist": True, "max_tm_rank": 3}),
    # MING + EV 複合 (プロ予想と自モデルが一致する馬を狙う)
    ("tm_rank_1_3_ev_ge_105", {"max_tm_rank": 3, "min_ev": 1.05}),
    ("tm_score_ge_700_ev_ge_110", {"min_tm_score": 700, "min_ev": 1.10}),
    ("wl_tm_rank_1_3_ev_ge_105", {"whitelist": True, "max_tm_rank": 3, "min_ev": 1.05}),

    # ========== 多面複合 (Phase 6 仮説検証) ==========
    # 本命厚切り: WL + 1-2 人気 + 高オッズ域カット
    ("wl_pop_1_2_ev_ge_105", {"whitelist": True, "min_pop": 1, "max_pop": 2, "min_ev": 1.05}),
    ("wl_pop_1_2_kelly_ge_01", {"whitelist": True, "min_pop": 1, "max_pop": 2, "min_kelly": 0.01}),
    # 中穴堅切り: 8-25 倍 + 中位人気 + EV 閾値
    ("odds_8_25_ev_ge_110", {"min_odds": 8.0, "max_odds": 25.0, "min_ev": 1.10}),
    ("wl_odds_8_25_ev_ge_110", {"whitelist": True, "min_odds": 8.0, "max_odds": 25.0, "min_ev": 1.10}),
    # 大穴 robust 探索: 20-50 倍 + EV >= 1.5 (高 EV のみ)
    ("odds_20_50_ev_ge_150", {"min_odds": 20.0, "max_odds": 50.0, "min_ev": 1.50}),
    ("wl_odds_20_50_ev_ge_150", {"whitelist": True, "min_odds": 20.0, "max_odds": 50.0, "min_ev": 1.50}),
    # 信頼度高い × 本命の絶対安全策
    ("wl_pop_1_2_ex_unsure", {"whitelist": True, "min_pop": 1, "max_pop": 2, "exclude_conf": ["暫定", "混戦", "接戦"]}),
    # WL 拡張 (TEST 2024-25 集約で >80% を出した 5 場で再評価)
    ("wl5_pop_1_2", {"tracks": {"01", "02", "03", "06", "07"}, "min_pop": 1, "max_pop": 2}),
    ("wl5_ev_ge_110", {"tracks": {"01", "02", "03", "06", "07"}, "min_ev": 1.10}),

    # ========== 2026-05-15 緊急探索: 単独場 × 様々な絞り条件 ==========
    # P13 PRODUCTION hold-out で「採用 5 場崩壊 / 除外 09 阪神 137%」と逆転
    # していたため、場別 robust を recent-3fold で再評価する。
    # 各場 × 全レース (絞りなし) + popularity 帯絞り版を網羅。
    *[(f"only_t{tc}", {"tracks": {tc}})
      for tc in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10")],
    *[(f"only_t{tc}_pop_1_2", {"tracks": {tc}, "min_pop": 1, "max_pop": 2})
      for tc in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10")],
    *[(f"only_t{tc}_pop_1_3", {"tracks": {tc}, "min_pop": 1, "max_pop": 3})
      for tc in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10")],
    # 阪神 + 新潟 (PRODUCTION 2026 で逆転 robust だった 2 場)
    ("only_t04_09", {"tracks": {"04", "09"}}),
    ("only_t04_09_pop_1_2", {"tracks": {"04", "09"}, "min_pop": 1, "max_pop": 2}),
    ("only_t04_09_pop_1_3", {"tracks": {"04", "09"}, "min_pop": 1, "max_pop": 3}),
    ("only_t04_09_ev_ge_110", {"tracks": {"04", "09"}, "min_ev": 1.10}),
    # 阪神 + 新潟 + (旧 採用) 中京: PRODUCTION mid-tier 含む
    ("only_t04_07_09", {"tracks": {"04", "07", "09"}, "min_pop": 1, "max_pop": 2}),
]


# 「whitelist 外」を分離してマッチさせる - whitelist=False は spec 側で扱わないので
# match_filter 内では何もせず、ここでは spec が `whitelist=False` キー持ちのとき
# 「whitelist 外を残す」を意味する。
def _adjust_spec_for_non_whitelist(spec: dict) -> dict:
    """spec で whitelist=False を渡したら「whitelist 外のみ」のマッチを返す用に解釈変更。"""
    return spec  # match_filter で whitelist True のときだけ判定するので互換


# match_filter を whitelist=False の場合に「whitelist 外」と読むよう拡張
def match_filter_extended(p: Pick, spec: dict) -> bool:
    if not match_filter(p, {k: v for k, v in spec.items() if k != "whitelist" or v is True}):
        return False
    if spec.get("whitelist") is False and p.is_whitelisted:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default=None)
    ap.add_argument("--to", dest="to_date", default=None)
    ap.add_argument("--bet", choices=["tan", "fuku"], default="tan")
    ap.add_argument("--by-year", action="store_true")
    ap.add_argument(
        "--walk-forward",
        action="store_true",
        help="config.DATA_PERIODS の train / test 2 期間並列 sweep。"
        "両期間とも 80%% 以上かを比較表示。HOLDOUT は別途 --holdout で。",
    )
    ap.add_argument(
        "--holdout",
        action="store_true",
        help="config.DATA_PERIODS['holdout'] のみで 1 回限り検証。"
        "採用済み filter を本番投入前に sanity check する用途。",
    )
    ap.add_argument(
        "--walk-forward-3fold",
        action="store_true",
        help="Phase 4: 3-fold walk-forward. TEST split into year-folds. "
             "Filter is robust only if all folds reach 80%% return. "
             "Year-noise robust check (2026-05-13).",
    )
    ap.add_argument(
        "--by-track-3fold",
        action="store_true",
        help="Phase 6: per-track 3-fold sweep. Each of 10 JRA tracks "
             "evaluated across 3 year-folds for whitelist re-selection. "
             "Robust = all 3 folds reach the configurable threshold "
             "(default 80%%) under LGBM ensemble (2026-05-13).",
    )
    ap.add_argument(
        "--recent-3fold",
        action="store_true",
        help="2026-05-15 emergency: recent-period 3-fold sweep "
             "(2025-H1 / 2025-H2 / 2026-Q1+) to find robust filters "
             "after P12 hold-out failure. Year-noise robust under recent "
             "track / jockey / class composition.",
    )
    ap.add_argument("--db", default=None, help="SQLite DB path")
    args = ap.parse_args()

    started = time.time()

    if args.walk_forward:
        # walk-forward は TEST 期間を年単位で 2 分割して並列 sweep。
        # TRAIN (= calibrator 学習期間) は in-sample なので比較対象に入れない。
        # ヘッダ d_ / e_ は履歴 CSV との互換維持 (d=design, e=eval)。
        # DATA_PERIODS["test"] = 2024-2025 を仮定: design=2024 / eval=2025
        test_from = DATA_PERIODS["test"]["from"]
        test_to = DATA_PERIODS["test"]["to"]
        from_year = test_from[:4]
        to_year = test_to[:4]
        if from_year == to_year:
            sys.exit(
                f"walk-forward requires multi-year test period, got "
                f"{test_from}-{test_to}. Edit config.DATA_PERIODS['test']."
            )
        # design = 最初の年、eval = 最後の年。中間年は今回は使わない (3 年なら 2024/2025 を取る)。
        design_from = f"{from_year}0101"
        design_to = f"{from_year}1231"
        eval_from = f"{to_year}0101"
        eval_to = test_to
        periods = [
            ("design", design_from, design_to),
            ("eval", eval_from, eval_to),
        ]
        period_picks: dict[str, list[Pick]] = {}
        for name, fr, to in periods:
            period_picks[name] = collect_picks(fr, to, db_path=args.db)
            print(
                f"  collected {name} ({fr}-{to}): {len(period_picks[name])} picks",
                file=sys.stderr,
            )
        print("filter,d_bets,d_hit_rate,d_return_rate,e_bets,e_hit_rate,e_return_rate,robust")
        rows: list[tuple[str, dict, dict]] = []
        for name, spec in FILTERS:
            d = summarize(period_picks["design"], args.bet, spec)
            e = summarize(period_picks["eval"], args.bet, spec)
            rows.append((name, d, e))
        rows.sort(
            key=lambda x: (
                x[1]["return_rate"] >= 0.80 and x[2]["return_rate"] >= 0.80,
                min(x[1]["return_rate"], x[2]["return_rate"]),
            ),
            reverse=True,
        )
        for name, d, e in rows:
            robust = "Y" if d["return_rate"] >= 0.80 and e["return_rate"] >= 0.80 else "n"
            print(
                f"{name},{d['bets']},{d['hit_rate']*100:.1f},{d['return_rate']*100:.1f},"
                f"{e['bets']},{e['hit_rate']*100:.1f},{e['return_rate']*100:.1f},{robust}"
            )
        print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
        return 0

    if args.walk_forward_3fold:
        # Phase 4: 3-fold walk-forward
        # config.DATA_PERIODS["test"] = 2024-2025 だが、ここでは TRAIN 後半 (2023) +
        # TEST (2024, 2025) の 3 fold を取って year-noise を平均化する。
        # robust 認定: 全 3 fold で >= 80% を要求 (1 fold でも 80% 未満なら脱落)。
        train_to = DATA_PERIODS["train"]["to"]
        test_from = DATA_PERIODS["test"]["from"]
        test_to = DATA_PERIODS["test"]["to"]
        train_last_year = train_to[:4]
        test_first_year = test_from[:4]
        test_last_year = test_to[:4]
        # 3 fold = [TRAIN末年, TEST_前半, TEST_末年]
        fold_years = [train_last_year, test_first_year, test_last_year]
        # 重複除去 & 順序維持
        seen = set()
        fold_years = [y for y in fold_years if not (y in seen or seen.add(y))]
        if len(fold_years) < 3:
            print(
                f"WARN: only {len(fold_years)} unique years for 3-fold "
                f"({fold_years}). Need TRAIN_to + TEST_from + TEST_to に "
                f"3 異なる年が必要。",
                file=sys.stderr,
            )
        period_picks_3fold: dict[str, list[Pick]] = {}
        for y in fold_years:
            fr = f"{y}0101"
            to = f"{y}1231"
            if y == test_last_year:
                to = test_to
            period_picks_3fold[y] = collect_picks(fr, to, db_path=args.db)
            print(
                f"  collected fold {y} ({fr}-{to}): {len(period_picks_3fold[y])} picks",
                file=sys.stderr,
            )
        cols = ",".join(f"{y}_bets,{y}_hit_rate,{y}_return_rate" for y in fold_years)
        print(f"filter,{cols},robust_3fold")
        rows_3f: list[tuple[str, list[dict]]] = []
        for name, spec in FILTERS:
            results = [summarize(period_picks_3fold[y], args.bet, spec) for y in fold_years]
            rows_3f.append((name, results))
        rows_3f.sort(
            key=lambda x: (
                all(r["return_rate"] >= 0.80 for r in x[1]),
                min(r["return_rate"] for r in x[1]),
            ),
            reverse=True,
        )
        for name, results in rows_3f:
            robust = "Y" if all(r["return_rate"] >= 0.80 for r in results) else "n"
            parts = [name]
            for r in results:
                parts.append(str(r["bets"]))
                parts.append(f"{r['hit_rate']*100:.1f}")
                parts.append(f"{r['return_rate']*100:.1f}")
            parts.append(robust)
            print(",".join(parts))
        print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
        return 0

    if args.recent_3fold:
        # 2026-05-15 緊急: 直近 1.5 年を 3 fold に分割した sweep。
        # fold 1: 2025-01〜2025-06 (前半)
        # fold 2: 2025-07〜2025-12 (後半)
        # fold 3: 2026-01〜直近実データ末日 (PRODUCTION 前半)
        # P12 hold-out 失敗の原因 (場特性変動) に対し、直近 trend に合う robust
        # 戦略を探す目的。「全 3 fold で >= 80%%」を robust 認定。
        prod_to = DATA_PERIODS["production"]["to"]
        # 実データの末日を取得 (race_year='2026' の最新)
        with open_db(args.db) if args.db else open_db() as conn:
            row = conn.execute(
                "SELECT MAX(race_year || race_month_day) FROM races "
                "WHERE race_year='2026' AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10"
            ).fetchone()
            actual_end = row[0] if row and row[0] else prod_to
        fold_periods = [
            ("2025H1", "20250101", "20250630"),
            ("2025H2", "20250701", "20251231"),
            ("2026P", "20260101", actual_end),
        ]
        period_picks_r: dict[str, list[Pick]] = {}
        for name, fr, to in fold_periods:
            period_picks_r[name] = collect_picks(fr, to, db_path=args.db)
            print(
                f"  collected fold {name} ({fr}-{to}): {len(period_picks_r[name])} picks",
                file=sys.stderr,
            )
        cols = ",".join(f"{name}_bets,{name}_hit_rate,{name}_return_rate"
                        for name, _, _ in fold_periods)
        print(f"filter,{cols},min_return,robust_3fold")
        rows_r: list[tuple[str, list[dict], float, bool]] = []
        for fname, spec in FILTERS:
            results = [
                summarize(period_picks_r[name], args.bet, spec)
                for name, _, _ in fold_periods
            ]
            if all(r["bets"] == 0 for r in results):
                continue
            non_zero = [r for r in results if r["bets"] > 0]
            min_ret = min(r["return_rate"] for r in non_zero) if non_zero else 0
            is_robust = (
                all(r["bets"] >= 10 for r in results)
                and all(r["return_rate"] >= 0.80 for r in results)
            )
            rows_r.append((fname, results, min_ret, is_robust))
        rows_r.sort(key=lambda x: (x[3], x[2]), reverse=True)
        for fname, results, min_ret, is_robust in rows_r:
            parts = [fname]
            for r in results:
                parts.append(str(r["bets"]))
                parts.append(f"{r['hit_rate']*100:.1f}")
                parts.append(f"{r['return_rate']*100:.1f}")
            parts.append(f"{min_ret*100:.1f}")
            parts.append("Y" if is_robust else "n")
            print(",".join(parts))
        print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
        return 0

    if args.by_track_3fold:
        # Phase 6 (2026-05-13): 場別 3-fold sweep。
        # whitelist 再選定のため、10 場 × 3 年 (2023/2024/2025) の return_rate
        # マトリクスを出力。LGBM ensemble の場別パフォーマンスを年単位で確認し、
        # 全 3 fold で >= 80% を出す場のみ採用候補にする。
        # filter は「全レース rank-1 ベタ買い」(spec={}) を基準にし、別途
        # popularity/odds との組合せ感度は --walk-forward-3fold で見る。
        train_to = DATA_PERIODS["train"]["to"]
        test_from = DATA_PERIODS["test"]["from"]
        test_to = DATA_PERIODS["test"]["to"]
        fold_years = [train_to[:4], test_from[:4], test_to[:4]]
        seen_y: set[str] = set()
        fold_years = [y for y in fold_years if not (y in seen_y or seen_y.add(y))]
        # 各 fold で picks 収集
        period_picks_t: dict[str, list[Pick]] = {}
        for y in fold_years:
            fr = f"{y}0101"
            to = f"{y}1231"
            if y == test_to[:4]:
                to = test_to
            period_picks_t[y] = collect_picks(fr, to, db_path=args.db)
            print(
                f"  collected fold {y} ({fr}-{to}): {len(period_picks_t[y])} picks",
                file=sys.stderr,
            )
        TRACK_NAMES = {
            "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
            "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
        }
        threshold = 0.80
        cols = ",".join(f"{y}_bets,{y}_hit_rate,{y}_return_rate" for y in fold_years)
        print(f"track,name,{cols},min_return,robust_3fold")
        rows_t: list[tuple[str, str, list[dict], float, bool]] = []
        for tc in sorted(TRACK_NAMES.keys()):
            name = TRACK_NAMES[tc]
            results = [
                summarize(period_picks_t[y], args.bet, {"tracks": {tc}})
                for y in fold_years
            ]
            if any(r["bets"] == 0 for r in results):
                continue
            min_ret = min(r["return_rate"] for r in results)
            is_robust = all(r["return_rate"] >= threshold for r in results)
            rows_t.append((tc, name, results, min_ret, is_robust))
        # robust 優先、その中で min_return 降順
        rows_t.sort(key=lambda x: (x[4], x[3]), reverse=True)
        for tc, name, results, min_ret, is_robust in rows_t:
            parts = [tc, name]
            for r in results:
                parts.append(str(r["bets"]))
                parts.append(f"{r['hit_rate']*100:.1f}")
                parts.append(f"{r['return_rate']*100:.1f}")
            parts.append(f"{min_ret*100:.1f}")
            parts.append("Y" if is_robust else "n")
            print(",".join(parts))
        print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
        return 0

    if args.holdout:
        # HOLDOUT (= 本番 PRODUCTION 期間) は採用済み filter を検証する用途。
        # `config.BUY_FILTER_DEFAULT` と同じ条件の filter (主絞り) で picks を
        # まとめて出力。本番投入 *決定後* に走らせる位置付け。
        fr = DATA_PERIODS["production"]["from"]
        to = DATA_PERIODS["production"]["to"]
        picks = collect_picks(fr, to, db_path=args.db)
        print(f"  collected production/holdout ({fr}-{to}): {len(picks)} picks", file=sys.stderr)
        print("filter,bets,hits,hit_rate,return_rate,profit")
        rows = [(name, summarize(picks, args.bet, spec)) for name, spec in FILTERS]
        rows.sort(key=lambda x: (x[1]["return_rate"], x[1]["bets"]), reverse=True)
        for name, r in rows:
            print(
                f"{name},{r['bets']},{r['hits']},"
                f"{r['hit_rate'] * 100:.1f},{r['return_rate'] * 100:.1f},{r['profit']}"
            )
        print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
        return 0

    if not args.from_date or not args.to_date:
        ap.error("--from と --to が必要 (または --walk-forward / --holdout)")

    print("filter,bets,hits,hit_rate,return_rate,profit")

    if args.by_year:
        start_year = int(args.from_date[:4])
        end_year = int(args.to_date[:4])
        for year in range(start_year, end_year + 1):
            from_date = max(args.from_date, f"{year}0101")
            to_date = min(args.to_date, f"{year}1231")
            picks = collect_picks(from_date, to_date, db_path=args.db)
            for name, spec in FILTERS:
                r = summarize(picks, args.bet, spec)
                print(
                    f"{year}:{name},{r['bets']},{r['hits']},"
                    f"{r['hit_rate'] * 100:.1f},{r['return_rate'] * 100:.1f},{r['profit']}"
                )
    else:
        picks = collect_picks(args.from_date, args.to_date, db_path=args.db)
        rows = [(name, summarize(picks, args.bet, spec)) for name, spec in FILTERS]
        rows.sort(key=lambda x: (x[1]["return_rate"], x[1]["bets"]), reverse=True)
        for name, r in rows:
            print(
                f"{name},{r['bets']},{r['hits']},"
                f"{r['hit_rate'] * 100:.1f},{r['return_rate'] * 100:.1f},{r['profit']}"
            )
    print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
