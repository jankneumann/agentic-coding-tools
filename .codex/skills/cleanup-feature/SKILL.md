---
name: linear-cleanup-feature
description: Merge approved PR, migrate open tasks, archive OpenSpec proposal, and cleanup branches
category: Git Workflow
tags: [openspec, archive, cleanup, merge, linear]
triggers:
  - "cleanup feature"
  - "merge feature"
  - "finish feature"
  - "archive feature"
  - "close feature"
  - "linear cleanup feature"
---

# Cleanup Feature

Merge an approved PR, migrate any open tasks to beads or a follow-up proposal, archive the OpenSpec proposal, and cleanup branches.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (optional, will detect from current branch or open PR)

## Prerequisites

- PR has been approved
- All CI checks passing
- Run `/implement-feature` first if PR doesn't exist
- Recommended: Run `/validate-feature` first to verify live deployment

## OpenSpec Execution Preference

Use OpenSpec-generated runtime assets first, then CLI fallback:
- Claude: `.claude/commands/opsx/*.md` or `.claude/skills/openspec-*/SKILL.md`
- Codex: `.codex/skills/openspec-*/SKILL.md`
- Gemini: `.gemini/commands/opsx/*.toml` or `.gemini/skills/openspec-*/SKILL.md`
- Fallback: direct `openspec` CLI commands

## Coordinator Integration (Optional)

Use `docs/coordination-detection-template.md` as the shared detection preamble.

- Detect transport and capability flags at skill start
- Execute hooks only when the matching `CAN_*` flag is `true`
- If coordinator is unavailable, continue with standalone behavior

## Steps

### 0. Detect Coordinator and Read Handoff

At skill start, run the coordination detection preamble and set:

- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

If `CAN_HANDOFF=true`, read latest handoff context before merge/archive actions:

- MCP path: `read_handoff`
- HTTP path: `scripts/coordination_bridge.py` `try_handoff_read(...)`

On handoff failure/unavailability, continue with standalone cleanup and log informationally.

### 1. Determine Change ID

```bash
# From current branch
BRANCH=$(git branch --show-current)
CHANGE_ID=$(echo $BRANCH | sed 's/^openspec\///')

# Or from argument
CHANGE_ID=$ARGUMENTS

# Verify
openspec show $CHANGE_ID
```

### 2. Verify PR is Approved

```bash
# Check PR status
gh pr status

# Or check specific PR
gh pr view openspec/<change-id>
```

Confirm PR is approved and CI is passing before proceeding.

### 3. Merge PR

```bash
# Squash merge (recommended)
gh pr merge openspec/<change-id> --squash --delete-branch

# Or merge commit
gh pr merge openspec/<change-id> --merge --delete-branch
```

### 4. Update Local Repository

```bash
# Switch to main
git checkout main

# Pull merged changes
git pull origin main
```

After merge, refresh project-global architecture artifacts:

```bash
make architecture
```

### 5. Migrate Open Tasks

Before archiving, check for incomplete tasks in the proposal. Open tasks must not be silently dropped.

#### 5a. Detect open tasks

Read `openspec/changes/<change-id>/tasks.md` and scan for unchecked items (`- [ ]`).

If **all tasks are checked** (`- [x]`), skip to Step 6.

If there are **open tasks**, collect them with their context:
- Task number and description (e.g., `3.2 Add retry logic for failed requests`)
- Parent task group heading (e.g., `### 3. Error Handling`)
- Dependencies from the group's `**Dependencies**:` line
- File scope from the group's `**Files**:` line

#### 5b. Choose migration target

Ask the user which migration strategy to use:

**Option A — Beads issues** (if `.beads/` directory exists):

For each open task group that has unchecked items:
```bash
# Create a beads issue per open task
bd create "<task description>" \
  --label "followup,openspec:<change-id>" \
  --priority medium

# If tasks have dependencies on each other, link them
bd dep add <child-id> <parent-id>
```

Include in each issue description:
- Original OpenSpec change-id for traceability
- The file scope from the task group
- Any relevant context from `proposal.md` or `design.md`

**Option B — Follow-up OpenSpec proposal** (default if beads is not initialized):

Create a new proposal using runtime-native new/continue workflow (or CLI fallback) with:
- **Change-id**: `followup-<original-change-id>` (e.g., `followup-add-retry-logic`)
- **proposal.md**: Reference the original change-id, explain these are remaining tasks
- **tasks.md**: Copy only the open (unchecked) tasks, preserving their numbering, dependencies, and file scope
- **specs/**: Copy any spec deltas that correspond to the open tasks (if the original proposal's spec changes included requirements that depend on unfinished work)

Let the user review and confirm the follow-up proposal before proceeding.

#### 5c. Mark original tasks.md

After migration, annotate the original `tasks.md` to record where open tasks went:

```markdown
## Migration Notes
Open tasks migrated to [beads issues labeled `openspec:<change-id>`] | [follow-up proposal `followup-<change-id>`] on YYYY-MM-DD.
```

This annotation is preserved in the archive for traceability.

### 6. Archive OpenSpec Proposal

Preferred path:
- Use runtime-native archive workflow (`opsx:archive` equivalent for the active agent).

CLI fallback path:

```bash
openspec archive <change-id> --yes
openspec validate --strict
```

This archives the change, merges delta specs, and validates repository integrity.

### 7. Verify Archive

```bash
# Confirm specs updated
openspec list --specs

# Confirm change archived
ls openspec/changes/archive/<change-id>/

# Validate everything
openspec validate --strict
```

### 8. Cleanup Local Branches

```bash
# Delete local feature branch (if not already deleted)
git branch -d openspec/<change-id> 2>/dev/null || true

# Prune remote tracking branches
git fetch --prune
```

If `CAN_LOCK=true`, perform best-effort lock cleanup for files touched on the feature branch:

- Compare `main...openspec/<change-id>` changed files
- Attempt release for each lock owned by this agent/session
- Treat release failures as warnings (do not block cleanup)

### 8.5. Remove Worktree

If a worktree was created for this feature, remove it:

```bash
# Remove worktree (checks both .git-worktrees/ and legacy locations)
python3 scripts/worktree.py teardown "${CHANGE_ID}"
```

### 9. Final Verification

```bash
# Confirm clean state
git status

# Run tests on main
pytest
```

### 10. Clear Session State

- Clear todo list
- Document any lessons learned in `CLAUDE.md` if applicable
- If `CAN_HANDOFF=true`, write a final handoff summary with merge status, migration notes, archive outcome, and follow-up references

## Output

- PR merged to main
- Open tasks migrated to beads issues or follow-up OpenSpec proposal (if any)
- OpenSpec proposal archived
- Specs updated in `openspec/specs/`
- Branches cleaned up
- Repository in clean state

## Complete Workflow Reference

```
/plan-feature <description>     # Create proposal → approval gate
/implement-feature <change-id>  # Build + PR → review gate
/validate-feature <change-id>   # Deploy + test → validation gate (optional)
/cleanup-feature <change-id>    # Merge + archive → done
```
