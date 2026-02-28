# Change: add-two-level-parallel-development

## Why

The agentic-coding-tools project executes features sequentially through lifecycle phases (explore, plan, implement, validate, cleanup). When AI agents produce working code in minutes, this sequential structure becomes the primary bottleneck: gate latency and phase transition overhead dominate wall-clock time, a single agent per skill underutilizes available parallelism, and monolithic post-implementation validation discovers problems too late.

The cost structure has inverted. Code synthesis is no longer the dominant cost — ideation, specification, evaluation, and integration are. Two features that could be built in parallel are serialized because there is no mechanism to coordinate their resource claims. Within a single feature, if the work touches the API layer, a React component, and a database migration, three agents working in parallel on separate worktrees would complete faster and produce more focused code.

This change introduces two explicit levels of parallelism — cross-feature and intra-feature — with a new `parallel-*` skill family alongside the existing skills (renamed to `linear-*`), enabling both workflows to coexist while the parallel model matures.

## What Changes

### Skill Family Architecture
- **Rename** existing skills to `linear-*` prefix with backward-compatible aliases.
- **NEW** `parallel-*` skill family: `parallel-explore-feature`, `parallel-plan-feature`, `parallel-implement-feature`, `parallel-review-plan`, `parallel-review-implementation`, `parallel-validate-feature`, `parallel-cleanup-feature`.
- Add `CAN_DISCOVER`, `CAN_POLICY`, `CAN_AUDIT` capability flags for coordinator feature detection.

### Contract-First Development
- **NEW** contracts phase producing machine-readable interface definitions (OpenAPI specs, generated Pydantic/TypeScript types, SQL schema definitions, event schemas, Prism mocks).
- Three-layer contract compliance verification: static type checking, Schemathesis property-based testing, Pact consumer-driven contract tests.
- Contract revision semantics: any contract file modification after implementation dispatch bumps the revision and triggers rescheduling.

### Work Packages and DAG Scheduling
- **NEW** `work-packages.yaml` artifact: versioned, validated execution contract grouping tasks into agent-scoped packages with deterministic scheduling.
- `work-packages.schema.json` and `work-queue-result.schema.json` (already extracted to `openspec/schemas/`).
- DAG dependency graph with topological sort, cycle detection, and cancellation propagation.
- Scope enforcement via write/read/deny globs with deterministic diff checks.
- Logical lock key namespaces (`api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:`) stored in the existing `file_locks.file_path` column.

### Execution Protocol
- Phase A (orchestrator preflight): parse, validate, compute DAG, submit work queue tasks, monitor.
- Phase B (worker protocol): session registration, pause-lock checks, deadlock-safe lock acquisition, code generation within scope, deterministic scope check, verification, structured result publication.
- Phase C (review + integration): result validation, escalation processing, per-package review, integration merge as first-class work package.

### Escalation Protocol
- Structured escalation types: `CONTRACT_REVISION_REQUIRED`, `PLAN_REVISION_REQUIRED`, `RESOURCE_CONFLICT`, `VERIFICATION_INFEASIBLE`, `SCOPE_VIOLATION`, `ENV_RESOURCE_CONFLICT`, `SECURITY_ESCALATION`, `FLAKY_TEST_QUARANTINE_REQUEST`.
- Stop-the-line mechanism using `feature:<id>:pause` lock keys.
- Contract revision bump and plan revision bump procedures.

### Coordinator Extensions
- **Delta A**: Expose `get_task(task_id)` as MCP tool + HTTP endpoint for dependency result reads.
- **Delta B**: Cancellation convention using `complete_work(success=false)` with `error_code="cancelled_by_orchestrator"`.
- **Delta C**: Lock key policy updates to permit `api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:` patterns.

### Review Agent Decoupling
- **NEW** `/parallel-review-plan` and `/parallel-review-implementation` as independent, vendor-agnostic review agents.
- `review-findings.schema.json` (already extracted to `openspec/schemas/`).
- Findings dispositions: `fix`, `regenerate`, `accept`, `escalate`.

### Feature Registry and Cross-Feature Coordination
- **NEW** feature registry for cross-feature resource claim management and conflict detection.
- Parallel feasibility assessment: `FULL`, `PARTIAL`, or `SEQUENTIAL`.

### Verification Tiers
- Tier A (local): full CLI tooling (pytest, mypy, ruff, Schemathesis, Pact).
- Tier B (remote): CI pipeline trigger and poll.
- Tier C (degraded): static checks only, flags for follow-up.

## Impact

- Affected specs:
  - `skill-workflow` via `openspec/changes/add-two-level-parallel-development/specs/skill-workflow/spec.md`
  - `agent-coordinator` via `openspec/changes/add-two-level-parallel-development/specs/agent-coordinator/spec.md`
- Affected code:
  - `skills/linear-*/SKILL.md` (renamed from existing skills)
  - `skills/parallel-*/SKILL.md` (new skill family)
  - `agent-coordinator/src/agent_coordinator/services/work_queue.py` (expose `get_task`)
  - `agent-coordinator/src/agent_coordinator/mcp_server.py` (new `get_task` tool)
  - `agent-coordinator/src/agent_coordinator/http_api.py` (new `/api/v1/tasks/{task_id}` endpoint)
  - `agent-coordinator/src/agent_coordinator/services/lock_service.py` (policy updates for key namespaces)
  - `agent-coordinator/src/agent_coordinator/services/feature_registry.py` (new)
  - `scripts/parallel_zones.py` (add `--validate-packages` mode)
  - `openspec/schemas/work-packages.schema.json` (already exists)
  - `openspec/schemas/work-queue-result.schema.json` (already exists)
  - `openspec/schemas/review-findings.schema.json` (already exists)
- Affected docs:
  - `CLAUDE.md` (workflow section update for dual skill families)
  - `AGENTS.md` (skill catalog update)
  - `docs/skills-workflow.md` (parallel workflow documentation)
  - `docs/agent-coordinator.md` (new capabilities)
- Affected architecture layers:
  - **Execution**: DAG scheduling, multi-worktree dispatch, scope enforcement, verification tiers
  - **Coordination**: work packages, logical lock keys, feature registry, escalation protocol
  - **Trust**: contract-first development, deterministic scope checks, pause-lock mechanism
  - **Governance**: review agent decoupling, vendor-diverse evaluation, audit trail
- Breaking changes: None. `parallel-*` skills are additive. Existing skills are renamed to `linear-*` with backward-compatible aliases.

## Non-Goals

- Replacing human approval gates at plan approval and PR review.
- Building a general-purpose multi-agent orchestration framework.
- Automating product ideation or specification writing.
