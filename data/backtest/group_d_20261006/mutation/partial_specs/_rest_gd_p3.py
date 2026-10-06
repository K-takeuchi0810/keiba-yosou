TESTS = ['tests/test_group_d.py', 'tests/test_group_d_run.py']
MUTANTS = [('P3 SE の小さい方を採る',
  'scripts/prereg_runner.py',
  '    se_fixed = max(se_analytic, se_scaled) if se_scaled is not None else se_analytic',
  '    se_fixed = min(se_analytic, se_scaled) if se_scaled is not None else se_analytic')]
