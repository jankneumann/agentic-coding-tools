# Design: add-two-level-parallel-development

## Context

The agentic-coding-tools project provides a structured feature development workflow using OpenSpec-driven skills. The current workflow executes features sequentially through lifecycle phases. Within a feature, parallelism exists at two tactical levels: Task(Explore) agents for context gathering and Task(Bash) agents for quality checks. Implementation tasks can optionally run in parallel when they have non-overlapping file scopes. Across features, the coordinator provides file-level locking and a work queue with `depends_on` support, but no higher-level coordination of which features can safely run concurrently.

When AI agents produce working code in minutes instead of days, the cost structure inverts. The dominant costs become ideation, specification, evaluation, and integration. This is a phase transition in what constrains velocity.

## Goals / Non-Goals

### Goals

1. Enable multiple features to be developed in parallel by different orchestrator agents, with the coordinator managing resource claims, conflict detection, and merge ordering.
2. Enable a single feature's implementation to be decomposed into agent-scoped work packages that execute in parallel across worktrees, coordinated by a dependency DAG.
3. Introduce contract-first development so that agents working on different architectural boundaries work independently against shared interface definitions.
4. Shift validation left so that quality checks run continuously during implementation.
5. Separate the workflow into two skill families — `linear-*` (preserved) and `parallel-*` (new) — so that both coexist.
6. Decouple review from building by restructuring iteration skills into independent review agents, enabling vendor-diverse evaluation.
7. Accomplish all of the above incrementally, backwards-compatible with the current skill set.

### Non-Goals

- Replacing human approval gates at plan approval and PR review.
- Building a general-purpose multi-agent orchestration framework.
- Automating product ideation or specification writing.

## Decisions

### 1. Two-level coordination model

Cross-feature coordination operates at the program level: the coordinator acts as a program manager, validating resource claims do not conflict with in-flight features, extracting shared contracts, assigning merge priority, and managing a merge queue. Intra-feature coordination operates at the team level: each feature's orchestrator decomposes implementation into work packages grouped by architectural boundary, validates non-overlapping file scopes and lock claims, computes a dependency DAG, and dispatches parallel agents per work package in separate worktrees.

Rationale:
- Mirrors organizational design (program manager + tech lead) adapted for AI agents.
- Cross-feature conflicts are rare but expensive; intra-feature decomposition is frequent and mechanizable.

### 2. Contract-first development with OpenAPI as canonical artifact

Before any implementation agent starts, a contracts phase produces machine-readable interface definitions: OpenAPI specs as the canonical contract, language-specific type generation (Pydantic for Python, TypeScript interfaces for frontend), SQL schema definitions, event schemas (JSON Schema), and executable mocks (Prism-generated API stubs).

Rationale:
- OpenAPI is language-neutral, tooling-rich, and already industry-standard.
- Pydantic as canonical contract was rejected because it couples to Python.
- Contracts are the only shared artifact between agents — this enforces communication through contracts, not shared code.

### 3. Three-layer contract compliance verification

Layer 1: Static type checking of generated types against implementation. Layer 2: Schemathesis property-based testing against the OpenAPI spec. Layer 3: Pact consumer-driven contract tests ensuring the provider satisfies actual consumer needs.

Rationale:
- Static types catch structural drift cheaply and fast.
- Schemathesis catches behavioral violations that types miss.
- Pact ensures real consumer expectations are met, not just schema compliance.

### 4. Contract revision as sole rescheduling trigger

Any contract file modification after implementation dispatch bumps `contracts.revision` in `work-packages.yaml`. Compatibility semantics (additive/breaking) may be recorded as metadata, but the revision number is the sole trigger for rescheduling.

Rationale:
- Avoids the trap of "additive but behaviorally meaningful" changes silently invalidating downstream work.
- Single, unambiguous trigger simplifies orchestrator logic.

### 5. Work packages as versioned execution contracts

`work-packages.yaml` is a validated artifact (against `work-packages.schema.json`) that groups tasks into agent-scoped packages with explicit file scope (write/read/deny globs), explicit resource claims (file locks + logical lock keys), dependency DAG, verification steps, and retry budget.

Rationale:
- Makes decomposition machine-auditable, not conversational.
- Scope and lock declarations enable deterministic conflict detection at plan time.
- DAG scheduling enables maximum parallelism with correctness guarantees.

### 6. Scope enforcement as deterministic diff check, not guardrails

Scope compliance runs `git diff --name-only` and matches each modified file against the package's `scope.write_allow` and `scope.deny` globs. This is a post-hoc deterministic check, not a pre-hoc sandbox. `check_guardrails` remains as defense-in-depth but does not enforce per-package scopes.

Rationale:
- Guardrails is regex/pattern matching over operation_text — it cannot evaluate per-package file allowlists.
- Deterministic diff check is simple, auditable, and unforgeable.

### 7. Logical lock keys using existing file_locks table

Logical resource locks (`api:GET /v1/users`, `db:schema:users`, `event:user.created`) are stored in the same `file_locks.file_path` TEXT column as file locks, with namespace prefixes for disambiguation. The coordinator treats the string as an opaque resource key.

Rationale:
- No new tables or tools required — existing `acquire_lock`/`release_lock`/`check_locks` work unchanged.
- Namespace prefixes are self-documenting and policy-evaluable.

### 8. Pause-lock mechanism for stop-the-line coordination

The orchestrator acquires `feature:<feature_id>:pause` as a lock key to signal all workers to stop. Workers check for this lock at two points: before starting work (B2) and before finalizing results (B9).

Rationale:
- Uses existing lock infrastructure — no new primitives needed.
- Two-point check ensures workers don't start against stale contracts and don't finalize stale results.

### 9. Escalation as structured payload in work queue

Escalations are dual-written: embedded in the failing package's `result.escalations[]` and submitted as an independent `task_type: "escalation"` work-queue task with priority=1. The orchestrator follows a deterministic decision procedure per escalation type.

Rationale:
- Dual-write ensures escalation is both traceable to origin and independently triageable.
- Priority=1 ensures escalations are processed before normal work.
- Deterministic procedures prevent conversational drift in escalation handling.

### 10. Retry at scheduler level, not queue level

The coordinator's `max_attempts` and `attempt_count` fields exist but `claim_task` does not consult them. Retry means the orchestrator submits a new task for the same `package_id` with `attempt = previous + 1`. Failed tasks remain failed; a new task is created for the retry.

Rationale:
- Aligns with how the coordinator actually works today.
- Orchestrator-level retry gives full control over retry context (updated contracts, narrowed scope).

### 11. Review agents as independent, vendor-agnostic evaluators

`/parallel-review-plan` and `/parallel-review-implementation` receive artifacts as read-only input and produce a findings table as output. They do not modify artifacts directly and can be dispatched to different AI vendors than the implementing agent.

Rationale:
- Separates build from evaluation, enabling diverse perspectives.
- Structured findings table (fix/regenerate/accept/escalate) makes dispositions actionable.

### 12. Verification tiers with no silent downgrade

Tier A (local full tooling), Tier B (CI pipeline), Tier C (static only). Each work package specifies `verification.tier_required`. The orchestrator MUST NOT silently downgrade — if an agent cannot satisfy the tier, it escalates with `VERIFICATION_INFEASIBLE`.

Rationale:
- Prevents "it compiled" from substituting for "it passed integration tests."
- Explicit tier requirement makes verification expectations machine-auditable.

### 13. Dual skill families with coexistence

Existing skills are renamed to `linear-*` with backward-compatible aliases. New `parallel-*` skills are added alongside. Both families share the same OpenSpec artifact structure.

Rationale:
- Preserves the working sequential workflow while the parallel model matures.
- Single skill family with flags was rejected due to conditional complexity in skill definitions.

## Alternatives Considered

### A. Full rebuild around DAG engine
Rejected: breaks the skill model that the entire workflow is built on.

### B. Agent-per-file granularity
Rejected: too much coordination overhead for the typical feature size.

### C. Optimistic concurrency (write freely, merge later)
Rejected: AI merge conflicts are expensive to resolve correctly.

### D. Review embedded in build skills
Rejected: prevents vendor diversity and couples review to implementation context.

### E. Single skill family with mode flags
Rejected: conditional complexity in skill definitions; harder to reason about behavior.

### F. Pydantic as canonical contract
Rejected: couples contract format to Python; OpenAPI is language-neutral.

## Risks / Trade-offs

- **Decomposition overhead for small features**: Work package planning adds overhead.
  Mitigation: Optional; features with fewer than 3 tasks fall back to sequential execution.

- **Contract drift during implementation**: Contracts may become stale as agents discover requirements.
  Mitigation: Three-layer verification (types + Schemathesis + Pact) plus contract revision bump procedure.

- **Semantic conflicts with non-overlapping files**: Two packages may not touch the same files but produce logically incompatible changes.
  Mitigation: Logical lock keys capture semantic resources; `wp-integration` runs the full test suite.

- **Feature registry as single point of failure**: Cross-feature coordination depends on coordinator availability.
  Mitigation: Coordinator is optional; degraded mode uses git-level conflict detection.

- **Integration bugs from worktree merge**: Independent worktree development may produce merge conflicts.
  Mitigation: `wp-integration` is a first-class work package with its own verification steps.

- **Orchestrator context exhaustion**: Broadcasting full feature context to every agent degrades reasoning.
  Mitigation: Information hiding via context slicing; agents receive only their work package definition + dependency results.

- **Test flakiness from parallelism**: Parallel test execution may produce port conflicts or fixture collisions.
  Mitigation: `allocate_ports` coordinator primitive + `FLAKY_TEST_QUARANTINE_REQUEST` escalation type.

- **Merge queue cascading failures**: Failed pre-merge checks may block the queue.
  Mitigation: Pre-merge checks + pause lock mechanism for coordinated stops.

## Migration Plan

1. Rename existing skills to `linear-*` with aliases. No behavior change.
2. Add contract and work-package artifact types to `schema.yaml`.
3. Implement work-packages DAG validation and coordinator deltas (A, B, C).
4. Build `parallel-plan-feature` and `parallel-explore-feature`.
5. Build review skills (parallel with steps 4 and 6).
6. Build `parallel-implement-feature` with DAG dispatch.
7. Add feature registry for cross-feature coordination.
8. Add merge queue and `parallel-cleanup-feature`.
9. Build `parallel-validate-feature`.

Rollback:
- Remove `parallel-*` skills and restore `linear-*` names to originals.
- Coordinator deltas are additive and do not affect existing behavior.
- Contract artifacts and work-packages.yaml are per-feature and self-contained.
