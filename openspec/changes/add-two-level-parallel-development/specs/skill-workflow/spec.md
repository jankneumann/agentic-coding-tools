## ADDED Requirements

### Requirement: Parallel Skill Family

The system SHALL provide a `parallel-*` skill family alongside the existing skills (renamed to `linear-*`) for multi-agent parallel feature development.

- The `parallel-*` skills SHALL include: `parallel-explore-feature`, `parallel-plan-feature`, `parallel-implement-feature`, `parallel-review-plan`, `parallel-review-implementation`, `parallel-validate-feature`, `parallel-cleanup-feature`.
- Existing skills SHALL be renamed to `linear-*` prefix with backward-compatible aliases.
- Both skill families SHALL coexist and share the same OpenSpec artifact structure.

#### Scenario: Invoke parallel plan skill
- **WHEN** a user invokes `/parallel-plan-feature <description>`
- **THEN** the skill SHALL produce a `contracts/` directory with OpenAPI specs and a `work-packages.yaml` conforming to `work-packages.schema.json`
- **AND** the skill SHALL validate work-packages against the schema before presenting for approval

#### Scenario: Invoke existing skill by original name
- **WHEN** a user invokes a skill by its original name (e.g., `/explore-feature`)
- **THEN** the system SHALL resolve it to the `linear-*` equivalent via alias
- **AND** behavior SHALL be identical to the pre-rename skill

#### Scenario: Parallel skill degrades when coordinator unavailable
- **WHEN** a `parallel-*` skill detects that required coordinator capabilities (`CAN_DISCOVER`, `CAN_QUEUE_WORK`, `CAN_LOCK`) are unavailable
- **THEN** the skill SHALL degrade to linear-equivalent behavior
- **AND** the skill SHALL emit a warning explaining the degradation

### Requirement: Contract-First Development Phase

The `/parallel-plan-feature` skill SHALL produce machine-readable interface definitions before any implementation agent starts.

- Contracts SHALL include OpenAPI specs as the canonical artifact for API endpoints.
- Contracts SHALL support language-specific type generation: Pydantic models for Python, TypeScript interfaces for frontend.
- Contracts SHALL include SQL schema definitions for new database tables.
- Contracts SHALL include event schemas (JSON Schema) for async communication.
- Contracts SHALL support executable mock generation via Prism from the OpenAPI spec.

#### Scenario: Plan produces contract artifacts
- **WHEN** `/parallel-plan-feature` completes successfully
- **THEN** the `contracts/` directory SHALL contain at least one valid OpenAPI spec file
- **AND** `work-packages.yaml` SHALL reference all contract files in `contracts.openapi.files`
- **AND** `contracts.revision` SHALL be set to 1

#### Scenario: Contract compliance verification layers
- **WHEN** a work package completes implementation
- **THEN** the package's verification steps SHALL include static type checking of generated types
- **AND** Schemathesis property-based testing against the OpenAPI spec (Tier A minimum)
- **AND** Pact consumer-driven contract tests when CDC is enabled

### Requirement: Contract Revision Semantics

The system SHALL enforce contract revision tracking to prevent agents from working against stale contracts.

- Any contract file modification after implementation dispatch SHALL require a `contracts.revision` bump in `work-packages.yaml`.
- The orchestrator SHALL reject results whose `contracts_revision` does not match the current `work-packages.yaml` value.

#### Scenario: Contract changes during implementation
- **WHEN** an escalation triggers a contract modification after work packages have been dispatched
- **THEN** the orchestrator SHALL bump `contracts.revision` in `work-packages.yaml`
- **AND** the orchestrator SHALL resubmit all packages whose `contracts_revision` is now stale
- **AND** the orchestrator SHALL acquire the `feature:<id>:pause` lock during the bump procedure

#### Scenario: Result with stale contract revision
- **WHEN** a completed package reports `contracts_revision` lower than the current `work-packages.yaml` value
- **THEN** the orchestrator SHALL treat the result as stale and ignore it
- **AND** the orchestrator SHALL not merge the package's worktree

### Requirement: Work Package DAG Scheduling

The `/parallel-implement-feature` skill SHALL decompose implementation into agent-scoped work packages with deterministic DAG scheduling.

- Each work package SHALL declare explicit file scope (`scope.write_allow`, `scope.read_allow`, `scope.deny`).
- Each work package SHALL declare explicit resource claims (`locks.files`, `locks.keys`).
- For any two packages that can run in parallel, `scope.write_allow` sets SHALL NOT overlap (except `wp-integration`).
- For parallel packages, `locks.keys` sets SHALL NOT overlap.
- The DAG SHALL be computed via topological sort with cycle detection.
- No dependent package SHALL run if its dependency is FAILED or CANCELLED.

#### Scenario: DAG preflight validation
- **WHEN** the orchestrator parses `work-packages.yaml` before dispatch
- **THEN** the orchestrator SHALL validate against `work-packages.schema.json`
- **AND** detect and reject cycles in the dependency graph
- **AND** verify file scope non-overlap for parallel packages
- **AND** verify logical lock non-overlap for parallel packages

#### Scenario: Dependency package fails
- **WHEN** a work package completes with `status=failed`
- **THEN** all packages that transitively depend on it SHALL be marked CANCELLED
- **AND** the orchestrator SHALL not dispatch cancelled packages

#### Scenario: All packages complete successfully
- **WHEN** all non-integration packages complete with `status=completed`
- **THEN** the orchestrator SHALL dispatch the `wp-integration` package
- **AND** `wp-integration` SHALL claim the union of all file locks from all packages

### Requirement: Scope Enforcement

The system SHALL enforce per-package file scope compliance via deterministic diff checks.

- Modified files SHALL be computed from `git diff --name-only`.
- Each modified file SHALL match at least one glob in `scope.write_allow`.
- No modified file SHALL match any glob in `scope.deny`.
- Scope violations SHALL cause the package to fail with `error_code="SCOPE_VIOLATION"`.

#### Scenario: Agent modifies file within scope
- **WHEN** a work package agent modifies a file that matches `scope.write_allow` and does not match `scope.deny`
- **THEN** the scope check SHALL pass for that file

#### Scenario: Agent modifies file outside scope
- **WHEN** a work package agent modifies a file that does not match any `scope.write_allow` glob
- **THEN** the scope check SHALL fail
- **AND** the package SHALL report `error_code="SCOPE_VIOLATION"` with the violating file paths

#### Scenario: Agent modifies file in deny list
- **WHEN** a work package agent modifies a file that matches a `scope.deny` glob, even if it also matches `scope.write_allow`
- **THEN** the scope check SHALL fail with `error_code="SCOPE_VIOLATION"`

### Requirement: Escalation Protocol

Work package executors SHALL signal structured escalations when they cannot complete correctly under current constraints.

- Escalations SHALL be dual-written: in the package's `result.escalations[]` and as an independent `task_type="escalation"` work-queue task with `priority=1`.
- The orchestrator SHALL follow a deterministic decision procedure per escalation type.
- `BLOCKING` severity escalations SHALL trigger the pause-lock mechanism (`feature:<id>:pause`).

#### Scenario: Contract revision required escalation
- **WHEN** a package agent discovers the contract is wrong during implementation
- **THEN** the agent SHALL submit an escalation with `type="CONTRACT_REVISION_REQUIRED"` and `severity="BLOCKING"`
- **AND** the agent SHALL stop making forward progress and fail the package
- **AND** the orchestrator SHALL execute the contract revision bump procedure

#### Scenario: Non-blocking escalation
- **WHEN** a package agent encounters a flaky test unrelated to its code changes
- **THEN** the agent SHALL include an escalation with `type="FLAKY_TEST_QUARANTINE_REQUEST"` and `severity="NON_BLOCKING"` in `result.escalations[]`
- **AND** the agent MAY complete the package successfully
- **AND** `wp-integration` SHALL evaluate quarantined tests separately

#### Scenario: Security escalation requires human decision
- **WHEN** a package agent discovers a security-sensitive issue
- **THEN** the agent SHALL submit an escalation with `type="SECURITY_ESCALATION"`, `severity="BLOCKING"`, and `requires_human=true`
- **AND** the orchestrator SHALL pause the DAG and wait for human decision

### Requirement: Verification Tiers

Each work package SHALL specify a minimum verification tier, and the system SHALL NOT silently downgrade.

- Tier A: local CLI agent with full tooling (pytest, mypy, ruff, Schemathesis, Pact).
- Tier B: agent triggers CI pipeline, pushes branch, polls for required checks.
- Tier C: static checks only (syntax, formatting, basic type inference). Flags package for Tier A/B follow-up.

#### Scenario: Agent cannot satisfy required verification tier
- **WHEN** a work package requires Tier A verification but the agent only has Tier C capabilities
- **THEN** the agent SHALL escalate with `type="VERIFICATION_INFEASIBLE"` and `severity="HIGH"`
- **AND** the package SHALL NOT be marked as completed

#### Scenario: Tier B verification via CI
- **WHEN** a work package's verification includes a `kind="ci"` step
- **THEN** the agent SHALL push the branch and trigger the specified CI workflow
- **AND** poll for completion of all `required_checks`
- **AND** include the CI `run_id` and URL in the evidence

### Requirement: Review Agent Decoupling

`/parallel-review-plan` and `/parallel-review-implementation` SHALL operate as independent, read-only evaluation agents.

- Review agents SHALL receive artifacts as read-only input.
- Review agents SHALL produce findings conforming to `review-findings.schema.json`.
- Review agents SHALL NOT modify any artifacts directly.
- Review agents SHALL support dispatch to different AI vendors than the implementing agent.

#### Scenario: Review produces actionable findings
- **WHEN** `/parallel-review-implementation` reviews a completed work package's diff
- **THEN** the review SHALL produce a findings table with `id`, `type`, `criticality`, `description`, and `disposition`
- **AND** each finding SHALL have disposition of `fix`, `regenerate`, `accept`, or `escalate`

#### Scenario: Review finding with fix disposition
- **WHEN** a review finding has `disposition="fix"`
- **THEN** the orchestrator SHALL dispatch a `wp-fix-<package_id>` package inheriting the same locks and scope
- **AND** the fix package SHALL address the specific finding

#### Scenario: Review finding with escalate disposition
- **WHEN** a review finding has `disposition="escalate"`
- **THEN** the orchestrator SHALL follow the escalation protocol
- **AND** the finding SHALL be flagged for human decision

### Requirement: Continuous Validation

Validation SHALL be distributed across implementation phases rather than concentrated in a monolithic post-implementation step.

- Linting, type checking, and unit tests SHALL run during implementation in each package's `verification.steps`.
- Contract compliance (Schemathesis, Pact) SHALL run during implementation at Tier A minimum.
- Scope compliance SHALL run after code generation as a deterministic diff check.
- Full end-to-end and integration tests SHALL run only in `wp-integration` and `/parallel-validate-feature`.

#### Scenario: Package-level verification during implementation
- **WHEN** a work package agent completes code generation
- **THEN** the agent SHALL execute all `verification.steps` in order
- **AND** on any step failure the agent SHALL fail fast without continuing to subsequent steps
- **AND** the result SHALL include which step failed and why

#### Scenario: Integration-only checks after merge
- **WHEN** `wp-integration` merges all worktrees into the feature branch
- **THEN** `wp-integration` SHALL run the full test suite
- **AND** run cross-package contract verification (Schemathesis, Pact)
- **AND** this SHALL be the only place expensive end-to-end checks run

### Requirement: Feature Registry and Cross-Feature Coordination

The coordinator SHALL maintain a feature registry for cross-feature resource claim management.

- Each registered feature SHALL declare resource claims using the lock key namespace.
- The coordinator SHALL produce parallel feasibility assessments: `FULL` (no conflicts), `PARTIAL` (some conflicts, can be sequenced), or `SEQUENTIAL` (blocking conflicts).
- Cross-feature resource collisions SHALL be handled via the `RESOURCE_CONFLICT` escalation type.

#### Scenario: Two features with no resource conflicts
- **WHEN** two features register resource claims that do not overlap
- **THEN** the feasibility assessment SHALL be `FULL`
- **AND** both features MAY proceed in parallel

#### Scenario: Two features with partial resource overlap
- **WHEN** two features share some logical lock keys but not all
- **THEN** the feasibility assessment SHALL be `PARTIAL`
- **AND** the coordinator SHALL recommend a merge order

#### Scenario: Two features with blocking conflicts
- **WHEN** two features claim the same critical resource (e.g., same database migration slot)
- **THEN** the feasibility assessment SHALL be `SEQUENTIAL`
- **AND** the second feature SHALL wait until the first completes
