# 採点 2026-06-07 05:43

**改修内容**: pytest を正式依存化 — requirements-dev.txt 新設 / pyproject.toml に testpaths+pythonpath / weekly_monitor.bat に回帰検知フック組込 / conftest.py の sys.path ハック削減
**対象ファイル**: requirements-dev.txt, pyproject.toml, weekly_monitor.bat, tests/conftest.py

前回 scorecard (`20260607_0530_portfolio_helper_extract.md`) の「横断的優先課題 1: pytest を依存・運用フックに正式化」(4 名指摘) への直接対応。GUI / モバイル HTML / 予想ロジック / 収益性の 4 専門家は本改修 (テスト基盤 / 運用フックのみ、本体ロジック・HTML・backtest 数値に diff なし) では採点対象範囲外のため、関連 3 名のみ起動した。

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 |
|---|---|---|---|
| コード品質レビュアー | 4.4 | 3.9 | +0.5 |
| 検証プロセス監査人 | 4.5 | 4.2 | +0.3 |
| データパイプライン技師 | 4.2 | 4.4 | -0.2 (採点軸が運用フック関連に限定された範囲差。本体品質劣化ではない) |
| (GUI / モバイル / 予想ロジック / 収益性) | N/A | — | 本改修は対象範囲外のため未起動 |

全項目維持または改善。-0.3 以上の後退なし (data-pipeline の -0.2 は評価範囲限定によるもので回帰ではない)。

## 各専門家の所見

### コード品質レビュアー (4.4 / 5, +0.5)

- DRY 5/5: sys.path 注入を pyproject.toml 1 箇所に集約、conftest.py から手動ハック完全撤去。pytest 設定の出典は pyproject.toml のみ (setup.cfg/pytest.ini/tox.ini いずれも不在)。
- dead code 5/5: 新規 3 ファイルに dead シンボルなし。conftest.py は docstring のみに縮退。
- magic number 4/5: pythonpath/testpaths を設定外出し。バージョン pin は正しい慣行。
- テスト容易性 4/5: tests/ 不在の長年の減点要因が解消。compute_day_portfolio の 12 ケース境界テストを weekly_monitor.bat で自動回帰検知化。減点理由は portfolio 1 モジュールのみで rules.py/features.py 等中核未カバー (第一歩としては妥当)。
- エラー処理 4/5: exit code 合成が堅実。改善余地は失敗時の詳細出力導線。
- 提案: (1) 失敗時 `-v --tb=short --lf` 再実行導線、(2) scripts/ の sys.path.insert 11 箇所を pythonpath 化する横展開、(3) requirements-dev.txt と .bat の実行コマンド二重記述を doc 参照化。

### 検証プロセス監査人 (4.5 / 5, +0.3)

- A/B・バージョン管理 4→4.5: pytest を `>=9.0,<10.0` で pin + testpaths/pythonpath 固定で「どの起動ディレクトリ・どの venv でも同一収集」を保証。前回 +0.5 を抑えた唯一の理由「subagent 環境で pytest 未導入・飾り状態」を構造的に解消。
- 過適合監視 4→4.5: 月次 Brier 監視バッチに回帰 test を編入、helper 契約崩れの二次汚染を週次検知。
- backtest/calibration/リーク防止は本改修で無介入のため据え置き (リーク防止 test を運用フックへ常時接続した点を評価)。
- 提案: (1) test 失敗と Brier drift を exit code で区別 (bit 合算)、(2) pytest exit 5 (no tests collected) の専用メッセージ、(3) docs/OPERATION.md に `pip install -r requirements-dev.txt` 前提条件を明記。

### データパイプライン技師 (4.2 / 5)

- パイプライン本体 (client.py/ingest.py/parser.py/db.py/schema.sql) に diff なしを明記。運用フック weekly_monitor.bat の exit code 設計のみが関連範囲。
- exit code 伝播 5/5: TESTCODE/MONCODE 分離保持、test 失敗を Brier drift 警告と独立させ誤発火しない設計が模範的。
- 回帰検知の妥当性 4/5: 12 テスト 0.04s と軽量。ただし pytest 未導入環境で毎週誤警告の恐れ。
- 提案: (1) pytest 未導入時の誤警告ガード、(2) test 失敗ログの保全 (`--tb=line` / ログ出力)、(3) ingest 冪等性・parser 固定長境界の回帰テストを tests/ に追加。

## 横断的に見た優先課題

1. **【本セッションで対応済】weekly_monitor.bat の運用堅牢性** (担当: data-pipeline #1 + validation #1)
   - pytest 未導入環境での誤警告を `import pytest` プローブでガードしスキップ (狼少年化防止) → 実装済。
   - test 失敗 (bit1=2) と Brier drift (bit0=1) を区別する exit code 合算に変更 → 実装済。
   - 副次的に、echo 内の未エスケープ `)` が if ブロックを途中終了させる潜在バグ (元ファイルからの持ち越し、Brier ブロックが実際に走ると ". was unexpected" で落ちる) を `^(` `^)` エスケープで修正。
2. **docs/OPERATION.md に dev 依存の前提条件を明記** (担当: validation #3)
   - Task Scheduler セットアップ手順に `.venv64` への `pip install -r requirements-dev.txt` を前提として追記。未対応 (次セッション候補、ガード実装で実害は軽減済)。
3. **テストカバレッジを中核ロジックへ拡張** (担当: code-quality #2 + data-pipeline #3)
   - 現状 portfolio 1 モジュール 12 ケースのみ。rules.py / features.py / ingest 冪等性 / parser 固定長境界へ拡張すれば本フックが真の安全網になる。未着手。

## 検証ログ

- `.venv64\Scripts\python.exe -m pytest tests/ -q` → **12 passed** (リポルートから)
- `.venv64\Scripts\python.exe -m pytest -q` → **12 passed** (testpaths 駆動、パス引数なし)
- conftest.py の sys.path ハック撤去後も pythonpath=["."] で `from config import` 解決を確認
- weekly_monitor.bat 実機実行: pytest 12 passed → scripts.monitor (LGBM/calibrator ロード) へ正常遷移。ASCII 化 + paren エスケープで cmd パースエラー解消を確認。
