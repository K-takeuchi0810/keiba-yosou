# Expert review 2026-08-02 21:55

**Change**: Repair the fresh-odds batch encoding and run eight user scheduled tasks through a hidden, wait-for-completion wrapper while preserving their commands, arguments, triggers, principals, conditions, working directories, and effective time limits.

**Files and system configuration**:

- `scripts/fetch_fresh_odds.bat`
- `%LOCALAPPDATA%\ScheduledTaskRunner\run-scheduled-task-hidden.vbs`
- Eight user-created Task Scheduler actions
- Pre-change backup: `outputs/scheduled-task-backup_20260802_214740`

## Aggregate score

| Reviewer | Judgment | Score |
|---|---:|---:|
| GUI / UX auditor | HOLD | 3.6 |
| Mobile HTML reviewer | PASS | 4.0 |
| Prediction logic analyst | PASS | 4.8 |
| Profitability judge | PASS | 4.4 |
| Data pipeline engineer | PASS | 4.0 |
| Code quality reviewer | PASS | 4.2 |
| Validation process auditor | PASS | 4.0 |
| **Overall** | **PASS with UX follow-up** | **4.1 / 5** |

## Confirmed evidence

- All eight current task definitions match their pre-change XML for principals, triggers, conditions, working directories, multiple-instance policy, and non-Action settings.
- `keiba-fresh-odds` has the original effective `PT72H` Task Scheduler default. The temporary `PT8M` limit was removed after review identified stale-lock/data-gap risk.
- The runner waits for completion and preserves exit codes: cmd fixture `7`, PowerShell fixture `9`, missing target `2`, invalid mode/arguments `87`.
- A real `MAIBuilder Live JRA Data` scheduled run completed at 22:00 with result `0x00000000` and did not create a new Windows Terminal process.
- `fetch_fresh_odds.bat` is ASCII-only, BOM-free, and all six line endings are CRLF. The executable Python command is unchanged.
- The pre-change task XML files all parse successfully and remain available for rollback.

## Findings addressed during review

1. **Stale lock after forced timeout**: the proposed eight-minute execution limit could have caused fresh-odds gaps. Reverted to the original effective `PT72H` behavior.
2. **False success for missing targets**: the initial runner could return zero when a batch path no longer existed. Added an explicit file-existence check and verified exit code `2`.

## Remaining follow-ups

1. Add a non-intrusive aggregate failure log or notification policy if silent Task Scheduler failures need proactive visibility. Do not restore console flashes.
2. Keep the installed runner and its backup/hash together when moving tasks to another machine.
3. Confirm the remaining seven tasks after their next natural scheduled runs; their static definitions and synthetic exit-code tests already pass.

No reviewer found a prediction, profitability, HTML, database, or data-ingestion behavior change in the final configuration.
