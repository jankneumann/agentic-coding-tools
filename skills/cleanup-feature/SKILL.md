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

Merge an approved PR, migrate any open tasks to coordinator issues or a follow-up proposal, archive the OpenSpec proposal, and cleanup branches.

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
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID" --agent-id cleanup)"
cd "$WORKTREE_PATH"

# The cleanup worktree is on its OWN scratch branch (with the --cleanup suffix),
# so that cleanup operations don't collide with a still-running implementation
# worktree. We need two distinct branch variables:
#
#   CLEANUP_BRANCH — this worktree's own branch (openspec/<change-id>--cleanup
#                    by default, or <override>--cleanup when OPENSPEC_BRANCH_OVERRIDE
#                    is set). Used for teardown.
#   FEATURE_BRANCH — the PARENT feature branch being merged/deleted. This is
#                    the branch implement-feature pushed and opened a PR against.
#                    Used for gh pr merge, git branch -d, and lock cleanup.
CLEANUP_BRANCH="$WORKTREE_BRANCH"
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" resolve-branch "$CHANGE_ID" --parent)"
FEATURE_BRANCH="$BRANCH"
```

### 2. Verify PR is Approved

```bash
# Check PR status
gh pr status

# Or check specific PR (use the resolved FEATURE_BRANCH, not a hardcoded prefix)
gh pr view "$FEATURE_BRANCH"
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

### 2.5a. Pre-Merge Validation Gate

**Programmatic enforcement** — run the gate check script before merge:

```bash
python3 skills/validate-feature/scripts/gate_logic.py \
  openspec/changes/<change-id>/validation-report.md
```

This checks **all required phases** (smoke tests, security scan, E2E tests) in `validation-report.md`:
- Exit code 0 → all phases passed, proceed to merge
- Exit code 1 → one or more phases failed/missing/skipped → **HALT**

If the gate halts:
1. Re-run the failing phases: `/validate-feature <change-id> --phase deploy,smoke,security,e2e`
2. Re-check the gate
3. Only if re-run fails AND the user explicitly requests override: add `--force`

```bash
# Explicit user override (must be requested by user, never autonomous)
python3 skills/validate-feature/scripts/gate_logic.py \
  openspec/changes/<change-id>/validation-report.md --force
```

This is a **hard gate** — merge is blocked until all required phases pass or the user explicitly overrides.

### 2.5b. Holdout Gate Check (If Rework Report Exists)

If `openspec/changes/<change-id>/rework-report.json` exists, check whether holdout scenario failures block cleanup:

```bash
REWORK_REPORT="openspec/changes/$CHANGE_ID/rework-report.json"
if [[ -f "$REWORK_REPORT" ]]; then
  python3 -c "
import json, sys
data = json.load(open('$REWORK_REPORT'))
summary = data.get('summary', {})
if summary.get('has_blocking_holdout'):
    holdout_ids = [f['scenario_id'] for f in data.get('failures', [])
                   if f.get('visibility') == 'holdout' and f.get('recommended_action') == 'block-cleanup']
    print(f'HALT: Holdout scenario failures block cleanup: {holdout_ids}')
    sys.exit(1)
print('Holdout gate: clear')
"
fi
```

If the holdout gate halts:
1. Return to `/iterate-on-implementation` to address holdout failures
2. Re-run `/validate-feature` to regenerate the rework report
3. Only proceed if the rework report no longer contains blocking holdout failures

The `process-analysis.md` artifact, if present, is consumed **read-only** at this stage for inclusion in the PR description and session log. It is NOT regenerated during cleanup.

### 2.6. Merge Queue Integration [coordinated only]

These steps run only when coordinator is available with `CAN_MERGE_QUEUE` and `CAN_FEATURE_REGISTRY` capabilities.

**2.6a. Enqueue**: `enqueue_merge(feature_id="<change-id>", pr_url="<pr-url>")`
**2.6b. Pre-merge checks**: `run_pre_merge_checks(feature_id="<change-id>")` -- verifies no new resource conflicts
**2.6c. Check merge order**: `get_next_merge()` -- inform user if another feature has higher priority
**2.6d. Cross-feature rebase**: If other features merged since branching, rebase on origin/main

### 3. Merge PR

The merge command integrates the pre-merge gate — it will refuse to merge unless the gate passes:

```bash
# Via merge_pr.py with gate enforcement (preferred)
python3 skills/merge-pull-requests/scripts/merge_pr.py merge <pr_number> \
  --origin openspec \
  --validation-report openspec/changes/<change-id>/validation-report.md

# Direct gh merge (only if gate already passed in step 2.5a)
# Uses the resolved FEATURE_BRANCH, which honors OPENSPEC_BRANCH_OVERRIDE
gh pr merge "$FEATURE_BRANCH" --rebase --delete-branch
```

**Explicit user override** (only when user explicitly requests):
```bash
python3 skills/merge-pull-requests/scripts/merge_pr.py merge <pr_number> \
  --origin openspec \
  --validation-report openspec/changes/<change-id>/validation-report.md \
  --force
```

**Strategy rationale**: OpenSpec PRs use rebase-merge by default because agent-authored commits follow conventional format and encode design intent (interface → implementation → tests). Preserving this history improves `git blame` and `git bisect` for future agents. Use squash only if the PR has noisy WIP commits.

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

### 4.5. Fast-Forward Submodule Main Branches

If the merged PR bumped any submodule gitlink SHAs (e.g., personas/ mount points), their own `main` branches must be fast-forwarded to avoid silent divergence.

```bash
# Detect changed submodules and sync their main branches
python3 "<skill-base-dir>/scripts/sync_submodules.py" \
  --repo-dir "." \
  --feature-branch "$FEATURE_BRANCH"
```

This script:
1. Detects submodules whose SHA changed via `git diff --raw main@{1} main` (mode 160000 = gitlink)
2. For each changed submodule:
   - Fetches `origin main` inside the submodule
   - Switches to main and fast-forwards (`--ff-only`) to the SHA the parent records
   - Pushes main to the submodule's remote
   - Deletes the submodule's feature branch (local + remote)
3. If the fast-forward fails (non-FF changes on submodule main), logs a warning and stops for that submodule — does NOT force-merge

**Credential handling**: The same credentials may not work for the submodule's private remote. On auth/push failure, the script:
- Logs a clear diagnostic (submodule path, remote URL, error)
- Prints operator handoff commands to run manually
- Continues with the rest of cleanup (does not abort)

If no submodules changed, this step is a no-op.

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

**Option A — Coordinator issues** (if coordinator is available):

For each open task group that has unchecked items, use the coordinator's issue tracking MCP tools:
```
issue_create(
  title="<task description>",
  description="Followup from OpenSpec <change-id>. File scope: <files>",
  issue_type="task",
  priority=5,
  labels=["followup", "openspec:<change-id>"]
)

# If tasks have dependencies on each other, create with depends_on
issue_create(
  title="<dependent task>",
  depends_on=["<parent-issue-id>"],
  labels=["followup", "openspec:<change-id>"]
)
```

Include in each issue description:
- Original OpenSpec change-id for traceability
- The file scope from the task group
- Any relevant context from `proposal.md` or `design.md`

**Option B — Follow-up OpenSpec proposal** (default if coordinator is not available):

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
Open tasks migrated to [coordinator issues labeled `openspec:<change-id>`] | [follow-up proposal `followup-<change-id>`] on YYYY-MM-DD.
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
# Uses the resolved FEATURE_BRANCH to honor OPENSPEC_BRANCH_OVERRIDE
git branch -d "$FEATURE_BRANCH" 2>/dev/null || true

# Prune remote tracking branches
git fetch --prune
```

If `CAN_LOCK=true`, perform best-effort lock cleanup for files touched on the feature branch:

- Compare `main...$FEATURE_BRANCH` changed files
- Attempt release for each lock owned by this agent/session
- Treat release failures as warnings (do not block cleanup)

### 8.5. Remove Worktrees

Remove all worktrees for this feature (including the cleanup worktree).

**Submodule handling**: `worktree.py teardown` automatically handles worktrees containing initialized submodules:
1. Runs `git submodule deinit -f --all` inside the worktree first
2. Attempts normal `git worktree remove`
3. If removal still fails with *"working trees containing submodules cannot be moved or removed"*, falls back to `git worktree remove --force` (safe because the worktree's branch is already merged/pushed)
4. Other removal errors (dirty tree, conflicts) are NOT force-overridden — they surface for operator attention

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
- Open tasks migrated to coordinator issues or follow-up OpenSpec proposal (if any)
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
