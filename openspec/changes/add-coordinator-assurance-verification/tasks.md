## 1. Enforcement Remediation

- [ ] 1.0 Reconcile with active changes before editing code: confirm ownership boundaries with `complete-missing-coordination-features` and `add-dynamic-authorization`.
- [ ] 1.1 Enforce profile/policy checks in all mutation MCP tools before service mutation calls (`acquire_lock`, `release_lock`, `get_work` claim path, `complete_work`, `submit_work`, `write_handoff`, `remember`).
- [ ] 1.2 Enforce equivalent authorization checks in HTTP mutation endpoints.
- [ ] 1.3 Pass effective trust level/context into guardrail checks on claim/submit/complete flows.
- [ ] 1.4 Ensure guardrail violations are persisted to `guardrail_violations` and audit trail with consistent schema.
- [ ] 1.5 Log policy-engine decisions (native and Cedar) to audit trail.

## 2. API and Architecture Alignment

- [ ] 2.1 Reconcile `verification_gateway/coordination_api.py` RPC names with canonical migrations (remove stale function references).
- [ ] 2.2 Decide and document primary production path for cloud API (integrated vs legacy gateway).
- [ ] 2.3 Update docs to reflect actual runnable architecture and migration names.

## 3. Security Hardening

- [ ] 3.1 Harden `DirectPostgresClient` dynamic identifier handling (table/select/order allowlists or safe quoting strategy).
- [ ] 3.2 Add tests proving unsafe identifier injection is rejected.

## 4. Behavioral Verification Suite

- [ ] 4.1 Add boundary integration tests validating denied mutations are blocked pre-side-effect.
- [ ] 4.2 Add stateful/property tests for lock and work-queue invariants under concurrent interleavings.
- [ ] 4.3 Extend Cedar-vs-native differential tests to full operation/resource matrix.
- [ ] 4.4 Add migration-level RLS tests for service_role/anon behavior on sensitive tables.
- [ ] 4.5 Add audit completeness tests ensuring each mutation emits immutable audit records.

## 5. Formal Verification Track

- [ ] 5.1 Create initial TLA+ model for lock/task lifecycle.
- [ ] 5.2 Encode safety invariants and liveness checks from this proposal.
- [ ] 5.3 Add TLC execution script and CI job (initially non-blocking).
- [ ] 5.4 Map formal invariants to OpenSpec requirement/scenario IDs.

## 6. Validation and Rollout

- [ ] 6.1 Run full test suite and report behavioral deltas caused by tightened enforcement.
- [ ] 6.2 Add rollout notes for compatibility impact and mitigation (feature flags, profile updates).
- [ ] 6.3 Update OpenSpec tasks/spec links in PR description for traceability.
- [ ] 6.4 Confirm no duplicate implementation of dynamic-authorization features (delegation/approval/risk/policy-sync/versioning/session-grants) in this change.

## Dependency / Merge-Order Summary

- [ ] D1 Merge-order prerequisite: `complete-missing-coordination-features` landed (or equivalent surfaces available) before starting `1.1+`.
- [ ] D2 Ownership check: this change does not implement capabilities owned by `add-dynamic-authorization`.
- [ ] D3 Internal order: complete `1.x` and `2.x` before `4.1`/`4.5`.
- [ ] D4 Internal order: complete `3.x` before closing security verification for direct-postgres path.
- [ ] D5 Internal order: complete `4.x` before making `5.3` formal verification CI gate blocking.
