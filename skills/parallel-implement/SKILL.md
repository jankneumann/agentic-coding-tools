---
name: parallel-implement
description: Implement OpenSpec proposals using parallel Task() subagents for independent tasks. Use when implementing features with multiple independent tasks that can be parallelized. Extends implement-feature with native multi-agent orchestration.
category: Git Workflow
tags: [openspec, implementation, parallel, multi-agent, beads, orchestration]
triggers:
  - "parallel implement"
  - "implement with agents"
  - "spawn agents"
  - "parallel build"
  - "multi-agent implement"
---

# Parallel Implement Feature

Implement OpenSpec proposals using parallel Task() subagents. The orchestrator identifies independent tasks, spawns worker agents using the native Task() tool, and coordinates completion without requiring git worktrees.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required)

## Prerequisites

- Approved OpenSpec proposal at `openspec/changes/<change-id>/`
- Beads CLI installed (optional, for task tracking): `bd --version`
- Run `/plan-feature` first if no proposal exists

## Workflow Overview

```
┌─────────────────┐
│  Orchestrator   │ ← You (main Claude session)
└────────┬────────┘
         │ 1. Load tasks from OpenSpec
         │ 2. Identify independent vs sequential tasks
         │ 3. Create beads for tracking (optional)
         │ 4. Spawn parallel Task() agents
         ▼
    ┌────┼────┬────┐
    ▼    ▼    ▼    ▼
┌──────┐┌──────┐┌──────┐┌──────┐
│Task()││Task()││Task()││Task()│  ← Native subagents (no worktrees)
│Agent ││Agent ││Agent ││Agent │  ← run_in_background=true
└──┬───┘└──┬───┘└──┬───┘└──┬───┘
   │       │       │       │
   └───────┴───────┴───────┘
         │ 5. Collect results via TaskOutput
         │ 6. Verify and commit
         ▼
┌─────────────────┐
│  Orchestrator   │ ← Integrate, test, PR
└─────────────────┘
```

**Key difference from old pattern**: No git worktrees needed. Task() agents are coordinated by the orchestrator and scoped to non-overlapping files via prompts.

## Steps

### 1. Verify Proposal and Analyze Tasks

```bash
openspec show <change-id>
cat openspec/changes/<change-id>/tasks.md
```

Classify each task:
- **Independent**: No shared files/state with other tasks → can parallelize
- **Sequential**: Shares files or depends on another task → must run in order

**File overlap check**: If two tasks modify the same file, they MUST be sequential. Review the `**Files**` annotation in tasks.md.

### 2. Setup Feature Branch

```bash
git checkout main && git pull origin main
git checkout -b openspec/<change-id>
```

### 3. Create Beads for Task Tracking (Optional)

If using Beads for tracking:

```bash
# Create beads from independent tasks
bd add "Implement task 1 - OpenSpec <change-id>"
bd add "Implement task 2 - OpenSpec <change-id>"

# For sequential tasks, use blocking
A_ID=$(bd add "Task A - foundation")
B_ID=$(bd add "Task B - depends on A" --blocked-by $A_ID)

# Verify
bd list
```

**Note**: Beads is optional. You can track progress directly in tasks.md instead.

### 4. Spawn Parallel Task() Agents

For each independent task, spawn a Task(general-purpose) agent with `run_in_background=true`. **Send all parallel tasks in a single message:**

```
# Example: 3 independent tasks spawned in parallel
Task(
  subagent_type="general-purpose",
  description="Implement task 1: <brief>",
  prompt="You are implementing OpenSpec <change-id>, Task 1.

## Your Task
<TASK_DESCRIPTION from tasks.md>

## Scope
Files you may modify: <list specific files>
Files you must NOT modify: <everything else>

## Context
- Read openspec/changes/<change-id>/proposal.md for full context
- Read openspec/changes/<change-id>/design.md for architectural decisions

## Process
1. Read the proposal and design docs
2. Write failing tests first (TDD)
3. Implement minimal code to pass tests
4. Run tests: pytest <relevant_test_file>
5. Report completion with summary of changes made

Do NOT commit - the orchestrator will handle commits.",
  run_in_background=true
)

Task(
  subagent_type="general-purpose",
  description="Implement task 2: <brief>",
  prompt="...",
  run_in_background=true
)

Task(
  subagent_type="general-purpose",
  description="Implement task 3: <brief>",
  prompt="...",
  run_in_background=true
)
```

**Critical**: Each agent's prompt MUST explicitly list which files are in scope. This prevents conflicts.

### 5. Monitor and Collect Results

Background agents will complete and return results. For each agent:

1. Check TaskOutput for completion status
2. Review the agent's reported changes
3. Verify no out-of-scope modifications: `git status`

If an agent fails:
- Check the error in TaskOutput
- Use `Task(resume=<agent_id>)` to retry with context
- Or fix manually and continue

### 6. Handle Sequential Tasks

After parallel tasks complete, run any sequential tasks:

```
Task(
  subagent_type="general-purpose",
  description="Implement sequential task: <brief>",
  prompt="...",
  run_in_background=false  # Wait for completion
)
```

Sequential tasks run one at a time, waiting for each to complete.

### 7. Verify Integration

After all tasks complete:

```bash
# Run full test suite
pytest

# Type check and lint
mypy src/ && ruff check .

# Validate OpenSpec
openspec validate <change-id> --strict
```

**If tests fail**: Review which agent's changes caused the issue. The orchestrator can see all changes and fix integration problems.

### 8. Update Task Tracking

```bash
# Mark all tasks complete in tasks.md
# Edit tasks.md: change "- [ ]" to "- [x]" for completed tasks

# If using Beads
bd close <bead_id>  # for each completed bead
```

### 9. Commit and PR

```bash
git add .
git commit -m "$(cat <<'EOF'
feat(<scope>): <description>

Implements OpenSpec: <change-id>
Parallel execution: <N> tasks

- <task 1 summary>
- <task 2 summary>
- <task 3 summary>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

git push -u origin openspec/<change-id>

gh pr create --title "feat(<scope>): <title>" --body "$(cat <<'EOF'
## Summary
Implements OpenSpec: `<change-id>` using parallel Task() agents.

**Proposal**: `openspec/changes/<change-id>/proposal.md`

### Parallel Execution
- Independent tasks: <N>
- Sequential tasks: <M>

### Changes
- <bullet points summarizing changes>

## Test Plan
- [ ] All tests pass (`pytest`)
- [ ] Type checks pass (`mypy src/`)
- [ ] Linting passes (`ruff check .`)
- [ ] OpenSpec validates
- [ ] All tasks complete in `tasks.md`

---
🤖 Generated with Claude Code (parallel agents)
EOF
)"
```

## Agent Prompt Templates

### Minimal Agent Prompt

```
Implement OpenSpec <change-id>, Task <N>: <TASK_TITLE>
Scope: Only modify <file1>, <file2>
Read: openspec/changes/<change-id>/proposal.md
Write tests first. Report changes when done.
```

### Detailed Agent Prompt

```
You are a worker agent implementing part of OpenSpec <change-id>.

## Your Task
<TASK_DESCRIPTION>

## File Scope (CRITICAL)
You MAY modify:
- src/module/file1.py
- tests/test_file1.py

You must NOT modify any other files. If you need changes outside your scope, report this to the orchestrator instead of making the change.

## Context
- Proposal: openspec/changes/<change-id>/proposal.md
- Design: openspec/changes/<change-id>/design.md

## Process
1. Read the proposal for context
2. Write failing tests first (TDD)
3. Implement minimal code to pass tests
4. Run tests: pytest tests/test_file1.py
5. Report: files changed, tests added, any issues encountered

## Important
- Do NOT commit changes (orchestrator handles this)
- Do NOT modify files outside your scope
- Do NOT install new dependencies without reporting
```

## Coordination Patterns

### Independent Tasks (Parallel)

Tasks with no file overlap run simultaneously:

```
Task 1: src/auth/login.py, tests/test_login.py
Task 2: src/api/endpoints.py, tests/test_endpoints.py
Task 3: src/utils/helpers.py, tests/test_helpers.py

→ All 3 spawn in parallel
```

### Sequential Dependencies

Tasks that share files or have logical dependencies:

```
Task A: src/models/user.py (foundation)
Task B: src/auth/login.py (imports user model)

→ Task A completes first, then Task B
```

### Mixed Pattern

```
Independent: Tasks 1, 2, 3 (parallel)
Sequential: Task 4 depends on Task 1
Sequential: Task 5 depends on Tasks 2, 3

Execution:
1. Spawn Tasks 1, 2, 3 in parallel
2. When Task 1 completes → spawn Task 4
3. When Tasks 2 AND 3 complete → spawn Task 5
```

## Why No Worktrees?

The old pattern used git worktrees because external `claude -p` processes had no coordination—two agents editing the same file would corrupt it.

Task() agents don't need worktrees because:
1. **Prompt scoping**: Each agent's prompt explicitly lists allowed files
2. **Orchestrator control**: Parent coordinates what runs when
3. **No file overlap**: Independent tasks target different files (enforced by task design)
4. **Result review**: Orchestrator verifies changes before committing

**When worktrees would still be needed**: Only if you wanted concurrent edits to the same file, which the workflow prohibits.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent modifies wrong file | Clearer file scope in prompt; review before commit |
| Agent hangs | Use TaskOutput to check status; resume or restart |
| Integration test fails | Run tests after each agent completes; fix before next |
| Two agents need same file | Make tasks sequential, not parallel |
| Agent reports blocker | Resume agent with guidance, or fix manually |

## Output

- Feature branch: `openspec/<change-id>`
- All tests passing
- Beads closed (if using)
- PR created and awaiting review

## Next Step

After PR approved: `/cleanup-feature <change-id>`
