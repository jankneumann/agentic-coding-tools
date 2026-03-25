---
name: parallel-cleanup-feature
description: Merge via coordinator merge queue, cross-feature rebase coordination, archive OpenSpec proposal
category: Git Workflow
tags: [openspec, archive, cleanup, merge, parallel, merge-queue]
triggers:
  - "parallel cleanup feature"
  - "parallel merge feature"
  - "parallel finish feature"
requires:
  coordinator:
    required: []
    safety: [CAN_GUARDRAILS]
    enriching: [CAN_HANDOFF, CAN_MEMORY, CAN_AUDIT, CAN_LOCK]
---

# Parallel Cleanup Feature

Extends `linear-cleanup-feature` with cross-feature coordination: merge queue integration, pre-merge conflict re-validation, and cross-feature rebase coordination. Falls back to linear cleanup behavior when coordinator is unavailable.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (optional, will detect from current branch or open PR)

## Prerequisites

- PR has been approved and CI is passing
- Run `/parallel-implement-feature` first if PR doesn't exist
- Recommended: Run `/parallel-validate-feature` first for evidence completeness
- Feature must be registered in the coordinator's feature registry (if coordinator available)

## Coordinator Integration

Uses coordinator merge queue primitives when available:

- `register_feature` / `deregister_feature` — feature registry lifecycle
- `merge_queue.enqueue` / `merge_queue.run_pre_merge_checks` — merge ordering
- `merge_queue.mark_merged` — post-merge deregistration
- `acquire_lock` / `release_lock` — file lock cleanup

When coordinator is unavailable, degrades to `linear-cleanup-feature` behavior.

## Steps

### 0. Detect Coordinator and Read Handoff

At skill start, run the coordinator detection script:

```bash
# Use the script bundled with this skill (resolve from skill base directory shown above)
python3 "<skill-base-dir>/scripts/check_coordinator.py" --json
```

Parse the JSON output to set `COORDINATOR_AVAILABLE`, `COORDINATION_TRANSPORT`, and all `CAN_*` flags.

If `CAN_HANDOFF=true`, read latest handoff context via MCP `read_handoff` tool.

### 1. Determine Change ID and Setup Cleanup Worktree

```bash
# Get change-id from argument or current branch
CHANGE_ID=$ARGUMENTS
# Or: CHANGE_ID=$(git branch --show-current | sed 's/^openspec\///')

openspec show $CHANGE_ID
```

**Launcher Invariant**: The shared checkout is read-only. Perform all cleanup operations in a worktree:

```bash
python3 scripts/worktree.py setup "$CHANGE_ID" --agent-id cleanup
cd $WORKTREE_PATH
```

### 2. Verify PR is Approved

```bash
gh pr view openspec/<change-id>
```

Confirm PR is approved and CI is passing before proceeding.

### 3. Enqueue in Merge Queue (Coordinator)

If coordinator is available, enqueue the feature for ordered merging:

```python
# Enqueue this feature's PR
merge_queue.enqueue(
    feature_id="<change-id>",
    pr_url="<pr-url>"
)
```

This registers the feature in the merge queue with its priority from the feature registry.

### 4. Run Pre-Merge Checks

Before merging, run pre-merge validation:

```python
result = merge_queue.run_pre_merge_checks("<change-id>")
```

Pre-merge checks verify:
- [ ] Feature is still active in registry
- [ ] No new resource conflicts with other active features (re-validates since registration)
- [ ] Feature is properly queued

If checks fail:
- Report the specific failures to the user
- If resource conflicts: recommend resolving conflicts first or rebasing
- Do NOT proceed with merge until checks pass

### 5. Check Merge Order

If other features have higher merge priority:

```python
next_to_merge = merge_queue.get_next_to_merge()
if next_to_merge.feature_id != "<change-id>":
    # Another feature should merge first
    # Inform the user and wait
```

If this feature is not next in line, inform the user which feature should merge first and why (priority ordering). The user can override by proceeding manually.

### 6. Cross-Feature Rebase (if needed)

If other features have merged since this feature branched:

```bash
# Inside the cleanup worktree (already on feature branch)
git fetch origin main
git rebase origin/main
```

If rebase conflicts occur:
- Attempt automatic resolution for non-overlapping changes
- For conflicting files, check if the conflict is with a feature that was in the registry
- Present conflict details and let the user resolve

### 7. Merge PR

```bash
# Prefer merge queue when enabled (validates combined PR state before merging)
gh pr merge openspec/<change-id> --squash --delete-branch --merge-queue

# If merge queue is not enabled, the --merge-queue flag is ignored and
# the PR merges directly. If merge queue IS enabled but --merge-queue is
# omitted, gh will prompt or error — so always include it.
```

### 8. Mark Merged in Registry

After successful merge, deregister the feature:

```python
merge_queue.mark_merged("<change-id>")
```

This:
- Marks the feature as `completed` in the feature registry
- Frees its resource claims for other features
- Removes it from the merge queue

### 9. Update Local Repository

```bash
git checkout main
git pull origin main
```

After merge, refresh architecture artifacts:

```bash
make architecture
```

### 10. Migrate Open Tasks

Same as `linear-cleanup-feature` Step 5:
- Scan `tasks.md` for unchecked items
- Migrate to beads issues or follow-up OpenSpec proposal
- Annotate original `tasks.md` with migration notes

### 11. Archive OpenSpec Proposal

```bash
openspec archive <change-id> --yes
openspec validate --strict
```

### 12. Cleanup

```bash
# Delete local feature branch
git branch -d openspec/<change-id> 2>/dev/null || true

# Prune remote tracking branches
git fetch --prune
```

If `CAN_LOCK=true`, release any locks held by this agent for the feature:
- Best-effort release for all lock keys in the feature's resource claims
- Treat release failures as warnings

Remove all worktrees for this feature (including the cleanup worktree itself):

```bash
# Return to the shared checkout first (cleanup worktree is about to be removed)
cd "$(git rev-parse --git-common-dir | sed 's|/.git$||')"

# Teardown all remaining agent worktrees for this change
python3 scripts/worktree.py teardown "${CHANGE_ID}" --agent-id cleanup
python3 scripts/worktree.py teardown "${CHANGE_ID}" --agent-id integrator

# GC any stale worktrees
python3 scripts/worktree.py gc
```

### 13. Final Verification

```bash
git status
pytest
```

### 14. Notify Dependent Features

If other features were waiting on this feature's merge (PARTIAL feasibility):

```python
# Re-run feasibility for features that had conflicts with this one
for feature in active_features:
    if feature had conflicts with <change-id>:
        new_report = analyze_conflicts(feature.feature_id, feature.resource_claims)
        # Report updated feasibility to user
```

This allows features that were PARTIAL or SEQUENTIAL to potentially upgrade to FULL feasibility now that this feature's claims are freed.

### 15. Clear Session State

- Clear todo list
- If `CAN_HANDOFF=true`, write a final handoff summary with:
  - Merge status and merge queue position
  - Resource claims freed
  - Migration notes for open tasks
  - Follow-up references
  - Feasibility changes for dependent features

## Output

- PR merged to main via merge queue ordering
- Feature deregistered from coordinator registry
- Resource claims freed for other features
- Open tasks migrated (if any)
- OpenSpec proposal archived
- Branches and worktree cleaned up
- Dependent features notified of freed resources

## Design Notes

Compared to `linear-cleanup-feature`, this skill adds:
- **Merge queue integration** — ordered merging based on feature priority
- **Pre-merge conflict re-validation** — catches conflicts introduced after registration
- **Cross-feature rebase coordination** — handles conflicts from concurrent features
- **Resource claim lifecycle** — deregisters claims to unblock other features
- **Dependent feature notification** — updates feasibility for waiting features

When coordinator is unavailable, all coordinator-specific steps are skipped and the skill behaves identically to `linear-cleanup-feature`.

## Next Step

After cleanup:
```
/parallel-explore-feature  # Find next feature to work on
```
