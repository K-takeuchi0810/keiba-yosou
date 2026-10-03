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
     "    return {c: float(sum(1 for r in rows if float(r[c]) == 1.0) / len(rows)) for c in AUDIT_COLUMNS}",
     "    return {c: float(sum(1 for r in rows if float(r[c]) != 1.0) / len(rows)) for c in AUDIT_COLUMNS}"),
    # 域外監査から監査列を外す → test_the_domain_audit_still_monitors_the_audit_column
    ("B11 域外監査が監査列を監視しない", "scripts/feature_domain_audit.py",
     "    features = list(features) + [c for c in audit_columns if c not in features]",
     "    features = list(features)"),
    # 評価の出力の監査列の率を空にする → test_collect_builds_the_input_from_the_model_schema
    ("B12 評価の監査列の率を空の行で数える", "scripts/market_offset_eval.py",
     '                  "audit_rates_eval_rows": audit_rates(data)}',
     '                  "audit_rates_eval_rows": audit_rates([])}'),
]
