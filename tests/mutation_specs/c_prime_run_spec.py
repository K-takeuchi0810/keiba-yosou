"""Phase 0.5-5 Group C′ の実行 (scripts/c_prime_run.py) の変異の定義 (2026-10-06)。

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/c_prime_run_spec.py
"""

TESTS = ["tests/test_c_prime_run.py"]

CR = "scripts/c_prime_run.py"

MUTANTS = [
    ("R1 主検定を同じ run_index で 2 回走らせられる", CR, "    if started_path.exists():", "    if False:"),
    ("R2 錠を 2 回書ける", CR, "    if previous is not None and not rerun_reason:", "    if False:"),
    ("R3 凍結物の sha256 を見ない", CR, '    if _sha(frozen / FROZEN_FILE) != man["frozen_sha256"]:', "    if False:"),
    ("R4 別の凍結物の検出力を受け入れる", CR,
     '    if power["frozen_sha256"] != man["frozen_sha256"] or power.get("frozen_manifest_sha256") != _sha(frozen / MANIFEST_FILE):',
     "    if False:"),
    ("R5 区間が無効なら MDE の理由を上書きする", CR,
     '''    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")
    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"''',
     '''    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"
    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")'''),
    ("R6 検出力の判定不能を無視する", CR, '    if power["inconclusive_by_power"]:', "    if False:"),
    ("R7 下限 0 ちょうどを PASS にする", CR,
     '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] > 0 else',
     '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] >= 0 else'),
    ("R8 学習期のブートストラップの回数を固定値から外す", CR,
     '    vals, discarded = es._block_resample(srows, st.make_beta_stat(packed, "S"), BOOT_N, BOOT_SEED)',
     '    vals, discarded = es._block_resample(srows, st.make_beta_stat(packed, "S"), 50, BOOT_SEED)'),
    ("R9 開始の印を 2025 を読む前に書かない", CR,
     '    _write_json(started_path, {"run_index": run_index,',
     '    _write_json(out / "moved.json", {"run_index": run_index,'),
    ("R10 主検定の時に錠の固定のファイルと照合しない", CR,
     '    if pinned["pinned_blob_sha1"] != lock["pinned_blob_sha1"]:', "    if False:"),
    ("R11 錠のコミットを確かめない", CR, "    if not _lock_is_committed(lock_path):", "    if False:"),
    ("R12 錠が別の凍結物・検出力でも走る", CR,
     '    if lock["frozen_sha256"] != man["frozen_sha256"] or lock["power_sha256"] != _sha(power_path):', "    if False:"),
    ("R13 SE の小さい方を採る", CR,
     "    se_fixed = max(se_analytic, se_scaled) if se_scaled is not None else se_analytic",
     "    se_fixed = min(se_analytic, se_scaled) if se_scaled is not None else se_analytic"),
    ("R14 臨界の倍率を 1.96 にする", CR, "    m = CRITICAL_MULTIPLIER * se_fixed", "    m = 1.96 * se_fixed"),
    ("R15 対象レースの SQL の結果の列の検査を外す", CR,
     '    if bad:\n        raise RunError(f"対象レースの SQL に結果の列が入っている: {bad}")',
     '    if False:\n        raise RunError(f"対象レースの SQL に結果の列が入っている: {bad}")'),
    ("R16 返る列の完全一致を確かめない", CR, "    if names != TARGET_COLUMNS:", "    if False:"),
    ("R17 返還の印を無視する", CR,
     '        cs = rm.build_choice_set({x["horse_num"]: ("3" if x["refunded"] else "0") for x in runners},',
     '        cs = rm.build_choice_set({x["horse_num"]: "0" for x in runners},'),
    ("R18 件数を exp(β·S) の目安で数える", CR,
     "    buys = mc.ratio_buys_at(rows, 1.0, BETA_TARGET)",
     '    buys = [r for r in rows if math.exp(BETA_TARGET * r["S"]) >= 1.25]'),
    ("R19 履歴の照合に脚質コードを含めない", CR,
     '            h.update(f"{rid}|{x.horse}|{x.horse_num}|{x.abnormal}|{x.finish}|{x.win_odds!r}|{x.leg}\\n".encode("utf-8"))',
     '            h.update(f"{rid}|{x.horse}|{x.horse_num}|{x.abnormal}|{x.finish}|{x.win_odds!r}\\n".encode("utf-8"))'),
    ("R20 検出力で履歴を照合しない", CR,
     "    _check_history(races, man)\n    history, experience = cp.style_history(races), cp.experience_index(races)\n    del races",
     "    history, experience = cp.style_history(races), cp.experience_index(races)\n    del races"),
    ("R21 錠のコミットの判定で変更を見ない", CR,
     "    return tracked.returncode == 0 and status.returncode == 0 and not status.stdout.strip()",
     "    return tracked.returncode == 0"),
    ("R22 条件付きロジットの列から市場を外す", CR, 'COLS = [mc.MARKET_COL, "S"]', 'COLS = ["S"]'),
    ("R23 凍結物の定数を照合しない", CR,
     '    if payload["constants"] != {"window_days": cp.WINDOW_DAYS, "history_runs": cp.HISTORY_RUNS, "style_codes": list(cp.STYLE_CODES)}:',
     "    if False:"),
    ("R24 作業ツリーの未コミットの変更を見ない", CR, '    if now["git_dirty"]:', "    if False:"),
]
