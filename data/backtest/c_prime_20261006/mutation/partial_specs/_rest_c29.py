TESTS = ['tests/test_c_prime.py']
MUTANTS = [('C29 履歴だけの読み込みで主検定の年の着順を NULL にしない',
  'scripts/c_prime.py',
  '        result_cols = (f"CASE WHEN CAST(h.race_year AS INTEGER) >= {PRIMARY_YEAR} THEN NULL ELSE h.confirmed_order END, "',
  '        result_cols = ("h.confirmed_order, "')]
