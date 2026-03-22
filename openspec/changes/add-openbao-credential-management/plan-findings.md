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

## Iteration 3

| # | Type | Criticality | Description | Status |
|---|------|-------------|-------------|--------|
| 15 | consistency | critical | Proposal says "trust 0–3" but `agents_config.py` schema uses `minimum: 1, maximum: 5` | Fixed — corrected to "trust 1–5" |
| 16 | clarity | high | "configured session lifetime" undefined — no TTL parameter, no defaults | Fixed — added `BAO_TOKEN_TTL` (default 3600s) to config dataclass and agent-identity spec |
| 17 | clarity | high | Renewal trigger "approaching expiry" undefined — no component, no threshold | Fixed — specified "less than 25% of TTL remaining", profile loader as responsible component |
| 18 | consistency | high | Task 4.2 doesn't specify HTTP-transport filter, contradicting spec | Fixed — added "(HTTP-transport agents only)" qualifier |
| 19 | consistency | medium | AppRole policy claims per-agent scoping but grants broad `secret/data/coordinator` read | Fixed — clarified shared path for MVP, per-agent sub-paths as future enhancement |
| 20 | completeness | medium | Wrapped SecretID delivery underspecified but referenced in proposal/design | Fixed — moved to non-goals, simplified to direct `BAO_SECRET_ID` env var for MVP |
| 21 | consistency | medium | Impact section missing `BAO_SECRET_PATH`, `BAO_TIMEOUT`, `BAO_TOKEN_TTL` parameters | Fixed — added all parameters to Impact list |

## Post-Iteration Fix (critical findings from late-arriving analysis agent)

| # | Type | Criticality | Description | Status |
|---|------|-------------|-------------|--------|
| 27 | clarity | critical | "Configured" database engine state undefined — no operational definition | Fixed — defined as database/ mount enabled + coordinator-agent role exists |
| 28 | clarity | critical | Session lifecycle / token revocation mechanism undefined — who triggers it? | Fixed — clarified TTL-based expiry (no coordinator action required) |
| 29 | consistency | high | Contradictory TTL model — proposal says single role, spec says per-agent | Fixed — clarified proposal: "coordinator-agent" is a role template generating per-agent creds |
| 30 | consistency | high | AppRole policy scope in agent-identity spec still claimed per-secret scoping | Fixed — aligned with MVP shared-path policy |

## Post-Iteration Fix 2 (completeness findings from late-arriving analysis agent)

| # | Type | Criticality | Description | Status |
|---|------|-------------|-------------|--------|
| 31 | completeness | high | Missing bao-seed error scenario for BAO_TOKEN/BAO_ADDR not set | Fixed — added validation scenario |
| 32 | completeness | medium | Missing bao-seed scenario for agents.yaml not found | Fixed — added graceful skip scenario |

## Remaining Findings (below threshold or deferred — max iterations reached)

| # | Type | Criticality | Description | Status |
|---|------|-------------|-------------|--------|
| 14 | completeness | low | Modified API Key Identity Generation has no OpenBao-specific scenario | Accepted — existing scenarios cover output format |
| 22 | completeness | medium | Missing bao-seed error scenarios (BAO_ADDR unreachable, BAO_TOKEN invalid during seeding) | Deferred — address during implementation |
| 23 | testability | medium | No explicit scenario testing profile inheritance with OpenBao-sourced secrets | Deferred — task 7.2 covers regression testing |
| 24 | testability | low | Dry-run output format unspecified | Deferred — implementation detail |
| 25 | testability | low | Idempotency verification criteria vague | Deferred — implementation detail |
| 26 | testability | low | No scenario for invalid KV mount path | Deferred — edge case for post-MVP |
