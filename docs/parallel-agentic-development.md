# Parallel Agentic Development — Implementation Reference

This document describes the **implemented** parallel agentic development system as it exists today. It serves as the authoritative reference for how multiple AI coding agents coordinate on shared codebases. For the original design proposal, see [`docs/archive/two-level-parallel-agentic-development.md`](archive/two-level-parallel-agentic-development.md). For the user-facing workflow guide, see [`docs/skills-workflow.md`](skills-workflow.md).

## Table of Contents

1. [Three-Level Coordination Model](#1-three-level-coordination-model)
2. [Agent Coordinator](#2-agent-coordinator)
3. [Level 1: Intra-Feature Parallelism](#3-level-1-intra-feature-parallelism)
4. [Level 2: Cross-Feature Parallelism](#4-level-2-cross-feature-parallelism)
5. [Level 3: Cross-Application / Program Coordination](#5-level-3-cross-application--program-coordination)
6. [Skill Workflows](#6-skill-workflows)
7. [Coordination Primitives](#7-coordination-primitives)
8. [Execution Protocol](#8-execution-protocol)
9. [Safety & Governance](#9-safety--governance)
10. [Implementation Status](#10-implementation-status)

---

## 1. Three-Level Coordination Model

The system implements coordination at three levels, each with distinct actors, scope, and automation:

```
Level 3: Cross-Application / Program    [Human-driven]
  ├── Portfolio prioritization, epic sequencing, org-level decisions
  ├── Actors: humans (tech leads, PMs), approval gates, /prioritize-proposals
  └── Scope: multiple repositories, epics, strategic trade-offs

Level 2: Cross-Feature                  [Coordinator-assisted]
  ├── Resource conflict detection, merge ordering, rebase coordination
  ├── Actors: feature registry, merge queue, /parallel-explore-feature
  └── Scope: concurrent features within one repository

Level 1: Intra-Feature                  [Agent-automated]
  ├── DAG scheduling, lock acquisition, scope enforcement, contract compliance
  ├── Actors: orchestrator agent, worker agents, coordinator MCP tools
  └── Scope: work packages within one feature
```

**Design principle**: automation increases as scope narrows. Level 1 is mostly automated (agents coordinate via coordinator primitives). Level 2 is coordinator-assisted (conflict detection is automated, merge ordering requires human judgment for edge cases). Level 3 is human-driven (strategic decisions about what to build and in what order).

---

## 2. Agent Coordinator

The coordinator is a PostgreSQL-backed service that provides coordination primitives to AI coding agents via two transport layers.

### Architecture

```
CLI Agents (Claude Code, Codex, Gemini)
  └── MCP Server (stdio transport, 19 tools)
        └── Coordinator Services (12 services)
              └── PostgreSQL (ParadeDB)
                    └── 12 tables, 17 PL/pgSQL functions

Cloud Agents (Claude Web, Codex Cloud)
  └── HTTP API (FastAPI, API-key auth)
        └── Same coordinator services
```

**Implementation**:
- MCP server: [`agent-coordinator/src/coordination_mcp.py`](../agent-coordinator/src/coordination_mcp.py) (40.8KB, 19 tools + 7 resources)
- HTTP API: [`agent-coordinator/src/coordination_api.py`](../agent-coordinator/src/coordination_api.py) (29.9KB, FastAPI endpoints)
- Database: [`agent-coordinator/supabase/migrations/`](../agent-coordinator/supabase/migrations/) (12 migrations)

### Services

| Service | File | Purpose | MCP Tools |
|---------|------|---------|-----------|
| **Locks** | [`locks.py`](../agent-coordinator/src/locks.py) | File + logical key locking with TTL | `acquire_lock`, `release_lock`, `check_locks` |
| **Work Queue** | [`work_queue.py`](../agent-coordinator/src/work_queue.py) | Task assignment with priority + DAG dependencies | `submit_work`, `get_work`, `complete_work`, `get_task` |
| **Discovery** | [`discovery.py`](../agent-coordinator/src/discovery.py) | Agent registration, heartbeat, dead agent cleanup | `register_session`, `discover_agents`, `heartbeat`, `cleanup_dead_agents` |
| **Handoffs** | [`handoffs.py`](../agent-coordinator/src/handoffs.py) | Session context preservation across sessions | `write_handoff`, `read_handoff` |
| **Memory** | [`memory.py`](../agent-coordinator/src/memory.py) | Episodic + procedural memory with relevance scoring | `remember`, `recall` |
| **Guardrails** | [`guardrails.py`](../agent-coordinator/src/guardrails.py) | Destructive operation detection (git force-push, rm -rf, DROP TABLE) | `check_guardrails` |
| **Profiles** | [`profiles.py`](../agent-coordinator/src/profiles.py) | Agent trust levels 0–4, operation allow/block lists | `get_my_profile` |
| **Policy Engine** | [`policy_engine.py`](../agent-coordinator/src/policy_engine.py) | Authorization via Native profiles or AWS Cedar PARC model | `check_policy`, `validate_cedar_policy` |
| **Audit** | [`audit.py`](../agent-coordinator/src/audit.py) | Immutable, append-only operation logging | `query_audit` |
| **Feature Registry** | [`feature_registry.py`](../agent-coordinator/src/feature_registry.py) | Cross-feature resource claim tracking, conflict analysis | (via `check_locks`, internal API) |
| **Merge Queue** | [`merge_queue.py`](../agent-coordinator/src/merge_queue.py) | Priority-ordered feature merging with pre-merge re-validation | (via internal API) |
| **Port Allocator** | [`port_allocator.py`](../agent-coordinator/src/port_allocator.py) | Conflict-free port blocks for parallel docker-compose stacks | `allocate_ports`, `release_ports`, `ports_status` |

### Transport & Degradation

Skills detect coordinator availability via [`scripts/check_coordinator.py`](../agent-coordinator/scripts/check_coordinator.py) and set capability flags:

```python
COORDINATOR_AVAILABLE = True/False
COORDINATION_TRANSPORT = "mcp" | "http" | "none"
CAN_LOCK = True        # acquire_lock / release_lock
CAN_QUEUE_WORK = True  # submit_work / get_work / complete_work / get_task
CAN_DISCOVER = True    # register_session / discover_agents
CAN_HANDOFF = True     # write_handoff / read_handoff
CAN_MEMORY = True      # remember / recall
CAN_GUARDRAILS = True  # check_guardrails
CAN_AUDIT = True       # query_audit
CAN_POLICY = True      # check_policy
```

When required capabilities are unavailable, parallel skills degrade to their linear equivalents. Enriching capabilities (handoffs, memory) fail gracefully without blocking execution.

---

## 3. Level 1: Intra-Feature Parallelism

A single feature decomposes into **work packages** grouped by architectural boundary (backend, frontend, contracts, migrations). Each package gets its own agent, worktree, and scope. A DAG scheduler coordinates execution order.

### Work Packages

Defined in `openspec/changes/<change-id>/work-packages.yaml`, validated against [`openspec/schemas/work-packages.schema.json`](../openspec/schemas/work-packages.schema.json).

```yaml
schema_version: 1
feature:
  id: add-user-auth
  plan_revision: 1
contracts:
  revision: 1
  openapi:
    primary: contracts/openapi/v1.yaml
    files: [contracts/openapi/v1.yaml]
packages:
  - package_id: wp-contracts
    task_type: contracts
    depends_on: []
    locks:
      keys: ["contract:openapi/v1.yaml"]
    scope:
      write_allow: ["contracts/**"]
      deny: ["src/**"]
    verification:
      tier_required: A

  - package_id: wp-backend
    task_type: implementation
    depends_on: [wp-contracts]
    locks:
      files: ["src/api/**"]
      keys: ["db:schema:users", "api:POST /v1/users"]
    scope:
      write_allow: ["src/api/**", "tests/api/**"]
      deny: ["src/ui/**"]
    verification:
      tier_required: A

  - package_id: wp-frontend
    task_type: implementation
    depends_on: [wp-contracts]
    locks:
      files: ["src/ui/**"]
      keys: []
    scope:
      write_allow: ["src/ui/**", "tests/ui/**"]
      deny: ["src/api/**"]
    verification:
      tier_required: A
```

**Key invariants**:
- Parallel packages have non-overlapping `write_allow` scopes (except `wp-integration`)
- Lock keys follow namespace conventions (see [Lock Key Namespaces](#lock-key-namespaces))
- DAG must be acyclic (validated via Kahn's algorithm in [`skills/validate-packages/scripts/validate_work_packages.py`](../skills/validate-packages/scripts/validate_work_packages.py))

### Contract-First Development

Contracts define the coordination boundary between parallel agents. The contracts package runs first, generating artifacts that other packages develop against independently.

| Artifact | Purpose | Implementation Status |
|----------|---------|----------------------|
| OpenAPI specs | Canonical API contract | Schema in `work-packages.yaml`, agents generate |
| Pydantic models | Python type stubs | Config in schema (`contracts.generated.pydantic_dir`), agent-generated |
| TypeScript interfaces | Frontend type stubs | Config in schema (`contracts.generated.typescript_dir`), agent-generated |
| Prism mocks | Executable API stubs | Config in schema (`contracts.mocks.prism`), agent-started |
| Schemathesis tests | Property-based API testing | Config in schema (`contracts.cdc`), agent-executed |
| Pact contracts | Consumer-driven contract tests | Config in schema, agent-executed |

**Contract revision semantics**: any contract file modification after implementation dispatch triggers `CONTRACT_REVISION_REQUIRED` escalation — the orchestrator bumps `contracts.revision`, regenerates types/mocks, and resubmits impacted packages. Handled by [`escalation_handler.py`](../skills/parallel-implement-feature/scripts/escalation_handler.py).

### Contract-Aware TDD

Contracts feed directly into test planning via a structured traceability chain:

1. **Planning** (`/plan-feature`): Test tasks in `tasks.md` are ordered *before* implementation tasks and reference the artifacts they validate — spec scenarios, contract files, and design decisions.
2. **Phase 1 — TDD RED** (`/implement-feature`): The `change-context.md` Requirement Traceability Matrix maps each spec requirement to its **Contract Ref** (e.g., `contracts/openapi/v1.yaml#/paths/~1users`) and **Design Decision** (e.g., `D3`). Failing tests are written that assert against contracted interfaces and architectural choices.
3. **Phase 2 — TDD GREEN**: Implementation code makes tests pass. Tests that reference contracts validate the contracted API surface, not just internal behavior.
4. **Phase 3 — Validation**: `/validate-feature` populates evidence in `change-context.md`.

This ensures tests at contract boundaries verify that module A's output matches module B's expected input per the contract — not just that each module works in isolation.

### DAG Scheduling

**Implementation**: [`dag_scheduler.py`](../skills/parallel-implement-feature/scripts/dag_scheduler.py)

The orchestrator:
1. Parses and validates `work-packages.yaml`
2. Computes topological order via Kahn's algorithm with `sorted()` for deterministic peer ordering
3. Submits packages to coordinator work queue with `submit_work()` (priority, depends_on, timeout)
4. Monitors progress by polling `get_task(task_id)` for each submitted task
5. Dispatches newly unblocked packages as dependencies complete

Package states: `PENDING → READY → SUBMITTED → IN_PROGRESS → COMPLETED | FAILED | CANCELLED`

### Scope Enforcement

**Implementation**: [`scope_checker.py`](../skills/parallel-implement-feature/scripts/scope_checker.py), [`skills/validate-packages/scripts/validate_work_result.py`](../skills/validate-packages/scripts/validate_work_result.py)

Post-hoc deterministic check at step B7 of the worker protocol:
1. Run `git diff --name-only` to get modified files
2. For each file: verify `fnmatch(file, write_allow_pattern)` matches at least one pattern
3. For each file: verify `NOT fnmatch(file, deny_pattern)` for all deny patterns
4. Any violation triggers `SCOPE_VIOLATION` escalation (blocking, fails the package)

### Worktree Management

**Implementation**: [`skills/worktree/scripts/worktree.py`](../skills/worktree/scripts/worktree.py)

Each work package gets an isolated git worktree:
- Location: `.git-worktrees/<change-id>/<agent-id>/`
- Lifecycle: `python3 skills/worktree/scripts/worktree.py setup|teardown|status|detect|heartbeat|list|pin|unpin|gc`
- Rule: one agent, one worktree, one branch — never shared

---

## 4. Level 2: Cross-Feature Parallelism

Multiple features develop in parallel within the same repository. The coordinator's feature registry and merge queue manage resource conflicts and merge ordering.

### Feature Registry

**Implementation**: [`feature_registry.py`](../agent-coordinator/src/feature_registry.py), database table `feature_registry`

Features register resource claims (lock keys) before implementation begins:

```python
# Registration
await registry.register(
    feature_id="add-user-auth",
    resource_claims=["db:schema:users", "api:POST /v1/users", "src/api/auth.py"],
    branch_name="openspec/add-user-auth",
    merge_priority=1
)

# Conflict analysis for a new candidate
report = await registry.analyze_conflicts(
    candidate_feature_id="add-billing",
    candidate_claims=["db:schema:users", "api:POST /v1/billing"]
)
# report.feasibility = "PARTIAL" (overlap on db:schema:users)
# report.overlapping_claims = {"db:schema:users": ["add-user-auth"]}
```

**Feasibility assessment**:
- `FULL` — no overlapping claims, safe to fully parallelize
- `PARTIAL` — some overlap, can parallelize with coordination during merge
- `SEQUENTIAL` — >50% overlap (`SEQUENTIAL_THRESHOLD = 0.5`), must serialize

### Merge Queue

**Implementation**: [`merge_queue.py`](../agent-coordinator/src/merge_queue.py)

Priority-ordered merging with pre-merge conflict re-validation:

```
Feature A (priority=1) ──enqueue──► Merge Queue
Feature B (priority=2) ──enqueue──►     │
                                        ▼
                                pre_merge_checks(A)
                                merge A to main
                                deregister(A) → free claims
                                        │
                                rebase B onto updated main
                                pre_merge_checks(B)
                                merge B to main
                                deregister(B)
```

States: `QUEUED → PRE_MERGE_CHECK → READY → MERGING → MERGED` (or `BLOCKED`)

### Speculative Merge Trains

**Implementation**: [`merge_train.py`](../agent-coordinator/src/merge_train.py) (pure engine) + [`merge_train_service.py`](../agent-coordinator/src/merge_train_service.py) (DB-backed orchestration)

Merge trains extend the legacy queue into a **speculative batching layer**. Instead of merging one feature at a time, the coordinator composes a *train* of features on a periodic sweep (default 60s), speculatively merges them in chains via `git merge-tree --write-tree`, and runs CI on the speculative refs in parallel. Features that pass speculation land on `main` without waiting for the features ahead of them to finish their own CI runs.

```
Queue:           F1 F2 F3 F4 F5            ── periodic compose_train (60s)
                 ↓  ↓  ↓  ↓  ↓
Partition by     ┌──────────┐ ┌──────┐     ── lock-key prefix grouping (D2)
lock prefix:     │ F1 F3 F5 │ │ F2 F4│        api:, db:schema:, flag:, …
                 │ (api:)   │ │(db:) │
                 └─────┬────┘ └───┬──┘
                       ↓          ↓
Speculative      main→F1→F3→F5    main→F2→F4   ── git merge-tree chains
refs:            (chain per partition — disjoint partitions run in parallel)
                       ↓          ↓
CI (affected              parallel
 tests or full):     verification            ── refresh-architecture probe
                       ↓          ↓             picks "affected" vs "full suite"
Merge wave:      F1 ✓  ──► main
                 F3 ✓  ──► main (fast-forward if F1 already landed)
                 F5 ✗  ──► EJECT, re-queue dependents
                 F2 ✓  ──► main (independent partition)
```

**Key mechanisms:**

- **Lock-key partitioning (D2)**: Features are grouped by the namespace prefix of their resource claims (`api:`, `db:schema:`, `event:`, `flag:`, …). Entries within a partition are serialized via chained speculative refs; different partitions merge independently. See [`lock-key-namespaces.md`](./lock-key-namespaces.md).
- **Wave merge algorithm (D4)**: Kahn's topological sort over the "ready graph" — an entry is ready when every entry at a lower `train_position` in the same partition has merged. Cross-partition entries wait on all their spanning partitions. This is strictly serial per partition but fully parallel across partitions.
- **Post-speculation claim validation (D8)**: After speculating, the engine diffs the file list against `file_path_to_namespaces()` and rejects entries whose *actual* touched namespaces exceed their *declared* `resource_claims`. This catches under-declared claims before they corrupt the merge order.
- **Eject / re-queue with priority decrement (D11, D12)**: Failed entries are ejected, priority is decremented by 10, and `eject_count` is incremented. After `MAX_EJECT_COUNT=3` ejections the entry transitions to `ABANDONED` (terminal; manual re-enqueue required). Dependent successors in the same train are re-queued; claim-prefix-disjoint successors stay in place.
- **refresh-architecture integration (R9)**: Before composing, `MergeTrainService` probes the architecture graph via [`refresh_rpc_client.py`](../agent-coordinator/src/refresh_rpc_client.py). If the graph is stale and no refresh is in flight, it fires a `trigger_refresh` (fire-and-forget) and sets `full_test_suite_required=True` on the composition so CI runs the full suite instead of the affected-tests subset. **The sentinel pattern is load-bearing**: `RefreshClientUnavailable` is a return type, not an exception — merge-train progress is NEVER blocked on refresh-architecture availability.
- **Crash recovery / TTL (R7)**: Speculative refs carry a 6-hour TTL; orphaned refs (train_id no longer in the queue) are garbage-collected. The periodic sweep re-speculates any entry stranded in `SPECULATING` after a coordinator restart.

**State machine (superset of the queue states):**

```
QUEUED ─► SPECULATING ─┬─► SPEC_PASSED ─► MERGING ─► MERGED
                       ├─► BLOCKED (1h auto re-eval per D9)
                       └─► EJECTED ─┬─► QUEUED (priority − 10)
                                    └─► ABANDONED (eject_count ≥ 3)
```

**APIs:**

| Surface | Tool / Endpoint | Purpose |
|---|---|---|
| MCP | `compose_train()` | Compose a new train on-demand (trust ≥ 3) |
| MCP | `eject_from_train(feature_id, reason)` | Eject entry (owner OR trust ≥ 3) |
| MCP | `get_train_status(train_id)` | List entries in a train |
| MCP | `report_spec_result(feature_id, passed, error_message?)` | CI callback (SPECULATING → SPEC_PASSED/BLOCKED) |
| MCP | `affected_tests(changed_files)` | Compute test subset for a candidate |
| HTTP | `POST /merge-train/compose` | Same as MCP (X-API-Key + trust ≥ 3) |
| HTTP | `POST /merge-train/eject` | Same as MCP |
| HTTP | `GET /merge-train/status/{train_id}` | Same as MCP |
| HTTP | `POST /merge-train/report-result` | Same as MCP |
| HTTP | `POST /merge-train/affected-tests` | Same as MCP |

**Background sweep**: `MergeTrainSweeper` is started in the HTTP API's lifespan hook. It calls `compose_train` every `MERGE_TRAIN_SWEEP_INTERVAL_SECONDS` (default 60). Exceptions are logged and swallowed — the sweeper MUST stay alive for the train to progress.

### Parallel Explore

**Implementation**: [`skills/parallel-explore-feature/SKILL.md`](../skills/parallel-explore-feature/SKILL.md)

The `/parallel-explore-feature` skill extends linear exploration with:
- Querying active features via `discover_agents()` and `check_locks()`
- Analyzing resource claim conflicts for each candidate
- Producing feasibility ratings per candidate
- Recommending parallel vs sequential execution

---

## 5. Level 3: Cross-Application / Program Coordination

Level 3 coordination operates above individual repositories and features. It is **human-driven by design** — the system explicitly declares "replacing human approval gates" as a non-goal.

### Human Approval Gates

The system preserves human judgment at five natural decision points:

| Gate | Skill | Human Decision | System Role |
|------|-------|----------------|-------------|
| **Feature selection** | `/explore-feature`, `/prioritize-proposals` | What to build next, resource allocation | Candidate ranking, feasibility analysis |
| **Plan approval** | `/plan-feature` produces `proposal.md` | Approve, revise, or reject | Design generation, conflict detection |
| **Code review** | `/implement-feature` creates PR | Approve, request changes | Code generation, testing, scope enforcement |
| **Validation sign-off** | `/validate-feature` produces evidence | Accept or reject deployment | Evidence collection, compliance checking |
| **Merge authorization** | `/cleanup-feature` | Approve merge timing | Merge queue ordering, rebase coordination |

### Escalation to Humans

Certain escalation types require human decisions. When `requires_human=true`, the orchestrator pauses the DAG and emits a structured escalation:

- `SECURITY_ESCALATION` — always requires human approval
- `PLAN_REVISION_REQUIRED` — human decides restructuring approach
- `CONTRACT_REVISION_REQUIRED` — human reviews contract changes (when ambiguous)

**Implementation**: [`escalation_handler.py`](../skills/parallel-implement-feature/scripts/escalation_handler.py) (8 escalation types with deterministic action mapping)

### Cross-Application Patterns

While no automated cross-application orchestration exists, the system supports cross-project coordination through:

| Pattern | Mechanism | Human Role |
|---------|-----------|------------|
| **Epic tracking** | Beads issue tracker with epics and cross-issue dependencies | Define epics, sequence features |
| **Proposal prioritization** | `/prioritize-proposals` analyzes active proposals against code drift | Review ranking, make strategic decisions |
| **Resource awareness** | Feature registry exposes active claims and conflicts | Decide parallelization vs serialization |
| **Knowledge transfer** | Coordinator memory (`remember`/`recall`) persists across sessions | Review lessons learned, adjust patterns |
| **Shared specifications** | OpenSpec specs in `openspec/specs/` serve as single source of truth | Maintain spec consistency across features |

### Design Principles for Multi-Agent Organizations

The system applies three organizational principles (documented in the original proposal):

- **Inverse Conway Maneuver** — agents organized by architectural boundary (backend, frontend, contracts), not lifecycle phase
- **Two-Pizza Team Autonomy** — each agent completes work independently, communicates via contracts
- **Mission Command (Auftragstaktik)** — agents receive intent-level specs, not step-by-step plans

These principles scale to Level 3: human program managers set strategic intent, agents execute tactically within well-defined boundaries.

---

## 6. Skill Workflows

### Parallel Workflow (requires coordinator)

```
/parallel-explore-feature [focus]     → Candidate shortlist + feasibility
/parallel-plan-feature <desc>         → Proposal + contracts + work-packages.yaml
  /parallel-review-plan <id>          → Structured findings (vendor-diverse)
/parallel-implement-feature <id>      → DAG-scheduled multi-agent execution
  /parallel-review-implementation <id> → Per-package review findings
/parallel-validate-feature <id>       → Evidence completeness audit
/parallel-cleanup-feature <id>        → Merge queue + cross-feature rebase
```

### Linear Workflow (default, no coordinator required)

```
/explore-feature [focus]              → Candidate shortlist
/plan-feature <desc>                  → Proposal approval gate
  /iterate-on-plan <id>              → Refine before approval
/implement-feature <id>              → PR creation
  /iterate-on-implementation <id>    → Bug fixes, improvements
  /validate-feature <id>             → Deployment verification
/cleanup-feature <id>                → Merge + archive
```

Original names (`/explore-feature`, `/plan-feature`, etc.) are backward-compatible aliases for `linear-*` equivalents.

### Coordinator Capability Requirements

| Skill | CAN_LOCK | CAN_QUEUE | CAN_DISCOVER | CAN_HANDOFF | CAN_GUARDRAILS |
|-------|----------|-----------|--------------|-------------|----------------|
| `/parallel-explore-feature` | optional | — | **required** | optional | — |
| `/parallel-plan-feature` | optional | optional | **required** | optional | optional |
| `/parallel-review-plan` | — | — | — | optional | optional |
| `/parallel-implement-feature` | **required** | **required** | **required** | optional | **required** |
| `/parallel-review-implementation` | — | — | — | optional | optional |
| `/parallel-validate-feature` | optional | optional | optional | optional | optional |
| `/parallel-cleanup-feature` | optional | — | optional | optional | — |

---

## 7. Coordination Primitives

### Lock Acquisition Protocol

**Deadlock prevention** via global lexicographic ordering:

1. Merge `locks.files` + `locks.keys` into a single list
2. Sort in **lexicographic order** (canonical global ordering)
3. Acquire each lock via `acquire_lock(file_path=<key>, session_id, ttl=ttl_minutes)`
4. On conflict: release **ALL** already-acquired locks in reverse order
5. Exponential backoff with jitter (max 3 retries)
6. If exhausted: `FAIL` with `error_code="LOCK_UNAVAILABLE"`

**Implementation**: [`package_executor.py`](../skills/parallel-implement-feature/scripts/package_executor.py) (lock ordering), [`locks.py`](../agent-coordinator/src/locks.py) (atomic acquisition via PL/pgSQL `ON CONFLICT`)

### Lock Key Namespaces

All lock keys are stored in the `file_locks.file_path` column — the coordinator treats them as opaque strings. Namespaces give semantic meaning:

| Prefix | Format | Example | Purpose |
|--------|--------|---------|---------|
| *(none)* | `path/to/file.py` | `src/api/users.py` | File-level locking |
| `api:` | `api:<METHOD> <PATH>` | `api:GET /v1/users` | API endpoint ownership |
| `db:migration-slot` | literal | `db:migration-slot` | Migration sequencing (only one at a time) |
| `db:schema:` | `db:schema:<table>` | `db:schema:users` | Database table ownership |
| `event:` | `event:<channel>` | `event:user.created` | Pub/sub channel coordination |
| `flag:` | `flag:<namespace>` | `flag:billing/*` | Feature flag ownership |
| `env:` | `env:<resource>` | `env:shared-fixtures` | Shared resource locking |
| `contract:` | `contract:<path>` | `contract:openapi/v1.yaml` | Contract artifact protection |
| `feature:` | `feature:<id>:<purpose>` | `feature:FEAT-123:pause` | Feature-level signals (pause/unpause) |

**Documentation**: [`docs/lock-key-namespaces.md`](lock-key-namespaces.md)
**Validation**: [`skills/validate-packages/scripts/validate_work_packages.py`](../skills/validate-packages/scripts/validate_work_packages.py) (canonicalization check), [`locks.py`](../agent-coordinator/src/locks.py) (`LOGICAL_LOCK_KEY_PATTERN`)

### Work Queue

Atomic task assignment with priority and DAG dependencies:

| Operation | MCP Tool | PL/pgSQL Function | Purpose |
|-----------|----------|-------------------|---------|
| Submit task | `submit_work(task_type, description, priority, input_data, depends_on)` | — | Add task to queue |
| Claim task | `get_work(task_types)` | `claim_task()` | Atomic claim (only one agent wins) |
| Complete task | `complete_work(task_id, success, result, error_message)` | `complete_task()` | Mark done with structured result |
| Poll status | `get_task(task_id)` | — | Orchestrator monitors progress |

**Cancellation convention**: `complete_work(success=false)` with `error_code="cancelled_by_orchestrator"` in result. No separate cancel RPC — uses existing complete_work infrastructure.

**Result schema**: [`openspec/schemas/work-queue-result.schema.json`](../openspec/schemas/work-queue-result.schema.json)

### Port Allocation

**Implementation**: [`port_allocator.py`](../agent-coordinator/src/port_allocator.py)

Conflict-free port blocks for parallel docker-compose stacks:
- Base port: 10000, range per session: 100
- 4 ports per block: `db_port`, `rest_port`, `realtime_port`, `api_port`
- TTL-based lease (default 60 minutes)
- MCP tools: `allocate_ports(session_id)`, `release_ports(session_id)`, `ports_status()`

---

## 8. Execution Protocol

### Three-Phase Execution

#### Phase A: Feature-Level Preflight (Orchestrator)

**Implementation**: [`dag_scheduler.py`](../skills/parallel-implement-feature/scripts/dag_scheduler.py)

| Step | Action | Coordinator Tool |
|------|--------|-----------------|
| A1 | Parse + validate `work-packages.yaml` (schema, DAG cycles, lock canonicalization) | — |
| A2 | Validate contract files exist on disk | — |
| A3 | Compute topological order (Kahn's algorithm) | — |
| A4 | Submit work queue tasks with dependency edges | `submit_work()` |
| A5 | Begin monitoring loop (poll `get_task()`, dispatch unblocked packages) | `get_task()`, `discover_agents()` |

#### Phase B: Worker Protocol (Every Package Agent)

**Implementation**: [`package_executor.py`](../skills/parallel-implement-feature/scripts/package_executor.py)

| Step | Action | Coordinator Tool | Failure Mode |
|------|--------|-----------------|--------------|
| B1 | Register session + start heartbeat (30s) | `register_session()`, `heartbeat()` | — |
| B2 | Check pause-lock `feature:<id>:pause` | `check_locks()` | Wait or exit with `PAUSED` |
| B3 | Acquire locks in sorted lexicographic order | `acquire_lock()` | Rollback all, backoff, retry (max 3) |
| B4 | Allocate ports for docker-compose | `allocate_ports()` | — |
| B5 | Read dependency results | `get_task(dependency_id)` | — |
| B6 | Code generation in isolated worktree | — | — |
| B7 | Deterministic scope check (`git diff` vs `write_allow \ deny`) | — | `SCOPE_VIOLATION` (blocking) |
| B8 | Run verification steps (Tier A/B/C) | — | `VERIFICATION_INFEASIBLE` escalation |
| B9 | Pause-lock re-check before finalizing | `check_locks()` | Wait or exit with `PAUSED` |
| B10 | Publish structured result | `complete_work()` | — |
| B11 | Cleanup: release ports, locks, stop heartbeat | `release_ports()`, `release_lock()` | Best-effort |

#### Phase C: Integration (Orchestrator)

**Implementation**: [`integration_orchestrator.py`](../skills/parallel-implement-feature/scripts/integration_orchestrator.py), [`result_validator.py`](../skills/parallel-implement-feature/scripts/result_validator.py)

| Step | Action | Notes |
|------|--------|-------|
| C1 | Validate all results (schema, revision matching, scope compliance) | [`validate_work_result.py`](../skills/validate-packages/scripts/validate_work_result.py) |
| C2 | Process escalations (deterministic action per type) | [`escalation_handler.py`](../skills/parallel-implement-feature/scripts/escalation_handler.py) |
| C3 | Dispatch per-package reviews | `/parallel-review-implementation` skill |
| C4 | Integration gate (all packages completed + reviewed, no blocking dispositions) | `IntegrationGateStatus`: PASS, BLOCKED_FIX, BLOCKED_ESCALATE |
| C5 | Merge worktrees, run full test suite, cross-package verification | `wp-integration` package claims union of all locks |
| C6 | Generate execution summary | DAG timeline, review findings, contract compliance |

### Escalation Protocol

**Implementation**: [`escalation_handler.py`](../skills/parallel-implement-feature/scripts/escalation_handler.py) (212 lines, 8 types)

| Type | Severity | Action | Requires Human |
|------|----------|--------|----------------|
| `CONTRACT_REVISION_REQUIRED` | BLOCKING | Pause DAG, bump `contracts.revision`, reschedule impacted packages | Sometimes |
| `PLAN_REVISION_REQUIRED` | BLOCKING | Pause DAG, bump `plan_revision`, restructure work packages | Yes |
| `RESOURCE_CONFLICT` | HIGH | Retry with exponential backoff, or fail | No |
| `SCOPE_VIOLATION` | BLOCKING | Fail package, require plan revision | No |
| `VERIFICATION_INFEASIBLE` | HIGH | Reassign to capable agent or create follow-up | No |
| `ENV_RESOURCE_CONFLICT` | MEDIUM | Retry with fresh port allocation, or fail | No |
| `SECURITY_ESCALATION` | BLOCKING | Pause DAG, emit report, require human approval | Yes |
| `FLAKY_TEST_QUARANTINE_REQUEST` | NON_BLOCKING | Quarantine test, re-run, don't block completion | No |

**Stop-the-line mechanism**: orchestrator acquires `feature:<id>:pause` lock. All workers check this lock at B2 (before starting) and B9 (before finalizing). This provides a coordinator-native signal that pauses all agents on a feature without cancelling their work.

### Circuit Breaker

**Implementation**: [`circuit_breaker.py`](../skills/parallel-implement-feature/scripts/circuit_breaker.py) (178 lines)

Not in the original proposal — added during implementation for robustness:
- Monitors heartbeats per package (detects stuck agents)
- Enforces retry budgets per package (prevents infinite loops)
- Propagates cancellation to transitive dependents when budget exhausted

### Verification Tiers

Defined in `work-packages.yaml` per package:

| Tier | Scope | Tools | When Used |
|------|-------|-------|-----------|
| **A** (local) | Full tooling | pytest, mypy, ruff, Schemathesis, Pact | Default for all packages |
| **B** (remote) | CI pipeline | Push, trigger CI, poll results | When local tooling insufficient |
| **C** (degraded) | Static checks only | Linting, type checking | When CI unavailable |

Evidence collected per [`work-queue-result.schema.json`](../openspec/schemas/work-queue-result.schema.json): each verification step records `name`, `kind` (command/ci/manual), `passed`, and `evidence` (artifacts, metrics).

---

## 9. Safety & Governance

### Trust Levels

**Implementation**: [`profiles.py`](../agent-coordinator/src/profiles.py)

| Level | Name | Capabilities |
|-------|------|--------------|
| 0 | Suspended | All operations denied |
| 1 | Restricted | Read-only |
| 2 | Standard | Read + write (default) |
| 3 | Advanced | Admin operations (force-push, DROP TABLE) |
| 4 | Superuser | All operations |

### Guardrails

**Implementation**: [`guardrails.py`](../agent-coordinator/src/guardrails.py)

Pattern-matching detection of destructive operations before task execution:
- Every `get_work()` claim passes through guardrails
- Scans task description + input_data for patterns (git force-push, rm -rf, DROP TABLE, env file access)
- Compares violation's `min_trust_level` against agent's trust level
- Blocks claim if insufficient trust; releases task back to queue

### Policy Engine

**Implementation**: [`policy_engine.py`](../agent-coordinator/src/policy_engine.py) (709 lines)

Two authorization backends:
- **Native** — `ProfilesService` + `NetworkPolicyService` (default)
- **Cedar** — AWS Cedar PARC model with policy caching

All coordinator operations follow: **policy check → execute → audit**

### Audit Trail

**Implementation**: [`audit.py`](../agent-coordinator/src/audit.py)

Immutable, append-only logging of all coordination operations. Best-effort (non-blocking) — audit failures don't prevent operations.

---

## 10. Implementation Status

### Fully Implemented (Production-Ready)

| Component | Status | Key Files |
|-----------|--------|-----------|
| Lock acquisition (deadlock-safe, lexicographic) | **Complete** | `locks.py`, `package_executor.py` |
| Lock key namespaces (9 prefixes) | **Complete** | `locks.py`, `validate_work_packages.py` |
| Work queue (DAG deps, atomic claiming) | **Complete** | `work_queue.py`, `coordination_mcp.py` |
| Work packages schema + validation | **Complete** | `work-packages.schema.json`, `validate_work_packages.py` |
| DAG scheduling (Kahn's algorithm) | **Complete** | `dag_scheduler.py` |
| Scope enforcement (deterministic diff check) | **Complete** | `scope_checker.py`, `validate_work_result.py` |
| Escalation protocol (8 types, deterministic) | **Complete** | `escalation_handler.py` |
| Port allocation (conflict-free blocks) | **Complete** | `port_allocator.py` |
| Feature registry (resource claims, conflict analysis) | **Complete** | `feature_registry.py` |
| Agent discovery + heartbeat | **Complete** | `discovery.py` |
| Handoffs + episodic memory | **Complete** | `handoffs.py`, `memory.py` |
| Guardrails + trust levels + policy engine | **Complete** | `guardrails.py`, `profiles.py`, `policy_engine.py` |
| Audit trail | **Complete** | `audit.py` |
| Circuit breaker | **Complete** | `circuit_breaker.py` |
| All 7 parallel skills | **Complete** | `skills/parallel-*/SKILL.md` |
| Review schemas (plan + implementation) | **Complete** | `review-findings.schema.json` |
| Worktree management | **Complete** | `skills/worktree/scripts/worktree.py` |

### Partially Implemented

| Component | Status | Gap |
|-----------|--------|-----|
| Contract-first tooling | Schema complete, agent-executed | No automated type generation (Pydantic/TS from OpenAPI) |
| Prism mock orchestration | Config in schema | Orchestrator doesn't start/verify Prism |
| Schemathesis / Pact execution | Config in schema | Agents responsible, no coordinator integration |
| Merge queue integration | Service + DB exist | Full cross-feature rebase coordination needs testing |

### Future Work

| Component | Status | Notes |
|-----------|--------|-------|
| `cancel_task(task_id, reason)` RPC | Proposed | Currently uses convention (`complete_work` + error_code) |
| Property-based testing vs TLA+ model | TLA+ model exists | Randomized test harness not yet built |
| Lean safety proofs | Types defined | Proofs not yet written |
| Cross-application coordination | Design principles only | No automated multi-repo orchestration |

### Differences from Original Proposal

| Area | Proposal | Implementation | Rationale |
|------|----------|---------------|-----------|
| Task cancellation | Dedicated `cancel_task()` RPC | Convention via `complete_work(error_code="cancelled_by_orchestrator")` | Simpler, no new schema |
| Circuit breaker | Not proposed | Added (`circuit_breaker.py`) | Robustness against stuck agents |
| Formal verification | TLA+ → Lean → property tests (phased) | TLA+ model + Lean types exist, proofs TBD | Incremental progress |
| Coordination levels | Two levels proposed | Three levels documented (added human/program level) | Reflects real-world usage |

---

## References

- **Original Proposal** (archived): [`docs/archive/two-level-parallel-agentic-development.md`](archive/two-level-parallel-agentic-development.md)
- **Lock Key Namespaces**: [`docs/lock-key-namespaces.md`](lock-key-namespaces.md)
- **Skills Workflow**: [`docs/skills-workflow.md`](skills-workflow.md)
- **Coordinator Overview**: [`docs/agent-coordinator.md`](agent-coordinator.md)
- **Lessons Learned**: [`docs/lessons-learned.md`](lessons-learned.md)
- **Architecture Artifacts**: [`docs/architecture-artifacts.md`](architecture-artifacts.md)
- **Presentation Slides**: [`docs/presentations/index.html`](presentations/index.html)
