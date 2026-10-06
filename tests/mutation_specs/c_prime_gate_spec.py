"""C′ の前の最終ゲート (市場の列の単一の出典・恒等性・fail-closed・不変性) の変異の定義 (2026-10-06)。

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/c_prime_gate_spec.py
"""

TESTS = ["tests/test_market_clogit.py", "tests/test_race_market.py"]

RM = "predictor/race_market.py"
MC = "predictor/market_clogit.py"

MUTANTS = [
    ("G1 市場の列を logit にする", RM,
     "    return math.log(p)\n",
     "    return math.log(p / (1 - p))\n"),
    ("G2 不正な市場の確率を epsilon で丸める", RM,
     "        raise MarketFeatureError(f\"市場の確率が不正: {p!r} (0 < p ≤ 1 の有限の値だけ)\")\n    return math.log(p)\n",
     "        p = 1e-12\n    return math.log(p)\n"),
    ("G3 1 を超える市場の確率を通す", RM,
     "not math.isfinite(p) or not 0.0 < p <= 1.0:",
     "not math.isfinite(p) or not 0.0 < p:"),
    ("G4 canonical (和 1) を確かめない", MC,
     "        if not abs(total - 1.0) <= SUM_TOL:",
     "        if False:"),
    ("G5 尤度の列が自前の log を使う", MC,
     "        r[MARKET_COL] = rm.market_feature(r[p_key])",
     "        r[MARKET_COL] = math.log(r[p_key])"),
    ("G6 Fisher の列が自前の log を使う", MC,
     "        X = np.array([[rm.market_feature(r[p_key]), r[s_col]] for r in rs], dtype=float)",
     "        X = np.array([[math.log(r[p_key]), r[s_col]] for r in rs], dtype=float)"),
    ("G7 Fisher の仮定の重みに P_market をそのまま使う", MC,
     '        p = np.array([p_null[r["horse_num"]] for r in rs])',
     "        p = np.array([r[p_key] for r in rs])"),
    ("G8 検出力の行の勝ちの列を拒否しない", MC,
     '    if any("won" in r for r in rows):',
     "    if False:"),
    ("G9 比を正規化した P_new でなく exp(β·S) で取る", MC,
     "        out.extend((rid, h) for h in rm.ratio_buys(pn, p_market, threshold))",
     "        out.extend((rid, r[\"horse_num\"]) for r in rs if math.exp(beta_s * r[s_col]) >= threshold)"),
    ("G10 S-correction only を推定した β_market で作る", MC,
     '            "s_correction_only": set(ratio_buys_at(rows, 1.0, beta_s_hat, s_col, p_key))}',
     '            "s_correction_only": set(ratio_buys_at(rows, beta_market_hat, beta_s_hat, s_col, p_key))}'),
    ("G11 market-recalibration only に S を入れる", MC,
     '            "market_recalibration_only": set(ratio_buys_at(rows, beta_market_hat, 0.0, s_col, p_key)),',
     '            "market_recalibration_only": set(ratio_buys_at(rows, beta_market_hat, beta_s_hat, s_col, p_key)),'),
    ("G12 P_new が β_market を無視する", RM,
     "    u = {h: beta_market * market_feature(p) + beta_s * s[h] for h, p in p_market.items()}",
     "    u = {h: market_feature(p) + beta_s * s[h] for h, p in p_market.items()}"),
    ("G13 P_new が market_feature を通らない", RM,
     "    u = {h: beta_market * market_feature(p) + beta_s * s[h] for h, p in p_market.items()}",
     "    u = {h: beta_market * math.log(p) + beta_s * s[h] for h, p in p_market.items()}"),
    ("G14 当てはめの列の順を入れ替える", MC,
     "    beta, ok = conditional_logit(rows, [MARKET_COL, s_col], with_status=True)",
     "    beta, ok = conditional_logit(rows, [s_col, MARKET_COL], with_status=True)"),
]
