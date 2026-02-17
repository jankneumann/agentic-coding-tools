## Context

The coordinator currently has strong building blocks (atomic DB functions, service abstractions, broad unit coverage), but enforcement and verification are fragmented across optional tool calls and partially integrated paths. This change formalizes an assurance architecture where safety invariants are enforced at boundaries and continuously verified.

## Goals / Non-Goals

- Goals:
  - Make policy/profile/guardrail enforcement mandatory at mutation boundaries
  - Remove stale API assumptions and align interfaces with canonical DB functions
  - Define measurable invariants and continuously verify them in CI
  - Introduce a formal model for high-risk coordination invariants
- Non-Goals:
  - Implement Phase 4 orchestration features (Strands/AgentCore runtime)
  - Replace Cedar or rewrite the full verification gateway architecture
  - Implement delegated identity, approval workflows, contextual risk scoring, realtime policy sync, policy rollback, or session-scoped grants (owned by `add-dynamic-authorization`)
  - Re-implement Phase 2/3 capability expansion already scoped in `complete-missing-coordination-features`

## Decisions

### 1) Boundary-first enforcement

All state-mutating operations (`acquire_lock`, `release_lock`, `submit_work`, `complete_work`, etc.) must perform authorization checks in the execution path, not as a separate optional tool call.

### 2) Canonical API surface

`verification_gateway/coordination_api.py` must target migration-backed function names and either be integrated into the primary runtime path or explicitly marked legacy with no production claims.

### 3) Trust-propagated guardrails

Guardrail checks must evaluate with effective trust context from profile/policy resolution. Default trust values are fallback-only and must not silently override known profile decisions.

### 4) Auditable policy decisions

Authorization and guardrail outcomes must be logged consistently (including allow/deny reason, engine, and context) so investigators can reconstruct decisions.

### 5) Multi-layer verification

Verification will combine runtime tests, database policy tests, and formal modeling:
- Runtime: boundary integration and end-to-end behavior
- DB: migration + RLS policy assertions
- Formal: TLA+ model checking of lock/queue safety+liveness invariants

### 6) Additive spec strategy to minimize merge conflicts

This change uses additive requirements for assurance behavior rather than re-modifying broad existing requirements that are actively modified by `complete-missing-coordination-features`.

### 7) Sequencing with active changes

- Preferred sequence: merge/settle `complete-missing-coordination-features` core enforcement surfaces first, then apply this assurance change.
- `add-dynamic-authorization` may merge before or after this change; this proposal intentionally avoids owning its new capability surfaces.

## Invariants to Verify

- Exclusive lock invariant: no two live locks exist for the same file path.
- Claim uniqueness invariant: a task cannot be claimed by two agents simultaneously.
- Completion ownership invariant: only the claiming agent can complete a claimed task.
- Enforcement invariant: all mutation endpoints invoke policy/profile checks before side effects.
- Audit completeness invariant: every mutation has a corresponding immutable audit event.
- Policy equivalence invariant: default Cedar and native engines make identical decisions for baseline profiles.

## Formal Methods Direction

- Create `agent-coordinator/formal/coordination.tla` modeling lock/task state machine.
- Encode safety invariants and basic liveness (eventual expiry/reclaimability).
- Use TLC in CI for bounded model checks.
- Keep model synchronized with OpenSpec requirement IDs to preserve traceability.

## Risks / Trade-offs

- Stricter enforcement may initially block workflows relying on previously permissive behavior.
- Additional test/modeling layers increase CI time.
- Formal model abstraction may drift from implementation unless maintained with requirement mapping.

## Migration Plan

1. Rebase against latest active-change state and resolve ownership of touched files/functions.
2. Add enforcement checks to mutation boundaries behind a temporary feature flag if needed.
3. Align/retire stale HTTP API endpoints.
4. Add verification suites and establish CI gates.
5. Introduce TLA+ checks as non-blocking, then promote to blocking after stabilization.

## Dependency / Merge Order

### External change dependencies

1. `complete-missing-coordination-features`:
   This change should merge first (or provide equivalent landed surfaces) for stable profile/guardrail/audit/policy-engine hooks.
2. `add-dynamic-authorization`:
   Can merge before or after this change, but this change must not implement or claim its capability surfaces.

### Internal execution order (this change)

1. Enforcement remediation (`tasks 1.x`)
2. API/architecture alignment (`tasks 2.x`)
3. Security hardening (`tasks 3.x`)
4. Behavioral verification suite (`tasks 4.x`)
5. Formal verification track (`tasks 5.x`)
6. Validation/rollout (`tasks 6.x`)

### Blocking graph

- `1.0` blocks all other tasks.
- `1.x` and `2.x` block `4.1` and `4.6` (boundary/audit tests require enforcement behavior).
- `3.x` blocks security test completion for direct-postgres path.
- `4.x` should complete before promoting formal checks to required CI status in `5.3`.

## Open Questions

- Should boundary enforcement failures return standardized error codes across MCP and HTTP?
- Should TLA+ checks be mandatory on every PR or only on coordinator-touching PRs?
