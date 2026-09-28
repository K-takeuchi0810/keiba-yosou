"""cross-date 修正 (branch cross-date-fix-20260926) の変異の定義。

**まだ実行しない** (2026-09-26 の CHAT 指示)。JST 統一ブランチ (変異テストの枠
`scripts/mutation_sandbox.py` を含む) が main に入った後、このブランチを新しい main に
統合してから、次のように流す:

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/cross_date_spec.py

書式は `scripts/mutation_sandbox.py` の spec (MUTANTS = (名前, 対象ファイル, 置換前, 置換後))。
各変異の後ろのコメントは、**落ちるべきテスト**。そのテストで落ちなければ、網が粗い。
"""

TESTS = [
    "tests/test_cross_date.py",
    "tests/test_build_daily_results.py",
    "tests/test_analyze_misses_exclusion.py",
]

BDR = "scripts/build_daily_results.py"

MUTANTS = [
    # 1. レース ID の日付を無視する (修正前の形に戻す)
    #    落ちるべき: test_the_anchor_keeps_the_date,
    #               test_a_foreign_race_with_the_same_track_and_number_is_not_scored
    ("X1 レース ID の日付を無視", BDR,
     "    return m.group(1), m.group(2), int(m.group(3))",
     "    return None if False else (None, m.group(2), int(m.group(3)))"),

    # 2. 日付の比較を常に true にする (別の日のレースも対象日として残る)
    #    落ちるべき: test_a_foreign_race_with_the_same_track_and_number_is_not_scored,
    #               test_foreign_races_are_recorded_not_silently_dropped
    ("X2 日付の比較を常に true", BDR,
     '    target = [r for r in races if r["race_date"] == date]',
     "    target = [r for r in races if True]"),

    # 3. manifest の drop 件数を 0 にする (黙って捨てる)
    #    落ちるべき: test_foreign_races_are_recorded_not_silently_dropped
    ("X3 manifest の drop 件数を 0 に", BDR,
     '            "foreign_date_predictions_dropped": foreign_horses,',
     '            "foreign_date_predictions_dropped": 0,'),

    # 4. 別の日の行を、対象日の同じ場・同じ R へ結合する (元の欠陥そのもの)
    #    落ちるべき: test_a_foreign_race_with_the_same_track_and_number_is_not_scored
    ("X4 別の日の行を同じ場・R へ結合", BDR,
     "        races, foreign_races = split_races_by_date(all_races, date)",
     "        races, foreign_races = all_races, []"),

    # 5. 1 レースに ◎ 2 頭を許す
    #    落ちるべき: test_two_honmei_in_one_race_stops
    ("X5 ◎ 2 頭を許す", BDR,
     "        if len(honmei) > 1:",
     "        if len(honmei) > 2:"),

    # 補助: 同じ馬番の重複を許す / レース ID が読めなくても進む / ID の一覧を空にする
    ("X6 同じ馬番の重複を許す", BDR,
     "        if dup:\n            raise PredictionInputError",
     "        if False:\n            raise PredictionInputError"),
    #    落ちるべき: test_a_repeated_horse_number_stops
    ("X7 読めないレース ID でも進む", BDR,
     "    if unreadable:\n        raise PredictionInputError",
     "    if False:\n        raise PredictionInputError"),
    #    落ちるべき: test_an_unreadable_race_id_stops
    ("X8 別の日の ID の一覧を空に", BDR,
     '            "foreign_date_race_ids": foreign_race_ids,',
     '            "foreign_date_race_ids": [],'),
    #    落ちるべき: test_foreign_races_are_recorded_not_silently_dropped
    # 9. ◎ を数える条件を広げる (○ も数える)。本番の HTML は全レースに ○ があるので、
    #    これが入ると答え合わせが全部止まる (2026-09-28 レビューの変異 Y8)
    #    落ちるべき: test_a_realistically_marked_target_race_is_scored_in_full
    ("Y8 ◎ の数え方に ○ を含める", BDR,
     '        honmei = [h for h in r["horses"] if (h.get("mark") or "") == "◎"]',
     '        honmei = [h for h in r["horses"] if (h.get("mark") or "") in ("◎", "○")]'),
]
