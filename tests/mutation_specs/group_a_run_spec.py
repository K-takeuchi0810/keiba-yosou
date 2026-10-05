"""Phase 0.5-5 Group A の実行 (scripts/group_a_run.py) と配列版の推定 (scripts/group_a_stats.py) の変異の定義 (2026-10-06)。

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/group_a_run_spec.py
"""

TESTS = ["tests/test_group_a_run.py", "tests/test_group_a_stats.py"]

GR = "scripts/group_a_run.py"
GS = "scripts/group_a_stats.py"

MUTANTS = [
    ("R1 E1b の選択と違う候補を凍結できる", GR,
     "    if sel != spec_name:",
     "    if False:"),
    ("R2 主検定を 2 回走らせられる", GR,
     "    if previous is not None and not rerun_reason:",
     "    if False:"),
    ("R3 凍結物の sha256 を見ない", GR,
     '    if _sha(frozen / FROZEN_FILE) != man["frozen_sha256"]:',
     "    if False:"),
    ("R4 別の凍結物の検出力を受け入れる", GR,
     '    if power["frozen_sha256"] != man["frozen_sha256"] or power.get("frozen_manifest_sha256") != _sha(frozen / MANIFEST_FILE):',
     "    if False:"),
    ("R5 区間が無効なら MDE の理由を上書きする", GR,
     '''    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")
    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"''',
     '''    if not ci["valid"]:
        return "PRIMARY_INCONCLUSIVE", "boot_na"
    if power["inconclusive_by_power"]:
        return "PRIMARY_INCONCLUSIVE", ("mde_above_beta_target" if ci["valid"] else "mde_above_beta_target+boot_na")'''),
    ("R6 検出力の判定不能を無視する", GR,
     '    if power["inconclusive_by_power"]:',
     "    if False:"),
    ("R7 下限 0 ちょうどを PASS にする", GR,
     '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] > 0 else',
     '("PRIMARY_PASS", "ci_lower_above_zero") if ci["lo"] >= 0 else'),
    ("R8 学習期のブートストラップの回数を固定値から外す", GR,
     "    vals, discarded = es._block_resample(rows, st.make_beta_stat(packed, \"S\"), BOOT_N, BOOT_SEED)",
     "    vals, discarded = es._block_resample(rows, st.make_beta_stat(packed, \"S\"), 50, BOOT_SEED)"),
    ("S1 配列版で標準化の SD を取らない", GS,
     "    scale = np.sqrt(var)\n",
     "    scale = np.ones_like(var)\n"),
    ("S2 配列版で 1 歩の上限を外す", GS,
     "        if big > STEP_CAP:",
     "        if False:"),
    ("S3 配列版で詰め物の行を確率に入れる", GS,
     "    neg = np.where(mask > 0, 0.0, -np.inf)",
     "    neg = np.zeros_like(mask)"),
    ("S4 配列版で勝ち馬のいないレースを残す", GS,
     "    keep = ysum > 0\n",
     "    keep = ysum >= 0\n"),
    ("S5 再抽出のレースの並びを使わない", GS,
     "        beta, ok = clogit_packed(p, races_of_draw(draw))",
     "        beta, ok = clogit_packed(p)"),
    ("R9 開始の印を 2025 を読む前に書かない (同じ run_index で 2 回走れる)", GR,
     '    _write_json(started_path, {"run_index": run_index,',
     '    _write_json(out / "started_moved.json", {"run_index": run_index,'),
    ("R10 主検定の前に未コミットの変更を見ない", GR,
     '    if now["git_dirty"]:',
     "    if False:"),
    ("R11 主検定の前に依存ファイルの sha を見ない", GR,
     "    if bad:\n        raise RunError(f\"主検定の前提のファイルが",
     "    if False:\n        raise RunError(f\"主検定の前提のファイルが"),
    ("R12 履歴の一致を見ない", GR,
     '    if d != man["history_digest"]:',
     "    if False:"),
    ("R13 判定を副次記録の後にだけ書く", GR,
     "    _write_json(out / PRIMARY_FILE, result)          # 判定までを先に書く",
     "    pass          # 判定までを先に書く"),
    ("R14 副次記録の失敗で主検定ごと落ちる", GR,
     "    except Exception as e:                           # 判定に使わない記録の失敗は",
     "    except ZeroDivisionError as e:                           # 判定に使わない記録の失敗は"),
    ("R15 JSON の NaN を残す", GR,
     "    if isinstance(obj, float) and not math.isfinite(obj):\n        return None",
     "    if False:\n        return None"),
    ("R16 錠が git にコミットされているかを見ない", GR,
     "    if not _lock_is_committed(lock_path):",
     "    if False:"),
    ("R17 開始の印があっても走る", GR,
     "    if started_path.exists():",
     "    if False:"),
    ("R18 錠を書いた後に固定のファイルが変わっても走る", GR,
     '    if pinned["pinned"] != lock["pinned"]:',
     "    if False:"),
    ("R19 錠が無くても走る", GR,
     "    if not lock_path.exists():\n        raise RunError(\"主検定の錠が無い",
     "    if False:\n        raise RunError(\"主検定の錠が無い"),
    ("R20 repo の外の錠をコミット済みとみなす", GR,
     "    if rel is None:                                  # repo の外の錠は git で証明できない\n        return False",
     "    if rel is None:                                  # repo の外の錠は git で証明できない\n        return True"),
]
