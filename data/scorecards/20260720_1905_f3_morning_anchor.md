# Expert review — F3 morning anchor

**Change**: Add a fixed 600-minute morning odds wrapper, bounded contention retry,
fail-closed no-op detection, and an idempotent daily Task Scheduler registration.
**Final HEAD**: `e5eaf34`
**Infrastructure verdict**: **PASS**.
**Race-day numerical acceptance**: **HOLD** (the smoke had zero races).

## Score trend

| Expert | Current | Previous | Delta | Verdict |
|---|---:|---:|---:|---|
| GUI / UX | 3.6 | 3.6 | 0.0 | HOLD (pre-existing issues; no regression) |
| Mobile HTML | 4.0 | 4.0 | 0.0 | PASS |
| Prediction logic | 4.3 | 4.2 | +0.1 | HOLD (wide-drift acceptance pending) |
| Profitability | 2.0 | 2.0 | 0.0 | Infrastructure PASS / Phase 1 HOLD |
| Data pipeline | 4.1 | 4.6 | **-0.5 — regression warning** | HOLD |
| Code quality | 4.5 | 4.5 | 0.0 | PASS |
| Validation process | 3.4 | 4.8 | **-1.4 — regression warning** | HOLD |
| **Average** | **3.70** | **3.96** | **-0.26** | **HOLD** |

## Why the warning is retained

The code and scheduler infrastructure passed static, unit, direct-wrapper, and
zero-race concurrent scheduler checks. The lower pipeline and validation scores
are retained because the precommitted race-day acceptance conditions could not be
observed at 19:03 after racing: lead >= 60 coverage, `wide_drift > 0`, actual
JV-Link/SQLite contention, missing odds patterns, and measured data growth remain open.

## Cross-review improvements completed

1. Shared-lock contention is retried six times at 30-second intervals and becomes
   rc=4 if unresolved; a skipped morning anchor is no longer reported as success.
2. Task updates use `Register-ScheduledTask -Force`; there is no delete-before-register gap.
3. Retry seconds and ping count have one source of truth. The wrapper is ASCII,
   fixed to 32-bit Python, and verifies the exact `window=0-600min` marker.

## Priority acceptance step

Merge before the scheduled action can resolve the batch file, then retain HOLD until
the first JRA race-day 08:45/09:00 logs and readiness rerun prove all numerical conditions.
