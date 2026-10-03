"""block_boot_ci / primary_block_ci (Phase 0.5-5 の主検定の区間) の変異の定義 (2026-10-04)。

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/block_boot_ci_spec.py
"""

TESTS = ["tests/test_eval_stats.py"]

ES = "predictor/eval_stats.py"

MUTANTS = [
    ("C1 端点を 95% に固定する", ES,
     "    alpha = (1.0 - level) / 2.0\n",
     "    alpha = 0.025\n"),
    ("C2 水準の検査を外す", ES,
     "    if not isinstance(level, float) or not (0.5 <= level < 1.0):",
     "    if False:"),
    ("C3 回数の下限を外す", ES,
     "    if not isinstance(n_boot, int) or isinstance(n_boot, bool) or n_boot < 100:",
     "    if False:"),
    ("C4 主検定で 99% 以外も許す", ES,
     "    if level != PRIMARY_CI_LEVEL:",
     "    if False:"),
    ("C5 主検定の回数を 1000 にする", ES,
     "PRIMARY_N_BOOT = 5000",
     "PRIMARY_N_BOOT = 1000"),
    ("C6 捨てる上限を見ない", ES,
     '    if discarded > out["max_discard"] or not vals:',
     '    if not vals:'),
    ("C7 捨てた回数を数えない", ES,
     "            discarded += 1\n",
     ""),
    ("C8 seed を使わない", ES,
     "    rng = random.Random(seed)\n",
     "    rng = random.Random()\n"),
    ("C9 従来の block_boot の端点を変える", ES,
     "    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]",
     "    return vals[int(0.005 * len(vals))], vals[int(0.995 * len(vals))]"),
    ("C10 主検定の seed を変える", ES,
     "PRIMARY_SEED = 20261004",
     "PRIMARY_SEED = 20260918"),
    ("C11 主検定の捨てる上限を 5% にする", ES,
     "PRIMARY_MAX_DISCARD_FRAC = 0.01",
     "PRIMARY_MAX_DISCARD_FRAC = 0.05"),
    ("C12 上側の分位を lower と同じ式にする", ES,
     '    return {**out, "lo": vals[int(alpha * n)], "hi": vals[int((1.0 - alpha) * n)], "valid": True}',
     '    return {**out, "lo": vals[int(alpha * n)], "hi": vals[int((1.0 - alpha) * n) - 1], "valid": True}'),
]
