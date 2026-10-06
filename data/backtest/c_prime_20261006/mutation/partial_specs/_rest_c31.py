TESTS = ['tests/test_c_prime.py']
MUTANTS = [('C31 来歴の git status で未追跡のディレクトリをまとめる', 'scripts/c_prime.py', '    status = git("status", "--porcelain", "--untracked-files=all")', '    status = git("status", "--porcelain")')]
