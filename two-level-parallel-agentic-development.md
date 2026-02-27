# Two-Level Parallel Agentic Development

## Part 1: Proposal

### Context

The agentic-coding-tools project provides a structured feature development workflow using OpenSpec-driven skills (`/explore-feature` → `/plan-feature` → `/implement-feature` → `/validate-feature` → `/cleanup-feature`). The workflow includes human approval gates, coordinator integration for multi-agent collaboration (file locking, work queues, handoffs, memory, guardrails), architecture analysis tooling, and git worktree isolation for parallel development.

The current workflow executes features sequentially through lifecycle phases. Within a feature, parallelism exists at two tactical levels: Task(Explore) agents for context gathering and Task(Bash) agents for quality checks. Implementation tasks can optionally run in parallel when they have non-overlapping file scopes. Across features, the coordinator provides file-level locking and a work queue with `depends_on` support, but no higher-level coordination of which features can safely run concurrently.

This proposal evolves the workflow to support two explicit levels of parallelism — cross-feature and intra-feature — drawing on organizational design principles adapted for an environment where AI has shifted the development bottleneck from code production to ideation, specification, and evaluation. A new `parallel-*` skill family is introduced alongside the existing skills (renamed to `linear-*`), enabling both workflows to coexist while the parallel model matures.

### Problem Analysis

#### The Bottleneck Shift

When AI agents produce working code in minutes instead of days, the cost structure inverts. Code synthesis drops from the dominant cost to a minor one. The dominant costs become ideation (knowing what to build), specification (expressing intent precisely), evaluation (determining correctness), and integration (proving independently-produced components work together). This is a phase transition in what constrains velocity.

Four consequences for the agentic-coding-tools workflow:

**Sequential phase structure becomes the primary bottleneck.** The current workflow is a linked list: explore → plan → approve → implement → approve → validate → cleanup. When implementation takes minutes, gate latency and phase transition overhead dominate wall-clock time. Two features that could be built in parallel are serialized because there is no mechanism to coordinate their resource claims.

**Single-agent-per-skill underutilizes available parallelism.** `/implement-feature` dispatches one agent that works through tasks sequentially. If a feature touches the API layer, a React component, and a database migration, three agents working in parallel on separate worktrees — each specialized for its architectural boundary — would complete faster and produce more focused code.

**Monolithic validation discovers problems too late.** `/validate-feature` runs 8 sequential phases only after all implementation is complete. Many checks (linting, type checking, contract compliance, architecture validation) could run continuously during implementation, catching problems within minutes of their introduction.

**Context windows become a strictly managed resource.** Broadcasting the entire feature context to every agent exhausts context limits and degrades reasoning quality. Context must be treated as a computational constraint requiring information hiding and state condensation.

#### Design Principles

Principles that drive design decisions:

- **Inverse Conway Maneuver**: Agents organized by architectural boundary (backend, frontend, contracts), not lifecycle phase.
- **Two-Pizza Team Autonomy / API Mandate**: Each agent completes its work, runs its own tests, declares "done" without mid-execution synchronization. Communication through contracts, not shared code.
- **Mission Command (Auftragstaktik)**: Agents receive intent-level specs, not step-by-step plans. Highest leverage is specification fidelity.
- **OODA Loops**: Minimize approval gates and maximize evaluation cycles per day.
- **Regenerate Over Repair**: When iteration finds multiple interrelated issues, improve the spec and regenerate rather than patching.
- **Deterministic Automation Over Conversational Coordination**: Schemas, explicit state machines, deterministic checks, and auditable operations replace freeform handoffs or memory-based coordination.

Principles that lose relevance: sprint planning/story points, code review as primary quality gate, code-level DRY (contract-level DRY remains important), Conway's Law optimization (architecture is more fluid but not free).

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

---

## Part 2: Design

### 2.1 Two-Level Coordination Model

**Cross-Feature Coordination (Program Level).** The coordinator acts as a program manager. Before any feature enters implementation, it registers resource claims (files, API routes, DB migrations, events) in a feature registry. The coordinator validates claims do not conflict with in-flight features, extracts shared contracts, assigns merge priority, and manages a merge queue.

**Intra-Feature Coordination (Team Level).** Each feature's orchestrator acts as a tech lead. During planning, it decomposes the feature into work packages grouped by architectural boundary, validates packages have non-overlapping file scopes and non-conflicting logical resource claims, and computes a dependency DAG. During implementation, it dispatches parallel agents per work package (each in its own worktree), monitors progress, and merges worktrees when all packages complete.

### 2.2 Contract-First Development

Before any implementation agent starts, a contracts phase produces machine-readable interface definitions:

- **OpenAPI specs** as the canonical contract artifact for API endpoints
- **Language-specific type generation** from OpenAPI: Pydantic models for Python, TypeScript interfaces for frontend
- **SQL schema definitions** for new database tables
- **Event schemas** (JSON Schema) for async communication
- **Executable mocks**: Prism-generated API stubs from the OpenAPI spec

Contracts are the only shared artifact between agents within a feature. Implementation agents code against contracts and mocks, not against each other's code.

**Contract compliance verification** uses three layers: (1) static type checking of generated types against implementation, (2) Schemathesis property-based testing against the OpenAPI spec, (3) Pact consumer-driven contract tests ensuring the provider satisfies actual consumer needs.

The `contracts` section of `work-packages.yaml` (see §3.1) declares the canonical OpenAPI files, generated output directories, mock configuration, and CDC (consumer-driven contract) settings. Every work package declares which `contracts_revision` it consumes — the orchestrator rejects results whose `contracts_revision` does not match the current `work-packages.yaml` value.

#### Contract Revision Semantics

Contracts are frozen per revision during a work-package execution wave. The revision model uses a single strict rule:

> **Any contract file modification after implementation dispatch ⇒ bump `contracts.revision` in `work-packages.yaml`.**

Compatibility semantics (additive/breaking) may be recorded as metadata, but the revision number is the sole trigger for rescheduling. This avoids the trap of "additive but behaviorally meaningful" changes silently invalidating downstream work.

The concrete **Contract Revision Bump Procedure** is specified in §2.6 (Escalation Protocol) because it is triggered by escalations and uses the same pause-lock coordination mechanism.

### 2.3 Work Packages and DAG Scheduling

The design introduces `work-packages.yaml` as a versioned, validated execution contract that groups tasks into agent-scoped packages with deterministic scheduling semantics. The full JSON Schema is in §3.1.

#### Coordinator Mapping

Each `packages[]` entry in `work-packages.yaml` maps to coordinator primitives as follows:

| work-packages.yaml field | Coordinator primitive | Notes |
|--------------------------|----------------------|-------|
| `package_id` | Tracked by orchestrator | Not a coordinator field; orchestrator maps `package_id → task_id` |
| `task_type` | `submit_work(task_type=...)` | 1:1 mapping to `work_queue.task_type` |
| `description` | `submit_work(description=...)` | 1:1 mapping to `work_queue.description` |
| `priority` | `submit_work(priority=...)` | 1:1 mapping; 1=highest, 10=lowest |
| `depends_on` | `submit_work(depends_on=[task_ids])` | Orchestrator resolves `package_id → task_id` list |
| `locks.files[]` | `acquire_lock(file_path=<raw_path>)` | Raw file paths — existing lock behavior |
| `locks.keys[]` | `acquire_lock(file_path=<prefixed_key>)` | Logical locks stored in same `file_locks.file_path` column |
| `inputs` | `submit_work(input_data={...})` | Arbitrary JSON merged with orchestrator envelope |
| `outputs.result_keys[]` | Validated against `work_queue.result` keys | Orchestrator enforces after `complete_work` |
| Package completion | `complete_work(task_id, success, result, error_message)` | Result payload per §3.2 |

#### Locks: Files vs Logical Keys

The `Locks` object in §3.1 separates file locks from logical resource locks for clarity and backward compatibility:

```yaml
locks:
  files:
    - src/api/users.py        # Raw file path → acquire_lock(file_path="src/api/users.py")
    - src/api/routes.py
  keys:
    - "api:GET /v1/users"     # Logical lock → acquire_lock(file_path="api:GET /v1/users")
    - "db:schema:users"
  ttl_minutes: 120
  reason: "Backend API implementation for user endpoints"
```

Both types are stored in the same `file_locks.file_path` TEXT column. The coordinator treats the string as a policy "resource" without path semantics — existing `acquire_lock`/`release_lock`/`check_locks` tools work unchanged.

**Canonicalization rules** (enforced at `work-packages.yaml` validation time):

| Prefix | Format | Normalization Rule | Example |
|--------|--------|--------------------|---------|
| (none — raw file path) | Repo-relative path | No leading slash, no trailing whitespace | `src/api/users.py` |
| `api:` | `api:<METHOD> <PATH>` | Method uppercase, single space, path normalized | `api:GET /v1/users` |
| `db:migration-slot` | literal | Only one migration package at a time | `db:migration-slot` |
| `db:schema:` | `db:schema:<table>` | Lowercase identifiers | `db:schema:users` |
| `event:` | `event:<channel>` | Dot-separated, lowercase | `event:user.created` |
| `flag:` | `flag:<namespace>` | Slash-delimited, lowercase | `flag:billing/*` |
| `env:` | `env:<resource>` | For non-port shared resources only | `env:shared-fixtures` |
| `contract:` | `contract:<path>` | Contract artifact lock | `contract:openapi/v1.yaml` |
| `feature:` | `feature:<id>:<purpose>` | Feature-level coordination lock | `feature:FEAT-123:pause` |

**Port allocation** uses `allocate_ports(session_id)` (coordinator primitive with TTL refresh), NOT `env:` lock keys. `env:` keys are reserved for non-port shared resources (test fixtures, shared tmp dirs).

**Policy implications**: Cedar/native policies must allow `api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, and `feature:` resource patterns in `acquire_lock`, or agents receive `operation_not_permitted` failures.

#### Scope: Write/Read/Deny Globs

Each work package declares its file access scope using glob patterns (§3.1 `Scope` definition):

```yaml
scope:
  write_allow:
    - "src/api/users.py"
    - "src/api/routes.py"
    - "tests/api/test_users.py"
  read_allow:
    - "src/api/**"
    - "contracts/**"
    - "src/models/**"
  deny:
    - "src/api/auth.py"       # Even though it matches read_allow glob
```

- `write_allow`: Globs the agent may modify. Empty means read-only package.
- `read_allow`: Globs the agent may read/scan for context.
- `deny`: Globs explicitly forbidden even if matched by allow lists.

The scope is echoed back in the result payload (§3.2 `scope` field) so the orchestrator can verify `files_modified ⊆ write_allow \ deny` deterministically.

#### Work Package State Machine

Each package follows explicit state transitions mapped to `work_queue.status` values:

```
PLANNED → QUEUED → CLAIMED → RUNNING → COMPLETED
                                     → FAILED → (dependents CANCELLED)
                              → CANCELLED (by orchestrator)
```

**Mapping to current coordinator primitives** (see §2.8 for gaps):

| Logical State | Coordinator Primitive | Notes |
|---------------|----------------------|-------|
| PLANNED | Not in queue yet | Exists only in `work-packages.yaml` |
| QUEUED | `submit_work()` → status=`pending` | Task created in work queue |
| CLAIMED | `get_work()` → status=`claimed` | Treat `claimed ≈ RUNNING` until `start_task` RPC exists |
| RUNNING | No distinct primitive yet | Use `claimed` + heartbeat presence as proxy |
| COMPLETED | `complete_work(success=true)` → status=`completed` | |
| FAILED | `complete_work(success=false)` → status=`failed` | |
| CANCELLED | `complete_work(success=false, result={"error_code": "cancelled_by_orchestrator"})` | Until `cancel_task` RPC exists |

#### Hard Invariants

These are enforced deterministically, not as guidelines:

1. Every work package has explicit file scope (`scope.write_allow`) AND explicit resource claims (`locks.files` + `locks.keys`). Omitting either is a validation error in `work-packages.schema.json`.
2. Any write outside declared scope fails the package. This is a **deterministic diff check** (see §2.5), not guardrails.
3. Every package must produce machine-checkable evidence that its verification steps passed. The result payload (§3.2) is validated against `work-queue-result.schema.json` — missing required keys cause the orchestrator to treat the package as failed.
4. Package outputs are structured JSON in `work_queue.result`, queryable by the orchestrator via `get_task(task_id)`.
5. Integration merge is a first-class work package (`wp-integration`) with its own lock claims and verification steps.
6. No dependent package runs if its dependency is FAILED or CANCELLED. Cancellation propagates automatically.

### 2.4 Execution Protocol

This is the precise procedural sequence. The orchestrator and every worker agent MUST execute these steps in order.

#### Phase A: Feature-Level Preflight (Orchestrator)

```
A1. Parse and validate work-packages.yaml
    ├─ YAML → JSON parse
    ├─ Validate against work-packages.schema.json (§3.1)
    ├─ Lock key canonicalization check (all keys match normalization rules from §2.3)
    ├─ File scope non-overlap: for any two packages P1, P2 that can run in parallel,
    │   P1.scope.write_allow ∩ P2.scope.write_allow == ∅ (except wp-integration)
    └─ Logical lock non-overlap: for parallel packages,
        P1.locks.keys ∩ P2.locks.keys == ∅

A2. Validate contracts exist
    ├─ Every file in contracts.openapi.files exists on disk
    ├─ Primary OpenAPI file parses without errors
    └─ If contracts.mocks.prism.enabled: verify Prism can start against the spec

A3. Compute DAG order
    ├─ Build directed graph from packages[].depends_on
    ├─ Detect cycles → validation error if found
    └─ Topological sort → execution order

A4. Submit work queue tasks
    For each package in topological order:
    ├─ Resolve depends_on package_ids → task_ids (from previously submitted packages)
    ├─ Build input_data envelope:
    │   {
    │     "feature_id": feature.id,
    │     "package_id": package.package_id,
    │     "plan_revision": feature.plan_revision,
    │     "contracts_revision": contracts.revision,
    │     "locks": package.locks,           // echoed so worker knows what to acquire
    │     "scope": package.scope,           // echoed so worker knows its boundaries
    │     "verification": package.verification,
    │     "worktree": package.worktree,
    │     "context_slice": { ... },         // assembled by orchestrator
    │     ...package.inputs                 // merged in
    │   }
    ├─ submit_work(
    │     task_type = package.task_type,
    │     description = package.description,
    │     input_data = <envelope above>,
    │     priority = package.priority,
    │     depends_on = [resolved_task_ids]
    │   )
    └─ Record mapping: package_id → task_id

A5. Begin monitoring loop
    ├─ Poll discover_agents() for agent health
    ├─ Poll get_task(task_id) for each in-flight package
    └─ On each completion: check if new packages are unblocked → dispatch
```

#### Phase B: Package Execution Protocol (Every Worker Agent)

When an agent claims a package via `get_work`, it MUST execute these steps in this order:

```
B1. Session + liveness
    ├─ register_session(feature_id, package_id, contracts_revision, capability_profile)
    └─ Begin periodic heartbeat (every 30s)

B2. Pause-lock check
    ├─ check_locks(file_paths=["feature:<feature_id>:pause"])
    └─ If pause lock exists AND not owned by this agent:
        → Do not proceed. Wait/poll until released, or exit with error_code="PAUSED"
    This prevents agents from working against stale contracts during an escalation.

B3. Lock acquisition (deadlock-safe)
    ├─ Merge locks.files + locks.keys into a single list
    ├─ Sort in LEXICOGRAPHIC ORDER (canonical ordering prevents deadlocks)
    ├─ For each lock key in sorted order:
    │   ├─ acquire_lock(file_path=<key>, session_id, ttl=locks.ttl_minutes)
    │   └─ On failure:
    │       ├─ Release ALL already-acquired locks (reverse order)
    │       ├─ Backoff (exponential, max 3 retries, jitter)
    │       └─ If all retries exhausted: FAIL with error_code="LOCK_UNAVAILABLE"
    └─ All locks acquired → proceed

B4. Environment allocation
    ├─ If package needs local compose stack / ports:
    │   ├─ allocate_ports(session_id)  ← coordinator primitive, NOT env: locks
    │   └─ Configure environment from returned port snippet
    └─ If no ports needed: skip

B5. Read dependency results
    For each dependency task_id (from input_data resolution):
    ├─ get_task(dependency_task_id)  ← requires Delta A (§2.8)
    ├─ Parse result JSON
    └─ Extract relevant outputs for this package's context

B6. Code generation
    ├─ Create or switch to package's worktree (per worktree.name and worktree.mode)
    ├─ Make changes ONLY within scope.write_allow, respecting scope.deny
    └─ Commit changes with structured commit message including package_id

B7. Deterministic scope check
    ├─ modified_files = git diff --name-only <merge_base>
    ├─ For each file in modified_files:
    │   ├─ Check: matches at least one glob in scope.write_allow
    │   └─ Check: does NOT match any glob in scope.deny
    ├─ out_of_scope = files failing either check
    └─ If out_of_scope is non-empty:
        → FAIL with error_code="SCOPE_VIOLATION"
        → Include scope_check.violations in result payload

    NOTE: This is a DETERMINISTIC DIFF CHECK, not guardrails.
    check_guardrails remains as defense-in-depth against destructive commands
    but does NOT enforce per-package scopes (it is regex/pattern matching
    over operation_text, not a per-package allowlist evaluator).

B8. Verification (done_when sequence)
    For each step in verification.steps (in order):
    ├─ If step.kind == "command":
    │   ├─ Run step.command with step.env, in step.cwd
    │   ├─ Capture: exit_code, duration, artifact paths from step.evidence.artifacts
    │   └─ Compare exit_code to step.expect_exit_code
    ├─ If step.kind == "ci":
    │   ├─ Push branch, trigger CI workflow per step.ci config
    │   └─ Poll for step.ci.required_checks completion
    ├─ If step.kind == "manual":
    │   └─ Record manual_instructions; flag for human
    ├─ Build VerificationStepResult (§3.2) for this step
    │   ├─ Populate evidence.artifacts with actual paths produced
    │   └─ Populate evidence.metrics with duration_seconds, test_count, etc.
    └─ On any step failure: FAIL FAST
        → Do not continue to subsequent steps
        → Include which step failed and why in result

B9. Pause-lock re-check (before finalizing)
    ├─ check_locks(file_paths=["feature:<feature_id>:pause"])
    └─ If pause lock appeared during execution:
        → Treat result as stale; do not complete_work
        → Wait for pause release, then re-verify (or fail)

B10. Publish structured result
    Build result payload per work-queue-result.schema.json (§3.2):
    ├─ Echo: feature_id, package_id, plan_revision, contracts_revision
    ├─ Echo: locks {files, keys} actually held
    ├─ Echo: scope {write_allow, read_allow, deny}
    ├─ Include: files_modified (from git diff), scope_check {passed, violations}
    ├─ Include: git {base.ref, head.commit, head.branch, head.worktree}
    ├─ Include: verification {tier, passed, steps[]}
    ├─ Include: contract_checks (if applicable: openapi_validation, schemathesis, pact)
    ├─ Include: resources.ports (if allocate_ports was used)
    ├─ Include: escalations[] (empty if none)
    └─ complete_work(task_id, success=<verification.passed>, result=<payload>,
         error_message=<short summary if failed>)

B11. Cleanup
    ├─ Release ports (if allocated)
    ├─ Release ALL locks (reverse of acquisition order)
    └─ Stop session / heartbeat
```

#### Phase C: Review + Integration Sequencing

After individual packages complete, the orchestrator follows this sequence:

```
C1. Result validation (on each package completion)
    ├─ Fetch result via get_task(task_id)
    ├─ Validate result against work-queue-result.schema.json (§3.2)
    ├─ Verify result.contracts_revision == current work-packages.yaml contracts.revision
    │   → If mismatch: treat as stale, ignore result
    ├─ Verify result.plan_revision == current work-packages.yaml feature.plan_revision
    │   → If mismatch: treat as stale, ignore result
    ├─ Verify all outputs.result_keys are present in result
    └─ If validation fails: treat as package failure, apply retry_budget

C2. Escalation processing
    ├─ If result.escalations is non-empty:
    │   └─ Execute Escalation Protocol (§2.6)
    └─ If any escalation is severity=BLOCKING:
        → Acquire pause lock via feature:<id>:pause

C3. Per-package review (for each successfully completed package)
    ├─ Dispatch /parallel-review-implementation on that package's diff
    ├─ Review produces findings table (§3.3)
    └─ If findings contain fixable issues:
        └─ Dispatch wp-fix-<package_id> package (inherits same locks + scope)

C4. Integration gate
    ├─ Wait until ALL packages are COMPLETED and reviewed
    └─ If any package is FAILED or CANCELLED: halt, emit escalation

C5. Integration merge (wp-integration package)
    ├─ Claims ALL file locks from all packages (union of all locks.files)
    ├─ Merges all worktrees into feature branch
    ├─ Runs full test suite (wp-integration verification.steps)
    ├─ Runs cross-package contract verification (Schemathesis, Pact)
    └─ This is the ONLY place expensive end-to-end checks run

C6. Execution summary generation
    ├─ Query coordinator audit trail: query_audit(feature_id=...)
    ├─ Generate execution-summary.md with:
    │   ├─ DAG execution timeline (from task timestamps)
    │   ├─ Contract compliance results (from contract_checks in each result)
    │   ├─ Review findings applied
    │   ├─ Changed logical resources (union of all locks.keys across packages)
    │   ├─ Risk classification (auto-high if migrations or public API changes)
    │   └─ Behavioral checklist for human review
    └─ Attach to PR
```

### 2.5 Scope Enforcement Clarification

**Scope compliance** is a **deterministic diff check** (step B7 in the Execution Protocol). It runs `git diff --name-only` and matches each modified file against the package's `scope.write_allow` globs (positive match required) and `scope.deny` globs (negative match required).

**Guardrails** (`check_guardrails`) remains available as **defense-in-depth** against destructive commands and dangerous output patterns. The guardrails engine is regex/pattern matching over an `operation_text` string. It is NOT a per-package allowlist evaluator.

The scope is echoed in the result payload (`result.scope` and `result.scope_check`) so both the worker's self-check and the orchestrator's validation use identical data.

### 2.6 Escalation Protocol

**Purpose.** Escalations adapt the plan or contracts safely when a work package discovers it cannot complete correctly under current constraints. Escalations are deterministic, machine-readable, and visible in existing coordinator primitives (work queue + locks).

#### Escalation Payload (Wire Format)

All escalations use the `Escalation` object defined in §3.2, embedded in both:

1. The failing package's `work_queue.result.escalations[]` array
2. An explicit `task_type: "escalation"` work-queue task submitted via `submit_work(task_type="escalation", priority=1, ...)` so it appears in `work://pending`

This dual-write ensures the escalation is both associated with the originating package and visible as an independent queue item for orchestrator triage.

**Example escalation payload:**

```json
{
  "escalation_id": "esc-2026-02-27T13:04:05Z-001",
  "feature_id": "FEAT-123",
  "package_id": "wp-backend",
  "type": "CONTRACT_REVISION_REQUIRED",
  "severity": "BLOCKING",
  "summary": "OpenAPI contract missing required error response schema for 409",
  "detected_at": "2026-02-27T13:04:05Z",
  "evidence": {
    "files": ["contracts/openapi/v1.yaml", "src/api/users.py"],
    "logs": ["artifacts/wp-backend/schemathesis.txt"]
  },
  "impact": {
    "contract_revision_bump_required": true,
    "impacted_packages": ["wp-frontend", "wp-integration"],
    "logical_locks": ["api:POST /v1/users"]
  },
  "proposed_action": "Bump contracts.revision, regenerate types+mocks, resubmit impacted packages",
  "requires_human": false
}
```

#### Agent Obligations (Any Work-Package Executor)

When a package hits a condition it cannot safely resolve locally, the agent MUST:

```
1. STOP making forward progress
   (do not continue implementing against an invalid contract or missing invariant)

2. Signal escalation visibly via the work queue:
   a. Submit escalation task:
      submit_work(
        task_type = "escalation",
        priority = 1,                    // highest priority
        description = <short summary>,
        input_data = <escalation payload>
      )
   b. Complete current package task as failed:
      complete_work(
        task_id,
        success = false,
        error_message = <short, human-scannable>,
        result = {
          ...standard result fields per §3.2...,
          "escalations": [<escalation payload>]
        }
      )

Note: error_message should be short and human-scannable.
The structured payload lives in result.escalations[].
For NON_BLOCKING issues (warnings), the agent may complete successfully
but still include result.escalations[] with severity="NON_BLOCKING".
```

#### Escalation Types

| Type | Trigger | Default Severity |
|------|---------|-----------------|
| `CONTRACT_REVISION_REQUIRED` | Agent discovers contract is wrong during implementation | BLOCKING |
| `PLAN_REVISION_REQUIRED` | New tasks needed or DAG structure must change | BLOCKING |
| `RESOURCE_CONFLICT` | Cannot acquire required lock; another feature holds it | HIGH |
| `VERIFICATION_INFEASIBLE` | Agent cannot satisfy required verification tier | HIGH |
| `SCOPE_VIOLATION` | Agent modified files outside declared scope | BLOCKING |
| `ENV_RESOURCE_CONFLICT` | Port/fixture collision despite allocate_ports | MEDIUM |
| `SECURITY_ESCALATION` | Security-sensitive issue discovered | BLOCKING |
| `FLAKY_TEST_QUARANTINE_REQUEST` | Test fails intermittently, not a code issue | NON_BLOCKING |

#### Stop-the-Line Mechanism (Using Existing Locks)

The orchestrator uses a **pause lock** to coordinate feature-wide stops:

```
Acquire pause lock:
  acquire_lock(
    file_path = "feature:<feature_id>:pause",
    reason = "handling escalation <escalation_id>",
    ttl_minutes = 120
  )
```

All package executors check for this lock at two points (steps B2 and B9):
- **At start** (B2): before proceeding with implementation
- **Before finalizing** (B9): before calling `complete_work`

If the pause lock exists and is not owned by the executor, the executor stops. This provides a coordinator-native coordination signal without new tables or tools.

#### Orchestrator Decision Procedure (Deterministic)

```
SCOPE_VIOLATION (severity=BLOCKING):
  → Mark package FAILED
  → Require plan_revision bump OR dispatch narrow-scope wp-fix-<package_id>
  → NEVER auto-expand scope silently

VERIFICATION_INFEASIBLE (severity=HIGH):
  → If agent lacks required tier: reassign to Tier A/B capable agent
  → OR create follow-up wp-verify-<package_id>
  → Package CANNOT become COMPLETED without required evidence

CONTRACT_REVISION_REQUIRED (severity=BLOCKING):
  → Execute Contract Revision Bump Procedure (below)
  → If requires_human == true: wait for human approval before proceeding

PLAN_REVISION_REQUIRED (severity=BLOCKING):
  → Execute Plan Revision Bump Procedure (below)

RESOURCE_CONFLICT (severity=HIGH):
  → Same feature: scheduling error; reorder DAG
  → Different feature: defer until lock clears, or escalate to human

ENV_RESOURCE_CONFLICT (severity=MEDIUM):
  → Retry with fresh allocate_ports call
  → If retry fails: FAIL with structured reason

SECURITY_ESCALATION (severity=BLOCKING):
  → Pause DAG, emit escalation.md, require human decision

FLAKY_TEST_QUARANTINE_REQUEST (severity=NON_BLOCKING):
  → Record as quarantined in result evidence
  → wp-integration evaluates quarantined tests separately
  → Does NOT block package completion
```

#### Contract Revision Bump Procedure

When escalation type is `CONTRACT_REVISION_REQUIRED`:

```
1. Acquire pause lock:
   acquire_lock(file_path="feature:<id>:pause", reason="contract revision bump", ttl_minutes=120)

2. Acquire contract file locks (raw file paths, not prefixed):
   For each file in contracts.openapi.files:
     acquire_lock(file_path=<path>, reason="contract revision bump")
   Plus any other contract artifact paths that will be edited/regenerated.

3. Bump contract revision:
   ├─ Update work-packages.yaml: contracts.revision += 1
   ├─ Apply contract changes (fix the issue that triggered escalation)
   ├─ Regenerate derived artifacts (Pydantic types, TS interfaces, Prism mocks)
   └─ Commit all changes

4. Resubmit impacted packages:
   For each package where result.contracts_revision < new contracts.revision:
   ├─ Submit new work-queue task (same package_id, new coordinator task_id)
   ├─ input_data includes:
   │   ├─ feature_id, package_id
   │   ├─ plan_revision (current)
   │   └─ contracts_revision (new)
   └─ Update orchestrator's package_id → task_id mapping

   NOTE: Orchestrator MUST ignore/decline merging results from any task
   whose result.contracts_revision does not match current work-packages.yaml.

5. Release contract file locks

6. Release pause lock → agents resume
```

#### Plan Revision Bump Procedure

When escalation type is `PLAN_REVISION_REQUIRED`:

```
1. Acquire pause lock:
   acquire_lock(file_path="feature:<id>:pause", reason="plan revision bump", ttl_minutes=120)

2. Acquire plan artifact lock:
   acquire_lock(file_path="work-packages.yaml", reason="plan revision bump")

3. Update plan artifacts:
   ├─ Modify proposal.md, tasks.md, work-packages.yaml as needed
   └─ Increment feature.plan_revision

4. Determine which existing tasks are now invalid:
   ├─ Packages removed → invalidate
   ├─ Packages with modified scope → invalidate
   ├─ Packages with modified locks → invalidate
   ├─ Packages with modified verification → invalidate
   └─ Packages unchanged → preserve (results are reusable)

5. For each invalid package:
   ├─ Mark old task as cancelled:
   │   complete_work(success=false, result={
   │     "error_code": "cancelled_by_orchestrator",
   │     "reason": "plan_revision_bump",
   │     "new_plan_revision": N+1
   │   })
   └─ Submit new task for same package_id with updated input_data

6. Write orchestrator handoff (for resumability):
   write_handoff(summary={
     "old_plan_revision": N,
     "new_plan_revision": N+1,
     "task_mapping": { package_id → {old_task_id, new_task_id, reused: bool} },
     "reason": <escalation summary>
   })

7. Release plan artifact lock

8. Release pause lock → agents resume
```

### 2.7 Retry Semantics

The DB table has `max_attempts` and `attempt_count`, but `claim_task` does not consult `max_attempts`, and failed tasks don't re-enter the claimable pool.

**Retry is implemented at the scheduler level, not the queue level:**

- "Retry" means the orchestrator **submits a new task** for the same `package_id` with `attempt = previous + 1`
- The orchestrator tracks `(package_id, plan_revision, attempt)` as the unique execution identity
- Failed tasks remain failed in the queue; a new task is created for the retry
- `retry_budget` in `work-packages.yaml` controls how many resubmissions the orchestrator will attempt before escalating

### 2.8 Required Coordinator Deltas

These are small, concrete changes to the coordinator. All extend existing infrastructure.

#### Delta A: Work Queue Read API — `get_task(task_id)`

**Why**: Dependency payloads in `work_queue.result` are only useful if other agents can fetch them. Today MCP only exposes `get_work` (which claims) and `work://pending` (which doesn't include results).

**What exists**: `WorkQueueService.get_task(task_id)` exists in `work_queue.py` but is only used internally.

**Change**: Expose as MCP tool + HTTP endpoint. ~20 lines. See §3.4 for schema.

#### Delta B: Cancellation Convention

**Why**: Work package state machine requires CANCELLED as reachable state.

**Change**: Represent cancellation as `complete_work(success=false)` with `error_code="cancelled_by_orchestrator"` in result. Helper function wraps this pattern. No new RPC required.

**Future**: Add `cancel_task(task_id, reason)` RPC for better UX.

#### Delta C: Lock Key Policy Updates

**Why**: `api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:` lock keys need policy permission.

**Change**: Update policy rules to permit `^(api|db|event|flag|env|contract|feature):.+$` pattern. Raw file path resources continue to work unchanged.

### 2.9 Verification Tiers

| Tier | Runtime | Capabilities | Evidence |
|------|---------|-------------|----------|
| A (local) | CLI agent with full tooling | `pytest`, `mypy`, `ruff`, Schemathesis, Pact | Command output + exit codes + artifact paths |
| B (remote) | Agent triggers CI pipeline | Push branch, trigger CI, poll results | CI run_id + URL + required_checks status |
| C (degraded) | Static checks only | Syntax, formatting, basic type inference | Flags package for Tier A/B follow-up |

Each work package's `verification.tier_required` specifies the minimum. The orchestrator MUST NOT silently downgrade. If an agent cannot satisfy the required tier, it escalates with `VERIFICATION_INFEASIBLE`.

### 2.10 Context Management

The orchestrator assembles each agent's context from coordinator primitives:

1. **Work package definition** + contract artifacts (mandatory, highest priority)
2. **Dependency results**: `get_task(dependency_task_id).result` for each declared dependency
3. **Procedural memories**: Codebase-specific patterns via `recall()` (high value, low token cost)
4. **Episodic memories**: Task-relevant memories via `recall()` (opportunistic)

Session handoffs retain their purpose: preserving human-readable context when the orchestrator needs to be resumed.

### 2.11 Continuous Validation

Validation is redistributed from a monolithic post-implementation phase:

| Check | When | Where |
|-------|------|-------|
| Linting, type checking, unit tests | During implementation | Each package's `verification.steps` |
| Contract compliance (Schemathesis, Pact) | During implementation | Each package's `verification.steps` (Tier A min) |
| Scope compliance | After code generation | Deterministic diff check (B7) |
| Architecture validation | After merge to main | Platform agent responsibility |
| Security scanning | Unchanged | `/security-review` skill |
| Deploy + smoke + E2E | Post-integration | `/parallel-validate-feature` |

### 2.12 Review Agent Decoupling

`/parallel-review-plan` and `/parallel-review-implementation` are independent agents that:
- Receive artifacts as **read-only** input
- Produce a **findings table** as output (schema in §3.3)
- Do NOT modify any artifacts directly
- Can be dispatched to **different AI vendors** than the implementing agent
- Can run **concurrently** with downstream work

**Findings dispositions**: `fix` (orchestrator applies), `regenerate` (re-run with improved constraints), `accept` (acknowledged, not actionable), `escalate` (requires human decision).

### 2.13 Feature Registry and Cross-Feature Coordination

The coordinator maintains a feature registry. Each registered feature declares resource claims using the same lock key namespace. Conflict analysis produces a parallel feasibility assessment (`FULL`, `PARTIAL`, or `SEQUENTIAL`) and a recommended merge order. Cross-feature resource collisions are handled via the `RESOURCE_CONFLICT` escalation type (§2.6).

### 2.14 Skill Family Architecture

**`linear-*` skills**: Current workflow, renamed with prefix.

**`parallel-*` skills**: New workflow for multi-agent parallel execution. Degrades to linear-equivalent when coordinator unavailable.

**Capability mapping** for `/parallel-implement-feature`:
- REQUIRED (hard failure): `CAN_DISCOVER`, `CAN_QUEUE_WORK`, `CAN_LOCK`
- REQUIRED (safety): `CAN_GUARDRAILS`
- ENRICHING (degrades gracefully): `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_POLICY`, `CAN_AUDIT`

### 2.15 Formal Verification Strategy

**Phase 0: TLA+ Model Checking** — Lock acquisition/release/expiry, task claim/complete, dependency gating, pause-lock coordination, orchestrator rescheduling. Run TLC on bounded instances.

**Phase 1: Lean Safety Proofs** — DAG scheduler correctness, rescheduling rules, cancellation propagation. Prove: lock exclusivity, no double-claim, dependency safety, result immutability, cancellation propagation, pause-lock safety.

**Phase 2: Property-Based Testing** — Randomized operation sequences against real coordinator, compared to abstract model.

---

## Part 3: Specs

### 3.1 `work-packages.schema.json`

Location: `openspec/schemas/work-packages.schema.json`

Validate `work-packages.yaml` after YAML→JSON parsing. Each `packages[]` entry becomes one `work_queue` row via `submit_work`. Locks are acquired via `acquire_lock(file_path=...)` where `file_path` is either a raw file path or a prefixed logical key.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://agentic-coding-tools.dev/schemas/work-packages.schema.json",
  "title": "work-packages.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "feature", "contracts", "packages"],
  "properties": {
    "schema_version": {
      "type": "integer",
      "const": 1,
      "description": "Schema version for work-packages.yaml"
    },
    "feature": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "plan_revision"],
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128,
          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
          "description": "Stable feature identifier (used in input_data/result payloads)"
        },
        "title": { "type": "string", "minLength": 1, "maxLength": 200 },
        "plan_revision": {
          "type": "integer",
          "minimum": 1,
          "description": "Monotonic integer. Increment when plan/work-packages change materially."
        },
        "created_by": { "type": "string", "minLength": 1, "maxLength": 128 },
        "created_at": { "type": "string", "format": "date-time" }
      }
    },
    "contracts": {
      "type": "object",
      "additionalProperties": false,
      "required": ["revision", "openapi"],
      "properties": {
        "revision": {
          "type": "integer",
          "minimum": 1,
          "description": "Monotonic integer. Increment on contract changes after dispatch."
        },
        "openapi": {
          "type": "object",
          "additionalProperties": false,
          "required": ["primary", "files"],
          "properties": {
            "primary": { "$ref": "#/$defs/FilePath", "description": "Primary OpenAPI entrypoint file." },
            "files": {
              "type": "array",
              "minItems": 1,
              "items": { "$ref": "#/$defs/FilePath" },
              "uniqueItems": true,
              "description": "All OpenAPI files considered part of the canonical contract."
            }
          }
        },
        "generated": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "pydantic_dir": { "$ref": "#/$defs/FilePath" },
            "typescript_dir": { "$ref": "#/$defs/FilePath" }
          }
        },
        "mocks": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "prism": {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "enabled": { "type": "boolean", "default": true },
                "command": { "type": "string", "minLength": 1 },
                "base_url": { "type": "string", "minLength": 1 }
              }
            }
          }
        },
        "cdc": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "pact": {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "enabled": { "type": "boolean", "default": false },
                "broker_url": { "type": "string", "minLength": 1 },
                "consumer_dir": { "$ref": "#/$defs/FilePath" }
              }
            }
          }
        }
      }
    },
    "defaults": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "priority": { "type": "integer", "minimum": 1, "maximum": 10, "default": 5 },
        "lock_ttl_minutes": { "type": "integer", "minimum": 1, "maximum": 480, "default": 120 },
        "timeout_minutes": { "type": "integer", "minimum": 1, "default": 60 },
        "retry_budget": { "type": "integer", "minimum": 0, "default": 1 },
        "verification_tier_required": { "type": "string", "enum": ["A", "B", "C"], "default": "A" },
        "min_trust_level": { "type": "integer", "minimum": 0, "maximum": 4, "default": 2 }
      }
    },
    "packages": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/WorkPackage" }
    }
  },
  "$defs": {
    "FilePath": {
      "type": "string",
      "minLength": 1,
      "maxLength": 512,
      "pattern": "^(?!/)(?!.*\\s+$).+",
      "description": "Repo-relative path (no leading slash)."
    },
    "Glob": {
      "type": "string",
      "minLength": 1,
      "maxLength": 512,
      "description": "Glob pattern (e.g., 'src/api/**')."
    },
    "PackageId": {
      "type": "string",
      "minLength": 1,
      "maxLength": 64,
      "pattern": "^[a-z][a-z0-9_-]{0,63}$",
      "description": "Stable id used for DAG dependencies (e.g., 'wp-contracts', 'wp-backend')."
    },
    "LogicalLockKey": {
      "type": "string",
      "minLength": 1,
      "maxLength": 512,
      "pattern": "^(api|db|event|flag|env|contract|feature):.+$",
      "description": "Non-file lock key stored in file_locks.file_path (namespace prefix required)."
    },
    "Locks": {
      "type": "object",
      "additionalProperties": false,
      "required": ["files", "keys"],
      "properties": {
        "files": {
          "type": "array",
          "items": { "$ref": "#/$defs/FilePath" },
          "uniqueItems": true,
          "description": "File locks (raw paths for acquire_lock — existing behavior)."
        },
        "keys": {
          "type": "array",
          "items": { "$ref": "#/$defs/LogicalLockKey" },
          "uniqueItems": true,
          "description": "Logical resource locks (stored as lock keys via acquire_lock)."
        },
        "ttl_minutes": { "type": "integer", "minimum": 1, "maximum": 480 },
        "reason": { "type": "string", "maxLength": 500 }
      }
    },
    "Scope": {
      "type": "object",
      "additionalProperties": false,
      "required": ["write_allow", "read_allow"],
      "properties": {
        "write_allow": {
          "type": "array",
          "items": { "$ref": "#/$defs/Glob" },
          "description": "Globs this package may modify. Empty means read-only package."
        },
        "read_allow": {
          "type": "array",
          "minItems": 1,
          "items": { "$ref": "#/$defs/Glob" },
          "description": "Globs this package may read/scan for context."
        },
        "deny": {
          "type": "array",
          "items": { "$ref": "#/$defs/Glob" },
          "description": "Globs explicitly forbidden even if included in allow lists."
        }
      }
    },
    "Worktree": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name"],
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 80,
          "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
        },
        "mode": { "type": "string", "enum": ["isolated", "shared"], "default": "isolated" }
      }
    },
    "VerificationStep": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "kind", "evidence"],
      "properties": {
        "name": { "type": "string", "minLength": 1, "maxLength": 80 },
        "kind": { "type": "string", "enum": ["command", "ci", "manual"] },
        "command": { "type": "string", "minLength": 1 },
        "cwd": { "$ref": "#/$defs/FilePath" },
        "env": { "type": "object", "additionalProperties": { "type": "string" } },
        "expect_exit_code": { "type": "integer", "default": 0 },
        "ci": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "provider": { "type": "string", "enum": ["github", "other"], "default": "github" },
            "workflow": { "type": "string", "minLength": 1 },
            "required_checks": {
              "type": "array",
              "items": { "type": "string", "minLength": 1 },
              "uniqueItems": true
            }
          }
        },
        "manual_instructions": { "type": "string", "minLength": 1 },
        "evidence": {
          "type": "object",
          "additionalProperties": false,
          "required": ["artifacts", "result_keys"],
          "properties": {
            "artifacts": {
              "type": "array",
              "items": { "$ref": "#/$defs/FilePath" },
              "description": "Paths expected to be produced (logs, junit xml, screenshots)."
            },
            "result_keys": {
              "type": "array",
              "items": { "type": "string", "minLength": 1 },
              "description": "Keys that must be present in work_queue.result.verification for this step."
            }
          }
        }
      },
      "allOf": [
        { "if": { "properties": { "kind": { "const": "command" } } }, "then": { "required": ["command"] } },
        { "if": { "properties": { "kind": { "const": "ci" } } }, "then": { "required": ["ci"] } },
        { "if": { "properties": { "kind": { "const": "manual" } } }, "then": { "required": ["manual_instructions"] } }
      ]
    },
    "Verification": {
      "type": "object",
      "additionalProperties": false,
      "required": ["tier_required", "steps"],
      "properties": {
        "tier_required": { "type": "string", "enum": ["A", "B", "C"] },
        "steps": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/VerificationStep" } }
      }
    },
    "WorkPackage": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "package_id", "task_type", "description", "depends_on", "priority",
        "locks", "scope", "worktree", "timeout_minutes", "retry_budget",
        "min_trust_level", "verification", "outputs"
      ],
      "properties": {
        "package_id": { "$ref": "#/$defs/PackageId" },
        "title": { "type": "string", "minLength": 1, "maxLength": 120 },
        "task_type": { "type": "string", "minLength": 1, "maxLength": 40 },
        "description": { "type": "string", "minLength": 1, "maxLength": 4000 },
        "role": { "type": "string", "minLength": 1, "maxLength": 60 },
        "priority": { "type": "integer", "minimum": 1, "maximum": 10 },
        "depends_on": {
          "type": "array",
          "items": { "$ref": "#/$defs/PackageId" },
          "uniqueItems": true
        },
        "locks": { "$ref": "#/$defs/Locks" },
        "scope": { "$ref": "#/$defs/Scope" },
        "worktree": { "$ref": "#/$defs/Worktree" },
        "timeout_minutes": { "type": "integer", "minimum": 1 },
        "retry_budget": { "type": "integer", "minimum": 0 },
        "min_trust_level": { "type": "integer", "minimum": 0, "maximum": 4 },
        "verification": { "$ref": "#/$defs/Verification" },
        "inputs": { "type": "object", "additionalProperties": true },
        "outputs": {
          "type": "object",
          "additionalProperties": false,
          "required": ["result_keys"],
          "properties": {
            "result_keys": {
              "type": "array",
              "minItems": 1,
              "items": { "type": "string", "minLength": 1 }
            },
            "artifacts": { "type": "array", "items": { "$ref": "#/$defs/FilePath" } }
          }
        }
      }
    }
  }
}
```

### 3.2 `work-queue-result.schema.json`

Location: `openspec/schemas/work-queue-result.schema.json`

Validated by the orchestrator immediately after a task completes (after fetching the row's `result`), before accepting the package as COMPLETED in the DAG state. This keeps "verification passed" from becoming a conversational claim and makes completion mechanically auditable.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://agentic-coding-tools.dev/schemas/work-queue-result.schema.json",
  "title": "work_queue.result payload",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "feature_id", "package_id", "plan_revision",
    "contracts_revision", "status", "locks", "scope", "files_modified",
    "git", "verification", "escalations"
  ],
  "properties": {
    "schema_version": { "type": "integer", "const": 1 },
    "feature_id": {
      "type": "string", "minLength": 1, "maxLength": 128,
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
    },
    "package_id": {
      "type": "string", "minLength": 1, "maxLength": 64,
      "pattern": "^[a-z][a-z0-9_-]{0,63}$"
    },
    "attempt": { "type": "integer", "minimum": 1, "default": 1 },
    "plan_revision": { "type": "integer", "minimum": 1 },
    "contracts_revision": { "type": "integer", "minimum": 1 },
    "status": {
      "type": "string",
      "enum": ["completed", "failed"],
      "description": "Mirrors complete_work(success). Use 'failed' for cancelled too."
    },
    "error_code": {
      "type": "string",
      "description": "Present when status=failed. Standard codes: SCOPE_VIOLATION, VERIFICATION_FAILED, LOCK_UNAVAILABLE, TIMEOUT, cancelled_by_orchestrator, PAUSED."
    },
    "timestamps": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "started_at": { "type": "string", "format": "date-time" },
        "finished_at": { "type": "string", "format": "date-time" }
      }
    },
    "locks": {
      "type": "object",
      "additionalProperties": false,
      "required": ["files", "keys"],
      "properties": {
        "files": { "type": "array", "items": { "$ref": "#/$defs/FilePath" }, "uniqueItems": true },
        "keys": { "type": "array", "items": { "$ref": "#/$defs/LogicalLockKey" }, "uniqueItems": true }
      }
    },
    "scope": {
      "type": "object",
      "additionalProperties": false,
      "required": ["write_allow", "read_allow", "deny"],
      "properties": {
        "write_allow": { "type": "array", "items": { "$ref": "#/$defs/Glob" } },
        "read_allow": { "type": "array", "items": { "$ref": "#/$defs/Glob" } },
        "deny": { "type": "array", "items": { "$ref": "#/$defs/Glob" } }
      },
      "description": "Echo of the package scope for deterministic verification."
    },
    "files_modified": {
      "type": "array",
      "items": { "$ref": "#/$defs/FilePath" },
      "uniqueItems": true,
      "description": "From git diff --name-only; orchestrator validates ⊆ write_allow \\ deny."
    },
    "scope_check": {
      "type": "object",
      "additionalProperties": false,
      "required": ["passed"],
      "properties": {
        "passed": { "type": "boolean" },
        "violations": { "type": "array", "items": { "$ref": "#/$defs/FilePath" }, "uniqueItems": true }
      }
    },
    "git": {
      "type": "object",
      "additionalProperties": false,
      "required": ["base", "head"],
      "properties": {
        "base": {
          "type": "object",
          "additionalProperties": false,
          "required": ["ref"],
          "properties": {
            "ref": { "type": "string", "minLength": 1 }
          }
        },
        "head": {
          "type": "object",
          "additionalProperties": false,
          "required": ["commit"],
          "properties": {
            "commit": { "type": "string", "minLength": 7, "maxLength": 64, "pattern": "^[0-9a-fA-F]+$" },
            "branch": { "type": "string", "minLength": 1 },
            "worktree": { "type": "string", "minLength": 1 }
          }
        }
      }
    },
    "verification": {
      "type": "object",
      "additionalProperties": false,
      "required": ["tier", "passed", "steps"],
      "properties": {
        "tier": { "type": "string", "enum": ["A", "B", "C"] },
        "passed": { "type": "boolean" },
        "steps": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/VerificationStepResult" } }
      }
    },
    "contract_checks": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "openapi_validation": {
          "type": "object", "additionalProperties": false, "required": ["passed"],
          "properties": {
            "passed": { "type": "boolean" },
            "details": { "type": "string" },
            "artifact": { "$ref": "#/$defs/FilePath" }
          }
        },
        "schemathesis": {
          "type": "object", "additionalProperties": false, "required": ["passed"],
          "properties": {
            "passed": { "type": "boolean" },
            "base_url": { "type": "string" },
            "artifact": { "$ref": "#/$defs/FilePath" },
            "seed": { "type": "integer" }
          }
        },
        "pact_provider_verification": {
          "type": "object", "additionalProperties": false, "required": ["passed"],
          "properties": {
            "passed": { "type": "boolean" },
            "broker": { "type": "string" },
            "artifact": { "$ref": "#/$defs/FilePath" }
          }
        }
      }
    },
    "resources": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "ports": { "type": "object", "additionalProperties": true }
      }
    },
    "notes": { "type": "string", "maxLength": 8000 },
    "escalations": {
      "type": "array",
      "items": { "$ref": "#/$defs/Escalation" },
      "description": "Escalations emitted by this package (may be empty)."
    }
  },
  "$defs": {
    "FilePath": {
      "type": "string", "minLength": 1, "maxLength": 512,
      "pattern": "^(?!/)(?!.*\\s+$).+"
    },
    "Glob": { "type": "string", "minLength": 1, "maxLength": 512 },
    "LogicalLockKey": {
      "type": "string", "minLength": 1, "maxLength": 512,
      "pattern": "^(api|db|event|flag|env|contract|feature):.+$"
    },
    "VerificationStepResult": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "kind", "passed", "evidence"],
      "properties": {
        "name": { "type": "string", "minLength": 1, "maxLength": 80 },
        "kind": { "type": "string", "enum": ["command", "ci", "manual"] },
        "passed": { "type": "boolean" },
        "command": { "type": "string", "minLength": 1 },
        "cwd": { "$ref": "#/$defs/FilePath" },
        "exit_code": { "type": "integer" },
        "ci": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "provider": { "type": "string" },
            "run_id": { "type": "string" },
            "url": { "type": "string" },
            "required_checks": { "type": "array", "items": { "type": "string", "minLength": 1 } }
          }
        },
        "manual": {
          "type": "object",
          "additionalProperties": false,
          "properties": { "instructions": { "type": "string", "minLength": 1 } }
        },
        "evidence": {
          "type": "object",
          "additionalProperties": false,
          "required": ["artifacts", "metrics"],
          "properties": {
            "artifacts": { "type": "array", "items": { "$ref": "#/$defs/FilePath" } },
            "metrics": {
              "type": "object",
              "additionalProperties": true,
              "description": "Machine-readable metrics (duration_seconds, test_count, etc.)."
            }
          }
        }
      },
      "allOf": [
        { "if": { "properties": { "kind": { "const": "command" } } }, "then": { "required": ["command", "exit_code"] } },
        { "if": { "properties": { "kind": { "const": "ci" } } }, "then": { "required": ["ci"] } },
        { "if": { "properties": { "kind": { "const": "manual" } } }, "then": { "required": ["manual"] } }
      ]
    },
    "Escalation": {
      "type": "object",
      "additionalProperties": false,
      "required": ["escalation_id", "feature_id", "package_id", "type", "severity", "summary", "detected_at"],
      "properties": {
        "escalation_id": { "type": "string", "minLength": 1, "maxLength": 128 },
        "feature_id": { "type": "string", "minLength": 1, "maxLength": 128 },
        "package_id": { "type": "string", "minLength": 1, "maxLength": 64 },
        "type": {
          "type": "string",
          "enum": [
            "CONTRACT_REVISION_REQUIRED", "PLAN_REVISION_REQUIRED", "RESOURCE_CONFLICT",
            "VERIFICATION_INFEASIBLE", "SCOPE_VIOLATION", "ENV_RESOURCE_CONFLICT",
            "SECURITY_ESCALATION", "FLAKY_TEST_QUARANTINE_REQUEST"
          ]
        },
        "severity": { "type": "string", "enum": ["NON_BLOCKING", "LOW", "MEDIUM", "HIGH", "BLOCKING"] },
        "summary": { "type": "string", "minLength": 1, "maxLength": 500 },
        "details": { "type": "string", "maxLength": 8000 },
        "detected_at": { "type": "string", "format": "date-time" },
        "evidence": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "files": { "type": "array", "items": { "$ref": "#/$defs/FilePath" }, "uniqueItems": true },
            "logs": { "type": "array", "items": { "$ref": "#/$defs/FilePath" }, "uniqueItems": true }
          }
        },
        "impact": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "contract_revision_bump_required": { "type": "boolean" },
            "plan_revision_bump_required": { "type": "boolean" },
            "impacted_packages": {
              "type": "array",
              "items": { "type": "string", "minLength": 1, "maxLength": 64 },
              "uniqueItems": true
            },
            "logical_locks": { "type": "array", "items": { "$ref": "#/$defs/LogicalLockKey" }, "uniqueItems": true }
          }
        },
        "proposed_action": { "type": "string", "maxLength": 2000 },
        "requires_human": { "type": "boolean", "default": false }
      }
    }
  }
}
```

### 3.3 `review-findings.schema.json`

Location: `openspec/schemas/review-findings.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://agentic-coding-tools.dev/schemas/review-findings.schema.json",
  "title": "Review Findings",
  "type": "object",
  "required": ["review_type", "target", "findings"],
  "properties": {
    "review_type": { "type": "string", "enum": ["plan", "implementation"] },
    "target": { "type": "string", "description": "feature_id for plan review, package_id for implementation review." },
    "reviewer_vendor": { "type": "string" },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "type", "criticality", "description", "disposition"],
        "properties": {
          "id": { "type": "integer" },
          "type": { "type": "string", "enum": ["spec_gap", "contract_mismatch", "architecture", "security", "performance", "style", "correctness"] },
          "criticality": { "type": "string", "enum": ["low", "medium", "high", "critical"] },
          "description": { "type": "string" },
          "resolution": { "type": "string" },
          "disposition": { "type": "string", "enum": ["fix", "regenerate", "accept", "escalate"] },
          "package_id": { "type": "string" }
        }
      }
    }
  }
}
```

### 3.4 Coordinator Extension: `get_task` MCP Tool

```json
{
  "name": "get_task",
  "description": "Retrieve a task's current state including status, result, and input_data. Does NOT claim the task.",
  "inputSchema": {
    "type": "object",
    "required": ["task_id"],
    "properties": {
      "task_id": { "type": "string", "description": "The UUID of the task to retrieve." }
    }
  }
}
```

**Response:**
```json
{
  "type": "object",
  "properties": {
    "task_id": { "type": "string" },
    "task_type": { "type": "string" },
    "status": { "type": "string", "enum": ["pending", "claimed", "completed", "failed", "cancelled"] },
    "input_data": { "type": ["object", "null"] },
    "result": { "type": ["object", "null"] },
    "error_message": { "type": ["string", "null"] },
    "priority": { "type": "integer" },
    "created_at": { "type": "string", "format": "date-time" },
    "completed_at": { "type": ["string", "null"], "format": "date-time" }
  }
}
```

**HTTP Endpoint:** `GET /api/v1/tasks/{task_id}`

---

## Part 4: Tasks

### Implementation Sequence

#### De-risking Strategy: Thin Vertical Slice First

1. **First**: `work-packages.yaml` + DAG scheduling using existing work queue, single worktree.
2. **Then**: Logical resource lock conventions.
3. **Then**: Multi-worktree dispatch.
4. **Finally**: Feature registry UI/reporting.

#### Dependency Graph

```
#1 (skill families) ──→ #4 (parallel-plan, parallel-explore)
                              │
#2 (contract artifacts) ──→ #3 (work-packages + coordinator deltas) ──→ #4 ──→ #6 (parallel-implement)
                                                                                    │
#5 (review skills) ─────────────────────────────────────────────── (parallel with #4-#6)
                                                                                    │
#7 (feature registry) ──→ #8 (merge queue + parallel-cleanup)                      │
                                                                                    │
#9 (parallel-validate) ──────────────────────────────────── (independent)
```

**Critical path:** #1 → #2 → #3 → #4 → #6

### Task 1: Create Skill Family Structure (S, Low Risk)

Rename existing skills to `linear-*` prefix. Add aliases. Update `CLAUDE.md`, `AGENTS.md`. Add `CAN_DISCOVER`, `CAN_POLICY`, `CAN_AUDIT` capability flags. No behavior change.

### Task 2: Add Contract and Work-Package Artifacts to Schema (S, Low Risk)

Add `contracts` and `work-packages` artifact types to `schema.yaml`. Templates for OpenAPI spec, Prism mocks, Schemathesis, Pact. Lock key namespace documentation.

### Task 3: Work-Packages DAG + Coordinator Deltas (S→M, Low-Medium Risk)

**3a: Schema validation** — Install `work-packages.schema.json` (§3.1) and `work-queue-result.schema.json` (§3.2). YAML→JSON→validate pipeline. DAG cycle detection. Lock key canonicalization.

**3b: `parallel_zones.py --validate-packages`** — Scope non-overlap and lock non-overlap for parallel packages.

**3c: Delta A — `get_task` API** — Expose existing `WorkQueueService.get_task` as MCP tool + HTTP endpoint (§3.4).

**3d: Delta B — Cancellation convention** — Document `error_code="cancelled_by_orchestrator"`. Add helper function.

**3e: Delta C — Lock key policy updates** — Permit `api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:` patterns.

### Task 4: parallel-plan-feature and parallel-explore-feature (M, Medium Risk)

Produce `contracts/` and `work-packages.yaml` conforming to §3.1. Context slicing. Capability-gated hooks.

### Task 5: Review Skills (M, Low Risk)

`/parallel-review-plan` and `/parallel-review-implementation`. Findings per §3.3. Vendor-agnostic. Parallel with #4 and #6.

### Task 6: parallel-implement-feature with DAG Dispatch (M, Medium Risk)

**6a: DAG scheduler** — Phase A preflight (§2.4). `submit_work` per package. Monitor via `discover_agents` + `get_task`.

**6b: Package execution protocol** — Phase B (§2.4). Pause-lock checks (B2, B9). Deadlock-safe locks (B3). Scope check (B7). Result per §3.2 (B10).

**6c: Result validation** — Phase C1 (§2.4). Schema validation. Revision matching.

**6d: Escalation handling** — §2.6 state machine. Pause lock. Contract/plan bump procedures.

**6e: Review + integration** — Phase C3-C6. `wp-integration` package. Execution summary.

**6f: Circuit breaking** — Heartbeat detection. Retry budget. Cancellation propagation.

### Task 7: Feature Registry (M, Medium Risk)

`feature_registry.py`. PostgreSQL migration. Lock-key-based conflict analysis. Feasibility assessment.

### Task 8: Merge Queue + Cross-Feature Rebase (M→S, Medium Risk)

Merge ordering. Pre-merge checks. `/parallel-cleanup-feature`. Extends GitHub coordination.

### Task 9: parallel-validate-feature (S, Low Risk)

Slim integration-only. Evidence completeness via §3.2 schema validation. Independent of #7-#8.

### Formal Verification Tasks

**FV-1: TLA+ Model** (S) — Locks, tasks, dependencies, pause-lock, rescheduling. TLC model checker.

**FV-2: Lean Safety Proofs** (M) — DAG correctness, cancellation propagation, 6 invariants from §2.15.

**FV-3: Property-Based Tests** (S) — Randomized sequences against real coordinator. CI integration.

---

## Appendix A: Alternatives Considered

**Full rebuild around DAG engine.** Rejected: breaks skill model.
**Agent-per-file.** Rejected: too much coordination overhead.
**Optimistic concurrency.** Rejected: AI merge conflicts expensive.
**Review in build skills.** Rejected: prevents vendor diversity.
**Single skill family with flags.** Rejected: conditional complexity.
**Pydantic as canonical contract.** Rejected: couples to Python.

## Appendix B: Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Decomposition overhead for small features | Optional; <3 tasks → sequential fallback |
| Contract drift | Three-layer: static types + Schemathesis + Pact |
| Semantic conflicts with non-overlapping files | Logical locks + `wp-integration` full suite |
| Feature registry SPOF | Coordinator optional; degrades to git conflicts |
| Integration bugs from worktree merge | `wp-integration` first-class package |
| Orchestrator context exhaustion | Information hiding via condensed coordinator reads |
| Test flakiness from parallelism | `allocate_ports` + quarantine mechanism |
| Merge queue cascading failures | Pre-merge checks + label lock pause |

## Appendix C: Coordinator Compatibility Matrix

| Feature | Support | Gap | Resolution |
|---------|---------|-----|------------|
| `work_queue.result` JSONB | ✅ | — | Aligned |
| Dependency enforcement | ✅ `claim_task` checks `depends_on` | — | Aligned |
| Lock key namespaces | ✅ `file_path` TEXT | Policy rules | Delta C (Task 3e) |
| Port allocation | ✅ `allocate_ports` | — | Use instead of env: locks |
| Read task by ID | ⚠️ Internal only | MCP tool + HTTP | Delta A (Task 3c) |
| CANCELLED state | ⚠️ DB value, no RPC | Convention | Delta B (Task 3d) |
| RUNNING state | ⚠️ No `start_task` | — | `claimed` + heartbeat proxy |
| Scope enforcement | ⚠️ Guardrails regex | Not per-package | Deterministic diff (§2.5) |
| Retry | ⚠️ `max_attempts` unused | — | Scheduler-level new task (§2.7) |
| Feature pause | ✅ `acquire_lock` with `feature:` key | — | No new infrastructure |

## Appendix D: Schema File Inventory

| Schema File | Location | Validates | When |
|-------------|----------|-----------|------|
| `work-packages.schema.json` | `openspec/schemas/` | `work-packages.yaml` | Plan time + before dispatch |
| `work-queue-result.schema.json` | `openspec/schemas/` | `work_queue.result` JSONB | After every `complete_work` |
| `review-findings.schema.json` | `openspec/schemas/` | Review agent output | After review completes |
