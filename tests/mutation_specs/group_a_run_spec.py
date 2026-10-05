"""Phase 0.5-5 Group A の実行 (scripts/group_a_run.py) と配列版の推定 (scripts/group_a_stats.py) の変異の定義 (2026-10-06)。

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/group_a_run_spec.py
"""

TESTS = ["tests/test_group_a_run.py", "tests/test_group_a_stats.py"]

GR = "scripts/group_a_run.py"
GS = "scripts/group_a_stats.py"

MUTANTS = [
    ("R1 E1b の選択と違う候補を凍結できる", GR,
     "    if sel != spec_name:",
     "    if False:"),
    ("R2 主検定を 2 回走らせられる", GR,
     "    if (out / PRIMARY_FILE).exists():",
     "    if False:"),
    ("R3 凍結物の sha256 を見ない", GR,
     '    if _sha(frozen / FROZEN_FILE) != man["frozen_sha256"]:',
     "    if False:"),
    ("R4 別の凍結物の検出力を受け入れる", GR,
     '    if power["frozen_sha256"] != man["frozen_sha256"]:',
     "    if False:"),
    ("R5 valid より先に検出力を見る", GR,
     '''    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"
    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", "mde_above_beta_target"''',
     '''    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", "mde_above_beta_target"
    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"'''),
    ("R6 検出力の判定不能を無視する", GR,
     '    if power["inconclusive_by_power"]:',
     "    if False:"),
    ("R7 下限 0 ちょうどを PASS にする", GR,
     '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] > 0 else',
     '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] >= 0 else'),
    ("R8 学習期のブートストラップの回数を固定値から外す", GR,
     "    vals, discarded = es._block_resample(rows, st.make_beta_stat(packed, \"S\"), BOOT_N, BOOT_SEED)",
     "    vals, discarded = es._block_resample(rows, st.make_beta_stat(packed, \"S\"), 50, BOOT_SEED)"),
    ("S1 配列版で標準化の SD を取らない", GS,
     "    scale = np.sqrt(var)\n",
     "    scale = np.ones_like(var)\n"),
    ("S2 配列版で 1 歩の上限を外す", GS,
     "        if big > STEP_CAP:",
     "        if False:"),
    ("S3 配列版で詰め物の行を確率に入れる", GS,
     "    neg = np.where(mask > 0, 0.0, -np.inf)",
     "    neg = np.zeros_like(mask)"),
    ("S4 配列版で勝ち馬のいないレースを残す", GS,
     "    keep = ysum > 0\n",
     "    keep = ysum >= 0\n"),
    ("S5 再抽出のレースの並びを使わない", GS,
     "        beta, ok = clogit_packed(p, races_of_draw(draw))",
     "        beta, ok = clogit_packed(p)"),
]
