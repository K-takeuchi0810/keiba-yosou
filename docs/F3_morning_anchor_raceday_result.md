# F3 morning anchor race-day result

Measurement date: **2026-07-26 JST**  
Data go-live date: **2026-07-25** (first JRA race day after merge)

## Verdict

- Operational run: **PASS**. The 08:45 task fetched all 36 races without errors on both 2026-07-25 and 2026-07-26.
- Strict numerical acceptance: **HOLD**. The requirement that every race have an anchor at least 60 minutes before post was 35/36 on each day, not 36/36.
- `wide_drift > 0`: **achieved**, but only for 29/36 races on each day. This is enough to prove that the anchor creates wide pairs, not enough to declare complete race coverage.
- The repeated two-day missing pattern is reported below as provisional evidence only. No race exclusion is frozen from two days.

## 1. Scheduler and acquisition

| Check | 2026-07-25 | 2026-07-26 |
|---|---:|---:|
| Scheduled start | 08:45:01 | 08:45:02 |
| End / result | 08:45:06 / rc=0 | 08:45:07 / rc=0 |
| Eligible / fetched races | 36 / 36 | 36 / 36 |
| JV records / raw files / errors | 36 / 36 / 0 | 36 / 36 / 0 |
| Effective marker | `window=0-600min` confirmed | `window=0-600min` confirmed |
| `odds_snapshots` rows at 08:45 | 448 | 449 |

Task Scheduler currently reports `LastRunTime=2026-07-26 08:45:01`, `LastTaskResult=0`, and `NextRunTime=2026-07-27 08:45:00`.

## 2. Canonical readiness result

`scripts.f3_phase1_readiness` was rerun through 2026-07-26. Eligibility was decided only by `predictor.pit_gate.usable_snapshots`.

| Race day | Entries | At least one usable | Earliest lead >=60 min | Drift computable | Wide drift |
|---|---:|---:|---:|---:|---:|
| 2026-07-25 | 36 | 36 (100%) | 35 (97.2%) | 30 (83.3%) | 29 (80.6%) |
| 2026-07-26 | 36 | 36 (100%) | 35 (97.2%) | 30 (83.3%) | 29 (80.6%) |
| Two days | 72 | 72 (100%) | 70 (97.2%) | 60 (83.3%) | 58 (80.6%) |

The development-window total is now 79/305 drift-computable races (**25.9%**) and 58/305 wide-drift races (**19.0%**). The former drift baseline was 19/225 (**8.4%**); the two go-live days added 60 drift-computable races.

Across the 72 go-live races, earliest lead minutes were: minimum 54.9, p25 142.4, median 319.9, p75 447.4, p90 543.4, maximum 584.9.

## 3. Provisional missing pattern

- Track `07` 1R started at 09:40 on both days. Its 08:45 anchor was only 54.9 minutes before post, so it failed the 60-minute and wide-drift conditions despite having a later T-20 point.
- Track `04` and `07`, 10R-12R, had only the morning point and no near-T-10 point on both days. These six races per day were therefore not drift-computable. The live task repeats every 10 minutes only from 09:00 through 16:40, while these posts were 17:20-18:30.
- This two-day repetition is a scheduling/coverage hypothesis for the next cycle, not a frozen exclusion rule.

## 4. Concurrency

The morning job completed in 4-5 seconds, about 15 minutes before the 09:00 live job. The two target days therefore had no real overlap: neither log contains `shared lock busy`, `another fetch_fresh_odds run is active`, or `database is locked`, and both scheduled jobs ended with result 0.

Operationally there was no contention, but the shared lock was **not exercised by a competing target-day process**, so race-day serialization under actual overlap remains unproven rather than failed.

## 5. Measured storage and attribution

| Metric per 36-race day | Estimate | 2026-07-25 | 2026-07-26 |
|---|---:|---:|---:|
| Snapshot rows | 479 | 448 (-6.5%) | 449 (-6.3%) |
| Raw files | 36 | 36 | 36 |
| Raw bytes | 34,668 (33.9 KiB) | 34,668 | 34,668 |

The exact SQLite physical-file delta cannot be reconstructed after the run because no pre/post file-size sample was retained and live collection subsequently wrote to the same database. Row delta and raw-file delta above are directly attributable by the 08:45 timestamps and file modification times.

At go-live, the coverage JSONL entry was treated as fresh by the then-current health check, and all inserted DB rows have `source='0B31'`, not `morning`. The 08:45 timestamps and 36 corresponding raw filenames prove the acquisition, but DB `source` alone cannot. The source-attribution health fix is now merged on `main`; it still needs its first race-day morning-run verification.

## Invariants

- Window remained `20260704` through `20260726`; no date on or after `20261001` was accessed.
- Database was opened read-only with `PRAGMA query_only=1` and a consistent read transaction.
- Frozen design SHA-256 remained `96b348411d2bda0ff8deeaf09fe4ea8a1484aec8effdc9f6c1f337318af950a4`.
- Production model, feature list, metadata, and calibrator hashes were unchanged before/after the audit.
- No production code, frozen design, protected skill, trend collection, other branch, Discord destination, or scheduler setting was modified. No push was performed.
