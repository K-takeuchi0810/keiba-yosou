# B: h_history_truncated の降格 — 限定再レビュー (d390c87、2026-10-04)

- 対象: SHA **d390c87** (前回 84b2376 → 4 名 PASS、validation は条件付きで must-fix M1 / M2)。差分 84b2376..d390c87 (10 files +413/−39)
- 担当: validation-process-auditor / code-quality-reviewer (外部の指示者の決定: 案 X = このブランチで是正 → 限定再レビュー)
- 運用: subagent CWD 限定運用 (ルール 1-bis (b))。変異は git archive d390c87 の隔離コピー。レビュー中 worktree 不変 (両名が終了時に status 空・HEAD d390c87 を確認)
- ai_builder_impact: none

| 担当 | 判定 | 点 | 前回 |
|---|---|---|---|
| validation-process-auditor | PASS | 4.2 | 3.8 (条件付き) |
| code-quality-reviewer | PASS | 4.4 | 4.2 |

## 確認されたこと

- M1 (collect の配線テストが値を見ない) 是正: 40 行 × 全特徴の乱数で margin / p_raw を直接計算と照合。前回生存の X1 / X2 / X3 / X6 は d390c87 で KILLED (validation が再実行)
- M2 (Fundamental が Column_*) 是正: `feature_name=list(FEATURES)`。2 つの fit() を合成データで実行するテストで、名前・meta・世代名・監査率 (年別も) を確認
- 公式変異 29/29 KILLED (両名とも隔離コピーで再現)。validation の追加プローブ 14 体中 13 KILLED、code-quality の自作 8 体中 2 KILLED / 5 生存 / 1 等価
- 率の定義は `fundamental_model.audit_rates` の 1 箇所 (grep で他の計算経路 0)。関数内 import に循環なし
- 全テスト (隔離コピー): 1047 passed / 13 skipped / 1 deselected (既存の環境依存の seal テスト)。fit テストの前後で本番 `predictor/*_model.txt` の sha 不変
- 凍結 4B の再現経路は不変 (4B meta に n_features / feature_set は無いので新しい照合は効かない。`"feature_set" not in model_meta` を明示 assert)

## 学習コミット (次に `predictor/*_model.*` を上書きするコミット) までに執行するもの

1. **受理条件の事前固定** (validation、fit の前に文書で): 目的は衛生の変更。β₂ の CI が 4B (0.4997 [−0.828, 1.726]) と重なり、域外率 (年別を含む) が悪化しなければ受理。β₂ が良くなっても信号と見なさない。strategy_dev 626 レースは消費済み窓の paired 再評価として CONSUMED_WINDOWS に追記。2025 の LogLoss は OOS の証拠にしない。CONFIRM_FROM=20260914 以降に触れない
2. **M2-b** (validation、記録 1 文): 凍結 4B の fundamental_model.txt は Column_* で名前照合できない。meta.features (31) は manifest.features、および market_offset_model.txt の feature_name() (学習コード 99eec68) と完全一致することをもって並びの契約とする
3. **M-new** (code-quality、既存の欠陥): `scripts/market_offset_model.py` が `conn.close()` の後で `snapshot(conn)` を呼び、`data_version` が sqlite3.ProgrammingError の握り潰しで常に "nodata" になる (凍結 4B の meta も "nodata")。close を snapshot の後ろへ。テストで data_version != "nodata" を確認
4. 学習後の評価 JSON の `model_feature_schema.model_meta.feature_set` = post_demotion_repaired_30features と、凍結 4B への参照 (label) を scorecard に記載

## nice-to-have (テストの穴ほか)

- feature_domain_audit の年別内訳を strategy_dev 側も assert (validation Y21)。`audit_columns` に既定と違う列名を使う (code-quality Xa)
- meta の n_features がモデルより大きい側 (30 / 32 で parametrize、Xb)
- audit_meta の validation 側の年別 (Xc)
- `set(model_meta) == set(MODEL_META_KEYS) & set(meta)` で全キーを固定 (Xd)、model_file 名 (X9')
- `_flag` の列欠落 (KeyError を明示 or ValueError に揃える、Xe)
- docstring「Fundamental は名前を持たない」は 4B 以前に限定 (fundamental_eval.py:121、model_schema.py:15-16)
- fundamental_eval に学習窓と評価窓の disjoint assert (2 回目の持ち越し)
- predict_proba(ndarray) の sklearn 警告 → `model.booster_.predict`
- 関数内 import (feature_domain_audit の audit_rates、model_schema の hashlib) を top-level に
- fit テストの `data[f[:4]]` を DATA_SPLIT から鍵を引く形に
- 全 suite 中で seal テストが skip せずに落ちる件 (単体では sealed_window_started()=False) は別件で原因を見る
