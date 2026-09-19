# F3-a morning odds anchor result

## Status

- Registration date: **2026-07-20**.
- Data go-live: **pending merge and the first subsequent JRA race-day run**.
- Infrastructure: implemented and registered.
- Numerical acceptance (all races with a lead of at least 60 minutes and `wide_drift > 0`): **pending**.

The direct smoke was run at 19:03 JST, after the day's races. The database had zero races for 2026-07-20, so the run safely selected zero races. This verifies argument propagation and no-race behavior, but cannot create or validate a historical PIT anchor.

## Dedicated batch smoke

| Check | Result |
|---|---|
| Command path | `scripts/fetch_morning_odds.bat` |
| Python | `.venv32/Scripts/python.exe` |
| Fixed arguments | `--window 600 --min-lead 0` |
| Effective log marker | **PASS**: `window=0-600min` |
| Wrapper no-op detector | **PASS**: `CHECK: effective window=600 confirmed` |
| Exit code | 0 |
| Eligible/fetched races | 0 / 0 (run after racing; not an acceptance sample) |
| DB file-size delta | 0 bytes |
| `wide_drift` after smoke | Not recalculated; no new snapshot was possible, so the prior value remains 0 |

The wrapper does not forward `%*`; callers cannot silently replace the fixed window. It captures module output, fails with rc=2 if the exact effective marker is missing, and writes only to `data/logs/fetch_morning_odds.log`. If the shared live/morning lock is busy, it retries six times at 30-second intervals and exits with rc=4 if contention remains; a morning anchor is no longer silently skipped as success.

## Schedule registration

`keiba-morning-odds` is registered and Ready:

| Setting | Value |
|---|---|
| Trigger | Daily **08:45 JST** |
| NextRunTime observed | **2026-07-21 08:45 JST** |
| Action | `cmd.exe /d /c call C:\Users\kizun\dev\keiba-yosou\scripts\fetch_morning_odds.bat` |
| ExecutionTimeLimit | 1 hour |
| MultipleInstances | IgnoreNew |
| Registration update | `Register-ScheduledTask -Force` (no delete-before-register gap) |

08:45 replaces the draft 09:30 time because recent JRA first posts were consistently 09:50. A 09:30 anchor is only 40 minutes early and can never satisfy the requested 60-minute coverage for the first races. At 08:45 the first-post lead is 65 minutes and the late races remain inside the 600-minute window.

**Merge coupling**: the scheduled action resolves the batch under the main working directory. After this task returns to `main`, that file is absent until branch `codex/f3-morning-anchor` is merged. The registered task therefore cannot function successfully before merge.

## Concurrency observation

At 19:03:49, `keiba-morning-odds` and `keiba-fresh-odds` were started together through Task Scheduler. Both returned 0 and became Ready. Their logs show the same 19:03:51 execution second and the expected windows (0-600 and 2-25 minutes).

There were no eligible races, so neither process entered JV-Link COM or DB ingest. This is a scheduler/process smoke only, not the requested live COM contention proof. Both commands call `scripts.fetch_fresh_odds` and share its atomic `single_run_lock`; the nested-lock regression test confirms the second acquisition is rejected. The first race-day overlap between the 08:45 morning run and 09:00 live schedule remains the real operational contention check.

SQLite connections already set `PRAGMA busy_timeout=5000`; no duplicate setting was added.

## Expected acquisition volume and missing-pattern status

The no-race smoke added zero records and zero raw bytes. A factual one-run increase cannot be reported until the first race-day execution.

For capacity planning only, the latest two race days contain 2,102 rows across 158 stored race/timestamp points, or 13.30 horse rows per point. One anchor for 36 races therefore projects about **479 `odds_snapshots` rows per race day**. The latest 100 raw 0B31 files average 963 bytes, projecting about **34,668 bytes (33.9 KiB) of raw data per 36-race day**, before filesystem and SQLite index overhead. This is an estimate, not the required measured increase.

Morning odds availability by post-time band and race type is also pending the first eligible run. No absence pattern can be inferred from a zero-race smoke.

## Acceptance work still open

After merge, on the first JRA race day:

1. Confirm the 08:45 log contains `window=0-600min`, nonzero eligible/fetched races, and no JV-Link/SQLite error.
2. Measure races with at least one `fetched_at` point at lead >= 60 minutes and report missing patterns.
3. Re-run the Phase 1 readiness audit after the T-10 collection points exist and require `wide_drift > 0`.
4. Compare morning/live task results around 09:00 and record actual row/raw-byte growth.

The readiness audit script currently lives on unmerged branch `codex/f3-phase1-readiness`; that branch must also be integrated before the documented recalculation command is available from `main`.

## Invariants and separate ticket

- `scripts/fetch_fresh_odds.bat` is unchanged. Its missing `%*` argument forwarding is recorded as a separate ticket.
- `docs/F3_MARKET_RESIDUAL_DESIGN.md` is unchanged.
- Prediction model, feature list, metadata, and calibrator artifacts are unchanged.
- No sealed-period data, Discord delivery, external trend-collection files, protected skill files, or other Codex branches were modified.
