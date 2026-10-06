TESTS = ['tests/test_c_prime_run.py']
MUTANTS = [('R35 2025 の履歴の digest から脚質コードを外す',
  'scripts/c_prime_run.py',
  '            h.update(f"{rid}|{x.horse}|{x.horse_num}|{int(rm.is_refunded(x.abnormal))}|{x.leg}\\n".encode("utf-8"))',
  '            h.update(f"{rid}|{x.horse}|{x.horse_num}|{int(rm.is_refunded(x.abnormal))}\\n".encode("utf-8"))'),
 ('R36 2025 の履歴の digest から返還を外す',
  'scripts/c_prime_run.py',
  '            h.update(f"{rid}|{x.horse}|{x.horse_num}|{int(rm.is_refunded(x.abnormal))}|{x.leg}\\n".encode("utf-8"))',
  '            h.update(f"{rid}|{x.horse}|{x.horse_num}|{x.leg}\\n".encode("utf-8"))'),
 ('R37 錠の前の照合で 2025 の結果を NULL にしない', 'scripts/c_prime_run.py', '                             primary_year_history_only=True)\n', '                             primary_year_history_only=False)\n')]
