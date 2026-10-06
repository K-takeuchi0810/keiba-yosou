TESTS = ['tests/test_c_prime_run.py']
CR = 'scripts/c_prime_run.py'
MUTANTS = [('R34 符号一致率の再抽出の回数を固定値から外す',
  'scripts/c_prime_run.py',
  '        vals, discarded = es._block_resample(data, st.make_beta_stat(packed, c + cp.STD_SUFFIX), SIGN_BOOT_N, BOOT_SEED)',
  '        vals, discarded = es._block_resample(data, st.make_beta_stat(packed, c + cp.STD_SUFFIX), 30, BOOT_SEED)')]
