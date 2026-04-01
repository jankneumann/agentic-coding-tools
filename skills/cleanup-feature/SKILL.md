---
name: cleanup-feature
description: Merge approved PR, migrate open tasks, archive OpenSpec proposal, and cleanup branches
category: Git Workflow
tags: [openspec, archive, cleanup, merge, merge-queue]
triggers:
  - "cleanup feature"
  - "merge feature"
  - "finish feature"
  - "archive feature"
  - "close feature"
  - "linear cleanup feature"
  - "parallel cleanup feature"
  - "parallel merge feature"
  - "parallel finish feature"
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
- HTTP path: `"<skill-base-dir>/../coordination-bridge/scripts/coordination_bridge.py"` `try_handoff_read(...)`

On handoff failure/unavailability, continue with standalone cleanup and log informationally.

### 1. Determine Change ID and Setup Cleanup Worktree

```bash
# From argument or current branch
CHANGE_ID=$ARGUMENTS
# Or: CHANGE_ID=$(git branch --show-current | sed 's/^openspec\///')

# Verify
openspec show $CHANGE_ID
```

**Launcher Invariant**: The shared checkout is read-only. Perform all cleanup operations in a worktree:

```bash
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID" --agent-id cleanup
cd $WORKTREE_PATH
```

### 2. Verify PR is Approved

```bash
# Check PR status
gh pr status

# Or check specific PR
gh pr view openspec/<change-id>
```

Confirm PR is approved and CI is passing before proceeding.

### 2.5. Pre-Merge Validation Gate

Check whether Docker-dependent validation has been run. Cloud-created PRs pass environment-safe checks during implementation but may lack deployment-based validation.

If `validation-report.md` exists at `openspec/changes/<change-id>/` with deploy/smoke/security/e2e phases completed, skip this step.

Otherwise, if Docker is available (`docker info` succeeds), run the missing phases:

```
/validate-feature <change-id> --phase deploy,smoke,security,e2e
```

This delegates to the canonical validation skill for service lifecycle, smoke tests, security scanning, and E2E. The resulting `validation-report.md` is committed to the PR branch.

If Docker is not available, warn the operator that deployment validation was skipped and let them decide whether to proceed.

If any phase **fails**, present findings and let the operator decide: fix, re-validate, or proceed anyway.

### 2.5a. Smoke Test Hard Gate

Check `validation-report.md` for smoke test results:

1. Parse `## Smoke Tests` section for `Status:` line
2. If `Status: pass` → proceed to merge
3. If `Status: fail`, `Status: skipped`, or section missing:
   a. Re-run: `phase_deploy.py --env docker && phase_smoke.py && stack_launcher.py teardown`
   b. If re-run passes → proceed to merge
   c. If re-run fails or no runtime available → **HALT** (do not merge)

This is a **hard gate** — merge is blocked until smoke tests pass.

### 2.6. Merge Queue Integration [coordinated only]

These steps run only when coordinator is available with `CAN_MERGE_QUEUE` and `CAN_FEATURE_REGISTRY` capabilities.

**2.5a. Enqueue**: `enqueue_merge(feature_id="<change-id>", pr_url="<pr-url>")`
**2.5b. Pre-merge checks**: `run_pre_merge_checks(feature_id="<change-id>")` -- verifies no new resource conflicts
**2.5c. Check merge order**: `get_next_merge()` -- inform user if another feature has higher priority
**2.5d. Cross-feature rebase**: If other features merged since branching, rebase on origin/main

### 3. Merge PR

```bash
# Squash merge (recommended)
gh pr merge openspec/<change-id> --squash --delete-branch

# Or merge commit
gh pr merge openspec/<change-id> --merge --delete-branch
```

### 3.5. Mark Merged in Registry [coordinated only]

If `CAN_MERGE_QUEUE=true`: `mark_merged(feature_id="<change-id>")` -- marks feature completed, frees resource claims, removes from merge queue.

### 4. Update Local Repository

```bash
# From the cleanup worktree, fetch the merged main
git fetch origin main
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

### 5b. Append Session Log

Append a `Cleanup` phase entry to the session log, capturing merge strategy and task migration decisions. If no `session-log.md` exists from prior phases, create it and summarize the change from context.

**Phase entry template:**

```markdown
---

## Phase: Cleanup (<YYYY-MM-DD>)

**Agent**: <agent-type> | **Session**: <session-id-or-N/A>

### Decisions
1. **<Decision title>** — <rationale>

### Alternatives Considered
- <Alternative>: rejected because <reason>

### Trade-offs
- Accepted <X> over <Y> because <reason>

### Open Questions
- [ ] <unresolved question>

### Context
<2-3 sentences: merge strategy, task migration decisions, archive outcome>
```

**Focus on**: Merge strategy (squash vs regular), open task migration decisions, any cleanup issues encountered.

**Sanitize-then-verify:**

```bash
python3 "<skill-base-dir>/../session-log/scripts/sanitize_session_log.py" \
  "openspec/changes/<change-id>/session-log.md" \
  "openspec/changes/<change-id>/session-log.md"
```

Read the sanitized output and verify: (1) all sections present, (2) no incorrect `[REDACTED:*]` markers, (3) markdown intact. If over-redacted, rewrite without secrets, re-sanitize (one attempt max). If sanitization exits non-zero, skip session log and proceed.

```bash
git add "openspec/changes/<change-id>/session-log.md"
```

If session log append or sanitization fails at any point, log a warning and proceed to archiving without the session log. This step is non-blocking.

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

### 8.5. Remove Worktrees

Remove all worktrees for this feature (including the cleanup worktree):

```bash
# Return to shared checkout first (cleanup worktree is about to be removed)
cd "$(git rev-parse --git-common-dir | sed 's|/.git$||')"

# Remove cleanup worktree
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown "${CHANGE_ID}" --agent-id cleanup

# Remove implementation worktree (if exists from linear-implement-feature)
AGENT_FLAG=""
if [[ -n "${AGENT_ID:-}" ]]; then
  AGENT_FLAG="--agent-id ${AGENT_ID}"
fi
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown "${CHANGE_ID}" ${AGENT_FLAG}

# Garbage-collect stale worktrees
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" gc
```

### 9. Final Verification

```bash
# Confirm clean state
git status

# Run tests on main
pytest
```

### 9.5. Notify Dependent Features [coordinated only]

If `CAN_FEATURE_REGISTRY=true`, re-analyze conflicts for active features. Features that were PARTIAL or SEQUENTIAL may upgrade to FULL now that this features claims are freed.

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
