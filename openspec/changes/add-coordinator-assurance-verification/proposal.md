# Change: Add Coordinator Assurance and Behavioral Verification

## Why

A focused architectural review of `agent-coordinator/` identified gaps between specified safety/governance behavior and enforced runtime behavior. The highest-risk findings are: policy/profile checks not enforced on all mutation paths, stale cloud API interfaces, incomplete trust propagation into guardrails, incomplete persistence/audit of safety decisions, and insufficient end-to-end verification of invariants.

Without an assurance-focused change, the system can appear compliant in unit tests while violating core safety assumptions in real operation.

## What Changes

- Enforce authorization/profile checks on all mutation entry points (MCP and HTTP), not as optional helper tools.
- Align cloud HTTP endpoints with canonical migration-backed functions and remove stale/duplicate API paths.
- Propagate effective trust context into guardrail evaluation and persist guardrail violations consistently.
- Log authorization decisions (including Cedar decisions) to immutable audit trail.
- Harden direct-PostgreSQL identifier handling to avoid SQL-injection risk from dynamic identifiers.
- Add a verification program that combines:
  - integration tests for enforcement boundaries,
  - property/stateful tests for lock/queue invariants,
  - differential tests for native vs Cedar policy equivalence,
  - migration-level RLS assertions,
  - formal modeling (TLA+) for lock/task state machine invariants.
- Reduce overlap with active OpenSpec changes by scoping this change to assurance and verification only:
  - **Does not add new authorization capabilities** (delegated identity, approvals, risk scoring, realtime policy sync, policy rollback, session grants), which remain in `add-dynamic-authorization`.
  - **Does not re-propose Phase 2/3 feature build-out**, which remains in `complete-missing-coordination-features`.
  - Focuses on correctness of enforcement boundaries, behavioral verification, and formal assurance for behavior already implemented or landing via those changes.

## Coordination With Active Changes

- Depends on base capability surfaces from `complete-missing-coordination-features` where applicable (profiles/guardrails/audit/policy-engine paths).
- Must remain compatible with `add-dynamic-authorization` and avoid schema/API ownership conflicts:
  - If `add-dynamic-authorization` lands first, this change reuses its tables/endpoints and only adds assurance tests/hooks.
  - If this change lands first, it must not reserve endpoint/function names targeted by `add-dynamic-authorization`.

## Impact

- Affected specs: `agent-coordinator`
- Affected code:
  - `agent-coordinator/src/coordination_mcp.py`
  - `agent-coordinator/src/work_queue.py`
  - `agent-coordinator/src/guardrails.py`
  - `agent-coordinator/src/policy_engine.py`
  - `agent-coordinator/src/db_postgres.py`
  - `agent-coordinator/src/audit.py`
  - `agent-coordinator/verification_gateway/coordination_api.py`
  - `agent-coordinator/verification_gateway/gateway.py`
  - `agent-coordinator/tests/` (new integration/property/equivalence tests)
  - `agent-coordinator/supabase/migrations/` (if schema hooks needed for decision logging/constraints)
  - `agent-coordinator/formal/` (new TLA+ specs and model configs)
- **BREAKING**: Potentially behavior-tightening for previously unguarded mutation paths (operations that were unintentionally allowed may now be denied).
