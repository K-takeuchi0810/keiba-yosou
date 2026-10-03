"""通過順位の backfill (scripts/backfill_corner_orders.py) の変異の定義 (2026-10-04)。

    python -m scripts.mutation_sandbox --copy <隔離コピー> --spec tests/mutation_specs/backfill_corner_spec.py
"""

TESTS = [
    "tests/test_backfill_corner_orders.py",
    "tests/test_corner_gate.py",
]

BF = "scripts/backfill_corner_orders.py"

MUTANTS = [
    ("K1 run の入口のガードを外す", BF,
     '    config.require_corner_bytes_verified("scripts.backfill_corner_orders")\n    raw, used = raw_corner_map(records)',
     '    raw, used = raw_corner_map(records)'),
    ("K2 オッズの列も書き換える", BF,
     '"UPDATE horse_races SET corner_order_1 = ?, corner_order_2 = ?, corner_order_3 = ?, corner_order_4 = ?"',
     '"UPDATE horse_races SET corner_order_1 = ?, corner_order_2 = ?, corner_order_3 = ?, corner_order_4 = ?, odds_fetched_at = NULL"'),
    ("K3 raw の食い違いを見逃す", BF,
     "        if key in out and out[key] != val:",
     "        if False:"),
    ("K4 data_div 7 以外の raw も使う", BF,
     '        if getattr(r, "record_type", "SE") != "SE" or str(r.data_div).strip() != "7":',
     '        if getattr(r, "record_type", "SE") != "SE":'),
    ("K5 raw の日付の範囲を見ない", BF,
     '        if not is_jra(r.track_code) or not in_range(f"{r.year}{r.month_day}"):',
     '        if not is_jra(r.track_code):'),
    ("K6 地方の raw も使う", BF,
     '        if not is_jra(r.track_code) or not in_range(f"{r.year}{r.month_day}"):',
     '        if not in_range(f"{r.year}{r.month_day}"):'),
    ("K7 計画の検収が不合格でも適用する", BF,
     "        if not planned[\"ok\"]:\n            raise BackfillError(",
     "        if False:\n            raise BackfillError("),
    ("K8 失敗しても rollback せず commit する", BF,
     '        except Exception:\n            conn.execute("ROLLBACK")',
     '        except Exception:\n            conn.execute("COMMIT")'),
    ("K9 開催日の拒否を外す", BF,
     "        if apply and is_race_day(conn, today):",
     "        if False:"),
    ("K10 dry-run でも書く", BF,
     '        if not apply:\n            report["result"] = "dry_run"\n            return report',
     '        if False:\n            report["result"] = "dry_run"\n            return report'),
    ("K11 範囲外の順位の判定を頭数 + 2 に緩める", BF,
     "        if cs is not None and any(c and c > field_n[key[:6]] for c in cs):",
     "        if cs is not None and any(c and c > field_n[key[:6]] + 2 for c in cs):"),
    ("K12 raw に無い行を 0 で埋める", BF,
     "        else:\n            plan.missing_in_raw += 1",
     "        else:\n            plan.updates[key] = (0, 0, 0, 0)\n            plan.missing_in_raw += 1"),
    ("K13 被覆率の閾値を見ない", BF,
     '    failed = sorted(ym for ym, r in rates.items() if r is None or r < THRESHOLD)',
     '    failed = []'),
    ("K14 出走頭数に競走除外も数える", BF,
     '        if str(row["abnormal_code"] or "").strip() not in REFUNDED:',
     '        if True:'),
]
