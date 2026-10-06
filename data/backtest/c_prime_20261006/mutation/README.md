# Group C′ の変異テストの記録 (2026-10-06)

- spec: `tests/mutation_specs/c_prime_spec.py` (最初 28 個 → 現在 32 個。C1〜C9 は対象レース自身の脚質コードの混入と PIT の変異)
- 実行: `git archive <sha>` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- run1 (`2bc5c47`): KILLED 27 / SURVIVED 1 (C4 直近 6 走を数える — テストの例が 5 走でも 6 走でも同じ値になっていた) → 例を差し替え
- run2 (`1e15c69`): **KILLED 28 / 28**
- run3 (`de3de16`): **KILLED 28 / 28** (実行のスクリプトを足した後の再確認)

## 実行のスクリプト (`tests/mutation_specs/c_prime_run_spec.py`、最初 24 個 → 現在 37 個)

- run_spec_r1 (`c100d73`): KILLED 21 / SURVIVED 3 (R4 別の凍結物の検出力 / R8 ブートストラップの回数 / R10 錠の後の固定のファイルの変更) → テストを足した
- run_spec_r2 (`de3de16`): R11 で **ABORTED** (11:30 の本番の fresh odds の取得・健全性チェック・DB の WAL。変異の影響ではない)
- run_spec_r3 (`de3de16`): **KILLED 24 / 24**

## 凍結の前の 4 名レビュー (ddc12b6) の反映の後 (`da6fce1` / `94a2bbb`)

- 実行の spec (34 個、R25〜R34 を追加): run_spec_r4 (`da6fce1`) は R1〜R33 が **KILLED 33** の後、R34 で ABORTED (本番の `keiba.db-wal` の更新)。
  R34 だけの spec (コピーの中の一時の spec) で run_spec_r4b → **KILLED** → **34 / 34**
- 計算の spec (30 個、C29・C30 を追加): run4 (`da6fce1`) は C4 で ABORTED (本番の WAL)。run5 (`da6fce1`) で KILLED 29 / SURVIVED 1
  (C29 主検定の年の着順を SQL で NULL にしない — それを殺すテストは実行のテストの側にあって、計算の spec の TESTS に入っていなかった) →
  計算のテストにも同じ検査を足し (`94a2bbb`)、C29 だけの spec で run5b → **KILLED** → **30 / 30**
- ABORT はすべて本番の別のプロセスの書き込みの検出で、変異の影響ではない
- run6 (`2f455ab`): C31 (来歴の git status で未追跡のディレクトリをまとめる) だけの spec で **KILLED** → 計算の spec **31 / 31**

## 主検定の後の 4 名レビュー (58dd91e) の後 (`5a58261`、テストだけ)

- R35 (2025 の履歴の digest から脚質コードを外す) / R36 (返還を外す) / R37 (錠の前の照合で 2025 の結果を NULL にしない) / C32 (Z_DIRECTION を変える) を
  追加し、それぞれだけの spec で **KILLED** (`run_spec_r5_5a58261_R35-R37_only.txt` / `run7_5a58261_C32_only.txt`) → 計算 **32 / 32**、実行 **37 / 37**
- 部分の再実行に使った一時の spec は `partial_specs/` に保存した (変異の 4 タプルはコミット済みの spec の同名のエントリと同じ。`runpy` で読み、名前の接頭辞で
  抜き出して書いたもの)
