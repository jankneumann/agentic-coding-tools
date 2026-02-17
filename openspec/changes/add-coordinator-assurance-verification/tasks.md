## 1. Enforcement Remediation

- [x] 1.0 Reconcile with active changes before editing code: confirm ownership boundaries with `complete-missing-coordination-features` and `add-dynamic-authorization`.
- [x] 1.1 Build a mutation-surface inventory (MCP + HTTP) and enforce profile/policy checks in every mutation path before side effects (`acquire_lock`, `release_lock`, `get_work` claim path, `complete_work`, `submit_work`, `write_handoff`, `remember`, and any newly added mutation tools/endpoints).
- [x] 1.2 Enforce equivalent authorization checks in HTTP mutation endpoints.
- [x] 1.3 Pass effective trust level/context into guardrail checks on claim/submit/complete flows.
- [x] 1.4 Ensure guardrail violations are persisted to `guardrail_violations` and audit trail with consistent schema.
- [x] 1.5 Log policy-engine decisions (native and Cedar) to audit trail.

## 2. API and Architecture Alignment

- [x] 2.1 Reconcile `src/coordination_api.py` RPC names with canonical migrations (remove stale function references).
- [x] 2.2 Decide and document primary production path for cloud API (integrated vs legacy gateway).
- [x] 2.3 Update docs to reflect actual runnable architecture and migration names.

## 3. Security Hardening

- [x] 3.1 Harden `DirectPostgresClient` dynamic identifier handling (table/select/order allowlists or safe quoting strategy).
- [x] 3.2 Add tests proving unsafe identifier injection is rejected.

## 4. Behavioral Verification Suite

- [ ] 4.1 Add boundary integration tests validating denied mutations are blocked pre-side-effect.
- [ ] 4.2 Add stateful/property tests for lock invariants under concurrent interleavings.
- [ ] 4.3 Add stateful/property tests for work-queue invariants under concurrent interleavings.
- [ ] 4.4 Extend Cedar-vs-native differential tests to full operation/resource matrix.
- [ ] 4.5 Add migration-level RLS tests for service_role/anon behavior on sensitive tables.
- [ ] 4.6 Add audit completeness tests ensuring each mutation emits immutable audit records.

## 5. Formal Verification Track

- [x] 5.1 Create initial TLA+ model for lock/task lifecycle.
- [x] 5.2 Encode safety invariants and liveness checks from this proposal.
- [x] 5.3 Add TLC execution script and CI job (initially non-blocking).
- [x] 5.4 Map formal invariants to OpenSpec requirement/scenario IDs.

## 6. Validation and Rollout

- [ ] 6.1 Run full test suite and report behavioral deltas caused by tightened enforcement.
- [ ] 6.2 Add rollout notes for compatibility impact and mitigation (feature flags, profile updates).
- [ ] 6.3 Update OpenSpec tasks/spec links in PR description for traceability.
- [x] 6.4 Confirm no duplicate implementation of dynamic-authorization features (delegation/approval/risk/policy-sync/versioning/session-grants) in this change.

## Dependency / Merge-Order Summary

- [ ] D1 Merge-order prerequisite: `complete-missing-coordination-features` landed (or equivalent surfaces available) before starting `1.1+`.
- [ ] D2 Ownership check: this change does not implement capabilities owned by `add-dynamic-authorization`.
- [ ] D3 Internal order: complete `1.x` and `2.x` before `4.1`/`4.6`.
- [ ] D4 Internal order: complete `3.x` before closing security verification for direct-postgres path.
- [ ] D5 Internal order: complete `4.x` before making `5.3` formal verification CI gate blocking.

## Parallelization and File Scope

- [ ] P1 Sequential prerequisite: complete `1.0` and D1-D2 before parallel implementation starts.
- [ ] P2 Parallel group A (minimal overlap): `3.1`, `3.2`, `5.1`, `5.2` (security hardening + formal model scaffolding).
- [ ] P3 Parallel group B (after `1.x` and `2.x`): `4.2`, `4.3`, `4.4`, `4.5` (independent verification suites).
- [ ] P4 Sequential closeout: `4.1` and `4.6` after enforcement paths stabilize, then `5.3`, `5.4`, and `6.x`.
- [ ] P5 For `/parallel-implement`, each task prompt SHALL declare allowed files explicitly; tasks touching shared files (`coordination_mcp.py`, `coordination_api.py`, `audit.py`, `policy_engine.py`) SHALL run sequentially.
