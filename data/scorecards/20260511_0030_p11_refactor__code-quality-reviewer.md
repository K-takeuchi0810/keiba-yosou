# コード品質 / 保守性レビュアー 採点

## 総合: 4.0 / 5  (前回 3.5 → **+0.5**)

## 項目別

- **DRY / 重複コード: 4.5/5** (前回 4.5 → ±0) — 影響なし。`is_whitelisted_race` 4 経路集約は維持。本改修は「直書き → `_w()` 経由」の置換が主で、新規重複の持ち込みは無し。`scripts/backtest.py:186, 315` の二重ローカル import が未解消で 5 に届かず。

- **dead code / 未使用シンボル: 4/5** (前回 2 → **+2.0**) — **大幅改善**。`weight_trend / recent_avg_starters / same_day_leg_bias / same_day_leg_samples` の 4 件 + (報告された 5 件目) を `predictor/features.py` から完全除去 (grep で残存ゼロ確認済み、唯一の hit は `features.py:856` の削除説明コメント)。`feat[...]` 計算のうち `rules.py` で未使用のキーは前回 6 件 → 今回 **2 件** (`estimated_leg_samples`, `same_track_type_runs`) まで圧縮。残 2 件と `scripts/probe_*.py` 4 本が残存するため 5 には届かないが、+2.0 は本改修最大のレバー。

- **マジックナンバー / 設定外出し: 4.8/5** (前回 4.5 → **+0.3**) — **顕著な改善**。`predictor/rules.py` の `score (+|-)= NN` 直書きが **60 → 1 箇所** (実測 1)、`_w()` 参照は **48 → 121 箇所** (実測 121) で、weights.json 経由率が 44% → 99% へ。残 1 箇所は `score -= 1000` の異常区分マーカーで、コメントに「`weights.json` の調整対象外。意図的に直書き」と明示済 (`predictor/rules.py:_score_one`)。`weights.json` も 13 → **25 namespace** に倍増 (`track_type / distance / course / class_level / had_grade_run_bonus / condition / jockey / trainer / going / time_signal / bloodline / recent_form` + `_comment_p11` メタ)。半年後に「中山だけ重み下げたい」が config 1 行修正で済む構造になった。`jvlink_client/client.py` の retry 秒数のみ未対応で 5 に届かず。

- **テスト容易性 / 副作用分離: 2.5/5** (前回 2.5 → ±0) — `tests/` 不在は不変。ただし `_w()` 集約により `predict_race` の挙動を `weights.json` 差し替えだけで網羅試験できる構造になり、**テスト ROI は更に上昇**。例: `weights.json` の 1 namespace を 0 倍にして「その namespace を消した影響」を unit 化できる。tests/ ファイル新設が無いため点数は据え置き。

- **エラー処理 / ログ / 観測可能性: 4.5/5** (前回 4.5 → ±0) — 影響なし。`_w()` は `weights.json` 欠損時に `default` を返す防御的設計で、新規 namespace 追加時の KeyError リスク無し。新規 try/except 追加なし、握り潰しなし。backtest 出力 (回収率 60.8% / whitelist_only 84.9%) が P0-3 と完全一致 = リファクタが意味論的中立であることが定量的に証明済 (regression test の代替として強い)。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`_score_one` (491 行: `predictor/rules.py:86-593`) のシグナル別関数分割** — 本改修は「定数の外出し」止まりで関数分割は **未着手**。次の P1-1 続編として、`_score_burden / _score_pace / _score_class / _score_jockey / _score_condition / _score_form / _score_bloodline` 等に分割すれば、新シグナル追加時の影響範囲が局所化し、項目 1 と 4 が同時に上がる (4.5/5 → 5/5、2.5/5 → 3.5/5)。総合 4.0 → 4.3 想定。

2. **`tests/test_weights.py` 新設** — `_w("burden.over_threshold", 0)` が weights.json から正しい値を取れるか / 欠損時に default を返すか / 25 namespace 全部が呼び出されているか (網羅率) の 3 ケースを書けば、weights.json と rules.py の同期破れを CI で検出可能。項目 4: 2.5 → 3.5、総合 4.0 → 4.2。

3. **残 dead feature 2 件 (`estimated_leg_samples` / `same_track_type_runs`) を features.py から削除** — 今回の P1-1 と同じ要領で grep → 削除のみ。項目 2 を 4 → 4.5 に、`scripts/probe_*.py` 退避まで合わせれば 5 到達。総合 4.0 → 4.1。

## 前回からの差分

- 項目1 (DRY): 4.5 → 4.5 (±0) **維持**: 新規重複の持ち込みなし
- 項目2 (dead code): 2 → 4 (**+2.0**) **大幅改善**: 5 件削除 + 未使用 feat キー 6 → 2
- 項目3 (magic number): 4.5 → 4.8 (**+0.3**) **顕著な改善**: 直書き 60 → 1 (-1000 マーカーのみ、コメント明示)、`_w()` 48 → 121、namespace 13 → 25
- 項目4 (test): 2.5 → 2.5 (±0) **維持**: tests/ 不在続行 (構造的 ROI は更に上昇)
- 項目5 (logging): 4.5 → 4.5 (±0) **維持**: backtest 数値が P0-3 と一致 (60.8% / 84.9%) = 意味論中立を担保

総合: 3.5 → **4.0** (+0.5) — dead code 5 件削除と直書き 60 → 1 が両輪で効き、項目 2 と 3 の改善が総合を 0.5 押し上げ。次のレバーは `_score_one` 491 行の関数分割 (提案 #1) と tests/ 初出 (提案 #2)。`_score_one` 分割は **今回未着手で P1-1 続編に持ち越し** と明記。
