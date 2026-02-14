## ADDED Requirements

### Requirement: Boundary Enforcement Integrity

The system SHALL enforce authorization and profile checks inline on every state-mutating coordination operation.

- Mutation operations SHALL evaluate policy/profile authorization in the same execution path before side effects.
- Denied mutation requests SHALL produce no state changes in coordination tables.
- Guardrail evaluation during mutation flows SHALL use effective trust context resolved from policy/profile lookups.
- Guardrail violations detected in mutation flows SHALL be persisted to `guardrail_violations` and audit trail.
- Policy decisions (native and Cedar) for mutation operations SHALL be logged to audit trail with decision reason and engine metadata.

#### Scenario: Denied lock mutation has no side effects
- **WHEN** an agent without permission attempts lock acquisition
- **THEN** the operation is denied before lock state mutation
- **AND** no new `file_locks` row is created
- **AND** an audit entry records the denial reason

#### Scenario: Denied task mutation has no side effects
- **WHEN** an agent without permission attempts task submission or completion
- **THEN** the operation is denied before queue mutation
- **AND** no new or updated `work_queue` row is committed
- **AND** an audit entry records the denial reason

#### Scenario: Trust-aware guardrail execution
- **WHEN** guardrails run during claim/submit/complete paths
- **THEN** guardrails evaluate with resolved trust context for the requesting agent
- **AND** fallback default trust is used only if profile/policy resolution is unavailable

#### Scenario: Guardrail violation persistence
- **WHEN** guardrails detect a mutation-flow violation
- **THEN** a `guardrail_violations` record is written
- **AND** an immutable audit entry includes matched pattern context and block/allow outcome

#### Scenario: Cedar decision auditability
- **WHEN** mutation authorization is evaluated with `POLICY_ENGINE=cedar`
- **THEN** the allow/deny decision is logged to audit trail
- **AND** the audit record includes Cedar as decision engine metadata

---

### Requirement: Direct PostgreSQL Identifier Safety

The direct PostgreSQL backend SHALL reject unsafe dynamic identifier inputs during query construction.

- Dynamic identifiers (table names, selected columns, order columns) SHALL be constrained to trusted/safe forms.
- Unsafe identifier inputs SHALL be rejected before SQL execution.

#### Scenario: Unsafe identifier rejected before execution
- **WHEN** identifier-like input contains unsafe SQL tokens or delimiters
- **THEN** the backend returns a validation error
- **AND** no SQL statement is executed

---

### Requirement: Behavioral Assurance and Formal Verification

The system SHALL maintain an assurance program that verifies safety-critical coordination behavior through automated tests and formal modeling.

- The system SHALL continuously verify lock/work queue invariants via automated tests.
- The system SHALL verify boundary enforcement behavior (denied mutations cause no side effects).
- The system SHALL verify audit completeness for mutation operations.
- The system SHALL verify default-decision equivalence between native and Cedar policy engines.
- The system SHALL include a formal model of lock/task lifecycle invariants.
- Formal model checks SHALL be runnable in CI.

#### Scenario: Lock exclusivity invariant under concurrency
- **WHEN** concurrent lock acquisition attempts target the same file
- **THEN** verification confirms at most one live lock exists for that file

#### Scenario: Task claim uniqueness invariant
- **WHEN** concurrent claim attempts run against a queue with one eligible task
- **THEN** verification confirms only one claimant receives that task

#### Scenario: Completion ownership invariant
- **WHEN** a non-claiming agent attempts to complete a claimed task
- **THEN** verification confirms completion is rejected
- **AND** task ownership is unchanged

#### Scenario: Audit completeness for mutations
- **WHEN** mutation operations execute (success or denial)
- **THEN** verification confirms corresponding audit entries exist with required decision fields

#### Scenario: Native/Cedar equivalence regression check
- **WHEN** differential verification runs baseline profiles and operation/resource matrix
- **THEN** native and Cedar engines produce identical allow/deny outcomes for baseline policy set

#### Scenario: Formal model safety check
- **WHEN** TLC runs on the coordination TLA+ model
- **THEN** lock/task safety invariants hold for bounded state exploration
