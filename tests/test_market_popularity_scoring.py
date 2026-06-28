from __future__ import annotations

import json

import predictor.rules as rules
from predictor.rules import _score_one, _w, _investment_probability


def test_market_popularity_bonus_is_active_for_large_fields():
    """P24 以降、市場人気は買い候補だけでなく◎決定前のスコアにも反映する。"""
    feat = {
        "current_starter_count": 16,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }
    fresh = {"odds_fetched_at": "2026-06-07T12:05:00"}

    score_pop1, reasons_pop1 = _score_one({"win_popularity": 1, **fresh}, feat)
    score_pop2, reasons_pop2 = _score_one({"win_popularity": 2, **fresh}, feat)
    score_pop3, reasons_pop3 = _score_one({"win_popularity": 3, **fresh}, feat)
    score_pop4, reasons_pop4 = _score_one({"win_popularity": 4, **fresh}, feat)

    assert score_pop1 - score_pop4 == _w("popularity.first", 7)
    assert score_pop2 - score_pop4 == _w("popularity.second", 4)
    assert score_pop3 - score_pop4 == _w("popularity.third", 2)
    assert "市場1人気" in reasons_pop1
    assert "市場2人気" in reasons_pop2
    assert "市場3人気" in reasons_pop3
    assert not any("市場" in r for r in reasons_pop4)


def test_market_popularity_bonus_is_disabled_for_small_fields():
    feat = {
        "current_starter_count": 10,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }
    fresh = {"odds_fetched_at": "2026-06-07T12:05:00"}

    score_pop1, reasons_pop1 = _score_one({"win_popularity": 1, **fresh}, feat)
    score_pop4, _ = _score_one({"win_popularity": 4, **fresh}, feat)

    assert score_pop1 == score_pop4
    assert "市場1人気" not in reasons_pop1


def test_market_popularity_bonus_requires_fresh_snapshot():
    feat = {
        "current_starter_count": 16,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }

    score_fresh, reasons_fresh = _score_one(
        {"win_popularity": 1, "odds_fetched_at": "2026-06-07T12:05:00"}, feat)
    score_stale, reasons_stale = _score_one(
        {"win_popularity": 1, "odds_fetched_at": "2026-06-07T11:45:00"}, feat)
    score_missing, reasons_missing = _score_one({"win_popularity": 1}, feat)
    score_post_start, _ = _score_one(
        {"win_popularity": 1, "odds_fetched_at": "2026-06-07T12:31:00"}, feat)

    assert score_fresh - score_stale == _w("popularity.first", 7)
    assert score_missing == score_stale
    assert score_post_start == score_stale
    assert "市場1人気" in reasons_fresh
    assert "市場1人気" not in reasons_stale
    assert "市場1人気" not in reasons_missing


def test_market_popularity_can_change_predict_race_mark_order():
    orig_compute_features = rules.compute_features

    def fake_compute_features(conn, horse, race, cache=None):
        return {
            "current_starter_count": 16,
            "current_race_date": "20260607",
            "current_start_time": "1230",
        }

    try:
        rules.compute_features = fake_compute_features
        horses = [
            {"horse_num": "01", "win_popularity": 4, "win_odds": 80, "odds_fetched_at": "2026-06-07T12:05:00"},
            {"horse_num": "02", "win_popularity": 1, "win_odds": 30, "odds_fetched_at": "2026-06-07T12:05:00"},
        ]
        preds = rules.predict_race(horses, conn=object(), race={"race_year": "2026", "race_month_day": "0607"})
    finally:
        rules.compute_features = orig_compute_features

    assert preds[0].horse_num == "02"
    assert preds[0].mark == "◎"
    assert "市場1人気" in preds[0].rationale


def test_market_popularity_layer_a_can_be_ablated_via_env(monkeypatch):
    """二重取り込みリスク監査: 層 (A) _market_score の人気ボーナスを ablation
    したいときは PRED_W_popularity_first/second/third=0 で完全無効化できる。

    これにより層 (A) を切ったまま層 (B) _investment_probability の market_blend
    だけを単体評価でき、A/B 両方が同方向に作用しているか実測で確認できる。
    """
    monkeypatch.setenv("PRED_W_popularity_first", "0")
    monkeypatch.setenv("PRED_W_popularity_second", "0")
    monkeypatch.setenv("PRED_W_popularity_third", "0")
    feat = {
        "current_starter_count": 16,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }
    fresh = {"odds_fetched_at": "2026-06-07T12:05:00"}
    score_pop1, reasons_pop1 = _score_one({"win_popularity": 1, **fresh}, feat)
    score_pop4, _ = _score_one({"win_popularity": 4, **fresh}, feat)
    assert score_pop1 == score_pop4, "weight=0 のとき 1 人気と 4 人気のスコア差は無くなる"
    assert not any("市場" in r for r in reasons_pop1), \
        "weight=0 のとき rationale に '市場N人気' を出さない (虚偽表示防止)"


def test_investment_probability_blend_disabled_by_env(monkeypatch):
    """層 (B) ablation: PRED_DISABLE_BLEND=1 のとき _investment_probability は
    market_probability にも odds discount にも依存せず、calibrator 後の
    model_probability をそのまま返す。factorial C3/C6 (B-only ablation) の前提。

    `PRED_W_model_blend_*=1.0` (model 100% だが discount は残る) との違いを
    明示的に検証する。
    """
    monkeypatch.setenv("PRED_DISABLE_BLEND", "1")
    # market_probability や odds を大きく変えても出力は model_probability のまま
    assert _investment_probability(0.30, 0.05, "高信頼", 5.0) == 0.30
    assert _investment_probability(0.30, 0.90, "標準", 40.0) == 0.30

    # env 無効化時は従来通り blend + discount が効き、model_probability と一致しない
    monkeypatch.delenv("PRED_DISABLE_BLEND", raising=False)
    blended = _investment_probability(0.30, 0.90, "標準", 5.0)
    assert blended != 0.30


def test_investment_probability_logit_mode_uses_second_blend(monkeypatch):
    """PRED_BLEND_MODE=logit のとき、second_blend 係数で sigmoid(b0+b1*log(model)+
    b2*log(market)) を返す (Benter 二段ロジット再ブレンド)。odds discount は通さない。
    """
    import math
    monkeypatch.setenv("PRED_BLEND_MODE", "logit")
    coef = {"intercept": 0.5, "log_model": 0.2, "log_market": 0.9}
    monkeypatch.setattr(rules, "_load_second_blend", lambda: {"coefficients": coef})
    mp, kp = 0.30, 0.20
    z = coef["intercept"] + coef["log_model"] * math.log(mp) + coef["log_market"] * math.log(kp)
    expected = 1.0 / (1.0 + math.exp(-z))
    # odds を変えても (discount を通さないので) 出力は不変
    assert abs(_investment_probability(mp, kp, "標準", 5.0) - expected) < 1e-9
    assert abs(_investment_probability(mp, kp, "標準", 40.0) - expected) < 1e-9


def test_investment_probability_logit_falls_back_to_linear_without_coeffs(monkeypatch):
    """logit mode でも second_blend.json が無ければ linear blend に安全フォールバック。"""
    monkeypatch.setattr(rules, "_load_second_blend", lambda: None)
    monkeypatch.setenv("PRED_BLEND_MODE", "logit")
    got = _investment_probability(0.30, 0.20, "標準", 5.0)
    monkeypatch.setenv("PRED_BLEND_MODE", "linear")
    linear = _investment_probability(0.30, 0.20, "標準", 5.0)
    assert got == linear


def test_second_blend_loader_rejects_rule_version_mismatch(monkeypatch, tmp_path):
    """second_blend 係数は RULES_VERSION が一致する時だけ opt-in 適用する。"""
    path = tmp_path / "second_blend.json"
    path.write_text(
        json.dumps({
            "rule_version": "old-rule-version",
            "coefficients": {"intercept": 0.0, "log_model": 0.2, "log_market": 0.8},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(rules, "SECOND_BLEND_PATH", path)
    monkeypatch.setattr(rules, "_SECOND_BLEND_CACHE", None)

    assert rules._load_second_blend() is None
