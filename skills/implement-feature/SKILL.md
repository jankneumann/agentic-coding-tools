---
name: implement-feature
description: "Implement approved OpenSpec proposal with tiered execution (coordinated / local-parallel / sequential)"
category: Git Workflow
tags: [openspec, implementation, pr, parallel, dag, work-packages]
triggers:
  - "implement feature"
  - "build feature"
  - "start implementation"
  - "begin implementation"
  - "code feature"
  - "linear implement feature"
  - "parallel implement feature"
  - "parallel implement"
  - "parallel build feature"
---

# Implement Feature

Implement an approved OpenSpec proposal. Automatically selects execution tier based on coordinator availability and existing artifacts. Ends when PR is created and awaiting review.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required)

## Prerequisites

- Approved OpenSpec proposal exists at `openspec/changes/<change-id>/`
- Run `/plan-feature` first if no proposal exists

## OpenSpec Execution Preference

Use OpenSpec-generated runtime assets first, then CLI fallback:
- Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- Fallback: direct `openspec` CLI commands

## Steps

### 0. Detect Coordinator and Select Tier [all tiers]

Run the coordinator detection script:

```bash
python3 "<skill-base-dir>/../coordination-bridge/scripts/check_coordinator.py" --json
```

Parse JSON output and set capability flags. Then select tier:

```
If COORDINATOR_AVAILABLE and CAN_DISCOVER and CAN_QUEUE_WORK and CAN_LOCK:
  TIER = "coordinated"
Else if work-packages.yaml exists at openspec/changes/<change-id>/:
  TIER = "local-parallel"
Else if tasks.md has 3+ independent tasks with non-overlapping file scopes:
  TIER = "local-parallel"
Else:
  TIER = "sequential"
```

Emit tier notification:
```
Tier: <tier> -- <rationale>
```

If `CAN_HANDOFF=true`, read recent handoff context.

### 1. Verify Proposal Exists [all tiers]

```bash
openspec show <change-id>
cat openspec/changes/<change-id>/tasks.md
```

Confirm the proposal is approved before proceeding.

### 2. Setup Worktree for Feature Isolation [all tiers]

```bash
AGENT_FLAG=""
if [[ -n "${AGENT_ID:-}" ]]; then
  AGENT_FLAG="--agent-id ${AGENT_ID}"
fi

eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "<change-id>" ${AGENT_FLAG})"
cd "$WORKTREE_PATH"
```

### 3. Verify Feature Branch [all tiers]

```bash
git branch --show-current  # Should show openspec/<change-id>
```

### 3a. Generate Change Context & Test Plan (Phase 1 -- TDD RED) [all tiers]

Before implementing, create the traceability skeleton and write failing tests:

1. Read spec delta files from `openspec/changes/<change-id>/specs/`. For each SHALL/MUST clause, create a row in the Requirement Traceability Matrix.
2. If `design.md` exists, populate Design Decision Trace.
3. Write failing tests (RED) for each row in the matrix.

Use template from `openspec/schemas/feature-workflow/templates/change-context.md`. Write to `openspec/changes/<change-id>/change-context.md`.

### 3b. Implement Tasks (Phase 2 -- TDD GREEN)

Implementation strategy depends on the selected tier:

---

#### Sequential Tier [sequential]

Work through tasks sequentially from `tasks.md`. Use the runtime-native apply workflow or CLI fallback:

```bash
openspec instructions apply --change "<change-id>" --json
openspec status --change "<change-id>"
```

##### Parallel Implementation (for independent tasks)

When tasks.md contains 3+ **independent tasks** (no shared files), implement concurrently:

```
Task(
  subagent_type="general-purpose",
  description="Implement task N: <brief>",
  prompt="You are implementing OpenSpec <change-id>, Task N.
## Your Task
<TASK_DESCRIPTION>
## File Scope (CRITICAL)
You MAY modify: <list specific files>
You must NOT modify any other files.
## Context
- Read openspec/changes/<change-id>/proposal.md
- Read openspec/changes/<change-id>/design.md
Do NOT commit - the orchestrator will handle commits.",
  run_in_background=true
)
```

**When to parallelize:** 3+ independent tasks with no file overlap.
**When NOT to:** Tasks that share files/state or have logical dependencies.

---

#### Local Parallel Tier [local-parallel]

Uses `work-packages.yaml` for structured DAG execution within a **single feature worktree**.

**A. Parse and validate work-packages.yaml:**

```bash
skills/.venv/bin/python "<skill-base-dir>/../parallel-infrastructure/scripts/dag_scheduler.py" \
  --validate openspec/changes/<change-id>/work-packages.yaml
```

Compute topological order from `packages[].depends_on`.

**B. Execute root packages sequentially:**

For each root package (depends_on == []), implement within the feature worktree.

**C. Dispatch independent packages in parallel:**

For each package whose dependencies are satisfied, dispatch via Agent tool:

```
Task(
  subagent_type="general-purpose",
  description="Implement <package-id>",
  prompt="You are implementing work package <package-id> for OpenSpec <change-id>.

## File Scope (CRITICAL)
write_allow: <from work-packages.yaml>
read_allow: <from work-packages.yaml>
deny: <from work-packages.yaml>

## Context
<context slice from Context Slicing table below>

## Verification
After implementation, run:
<verification steps from work-packages.yaml>

Do NOT commit - the orchestrator will handle commits.",
  run_in_background=true
)
```

**D. Collect results and verify scope:**

```bash
skills/.venv/bin/python "<skill-base-dir>/../parallel-infrastructure/scripts/scope_checker.py" \
  --packages openspec/changes/<change-id>/work-packages.yaml \
  --diff <git diff output>
```

**E. Update change-context.md:**

- Fill Files Changed column from `git diff --name-only main..HEAD`
- Update Design Decision Trace if design.md exists
- Update Coverage Summary counts

---

#### Coordinated Tier [coordinated]

Full multi-agent DAG execution with coordinator integration. Each work package runs in its own worktree with explicit lock claims.

##### Phase A: Feature-Level Preflight (Orchestrator)

```
A1. Parse and validate work-packages.yaml against schema
A2. Validate contracts exist
A3. Compute DAG order (topological sort, cycle detection)
A3.5. Generate Change Context with relevant rows per package
A4. Create or reuse feature branch
A5. Implement root packages (sequentially, each in own worktree)
A6. Setup worktrees for parallel packages (branch from feature branch)
A7. Dispatch parallel agents with WORKTREE_PATH, BRANCH, CHANGE_ID, PACKAGE_ID
A8. Begin monitoring loop (discover_agents, get_task polling)
```

##### Phase B: Package Execution Protocol (Every Worker Agent)

Each worker agent follows steps B1-B11: session registration, pause-lock check, deadlock-safe lock acquisition (lexicographic order), code generation within scope, deterministic scope check via git diff, verification steps, structured result publication.

Workers MUST call heartbeat every 30 minutes:
```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" heartbeat "${CHANGE_ID}" --agent-id "${PACKAGE_ID}"
```

##### Phase C: Review + Integration Sequencing

```
C1. Result validation against work-queue-result.schema.json
C2. Escalation processing
C3. Per-package multi-vendor review (via /parallel-review-implementation)
    - Self-review + vendor dispatch via parallel-infrastructure/scripts/review_dispatcher.py
    - Consensus synthesis via parallel-infrastructure/scripts/consensus_synthesizer.py
C4. Integration gate (consensus-aware)
C5. Integration merge (wp-integration package, merge_worktrees.py)
C5.5. Finalize Change Context (Files Changed, Design Decision Trace, Review Findings Summary)
C6. Execution summary generation
```

**Teardown** (after PR creation or on failure):
```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" unpin "<change-id>"
for pkg in <package-ids> integrator; do
    python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown "<change-id>" --agent-id "$pkg"
done
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" gc
```

---

### 4. Track Progress [all tiers]

Use TodoWrite to track implementation. Mark complete as you progress.

### 5. Verify All Tasks Complete [all tiers]

```bash
grep -E "^\s*- \[ \]" openspec/changes/<change-id>/tasks.md
# Should return nothing (all boxes checked)
```

### 6. Quality Checks (Parallel Execution) [all tiers]

Run all environment-safe checks. These must pass in both cloud and local environments:

```
Task(subagent_type="Bash", prompt="Run pytest and report pass/fail", run_in_background=true)
Task(subagent_type="Bash", prompt="Run mypy src/ and report type errors", run_in_background=true)
Task(subagent_type="Bash", prompt="Run ruff check . and report linting issues", run_in_background=true)
Task(subagent_type="Bash", prompt="Run openspec validate <change-id> --strict", run_in_background=true)
Task(subagent_type="Bash", prompt="Run validate_flows.py --diff main...HEAD", run_in_background=true)
```

Fix all failures before proceeding.

### 6.5. Artifact Validation [local-parallel+]

**Skip if TIER is "sequential".**

Delegate to `/validate-feature` for environment-safe validation phases:

```
/validate-feature <change-id> --phase spec,evidence
```

This runs the canonical validation skill targeting:
- **Spec compliance** (`spec` phase): Audits `change-context.md` Requirement Traceability Matrix — verifies no `---` entries in Files Changed, updates Coverage Summary counts, and checks each requirement against the implementation.
- **Evidence completeness** (`evidence` phase): Validates work-package results against `work-queue-result.schema.json`, checks revision consistency, scope compliance, and cross-package consistency. Populates the Evidence column in `change-context.md`.

These phases are environment-safe and run in both cloud and local. Docker-dependent phases (deploy, smoke, security, E2E) are deferred to the merge-time validation gate in `/cleanup-feature` or `/merge-pull-requests`.

### 7. Document Lessons Learned [all tiers]

Document patterns, gotchas, and design changes in CLAUDE.md and AGENTS.md.

### 8. Commit Changes [all tiers]

```bash
git add .
git commit -m "$(cat <<'EOF'
feat(<scope>): <description>

Implements OpenSpec: <change-id>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### 9. Push and Create PR [all tiers]

```bash
git push -u origin openspec/<change-id>
gh pr create --title "feat(<scope>): <title>" --body "..."
```

If `CAN_HANDOFF=true`, write a completion handoff.

**STOP HERE -- Wait for PR approval before proceeding to cleanup.**

## Context Slicing for Implementation

When dispatching work packages, each agent receives only the context it needs:

| Package Type | Context Slice |
|-------------|---------------|
| `wp-contracts` | `proposal.md` + spec deltas + contract templates |
| Backend packages | `design.md` (backend section) + `contracts/openapi/` + package scope |
| Frontend packages | `design.md` (frontend section) + `contracts/generated/types.ts` + package scope |
| `wp-integration` | Full `work-packages.yaml` + all contract artifacts |

## Output

- Feature branch: `openspec/<change-id>`
- All tests passing
- PR created and awaiting review

## Next Step

After PR is approved:
```
/cleanup-feature <change-id>
```
