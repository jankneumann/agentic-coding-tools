---
name: parallel-implement-feature
description: Implement approved OpenSpec proposal using DAG-scheduled multi-agent parallel execution
category: Git Workflow
tags: [openspec, implementation, pr, parallel, dag, work-packages]
triggers:
  - "parallel implement feature"
  - "parallel implement"
  - "parallel build feature"
requires:
  coordinator:
    required: [CAN_DISCOVER, CAN_QUEUE_WORK, CAN_LOCK]
    safety: [CAN_GUARDRAILS]
    enriching: [CAN_HANDOFF, CAN_MEMORY, CAN_POLICY, CAN_AUDIT]
---

# Parallel Implement Feature

Implement an approved OpenSpec proposal using DAG-scheduled multi-agent parallel execution. Each work package runs in its own worktree with explicit scope and lock claims. Degrades to linear-implement-feature behavior when the coordinator is unavailable.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required)

## Prerequisites

- Approved OpenSpec proposal with `work-packages.yaml` at `openspec/changes/<change-id>/`
- Contracts generated at `openspec/changes/<change-id>/contracts/`
- Coordinator available with required capabilities

## Coordinator Capability Check

At skill start, detect coordinator capabilities:

```
REQUIRED (hard failure without coordinator):
  CAN_DISCOVER  — discover_agents() for agent health monitoring
  CAN_QUEUE_WORK — submit_work()/get_work()/complete_work()/get_task() for DAG dispatch
  CAN_LOCK — acquire_lock()/release_lock()/check_locks() for resource claims

REQUIRED (safety):
  CAN_GUARDRAILS — check_guardrails() for destructive operation detection

ENRICHING (degrades gracefully):
  CAN_HANDOFF — write_handoff() for orchestrator resumability
  CAN_MEMORY — remember()/recall() for procedural memories
  CAN_POLICY — check_policy() for authorization decisions
  CAN_AUDIT — query_audit() for execution summary generation
```

If required capabilities are unavailable, degrade to `/linear-implement-feature` behavior and emit a warning.

## Steps

### Phase A: Feature-Level Preflight (Orchestrator)

```
A1. Parse and validate work-packages.yaml
    - YAML parse + validate against work-packages.schema.json
    - Lock key canonicalization check
    - File scope non-overlap for parallel packages
    - Logical lock non-overlap for parallel packages

A2. Validate contracts exist
    - Every file in contracts.openapi.files exists on disk
    - Primary OpenAPI file parses without errors

A3. Compute DAG order
    - Build directed graph from packages[].depends_on
    - Detect cycles (validation error if found)
    - Topological sort for execution order

A4. Submit work queue tasks
    - For each package in topological order:
      - Resolve depends_on package_ids to task_ids
      - Build input_data envelope with context slice
      - submit_work() with task_type, description, priority, depends_on

A5. Begin monitoring loop
    - Poll discover_agents() for agent health
    - Poll get_task(task_id) for each in-flight package
    - On each completion: dispatch newly unblocked packages
```

### Phase B: Package Execution Protocol (Every Worker Agent)

Each worker agent claiming a package via `get_work` MUST execute steps B1-B11 from the execution protocol (see design.md section 2.4).

Key steps: session registration, pause-lock check, deadlock-safe lock acquisition, code generation within scope, deterministic scope check via git diff, verification steps, structured result publication.

### Phase C: Review + Integration Sequencing

```
C1. Result validation (on each package completion)
    - Validate result against work-queue-result.schema.json
    - Verify contracts_revision and plan_revision match

C2. Escalation processing
    - Execute escalation protocol for any escalations

C3. Per-package review
    - Dispatch /parallel-review-implementation on each package diff

C4. Integration gate
    - Wait for all packages COMPLETED and reviewed

C5. Integration merge (wp-integration package)
    - Merge all worktrees into feature branch
    - Run full test suite and cross-package contract verification

C6. Execution summary generation
    - DAG timeline, contract compliance, review findings
```

### Final Steps

After integration:
1. Run quality checks (pytest, mypy, ruff, openspec validate)
2. Create PR with execution summary attached
3. Write handoff if CAN_HANDOFF=true

## Output

- Feature branch: `openspec/<change-id>`
- All tests passing
- PR created with execution summary

## Next Step

After PR is approved:
```
/parallel-cleanup-feature <change-id>
```
