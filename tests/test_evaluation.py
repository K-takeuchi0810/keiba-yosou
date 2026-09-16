"""評価バッテリーの契約テスト (憲法 docs/CHARTER_2026_09_17.md)。

## なぜ要るか

2026-09-15 に「回収率 112%」と報告したあと、上位 3 件の払戻を除くと 80% に
落ちることが判明した。**報告の形が悪いと、同じ誤りを何度でも繰り返す**。
評価バッテリーは合否に関わる数字の単一の出口なので、ここが壊れると
すべての判断が壊れる。

固定する不変条件:
  1. 大当たり依存を必ず暴く (方針 9)
  2. 市場に対する情報利得が主指標として出る (方針 3)
  3. 購入 0 件は例外にする (方針 13 で 0 件は正常だが、回収率は定義できない)
  4. ブートストラップはレース単位でまとめられる (方針 10)
  5. 的中率・AUC は出るが「診断用」と明示されている (方針 3)
"""
from __future__ import annotations

import math

import pytest

from predictor.evaluation import (
    evaluate_bets,
    evaluate_probabilities,
    format_bet_report,
)


# ---------------------------------------------------------------------------
# 方針 9: 大当たり依存を暴く
# ---------------------------------------------------------------------------

def test_single_big_payout_is_exposed():
    """利益が 1 本の大当たりに依存していたら、除外後の回収率で分かること。

    2026-09-15 の実例: 回収率 112% と報告したが、上位 3 件 (39.4/22.2/20.3 倍) を
    除くと 80.3% だった。報告の形でこれを強制する。
    """
    # 399 敗 + 1 本の 200 倍 → 見かけ 50% だが中身は 1 本だけ
    r = evaluate_bets([0.0] * 399 + [200.0], race_ids=list(range(400)),
                      bootstrap_iters=200)

    assert r.return_rate == pytest.approx(0.5)
    assert r.return_rate_excl_top1 == pytest.approx(0.0), "上位 1 件除外で消えるべき"
    assert r.top_payouts[0] == 200.0


def test_broad_profit_survives_exclusion():
    """広く薄く勝っている場合は、除外しても大きくは落ちないこと。"""
    # 100 件中 40 件が 3.5 倍 → 140%。1 本あたりの寄与は 3.5/100 = 3.5% しかない
    r = evaluate_bets([3.5] * 40 + [0.0] * 60, race_ids=list(range(100)),
                      bootstrap_iters=200)

    assert r.return_rate == pytest.approx(1.4)
    # 5 件除いても 1.29 = ほとんど落ちない (大当たり 1 本依存なら 0 に落ちる)
    assert r.return_rate_excl_top5 > 1.25, "広く勝っていれば 5 件除外でも残る"
    assert r.return_rate - r.return_rate_excl_top5 < 0.15, "落ち幅が小さいこと"


def test_format_flags_big_payout_dependence():
    """人が読む形でも大当たり依存が分かること。"""
    text = format_bet_report(evaluate_bets([0.0] * 99 + [200.0],
                                           race_ids=list(range(100)),
                                           bootstrap_iters=200))
    assert "大当たり非依存 ×" in text
    assert "上位1件除外" in text


# ---------------------------------------------------------------------------
# 方針 3: 市場に対する情報利得が主指標
# ---------------------------------------------------------------------------

def test_information_gain_is_positive_when_model_beats_market():
    y = [1, 0, 1, 0, 1, 0, 0, 0]
    market = [0.5] * 8
    better = [0.9, 0.1, 0.9, 0.1, 0.9, 0.1, 0.1, 0.1]

    rep = evaluate_probabilities(y, better, market)

    assert rep.information_gain_vs_market > 0
    assert rep.market_log_loss > rep.log_loss


def test_information_gain_is_negative_when_model_is_worse():
    y = [1, 0, 1, 0]
    market = [0.5] * 4
    worse = [0.1, 0.9, 0.1, 0.9]

    rep = evaluate_probabilities(y, worse, market)

    assert rep.information_gain_vs_market < 0


def test_auc_is_labelled_as_diagnostic_only():
    """AUC が「診断用」という名前で出ること (合否に使わせないため、方針 3)。

    フィールド名が auc_diagnostic であることを固定する。名前を auc に戻すと
    合否指標として使われかねない。
    """
    rep = evaluate_probabilities([1, 0], [0.9, 0.1], [0.5, 0.5])

    assert hasattr(rep, "auc_diagnostic")
    assert not hasattr(rep, "auc"), "AUC を素の名前で出さない (方針 3)"
    assert "auc_diagnostic" in rep.as_dict()


def test_calibration_error_detects_overconfidence():
    """予測が自信過剰なら較正誤差が大きく出ること。"""
    y = [1] * 10 + [0] * 90              # 実際は 10%
    overconfident = [0.9] * 100          # 90% と言い張る

    rep = evaluate_probabilities(y, overconfident)

    assert rep.calibration_error > 0.5


# ---------------------------------------------------------------------------
# 方針 13: 購入 0 件は「正常な結果」だが回収率は定義できない
# ---------------------------------------------------------------------------

def test_zero_bets_raises_with_an_explanation():
    with pytest.raises(ValueError, match="0 件"):
        evaluate_bets([])


# ---------------------------------------------------------------------------
# 方針 10: 不確実性
# ---------------------------------------------------------------------------

def test_bootstrap_groups_by_race():
    """同一レース内の相関を壊さないこと。

    race_ids を渡すとレース単位で再抽出するので、1 レースに複数点買う戦略でも
    区間が不当に狭くならない。
    """
    # **レース内の結果が連動する**形にする (例: 同じレースに 3 点買って
    # 当たるときは 3 点とも当たる)。連動が無ければまとめる意味がないので、
    # 連動を作らないとこの検査は空振りする。
    payouts: list[float] = []
    races: list[int] = []
    for i in range(40):
        hit = (i % 4 == 0)                       # 4 レースに 1 回当たる
        payouts += [4.0, 4.0, 4.0] if hit else [0.0, 0.0, 0.0]
        races += [i] * 3

    grouped = evaluate_bets(payouts, race_ids=races, bootstrap_iters=1000)
    ungrouped = evaluate_bets(payouts, race_ids=list(range(len(payouts))),
                              bootstrap_iters=1000)

    width_g = grouped.ci95_high - grouped.ci95_low
    width_u = ungrouped.ci95_high - ungrouped.ci95_low
    assert width_g > width_u, (
        f"レース単位でまとめたのに区間が広がっていない "
        f"(まとめ {width_g:.3f} / 素 {width_u:.3f}) = まとめが効いていない")


def test_drawdown_and_streak_follow_time_order():
    """ドローダウンと連敗は時系列順で測ること。"""
    # 先に 10 連敗、そのあと勝つ
    payouts = [0.0] * 10 + [20.0]
    dates = [f"202605{i + 1:02d}" for i in range(11)]

    r = evaluate_bets(payouts, dates=dates, race_ids=list(range(len(payouts))),
                      bootstrap_iters=200)

    assert r.max_losing_streak == 10
    assert r.max_drawdown == pytest.approx(10.0)


def test_monthly_reproducibility_is_reported():
    """複数月での再現性が出ること (方針 9)。"""
    payouts = [3.0, 0.0] * 3 + [0.0, 0.0] * 3      # 5 月は黒字、6 月は全敗
    dates = ["20260510"] * 6 + ["20260610"] * 6

    r = evaluate_bets(payouts, dates=dates, race_ids=list(range(len(payouts))),
                      bootstrap_iters=200)

    assert r.n_months == 2
    assert r.profitable_month_ratio == pytest.approx(0.5)
    assert set(r.monthly_return_rates) == {"202605", "202606"}


# ---------------------------------------------------------------------------
# 合否の形
# ---------------------------------------------------------------------------

def test_target_is_140_percent_by_default():
    """既定の目標が 140% であること (憲法の最終目標)。"""
    r = evaluate_bets([1.3] * 100, race_ids=list(range(100)),
                      bootstrap_iters=200)   # 130% では未達
    assert "未達" in format_bet_report(r)

    r2 = evaluate_bets([1.5] * 100, race_ids=list(range(100)),
                       bootstrap_iters=200)
    assert "達成" in format_bet_report(r2)


def test_report_is_serialisable():
    """結果を成果物に残せること (再現性のため)。"""
    d = evaluate_bets([2.0, 0.0], race_ids=[0, 1], bootstrap_iters=100).as_dict()
    assert isinstance(d, dict)
    assert d["n_bets"] == 2
    assert "return_rate_excl_top5" in d


# ---------------------------------------------------------------------------
# 「静かに誤った値を返す」経路の回帰 (2026-09-17 コード品質レビューで実測再現)
# ---------------------------------------------------------------------------

def test_length_mismatch_is_rejected_not_truncated():
    """長さ違いを黙って切り詰めないこと。

    zip は短いほうに合わせて切るので、**半分のデータで計算した値が正常に見える**。
    実際 log_loss([1,0,1,0], [0.9,0.1]) は正しい値の半分を返していた。
    """
    from predictor.evaluation import brier, log_loss

    with pytest.raises(ValueError, match="長さが違う"):
        log_loss([1, 0, 1, 0], [0.9, 0.1])
    with pytest.raises(ValueError, match="長さが違う"):
        brier([1, 0, 1, 0], [0.9, 0.1])
    with pytest.raises(ValueError, match="長さが違う"):
        evaluate_probabilities([1, 0, 1, 0], [0.9, 0.1])


def test_calibration_error_is_nan_when_it_cannot_be_measured():
    """件数不足を「完璧な較正」と偽装しないこと。

    以前は全 bin が最小件数に満たないと 0.0 を返していた。0.0 は
    「誤差ゼロ = 完璧」と読めるので、件数不足が良い結果に化ける。
    """
    from predictor.evaluation import expected_calibration_error

    assert math.isnan(expected_calibration_error([1, 0, 0, 0], [0.9] * 4))

    rep = evaluate_probabilities([1, 0], [0.9, 0.1])
    assert math.isnan(rep.calibration_error)


def test_hyphenated_dates_are_rejected():
    """日付は YYYYMMDD のみ。

    "2026-05-10" を渡すと月キーが "2026-0" になり、何ヶ月あっても 1 ヶ月と
    集計される。同じ事故を 2026-09-14 に config 側で直したのに、
    新モジュールで再発させた。
    """
    with pytest.raises(ValueError, match="YYYYMMDD"):
        evaluate_bets([1.0, 0.0], dates=["2026-05-10", "2026-06-10"],
                      race_ids=[0, 1], bootstrap_iters=100)


def test_mismatched_dates_or_races_are_rejected():
    with pytest.raises(ValueError, match="dates の長さ"):
        evaluate_bets([1.0, 0.0], dates=["20260510"], race_ids=[0, 1],
                      bootstrap_iters=100)
    with pytest.raises(ValueError, match="race_ids の長さ"):
        evaluate_bets([1.0, 0.0], race_ids=[1], bootstrap_iters=100)


def test_no_stake_argument_so_units_cannot_mix():
    """賭け金の引数を持たないこと (単位の混在を構造で防ぐ)。

    以前は stake_each を受け取っていたが、払戻は倍率・賭け金は金額として
    扱っていたため stake_each=100 にすると収支が桁違いになった。
    入力を「1 単位賭けたときの倍率」に統一して混ざりようをなくす。
    """
    import inspect

    assert "stake_each" not in inspect.signature(evaluate_bets).parameters


# ---------------------------------------------------------------------------
# 合否は点推定ではなく区間の下限 (2026-09-17 収益性レビュー指摘)
# ---------------------------------------------------------------------------

def test_judgement_uses_ci_lower_bound_not_point_estimate():
    """点推定が目標を超えただけでは「達成」と書かないこと。

    憲法の合格条件は「140% を統計的に確認できないモデルは本番投入しない」。
    点推定で達成と書くと、報告様式そのものが誤読を誘発する。
    """
    # 点推定は 140% ちょうどだが、外れが多くて区間は大きく下に開く
    payouts = [14.0] * 10 + [0.0] * 90        # 回収率 140%、的中 10%
    r = evaluate_bets(payouts, race_ids=list(range(len(payouts))),
                      bootstrap_iters=1000)
    text = format_bet_report(r)

    assert r.return_rate == pytest.approx(1.4)
    assert r.ci95_low < 1.4, "この構成なら区間下限は 140% を下回るはず"
    assert "未達" in text, "点推定 140% で『達成』と書いてはいけない"


def test_small_sample_is_reported_as_undecidable():
    """件数が少なすぎるときは合否を言わないこと。"""
    text = format_bet_report(evaluate_bets([2.0] * 20, race_ids=list(range(20)),
                                          bootstrap_iters=200))
    assert "判定不能" in text


def test_multiple_comparison_adjustment_is_shown():
    """何通り試した中の 1 つかを渡すと、補正後の下限が出ること。

    Phase 1 の交互作用探索では何百通りも試すので、素の区間だけを見ると
    「探して一番良かったもの」を実力と誤認する。
    """
    payouts = [3.0] * 50 + [0.0] * 50
    rid = list(range(len(payouts)))
    plain = evaluate_bets(payouts, race_ids=rid, bootstrap_iters=500)
    searched = evaluate_bets(payouts, race_ids=rid, bootstrap_iters=500,
                             n_hypotheses=500)

    assert searched.ci_adjusted_low < plain.ci95_low, "補正後は下限が下がるはず"
    assert "多重比較" in format_bet_report(searched)
    assert "多重比較" not in format_bet_report(plain)


def test_race_ids_are_required():
    """レース単位の指定を省略できないこと。

    省略すると馬単位の再抽出になり、1 レース複数点買う戦略で区間が不当に
    狭くなる。狭い区間は「有意」の誤認を生むので、黙って許さない
    (2026-09-17 検証レビュー指摘)。
    """
    with pytest.raises(ValueError, match="race_ids が必要"):
        evaluate_bets([1.0, 0.0, 2.0], bootstrap_iters=100)


def test_odds_source_must_be_declared_from_a_fixed_set():
    """T-10 と確定オッズを混ぜた数字を作らせないこと。

    2026-09-17 の予想ロジックレビューで、情報利得を「ほぼ確定オッズ」に対して
    測っていたことが判明した。出所を明示しないと同じ取り違えが起きる。
    """
    with pytest.raises(ValueError, match="odds_source"):
        evaluate_bets([1.0, 0.0], race_ids=[0, 1], odds_source="てきとう",
                      bootstrap_iters=100)

    r = evaluate_bets([1.0, 0.0], race_ids=[0, 1], odds_source="T-10",
                      bootstrap_iters=100)
    assert r.meta["odds_source"] == "T-10"


def test_report_carries_provenance():
    """成果物が「どの期間・どのコードで出した数字か」を自分で説明できること。"""
    r = evaluate_bets([1.0, 0.0], race_ids=[0, 1], dates=["20260510", "20260511"],
                      odds_source="T-10", split_name="strategy_dev",
                      bootstrap_iters=100)

    assert r.meta["window"] == ["20260510", "20260511"]
    assert r.meta["split_name"] == "strategy_dev"
    assert "git_sha" in r.meta and "evaluated_at" in r.meta
    assert "meta" in r.as_dict()
