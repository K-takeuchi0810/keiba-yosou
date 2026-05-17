"""買い候補判定の集約モジュール (S7-α-2、2026-05-18)。

これまで判定ロジックが 4 経路で重複していた:
- scripts/predict.py:_is_bet_candidate
- scripts/backtest.py:_matches_buy_filter
- gui/app.py:_is_buy_candidate
- web/generator.py inline (171-185 行で独立判定)

各経路でフィルタ項目の漏れが過去 2 回発生 (S5-3 で gui/app.py の min_kelly 漏れ修正、
S7-α で web/generator.py の min_kelly + max_predicted_p 漏れ修正)。再発を防ぐため、
全経路が **本モジュールの `is_buy_candidate` を直接 import** する形に統一する。

判定の出典は `config.BUY_FILTER_DEFAULT` で、これは「アプリ全体で唯一の出典」
(config.py で BUY_FILTER_DEFAULT の docstring に明記)。
"""

from __future__ import annotations

from typing import Any


def is_buy_candidate(
    pred: Any,
    horse: dict,
    tentative: bool,
    race: dict | None = None,
    filter_spec: dict | None = None,
) -> bool:
    """買い候補かを判定する単一関数。

    Args:
        pred: predictor.rules.Prediction (rank, mark, confidence, value_score,
              expected_value, kelly_fraction, win_probability を持つ)
        horse: 出走馬 dict (win_odds, win_popularity, odds_fetched_at 等)
        tentative: そのレースが「暫定」判定か (is_tentative(preds) の結果)
        race: race dict (track_code, grade_code 等)。is_whitelisted_race の評価に必要。
              None なら whitelist チェック skip。
        filter_spec: BUY_FILTER の override (テスト等で使用)。
                     None なら config.BUY_FILTER_DEFAULT を読む。

    Returns:
        買い候補なら True。

    判定順序 (短絡):
        1. rank == 1 かつ mark あり かつ 非 tentative
        2. whitelist (race ありかつ whitelist_mode=True のとき)
        3. confidence が exclude_confidence にない
        4. min_value, min_ev, min_odds, max_odds, min_kelly, max_predicted_p
        5. min_popularity, max_popularity
        6. kelly_fraction > 0 (最小エッジ要求)
    """
    if filter_spec is None:
        from config import BUY_FILTER_DEFAULT, is_whitelisted_race
        filter_spec = BUY_FILTER_DEFAULT
        _whitelist_fn = is_whitelisted_race
    else:
        from config import is_whitelisted_race as _whitelist_fn

    # 基本条件: rank=1 + mark あり + 非 tentative
    if tentative or pred.rank != 1 or not pred.mark:
        return False

    # whitelist (race ありの場合のみ評価。BET_WHITELIST=0 env で常に True)
    if race is not None and not _whitelist_fn(race):
        return False

    # confidence 除外
    exclude_conf = filter_spec.get("exclude_confidence") or []
    if pred.confidence in exclude_conf:
        return False

    odds = (horse.get("win_odds") or 0) / 10.0
    popularity = horse.get("win_popularity") or 0

    # value_score / expected_value
    if filter_spec.get("min_value") is not None and pred.value_score < filter_spec["min_value"]:
        return False
    if filter_spec.get("min_ev") is not None and pred.expected_value < filter_spec["min_ev"]:
        return False

    # odds 範囲
    if filter_spec.get("min_odds") is not None and (odds <= 0 or odds < filter_spec["min_odds"]):
        return False
    if filter_spec.get("max_odds") is not None and (odds <= 0 or odds > filter_spec["max_odds"]):
        return False

    # Kelly fraction (P15 wl_kelly_ge_05 採用以降の主絞り条件)
    if filter_spec.get("min_kelly") is not None and (pred.kelly_fraction or 0) < filter_spec["min_kelly"]:
        return False

    # max_predicted_p (S5-3 で導入、Phase A2 高 p 帯破綻防御)
    if filter_spec.get("max_predicted_p") is not None and (pred.win_probability or 0) > filter_spec["max_predicted_p"]:
        return False

    # popularity 範囲
    if filter_spec.get("min_popularity") is not None:
        if popularity <= 0 or popularity < filter_spec["min_popularity"]:
            return False
    if filter_spec.get("max_popularity") is not None:
        if popularity <= 0 or popularity > filter_spec["max_popularity"]:
            return False

    # 最小エッジ (Kelly > 0 = EV > 1 と同義)
    if pred.kelly_fraction <= 0:
        return False

    return True
