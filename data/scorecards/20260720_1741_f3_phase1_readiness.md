# Expert review — F3 Phase 1 readiness

**Change**: Measure dev-window PIT odds coverage through the canonical gate, read-only.
**Target**: final HEAD `cb56778`; `scripts/f3_phase1_readiness.py`, tests, JSON and report.
**Implementation verdict**: **PASS**.
**Phase 1 seven-model kickoff**: **HOLD** (19 drift-computable races, zero wide-drift races).

## Score trend

| Expert | Current | Previous | Delta | Verdict |
|---|---:|---:|---:|---|
| GUI / UX | 3.6 | 3.6 | 0.0 | HOLD (pre-existing GUI issues; no regression) |
| Mobile HTML | 4.0 | 4.0 | 0.0 | PASS |
| Prediction logic | 4.2 | 4.2 | 0.0 | HOLD (Phase 1 sample not ready) |
| Profitability | 2.0 | 2.0 | 0.0 | HOLD (no ROI evidence; measurement only) |
| Data pipeline | 4.6 | 4.3 | +0.3 | PASS |
| Code quality | 4.5 | 4.3 | +0.2 | PASS |
| Validation process | 4.8 | 4.8 | 0.0 | PASS |
| **Average** | **3.96** | **3.89** | **+0.07** | **No regression warning** |

## Cross-review findings

1. The measurement implementation satisfies the canonical PIT gate, fixed dev start,
   sealed-window guard, query-only consistent read transaction, production/design hashes,
   JRA/other scope disclosure, atomic output, and provenance requirements.
2. The observed population is not ready for a seven-model comparison: 19 / 225 races
   have at least two distinct eligible timestamps; wide-drift coverage is 0 / 225.
3. The four-week +76 projection is reference-only because it is based on two active
   collection days. It must not be used as a model kickoff criterion.

## Priority improvement

Human review should decide whether to authorize the documented 09:30 morning-anchor
collection task. No scheduler task or design change was made by this audit.
