# Plan Findings: add-openbao-credential-management

## Iteration 1

| # | Type | Criticality | Description | Status |
|---|------|-------------|-------------|--------|
| 1 | consistency | high | Impact section referenced `agent-coordinator` spec but deltas target `configuration` and `agent-identity` | Fixed |
| 2 | completeness | high | Proposal section 6 (Worktree Secret Elimination) had no corresponding requirement in spec deltas | Fixed — added Worktree Secret Handling requirement to configuration spec |
| 3 | completeness | medium | No scenario for `OpenBaoConfig.create_client()` success path | Fixed — added success scenario |
| 4 | completeness | medium | No scenario for token renewal failure (max TTL exceeded) | Fixed — added renewal failure scenario to agent-identity spec |
| 5 | completeness | medium | No requirement for handling non-string values from OpenBao KV v2 | Fixed — added filtering scenario to configuration spec |
| 6 | completeness | medium | Missing scenario for `bao-seed.py` when `.secrets.yaml` is missing | Fixed — added missing source file scenario |
| 7 | scope | medium | Task 7.3 (`hvac` for scripts) depended on 4.1 but should precede it | Fixed — moved to 1.1b in group 1, updated dependencies |
| 8 | parallelizability | medium | Independent tasks lacked parallel annotations | Fixed — added Parallel annotations to 1.1, 1.1b, 3.1, 5.1, 5.2, 7.1 |
| 9 | testability | low | Renewal scenario used vague "SHALL not be interrupted" | Fixed — reworded to measurable "SHALL remain valid during renewal" |
| 10 | clarity | low | `BAO_SECRET_PATH` default not mentioned in proposal section 1 | Fixed — added configurable paths to proposal |

## Iteration 2

| # | Type | Criticality | Description | Status |
|---|------|-------------|-------------|--------|
| 11 | completeness | medium | No scenario for `BAO_ADDR` set but `BAO_SECRET_ID` missing | Fixed — added missing credentials scenario |
| 12 | feasibility | medium | Task 6.1 incorrectly depended on 4.3 (seeding script); dynamic DSN resolution only needs 2.2 | Fixed — corrected dependency to 2.2 only |
| 13 | completeness | low | Task 2.3 test list didn't mention non-string filtering or missing credentials scenarios | Fixed — updated test description |
| 14 | completeness | low | Modified API Key Identity Generation requirement has no OpenBao-specific scenario | Accepted — existing scenarios cover output format; source is transparent |
