"""h_history_truncated の降格 (branch b-demote-h-history-truncated-20261004) の変異の定義。

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/b_demotion_spec.py

書式は scripts/mutation_sandbox.py の spec。各変異の後ろのコメントは、落ちるべきテスト。
"""

TESTS = [
    "tests/test_h_history_truncated_demotion.py",
    "tests/test_fundamental_dataset.py",
    "tests/test_feature_manifest.py",
]

FM = "scripts/fundamental_model.py"
MS = "predictor/model_schema.py"

MUTANTS = [
    # 監査列をモデルの特徴に戻す → test_the_flag_is_an_audit_column_not_a_model_feature
    ("B1 h_history_truncated を FEATURES に戻す", FM,
     '    "j_rides_365", "j_winrate", "t_runs_365", "t_winrate", "s_winrate",\n    # レース条件 (市場ではない)',
     '    "j_rides_365", "j_winrate", "t_runs_365", "t_winrate", "s_winrate",\n    "h_history_truncated",\n    # レース条件 (市場ではない)'),
    # 評価を今の FEATURES に戻す → test_collect_builds_the_input_from_the_model_schema[market_offset_eval]
    ("B2 market_offset_eval が今の FEATURES で入力を作る", "scripts/market_offset_eval.py",
     "    X = feature_matrix(data, model_features)\n",
     "    X = feature_matrix(data, FEATURES)\n"),
    # → test_collect_builds_the_input_from_the_model_schema[fundamental_eval]
    ("B3 fundamental_eval が今の FEATURES で入力を作る", "scripts/fundamental_eval.py",
     "    X = feature_matrix(data, model_features)\n",
     "    X = feature_matrix(data, FEATURES)\n"),
    # モデルの名前と meta の食い違いを見逃す → test_schema_conflicts_fail_closed
    ("B4 モデルの名前と meta の食い違いを許す", MS,
     "        if meta is not None and names != meta:",
     "        if False and meta is not None and names != meta:"),
    # 本数の不一致を見逃す → test_schema_conflicts_fail_closed
    ("B5 本数の不一致を許す", MS,
     "    if len(features) != num_feature:",
     "    if False and len(features) != num_feature:"),
    # 重複を見逃す → test_schema_conflicts_fail_closed
    ("B6 重複を許す", MS,
     "    if len(set(features)) != len(features):",
     "    if False and len(set(features)) != len(features):"),
    # 名前の無いモデルで meta が無くても Column_* を使う → test_schema_conflicts_fail_closed
    ("B7 名前も meta も無ければ Column_* で進む", MS,
     "        if meta is None:\n            raise ModelSchemaError(",
     "        if meta is None:\n            meta = names\n        if False:\n            raise ModelSchemaError("),
    # データに列が無ければ 0 で埋める → test_missing_data_columns_fail_closed / 4B の 30 列データ
    ("B8 データの列不足を 0 で埋める", MS,
     "    if missing:\n        raise ModelSchemaError(f\"データにモデルの特徴が無い: {missing}\")\n    return np.array([[r[c] for c in features] for r in rows], dtype=float)",
     "    return np.array([[r.get(c, 0.0) for c in features] for r in rows], dtype=float)"),
    # 今の FEATURES との違いを「一致」と記録 → test_an_older_model_is_kept_with_its_own_columns_and_recorded
    ("B9 今の FEATURES との一致を常に真と記録", MS,
     '        "matches_current_features": features == current,',
     '        "matches_current_features": True,'),
    # 発火率の数え方を逆に → test_audit_rates
    ("B10 監査列の率を逆に数える", FM,
     "    return v == 1.0",
     "    return v != 1.0"),
    # 域外監査から監査列を外す → test_the_domain_audit_still_monitors_the_audit_column
    ("B11 域外監査が監査列を監視しない", "scripts/feature_domain_audit.py",
     "    features = list(features) + [c for c in audit_columns if c not in features]",
     "    features = list(features)"),
    # 評価の出力の監査列の率を空にする → test_collect_builds_the_input_from_the_model_schema
    ("B12 評価の監査列の率を空の行で数える", "scripts/market_offset_eval.py",
     '    model_info = {"model_feature_schema": schema, **eval_audit_info(data)}',
     '    model_info = {"model_feature_schema": schema, **eval_audit_info([])}'),
    # --- 4 名レビュー (84b2376) の後に追加 (2026-10-04) ---
    # Fundamental の学習で名前を渡さない (validation M2) → test_fundamental_fit_names_the_features_and_records_the_audit
    ("B13 Fundamental の学習で特徴の名前を渡さない", FM,
     "              feature_name=list(FEATURES),\n",
     ""),
    # 評価で列を反転 (validation M1 / X2) → test_collect_builds_the_input_from_the_model_schema[fundamental_eval]
    ("B14 fundamental_eval が列を反転して予測する", "scripts/fundamental_eval.py",
     "    X = feature_matrix(data, model_features)\n",
     "    X = feature_matrix(data, model_features)[:, ::-1]\n"),
    # (validation M1 / X3) → test_collect_builds_the_input_from_the_model_schema[market_offset_eval]
    ("B15 market_offset_eval が列を反転して予測する", "scripts/market_offset_eval.py",
     "    X = feature_matrix(data, model_features)\n",
     "    X = feature_matrix(data, model_features)[:, ::-1]\n"),
    # 学習の meta の並びを反転 (validation X1) → test_fundamental_fit_names_the_features_and_records_the_audit
    ("B16 Fundamental の学習 meta の並びを反転", FM,
     '    meta = {**snapshot(conn_meta), "features": FEATURES,',
     '    meta = {**snapshot(conn_meta), "features": list(reversed(FEATURES)),'),
    # (code-quality X9) → test_a_model_with_fewer_features_than_now_is_recorded
    ("B17 今だけにある特徴を記録しない", MS,
     '        "only_in_current": [f for f in current if f not in features],',
     '        "only_in_current": [],'),
    # (code-quality X1 / validation X6) → test_collect_refuses_a_model_that_contains_a_market_feature[fundamental_eval]
    ("B18 fundamental_eval がモデルの並びの市場特徴を検査しない", "scripts/fundamental_eval.py",
     "    assert_no_market_features(\n        model_features, source_module",
     "    (lambda *a, **k: None)(\n        model_features, source_module"),
    # → test_collect_refuses_a_model_that_contains_a_market_feature[market_offset_eval]
    ("B19 market_offset_eval がモデルの並びの市場特徴を検査しない", "scripts/market_offset_eval.py",
     "    assert_no_market_features(\n        model_features, source_module",
     "    (lambda *a, **k: None)(\n        model_features, source_module"),
    # (code-quality X2) → test_missing_data_columns_fail_closed
    ("B20 列の欠落を先頭の行でしか調べない", MS,
     "    missing = sorted({c for r in rows for c in features if c not in r})",
     "    missing = sorted({c for r in rows[:1] for c in features if c not in r})"),
    # NaN を黙って 0 側に数える → test_audit_rates_refuse_a_non_binary_value
    ("B21 監査列の 0/1 以外の値を許す", FM,
     "    if v not in (0.0, 1.0):",
     "    if False:"),
    # 年別の内訳を月別にする → test_audit_rates_by_year
    ("B22 年別の内訳の鍵を誤る", FM,
     '        by_year[str(r["date"])[:4]].append(r)',
     '        by_year[str(r["date"])[:6]].append(r)'),
    # → test_the_frozen_4b_model_is_reproduced_with_its_31_columns
    ("B23 モデルファイルの sha256 を記録しない", MS,
     '    provenance["model_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()',
     '    provenance["model_sha256"] = None'),
    # → test_meta_n_features_disagreeing_with_the_model_fails_closed
    ("B24 meta の n_features との食い違いを許す", MS,
     '    if "n_features" in meta and meta["n_features"] != len(features):',
     '    if False:'),
    # → test_audit_meta_records_the_generation_and_the_rates / fit のテスト
    ("B25 学習 meta の特徴の本数を誤る", FM,
     '    return {"feature_set": FEATURE_SET, "n_features": len(FEATURES),',
     '    return {"feature_set": FEATURE_SET, "n_features": 31,'),
    # 学習と検証の率を取り違える (code-quality X3) → test_fundamental_fit_names_the_features_and_records_the_audit
    ("B26 Fundamental の学習 meta で学習と検証を取り違える", FM,
     "            **audit_meta(train, valid),\n",
     "            **audit_meta(valid, train),\n"),
    # → test_the_domain_audit_still_monitors_the_audit_column
    ("B27 域外監査が年別の内訳を残さない", "scripts/feature_domain_audit.py",
     '                     "audit_rates_by_year": {k: audit_rates_by_year(splits[k], audit_columns)',
     '                     "audit_rates_by_year": {k: {}'),
    # → test_market_offset_fit_names_the_features_and_records_the_audit
    ("B28 市場オフセットの学習 meta で学習と検証を取り違える", "scripts/market_offset_model.py",
     "            **audit_meta(train, valid),\n",
     "            **audit_meta(valid, train),\n"),
    # → test_the_frozen_4b_model_is_reproduced_with_its_31_columns
    ("B29 学習時の meta を評価の記録に写さない", MS,
     '    provenance["model_meta"] = {k: meta[k] for k in MODEL_META_KEYS if k in meta}',
     '    provenance["model_meta"] = {}'),
    # --- 学習用ブランチのレビュー (da05c51) の後に追加 (2026-10-04) ---
    # → test_collect_refuses_an_in_sample_evaluation_window / test_window_guard_treats_windows_as_closed_intervals
    ("B30 評価窓の重なりを見逃す", MS,
     "        if lo <= to_date and from_date <= hi:",
     "        if False:"),
    # → test_window_guard_treats_windows_as_closed_intervals
    ("B31 評価窓の境界日を重なりと見なさない", MS,
     "        if lo <= to_date and from_date <= hi:",
     "        if lo < to_date and from_date < hi:"),
    # → test_window_guard_fails_closed_without_windows
    ("B32 meta に窓が無ければ素通り", MS,
     '    if not meta.get("train") and not meta.get("validation"):',
     "    if False:"),
    # → test_market_offset_fit_names_the_features_and_records_the_audit (data_version)
    ("B33 市場オフセットの学習で接続を閉じてから snapshot", "scripts/market_offset_model.py",
     "    data_snapshot = snapshot(conn)\n    conn.close()\n",
     "    conn.close()\n    data_snapshot = snapshot(conn)\n"),
    # → test_collect_refuses_an_in_sample_evaluation_window[fundamental_eval-fundamental_model]
    ("B34 fundamental_eval が評価窓の重なりを確かめない", "scripts/fundamental_eval.py",
     "    assert_model_window_disjoint(MODEL_PATH, from_date, to_date)\n",
     ""),
]
