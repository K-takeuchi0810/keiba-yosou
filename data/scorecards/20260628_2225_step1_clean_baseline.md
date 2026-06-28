# Step 1 clean OOS baseline 2026-06-28 22:25

## Scope

Data-quality gates were applied before re-running the 2026 OOS baseline.

- Race completeness: `list_races(require_confirmed=True)` requires a confirmed winner (`confirmed_order=1`).
- Odds freshness: post-start or all-stale snapshot races are excluded by default.
- Snapshot monotonicity: `update_win_odds` no longer overwrites newer snapshots with older `fetched_at`.

## Validation

- Targeted review: data-pipeline reviewer found no blocking issues.
- Validation review: no P0/P1 issues; P2/P3 findings were addressed.
- Tests: `144 passed`.

## Clean Baseline

Artifact: `data/backtest/20260628_222404_tan_p25-clean-oos-step1-filtered.json`

| Metric | Value |
|---|---:|
| Window | 20260101-20260614 |
| Confirmed races | 1,578 |
| Odds-untrusted excluded races | 443 |
| Effective all bets | 1,135 |
| All-bet ROI | 66.1% |
| Buy-only bets | 127 |
| Buy-only ROI | 67.0% |
| Buy-only CI95 | 39.0%-99.8% |
| Calibration in-sample | false |
| git_dirty at run | false |

## Implication

The previous OOS baseline that used the same window was polluted by odds snapshots. After Step 1, 443/1,578 races are excluded, with almost all exclusions concentrated in May-June 2026. The true clean baseline remains below break-even, so the next ROI experiments must use this artifact as the baseline.

Next recommended work:

1. Build comparison/promotion tooling so future candidates are judged against this clean baseline.
2. Register and test `pop1-3 + p<=0.40` without the final Kelly gate.
3. Treat May-June fresh-odds capture as an operational issue before relying on recent odds-based experiments.
