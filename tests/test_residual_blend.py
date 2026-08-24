"""残差形式の確率ブレンドの契約テスト (改革 R1-2)。

p = 市場確率 × exp(λ × 残差)、残差 = log(モデル確率 / 市場確率)

固定する不変条件:
  1. λ=0 なら市場確率そのまま (= 市場に退化する)
  2. λ=1 ならモデル確率そのまま
  3. fade (モデル < 市場) と boost (モデル > 市場) で別の λ を使う
  4. boost の λ=0 なら、モデルがいくら高く評価しても市場を超えない
  5. 既定 (PRED_BLEND_MODE 未設定) は従来の線形ブレンドで、挙動が変わらない
"""
from __future__ import annotations

import pytest

from predictor.rules import _investment_probability


@pytest.fixture(autouse=True)
def _residual_mode(monkeypatch):
    monkeypatch.setenv("PRED_BLEND_MODE", "residual")
    monkeypatch.delenv("PRED_DISABLE_BLEND", raising=False)


def _p(model, market, confidence="標準", odds=5.0):
    return _investment_probability(model, market, confidence, odds)


def test_lambda_zero_degenerates_to_market(monkeypatch):
    """λ=0 (両側) なら市場確率そのまま = 市場に退化する。

    これが「市場をベースラインにする」ことの定義。残差に情報が無いと判明した
    ときの安全な既定値であり、この性質が崩れると設計の前提が壊れる。
    """
    monkeypatch.setenv("PRED_W_residual_lambda_fade", "0.0")
    monkeypatch.setenv("PRED_W_residual_lambda_boost", "0.0")

    assert _p(0.40, 0.10) == pytest.approx(0.10)   # モデルが 4 倍高く見ても
    assert _p(0.02, 0.10) == pytest.approx(0.10)   # 4 倍低く見ても市場のまま


def test_lambda_one_degenerates_to_model(monkeypatch):
    monkeypatch.setenv("PRED_W_residual_lambda_fade", "1.0")
    monkeypatch.setenv("PRED_W_residual_lambda_boost", "1.0")

    assert _p(0.40, 0.10) == pytest.approx(0.40)
    assert _p(0.02, 0.10) == pytest.approx(0.02)


def test_fade_and_boost_use_separate_lambdas(monkeypatch):
    """非対称の実装。fade は効かせ、boost は殺せること。"""
    monkeypatch.setenv("PRED_W_residual_lambda_fade", "0.5")
    monkeypatch.setenv("PRED_W_residual_lambda_boost", "0.0")

    # boost 側: モデルが高く評価しても市場のまま
    assert _p(0.40, 0.10) == pytest.approx(0.10)
    # fade 側: 市場 0.10、モデル 0.025 (1/4) → 0.10 * (1/4)^0.5 = 0.05
    assert _p(0.025, 0.10) == pytest.approx(0.05)


def test_boost_never_exceeds_market_when_lambda_boost_is_zero(monkeypatch):
    """boost λ=0 の間、どんなモデル確率でも市場を超えない。

    市場の 2.7 倍以上に評価した 26 戦が全敗だったことへの対処。
    """
    monkeypatch.setenv("PRED_W_residual_lambda_boost", "0.0")
    for model in (0.11, 0.2, 0.5, 0.9, 0.99):
        assert _p(model, 0.10) <= 0.10 + 1e-12


def test_result_stays_in_unit_interval(monkeypatch):
    monkeypatch.setenv("PRED_W_residual_lambda_fade", "3.0")
    monkeypatch.setenv("PRED_W_residual_lambda_boost", "3.0")
    assert 0.0 <= _p(0.99, 0.01) <= 1.0
    assert 0.0 <= _p(0.001, 0.9) <= 1.0


def test_no_market_falls_back_to_model(monkeypatch):
    """市場確率が無い (オッズ未確定) ときはモデル確率を返す。

    残差形式は市場を基準にするので、基準が無いレースでは成立しない。
    従来経路 (線形ブレンド側の market<=0 分岐) に落ちる。
    """
    monkeypatch.setenv("PRED_W_residual_lambda_fade", "0.3")
    got = _p(0.25, 0.0)
    assert got > 0, "市場が無くても確率は出す (0 にはしない)"


def test_default_mode_is_unchanged_linear(monkeypatch):
    """PRED_BLEND_MODE 未設定なら従来の線形ブレンド。

    残差形式は paired backtest の非劣化ゲートを通るまで既定にしない。
    """
    monkeypatch.delenv("PRED_BLEND_MODE", raising=False)
    linear = _p(0.30, 0.10, confidence="標準")
    monkeypatch.setenv("PRED_BLEND_MODE", "residual")
    monkeypatch.setenv("PRED_W_residual_lambda_boost", "0.0")
    residual = _p(0.30, 0.10, confidence="標準")
    assert linear != pytest.approx(residual), (
        "既定 (線形) と残差形式が同じ値になっている = モードが効いていない"
    )
    assert linear > 0.10, "線形はモデル側が支配的なので市場を大きく上回る"
    assert residual == pytest.approx(0.10), "残差形式は boost を殺すので市場のまま"


def test_weights_json_declares_residual_defaults():
    """既定値が weights.json に外出しされていること (単一出典)。"""
    import json
    from pathlib import Path

    w = json.loads((Path(__file__).resolve().parent.parent
                    / "predictor" / "weights.json").read_text(encoding="utf-8"))
    assert "residual" in w
    assert w["residual"]["lambda_boost"] == 0.0, (
        "boost の既定は 0 (実測で boost 方向は逆効果だった)"
    )
    assert 0.0 <= w["residual"]["lambda_fade"] <= 1.0


# ---------------------------------------------------------------------------
# 印を確率順に付け替える機能 (改革 柱 3)
# ---------------------------------------------------------------------------

def _fake_horses():
    """オッズだけが違う 3 頭。ルールスコアは過去走が無いので同点になる。"""
    return [
        {"horse_num": "01", "win_odds": 100, "win_popularity": 3, "mining_predicted_order": 3},
        {"horse_num": "02", "win_odds": 20, "win_popularity": 1, "mining_predicted_order": 2},
        {"horse_num": "03", "win_odds": 50, "win_popularity": 2, "mining_predicted_order": 1},
    ]


def test_rank_by_score_is_the_default(monkeypatch):
    """PRED_RANK_BY 未設定なら従来どおりスコア順 (挙動を変えない)。"""
    monkeypatch.delenv("PRED_RANK_BY", raising=False)
    monkeypatch.delenv("PRED_BLEND_MODE", raising=False)
    from predictor.rules import predict_race

    preds = predict_race(_fake_horses())
    # DB 無しのフォールバック経路ではマイニング順位がスコアの主因になる
    top = next(p for p in preds if p.rank == 1)
    assert top.horse_num == "03", "mining 1 位がスコア最上位 = 従来挙動"


def test_rank_by_probability_reorders_marks(monkeypatch):
    """PRED_RANK_BY=probability で印が確率順に付け替わること。"""
    monkeypatch.setenv("PRED_RANK_BY", "probability")
    from predictor.rules import predict_race

    preds = predict_race(_fake_horses())
    ranks = sorted(preds, key=lambda p: p.rank)
    probs = [p.win_probability for p in ranks]
    assert probs == sorted(probs, reverse=True), "確率の降順に並んでいる"
    assert ranks[0].mark == "◎" and ranks[1].mark == "○"


def test_rank_by_probability_with_lambda_zero_follows_market(monkeypatch):
    """λ=0 (市場そのまま) なら ◎ は市場最上位 (= 1 番人気) になる。

    これが「オッズに従う」設定の定義。実測で 1 番人気ベタは 79% で、
    モデル ◎ ベタ 71.5% より良かったので、この挙動が比較の基準線になる。
    """
    monkeypatch.setenv("PRED_RANK_BY", "probability")
    monkeypatch.setenv("PRED_BLEND_MODE", "residual")
    monkeypatch.setenv("PRED_W_residual_lambda_fade", "0.0")
    monkeypatch.setenv("PRED_W_residual_lambda_boost", "0.0")
    from predictor.rules import predict_race

    preds = predict_race(_fake_horses())
    top = next(p for p in preds if p.rank == 1)
    assert top.horse_num == "02", "最低オッズ (=1 番人気) が ◎ になる"
