TESTS = ['tests/test_group_d.py', 'tests/test_group_d_run.py']
MUTANTS = [('D5 要求水準を平均にする',
  'scripts/group_d.py',
  '            self.cache[k] = float(np.median(self.vals[(cls, surface)][lo:hi])) if hi - lo >= MIN_REQUIREMENT_RACES else math.nan',
  '            self.cache[k] = float(np.mean(self.vals[(cls, surface)][lo:hi])) if hi - lo >= MIN_REQUIREMENT_RACES else math.nan'),
 ('D12 class_move の欠損を 0 で埋める', 'scripts/group_d.py', '        m_fill = sum(r["class_move"] for r in obs) / len(obs)', '        m_fill = 0.0'),
 ('R5 主検定の結果を上書きできる', 'scripts/group_d_run.py', '    if (out / PRIMARY_FILE).exists():', '    if False:'),
 ('R7 別の凍結物の検出力を受け入れる',
  'scripts/group_d_run.py',
  '    if power["frozen_sha256"] != man["frozen_sha256"] or power.get("frozen_manifest_sha256") != pr.sha256(frozen / MANIFEST_FILE):',
  '    if False:'),
 ('R8 錠を 2 回書ける', 'scripts/group_d_run.py', '    if previous is not None and not rerun_reason:', '    if False:'),
 ('R9 学習期のブートストラップの回数を固定値から外す',
  'scripts/group_d_run.py',
  '    vals, discarded = es._block_resample(srows, st.make_beta_stat(packed, "S_std"), BOOT_N, BOOT_SEED)',
  '    vals, discarded = es._block_resample(srows, st.make_beta_stat(packed, "S_std"), 30, BOOT_SEED)'),
 ('R10 対象レースの SQL の結果の列の検査を外す',
  'scripts/group_d_run.py',
  '    if bad:\n        raise pr.RunError(f"対象レースの SQL に結果の列が入っている: {bad}")',
  '    if False:\n        raise pr.RunError(f"対象レースの SQL に結果の列が入っている: {bad}")'),
 ('R11 検出力で 2021-2024 の履歴を照合しない',
  'scripts/group_d_run.py',
  '    _check_history(races, man)\n'
  '    tables, _ = ga.tables_from_payload(payload["rating_tables"], races)\n'
  '    history = gd.run_ratings(races, tables)\n'
  '    req = gd.Requirements(races, gd.winner_ratings(races, history))\n'
  '    primary_history',
  '    tables, _ = ga.tables_from_payload(payload["rating_tables"], races)\n'
  '    history = gd.run_ratings(races, tables)\n'
  '    req = gd.Requirements(races, gd.winner_ratings(races, history))\n'
  '    primary_history'),
 ('R12 2025 の履歴の照合を外す',
  'scripts/group_d_run.py',
  '    if primary_year_history_digest(races, PRIMARY_YEAR) != power["primary_year_history_digest"]:\n        raise pr.RunError("2025 の履歴が検出力の計算の時点と違う (DB が変わった)")',
  '    pass'),
 ('R13 判定を副次の記録の後に書く', 'scripts/group_d_run.py', '    pr.write_json(out / PRIMARY_FILE, result)\n    try:\n        side = _side_records(', '    try:\n        side = _side_records('),
 ('R14 副次の記録の失敗を握り潰す', 'scripts/group_d_run.py', '        side = {"error": f"{type(e).__name__}: {e}"}', '        side = {}'),
 ('P1 git の状態が不明でも通す (fail-open)', 'scripts/prereg_runner.py', '    if now_prov["git_dirty"] is not False:', '    if now_prov["git_dirty"]:'),
 ('P2 固定のファイルが無くても通す', 'scripts/prereg_runner.py', '    if missing:\n        raise RunError', '    if False:\n        raise RunError'),
 ('P3 SE の小さい方を採る',
  'scripts/prereg_runner.py',
  '    se_fixed = max(se_analytic, se_scaled) if se_scaled is not None else se_analytic',
  '    se_fixed = min(se_analytic, se_scaled) if se_scaled is not None else se_analytic'),
 ('P4 下限 0 ちょうどを PASS にする', 'scripts/prereg_runner.py', '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] > 0 else', '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] >= 0 else'),
 ('P5 区間が無効なら MDE の理由を上書きする',
  'scripts/prereg_runner.py',
  '    if power["inconclusive_by_power"]:\n'
  '        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")\n'
  '    if not ci["valid"]:\n'
  '        return "PRIMARY_INCONCLUSIVE", "boot_na"',
  '    if not ci["valid"]:\n'
  '        return "PRIMARY_INCONCLUSIVE", "boot_na"\n'
  '    if power["inconclusive_by_power"]:\n'
  '        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")'),
 ('P6 来歴の git status で未追跡のディレクトリをまとめる', 'scripts/prereg_runner.py', '    status = _git(root, "status", "--porcelain", "--untracked-files=all")', '    status = _git(root, "status", "--porcelain")'),
 ('P7 自分の出力先を 1 つしか除かない',
  'scripts/prereg_runner.py',
  '        return any(p == o.rstrip("/") or p.startswith(o.rstrip("/") + "/") for o in owns)',
  '        return bool(owns) and (p == owns[0].rstrip("/") or p.startswith(owns[0].rstrip("/") + "/"))'),
 ('P8 NaN を null にしない', 'scripts/prereg_runner.py', '    if isinstance(obj, float) and not math.isfinite(obj):\n        return None', '    if False:\n        return None')]
