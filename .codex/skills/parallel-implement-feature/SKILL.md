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

At skill start, run the coordinator detection script:

```bash
# Use the script bundled with this skill (resolve from skill base directory shown above)
python3 "<skill-base-dir>/scripts/check_coordinator.py" --json
```

Parse the JSON output to set capability flags. Required capabilities:

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

If `COORDINATOR_AVAILABLE` is `false` or required capabilities are unavailable, degrade to `/linear-implement-feature` behavior and emit a warning.

## Steps

### Phase A: Feature-Level Preflight (Orchestrator)

**Launcher Invariant**: The shared checkout is READ-ONLY. The orchestrator never modifies it directly. All work happens in worktrees.

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

A3.5. Generate Change Context & Test Plan (Phase 1 — TDD RED)
    - Read spec delta files from openspec/changes/<change-id>/specs/
    - For each SHALL/MUST clause, create a row in the Requirement Traceability Matrix
      with Req ID, Spec Source, Description, and planned Test(s)
    - Files Changed = "---", Evidence = "---"
    - If design.md exists, populate Design Decision Trace (Implementation = "---")
    - Write failing tests (RED) for each row in the matrix
    - Each work package's input_data context slice includes the relevant
      change-context.md rows so workers know which tests to make pass
    - Write change-context.md to openspec/changes/<change-id>/

A4. Create or reuse feature branch
    - git branch openspec/<change-id> main (if not exists)
    - If planning already created the branch, reuse it

A5. Implement root packages (sequentially, each in own worktree)
    - For each root package (depends_on == []):
      - python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup <change-id> --agent-id <package-id>
      - Implement in worktree
      - Commit + push on package branch
      - Merge package branch into feature branch (git merge --no-ff)
      - python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown <change-id> --agent-id <package-id>

A6. Setup worktrees for parallel packages
    - For each non-root package:
      - python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup <change-id> --agent-id <package-id>
      - Worktrees branch from feature branch (includes root package work)
    - Record WORKTREE_PATH and BRANCH in dispatch context per package
    - Pin all worktrees (prevent GC during execution)

A7. Dispatch parallel agents
    - For each parallel package, dispatch Agent with:
      - WORKTREE_PATH, BRANCH, CHANGE_ID, PACKAGE_ID in prompt
      - isolation="worktree" if vendor supports it (check agents.yaml isolation field)
      - Otherwise instruct agent to cd into WORKTREE_PATH

A8. Begin monitoring loop
    - Poll discover_agents() for agent health
    - Poll get_task(task_id) for each in-flight package
    - On each completion: dispatch newly unblocked packages
```

### Phase B: Package Execution Protocol (Every Worker Agent)

Each worker agent claiming a package via `get_work` MUST execute steps B1-B11 from the execution protocol (see design.md section 2.4).

Key steps: session registration, pause-lock check, deadlock-safe lock acquisition, code generation within scope, deterministic scope check via git diff, verification steps, structured result publication.

#### Agent Identity

Each worker agent MUST have a unique agent-id. The orchestrator assigns agent-ids based on `package_id` (e.g., `wp-backend`, `wp-frontend`). The integrator uses agent-id `integrator`.

#### Worktree Verification

The orchestrator sets up worktrees in Phase A. Workers verify they are in the correct worktree:

```bash
# Verify worktree path and branch (set by orchestrator in dispatch context)
ACTUAL_ROOT=$(git rev-parse --show-toplevel)
ACTUAL_BRANCH=$(git branch --show-current)

if [ "$ACTUAL_ROOT" != "$WORKTREE_PATH" ] || [ "$ACTUAL_BRANCH" != "$BRANCH" ]; then
    # Not in expected worktree — cd into it
    cd "$WORKTREE_PATH"
fi
```

If the worker was dispatched with vendor `isolation: "worktree"`, it operates in its own git copy. The prompt instructs it to commit to the branch name from the dispatch context.

#### Heartbeat Requirement

Workers MUST call heartbeat every 30 minutes during execution to prevent GC from reclaiming their worktree:

```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" heartbeat "${CHANGE_ID}" --agent-id "${PACKAGE_ID}"
```

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
    - python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup <change-id> --agent-id integrator
    - cd into integrator worktree
    - python3 "<skill-base-dir>/../worktree/scripts/merge_worktrees.py" <change-id> <pkg1> <pkg2> ... --json
    - If conflicts: report SCOPE_VIOLATION escalation, do NOT auto-resolve
    - Run full test suite and cross-package contract verification

C5.5. Finalize Change Context (Phase 2 completion)
    - Update Files Changed column by cross-referencing files_modified from
      artifacts/<package-id>/work-queue-result.json per package
    - Update Design Decision Trace Implementation column if design.md exists
    - Synthesize Review Findings Summary from all review-findings.json files:
      include findings with disposition fix, escalate, or regenerate;
      for accept, include only medium+ criticality
    - Update Coverage Summary with exact counts from integrated result

C6. Execution summary generation
    - DAG timeline, contract compliance, review findings
```

### Final Steps

After integration:
1. Run quality checks (pytest, mypy, ruff, openspec validate)
2. Create PR with execution summary attached
3. Write handoff if CAN_HANDOFF=true

### Teardown

After PR creation (or on failure):

```bash
# Unpin all worktrees
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" unpin "<change-id>"

# Teardown each package worktree + integrator
for pkg in <package-ids> integrator; do
    python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown "<change-id>" --agent-id "$pkg"
done

# Optional: garbage collect stale worktrees from other features
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" gc
```

## Output

- Feature branch: `openspec/<change-id>`
- All tests passing
- PR created with execution summary

## Next Step

After PR is approved:
```
/parallel-cleanup-feature <change-id>
```
