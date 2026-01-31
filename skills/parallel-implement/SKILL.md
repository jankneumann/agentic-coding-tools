---
name: parallel-implement
description: Implement OpenSpec proposals using parallel Claude agents for independent tasks. Use when implementing features with multiple independent tasks that can be parallelized, when you want to spawn multiple Claude CLI instances, or when using Beads (bd) for task coordination. Extends implement-feature with multi-agent orchestration.
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

Implement OpenSpec proposals using parallel Claude agents. The orchestrator identifies independent tasks via Beads, spawns worker agents, and coordinates completion.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (required)

## Prerequisites

- Approved OpenSpec proposal at `openspec/changes/<change-id>/`
- Beads CLI installed (`bd --version`)
- Claude CLI installed (`claude --version`)
- Run `/plan-feature` first if no proposal exists

## Workflow Overview

```
┌─────────────────┐
│  Orchestrator   │ ← You (main Claude session)
└────────┬────────┘
         │ 1. Load tasks from OpenSpec
         │ 2. Create beads for independent tasks
         │ 3. Create git worktrees per bead
         │ 4. Spawn parallel agents
         ▼
┌────────┴────────┐
│   Beads (bd)    │ ← Task coordination layer
└────────┬────────┘
         │
    ┌────┼────┬────┐
    ▼    ▼    ▼    ▼
┌──────┐┌──────┐┌──────┐┌──────┐
│ WT-1 ││ WT-2 ││ WT-3 ││ WT-4 │  ← Isolated git worktrees
│Agent ││Agent ││Agent ││Agent │  ← Parallel Claude CLI instances
└──┬───┘└──┬───┘└──┬───┘└──┬───┘
   │       │       │       │
   └───────┴───────┴───────┘
         │ 5. Agents commit & close beads
         │ 6. Merge branches
         ▼
┌─────────────────┐
│  Orchestrator   │ ← Resume: verify, cleanup, PR
└─────────────────┘
```

## Steps

### 1. Verify Proposal and Analyze Tasks

```bash
openspec show <change-id>
cat openspec/changes/<change-id>/tasks.md
```

Identify tasks that are **independent** (no shared state, can run in parallel):
- Separate modules/files
- Independent test suites
- Non-overlapping functionality

Tasks with dependencies must be **sequential** (same agent or ordered execution).

### 2. Setup Feature Branch

```bash
git checkout main && git pull origin main
git checkout -b openspec/<change-id>
```

### 3. Create Beads for Parallel Tasks

Initialize beads for each independent task:

```bash
# Create beads from independent tasks
bd add "Implement auth module - OpenSpec <change-id> task 1"
bd add "Implement API endpoints - OpenSpec <change-id> task 2"
bd add "Add unit tests for auth - OpenSpec <change-id> task 3"

# Verify beads created
bd list
```

**Bead naming convention**: `<brief description> - OpenSpec <change-id> task <n>`

### 4. Create Worktrees for Agent Isolation

Each agent gets its own git worktree to prevent conflicts:

```bash
CHANGE_ID="<change-id>"
WORKTREE_BASE="../worktrees-$CHANGE_ID"
mkdir -p "$WORKTREE_BASE"

# Create a worktree per bead
bd ready --json | jq -r '.[] | .id' | while read bead_id; do
  BRANCH="agent-$bead_id"
  git worktree add "$WORKTREE_BASE/$bead_id" -b "$BRANCH"
  echo "Created worktree: $WORKTREE_BASE/$bead_id (branch: $BRANCH)"
done
```

### 5. Spawn Parallel Agents

**Recommended approach with worktrees and logging:**

```bash
CHANGE_ID="<change-id>"
WORKTREE_BASE="../worktrees-$CHANGE_ID"
LOGDIR="logs/openspec-$CHANGE_ID"
mkdir -p "$LOGDIR"

bd ready --json | jq -r '.[] | .id' | while read bead_id; do
  TASK=$(bd show $bead_id --json | jq -r '.title')
  AGENT_DIR="$WORKTREE_BASE/$bead_id"
  
  (cd "$AGENT_DIR" && claude -p "You are implementing OpenSpec $CHANGE_ID.

Your task: $TASK

You are in an isolated git worktree at: $AGENT_DIR
Your branch: agent-$bead_id

Instructions:
1. Read openspec/changes/$CHANGE_ID/proposal.md for context
2. Implement ONLY your assigned task
3. Write tests first (TDD)
4. Run tests to verify
5. Commit your changes: git add . && git commit -m 'feat: $TASK'
6. When complete, run: bd close $bead_id") \
    > "$LOGDIR/$bead_id.log" 2>&1 &
  
  echo "Spawned agent for bead $bead_id in $AGENT_DIR"
done

echo "Waiting for all agents to complete..."
wait
echo "All agents finished."
```

**Or use the helper script:**

```bash
./scripts/spawn_agents.sh <change-id> [max-parallel]
```

### 6. Merge Agent Branches

After all agents complete, merge their work:

```bash
CHANGE_ID="<change-id>"
WORKTREE_BASE="../worktrees-$CHANGE_ID"

# Return to main feature branch
git checkout openspec/$CHANGE_ID

# Merge each agent's branch
bd list --closed --json | jq -r '.[] | .id' | while read bead_id; do
  BRANCH="agent-$bead_id"
  echo "Merging $BRANCH..."
  git merge "$BRANCH" --no-edit || {
    echo "Conflict merging $BRANCH - resolve manually"
    exit 1
  }
done

echo "All branches merged successfully"
```

### 7. Cleanup Worktrees

```bash
CHANGE_ID="<change-id>"
WORKTREE_BASE="../worktrees-$CHANGE_ID"

# Remove worktrees
bd list --closed --json | jq -r '.[] | .id' | while read bead_id; do
  git worktree remove "$WORKTREE_BASE/$bead_id" --force
  git branch -d "agent-$bead_id"
done

rmdir "$WORKTREE_BASE" 2>/dev/null || true
echo "Worktrees cleaned up"
```

### 8. Monitor Progress

```bash
# Check remaining tasks
bd ready

# Check completed
bd list --closed

# Watch for completion (poll)
while [ "$(bd ready --json | jq length)" -gt 0 ]; do
  echo "$(date): $(bd ready --json | jq length) tasks remaining"
  sleep 30
done
echo "All tasks complete!"
```

### 9. Verify Integration

After merging all branches:

```bash
# Verify all beads closed
bd ready  # Should be empty

# Run full test suite
pytest

# Type check and lint
mypy src/ && ruff check .

# Validate OpenSpec
openspec validate <change-id> --strict
```

**If tests fail after merge:** Check logs in `logs/openspec-<change-id>/` to identify which agent's changes caused issues.

### 10. Update Task Tracking

```bash
# Mark all tasks complete in tasks.md
sed -i 's/- \[ \]/- [x]/g' openspec/changes/<change-id>/tasks.md
```

### 11. Commit and PR

```bash
git add .
git commit -m "feat(<scope>): <description>

Implements OpenSpec: <change-id>
Parallel execution: $(bd list --closed | wc -l) tasks

Co-Authored-By: Claude <noreply@anthropic.com>"

git push -u origin openspec/<change-id>

gh pr create --title "feat(<scope>): <title>" --body "## Summary
Implements OpenSpec: \`<change-id>\` using parallel agents.

### Parallel Execution
- Tasks parallelized: $(bd list --closed | wc -l)
- Execution logs: \`logs/openspec-<change-id>/\`

## Test Plan
- [ ] All tests pass
- [ ] No merge conflicts
- [ ] OpenSpec validates

---
🤖 Generated with Claude Code (parallel agents)"
```

## Agent Prompt Templates

### Minimal Agent Prompt

```
Implement OpenSpec <change-id>, task: <TASK>
Read proposal: openspec/changes/<change-id>/proposal.md
Write tests first. Run: bd close <bead_id> when done.
```

### Detailed Agent Prompt

```
You are a worker agent implementing part of OpenSpec <change-id>.

## Your Task
<TASK_DESCRIPTION>

## Context
- Proposal: openspec/changes/<change-id>/proposal.md
- Design: openspec/changes/<change-id>/design.md
- Your scope: Only implement YOUR assigned task

## Process
1. Read the proposal for context
2. Write failing tests first (TDD)
3. Implement minimal code to pass tests
4. Run tests: pytest <relevant_test_file>
5. Do NOT modify files outside your scope

## Completion
When done and tests pass, run:
bd close <bead_id>
```

## Coordination Patterns

### Sequential Dependencies

For tasks with dependencies, use bead blocking:

```bash
# Task B depends on Task A
A_ID=$(bd add "Task A - foundation")
B_ID=$(bd add "Task B - depends on A" --blocked-by $A_ID)

# Only Task A spawns initially
# Task B becomes ready when A closes
```

### Shared State Warning

If tasks share state (same file, database, etc.):
- Do NOT parallelize—run sequentially
- Or use file locking/separate branches per agent

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent hangs | Check logs; add timeout: `timeout 600 claude -p "..."` |
| Merge conflicts | Reduce parallelism; separate concerns better |
| Bead not closing | Agent may have failed; check logs, manually close |
| Tests fail after merge | Run integration tests; resolve conflicts |

## Output

- Feature branch: `openspec/<change-id>`
- Beads: All closed
- Logs: `logs/openspec-<change-id>/`
- PR created and awaiting review

## Next Step

After PR approved: `/cleanup-feature <change-id>`
