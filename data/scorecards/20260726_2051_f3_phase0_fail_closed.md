# Expert review — F3 Phase 0 fail-closed

**Change**: Add the closed `full / observation / blocked` prediction contract,
production-consumer enforcement, ledger migration, monitoring breakdown, and E01-E04
regression coverage.
**Branch**: `codex/phase0-fail-closed`
**Implementation verdict**: **PASS_WITH_FINDINGS**.
**Profitability verdict**: **HOLD**; this safety change does not authorize live betting.

## Score trend

| Expert | Current | Previous | Delta | Verdict |
|---|---:|---:|---:|---|
| GUI / UX | 3.6 | 3.6 | 0.0 | HOLD (pre-existing accessibility/help gaps) |
| Mobile HTML | 4.0 | 4.0 | 0.0 | PASS |
| Prediction logic | 4.4 | 4.3 | +0.1 | PASS |
| Profitability | 2.2 | 2.2 | 0.0 | HOLD (existing OOS ROI 62.0941%) |
| Data pipeline | 4.5 | 4.1 | +0.4 | PASS |
| Code quality | 4.5 | 4.5 | 0.0 | PASS |
| Validation process | 4.2 | 3.4 | +0.8 | PASS |
| **Average** | **3.91** | **3.73** | **+0.18** | **PASS_WITH_FINDINGS** |

## Cross-review result

- The shared validator, E04 severity priority, production-only buy guard, and
  Batch/member invariant close the fail-open paths found during the first review.
- Web, GUI, CLI, auto-predict, daily batch, ledger, and monitor expose or preserve the
  closed mode and reason contract. Blocked empty runs remain auditable.
- The exact G4 validation AUC pair and production artifact hashes are unchanged.
  The final suite is 441 passed / 4 skipped; Python-expanded GUI JavaScript parses.

## Retained finding

No expert domain regressed by 0.3 or more. Core validation is centralized, but guidance
text, run-level aggregation, and exit-code constants still have parallel representations
across Python, JavaScript, Jinja, CLI, and SQLite. This is the main maintainability finding,
not a functional regression.

## Top priorities

1. Move mode/reason guidance, severity aggregation, and process exit codes behind one
   small public status-contract module.
2. Add a Task Scheduler-level integration test covering bat → notification → final
   combined exit bits, plus a mixed-mode GUI execution test.
3. Keep betting disabled: the frozen paired OOS reference remains 425 bets at 62.0941%
   ROI and was intentionally not rerun for this safety-only phase.
