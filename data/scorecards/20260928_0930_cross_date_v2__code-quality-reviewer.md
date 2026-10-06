# code-quality-reviewer — cross-date 修正 v2 (must-fix Y8 の是正、スコープ限定再レビュー)

- 対象: worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\cross-date`, branch `cross-date-fix-20260926`, HEAD `9cff875cc53532f75c6783c6e0b3655172f74820` (前回の `c3be0e9` の上に 1 commit、tests のみ)
- 評価方式: **subagent CWD 限定運用での評価** (すべて `git -C <worktree>` / 絶対パス)。開始・終了とも HEAD `9cff875`、porcelain 空 (0 行) を確認
- 改修タイプ: **type-B** (前回と同じ)。P25 固有項目は N/A。前回 scorecard `20260928_0852_cross_date__code-quality-reviewer.md` の must-fix 1 件のみを再検査 (CHAT 指示の 5 項目に限定)
- 安全: 本番 DB 不使用 (builder の実行なし)。変異は scratchpad `cross_cqr/copy2` (`git archive 9cff875`、`.venv64` はジャンクション) で `scripts.mutation_sandbox` 経由のみ。main checkout / worktree への書き込みは本 scorecard のみ

## 判定: PASS

前回の must-fix は解消。停止条件への抵触なし。残る留保は前回の「任意」項目のみ。

## 総合: 4.2 / 5 (前回 4.1 → テスト容易性 4.0 → 4.5)

| 軸 | 点 | 要点 |
|---|---|---|
| DRY / 単一出典 | 4.0 | 変更なし (本体コード diff 0)。前回の留保 (anchor 契約 3 リテラル / race_id 組み立て 3 か所) はそのまま、任意項目 |
| dead code / 未実装前提 | 4.5 | 変更なし |
| マジックナンバー / 設定外出し | 4.0 | 変更なし (docstring の終了コード・manifest 新キー未記載は残る、任意項目) |
| テスト容易性 / 変更失敗モード | 4.5 | 本番と同じ印構成 (◎○▲△☆ + 印なし 2 頭、7 頭) の対象日レースが main() を通って rc 0・全 7 頭が summary に出ることを固定。**Y8 が KILLED** になり「答え合わせが全日止まるがテストは緑」の失敗モードは閉じた |
| 例外処理 / 観測可能性 | 4.0 | 変更なし (stderr 文言の固定 = 前回 Y2 は任意項目のまま) |

## CHAT 指定の 5 項目 (自分で実行)

1. **新テストの内容**: `tests/test_cross_date.py:178-194` `test_a_realistically_marked_target_race_is_scored_in_full`。馬 7 頭 (◎○▲△☆ + 印なし ×2)、DB 側に `extra_horses` で 2..7 番を着順付きで用意、`_run_main` (既定 `expected_rc=0`) → `evaluation_summary.csv` の race `20260712-02-01` が **7 行**、印の多重集合が `["◎","○","▲","△","☆","",""]` と一致、manifest `foreign_date_races_dropped == 0`。「rc=0 かつ全頭 summary」の両方を主張している。**満たす**
2. **Y8 の撃墜 (再現)**: `git archive 9cff875` の隔離コピーで著者 spec (`tests/mutation_specs/cross_date_spec.py`、Y8 を含む 9 本) を `mutation_sandbox` で実行 → **9/9 KILLED, rc=0**。Y8 は `test_a_realistically_marked_target_race_is_scored_in_full` で落ちる (著者の `run2_result.txt` と同一結果)。結果: scratchpad `cross_cqr/v2_result.txt`。**満たす**
3. **X1–X8 は依然 KILLED**: 上記同一 run で X1–X8 すべて KILLED、落ちるテストも前回 (`run1_result.txt`) と同じ。**満たす**
4. **既存 14 テストの意味を弱めていないか**: `git -C <wt> diff c3be0e9 9cff875` は **追加のみ (+25 行、削除 0)**。既存テスト本文・ヘルパ (`_race` / `_run_main` / `_summary` / `_manifest`)・fixture への変更なし。新テストは独立に `tmp_path` を使い、他テストの前提 (DB の 1 頭固定など) を変えていない。worktree で `tests/test_cross_date.py` **15 passed** (14 + 1)。**満たす**
5. **本体コード diff 0**: `git -C <wt> diff --stat c3be0e9 9cff875` = `tests/mutation_specs/cross_date_spec.py` +6 / `tests/test_cross_date.py` +19 の 2 ファイルのみ。`':!tests'` を除いた diff は **0 行**。**満たす**

## 所見

- 新テストが Y8 で落ちることを sandbox で確認済 = 空虚なテストではない (◎ を数える条件を広げると `PredictionInputError` → rc 2 → `_run_main` の `assert main() == 0` で落ちる)。印の照合を `sorted` の多重集合で行っているので、印なし 2 頭が `""` として出ることも同時に固定される
- spec 側の Y8 のコメントは「落ちるべきテスト」を明記しており、著者 X1–X8 と同じ規律で書かれている
- 変更失敗モード: 今後 `check_prediction_invariants` に不変条件を 1 つ足すとき、本番相当の happy path が 1 本あるため「本番だけで壊れる」経路は閉じた。ただし fixture は 1 レース 7 頭のみ。複数レース × 全印は無いが、不変条件はレース単位なので現状で十分

## 次アクション

- 本ブランチのマージを妨げる項目なし
- 前回の任意項目は据え置き: stop テストで stderr 文言を `capsys` 固定 (Y2) / docstring と `docs/EVALUATION_DATA_QUALITY.md:47` に manifest 3 キーと終了コードを追記 / anchor 契約 3 リテラルの一元化 / `output_dir.mkdir` を検証後へ
