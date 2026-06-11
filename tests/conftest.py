"""pytest 共通設定。

リポジトリルートの import path 追加は pyproject.toml の
`[tool.pytest.ini_options] pythonpath = ["."]` が担う
(predictor.portfolio が `from config import ...` するため)。
このファイルは tests/ を pytest のテストパッケージとして明示する役割のみ。
"""
