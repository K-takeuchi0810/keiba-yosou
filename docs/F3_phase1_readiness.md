# F3 Phase 1 readiness: development PIT odds coverage

Window: `20260704` through `20260726`. 
Gate: `usable_snapshots`, T-10. 
Measurement only; no model or feature was created.

## Coverage

| Metric | Count | Rate of races with entries |
|---|---:|---:|
| Total races | 305 | - |
| Races with entries | 305 | 100.0% |
| At least one usable timestamp | 143 | 46.9% |
| Drift computable (at least 2 distinct times) | 79 | 25.9% |
| Wide drift | 58 | 19.0% |

JRA central scope: 288 races, 79 drift-computable (27.4%). Other track codes: 17 races, 0 drift-computable (0.0%).

Wide drift is a measurement label: earliest lead >= 60 minutes and the latest eligible point is in the existing T-25 through T-10 collection window.

## Earliest lead by post time

| Band | Races with entries | Races with usable PIT | Earliest lead median |
|---|---:|---:|---:|
| Morning (<12:00) | 117 | 51 | 64.9 min |
| Afternoon (>=12:00) | 188 | 92 | 25.0 min |
| Overall | 305 | 143 | 54.9 min |

## Trend and readiness material

Daily drift coverage is **improving** by the first-half versus second-half descriptive comparison (0.0% to 27.4%); slope is +0.204 rate/week.
The observed corpus has 79 drift-computable races; this is below a hundreds-of-races corpus. This is the factual sample-size input for the human Phase 1 seven-model readiness decision; this audit does not change the design.
Wide-drift coverage is 58 / 305 (19.0%). Morning and afternoon lead medians above are the input for deciding whether a 09:30 anchor task is needed; no task was registered.
Reference-only four-week extrapolation: +158 drift-computable races, assuming two comparable race days/week at the observed active-day mean (4 active days observed).

## Invariants

Sealed holdout not accessed. Database opened read-only with query_only enabled. Production artifacts unchanged. F3 frozen design document unchanged.
