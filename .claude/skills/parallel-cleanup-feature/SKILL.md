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
    required: [CAN_MERGE_QUEUE, CAN_FEATURE_REGISTRY]
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

Uses coordinator tools when available (MCP or HTTP, detected at startup):

| Operation | MCP Tool | HTTP Endpoint | CLI Command |
|-----------|----------|---------------|-------------|
| Register feature | `register_feature` | `POST /features/register` | `coordination-cli feature register` |
| Deregister feature | `deregister_feature` | `POST /features/deregister` | `coordination-cli feature deregister` |
| Enqueue for merge | `enqueue_merge` | `POST /merge-queue/enqueue` | `coordination-cli merge-queue enqueue` |
| Pre-merge checks | `run_pre_merge_checks` | `POST /merge-queue/check/{id}` | `coordination-cli merge-queue check` |
| Next to merge | `get_next_merge` | `GET /merge-queue/next` | `coordination-cli merge-queue next` |
| Mark merged | `mark_merged` | `POST /merge-queue/merged/{id}` | `coordination-cli merge-queue merged` |
| Acquire/release lock | `acquire_lock` / `release_lock` | `POST /locks/acquire` / `POST /locks/release` | `coordination-cli lock acquire/release` |

When coordinator is unavailable, degrades to `linear-cleanup-feature` behavior.

## Steps

### 0. Detect Coordinator and Read Handoff

At skill start, run the coordinator detection script:

```bash
# Use the script bundled with this skill (resolve from skill base directory shown above)
python3 "<skill-base-dir>/scripts/check_coordinator.py" --json
```

Parse the JSON output to set `COORDINATOR_AVAILABLE`, `COORDINATION_TRANSPORT`, and all `CAN_*` flags (including `CAN_MERGE_QUEUE` and `CAN_FEATURE_REGISTRY`).

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
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID" --agent-id cleanup
cd $WORKTREE_PATH
```

### 2. Verify PR is Approved

```bash
gh pr view openspec/<change-id>
```

Confirm PR is approved and CI is passing before proceeding.

### 3. Enqueue in Merge Queue (Coordinator)

If `CAN_MERGE_QUEUE=true`, enqueue the feature for ordered merging:

**MCP path:**
```
enqueue_merge(feature_id="<change-id>", pr_url="<pr-url>")
```

**HTTP path:**
```
POST /merge-queue/enqueue
{"feature_id": "<change-id>", "pr_url": "<pr-url>"}
```

This registers the feature in the merge queue with its priority from the feature registry.

### 4. Run Pre-Merge Checks

Before merging, run pre-merge validation:

**MCP path:**
```
run_pre_merge_checks(feature_id="<change-id>")
```

**HTTP path:**
```
POST /merge-queue/check/<change-id>
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

**MCP path:**
```
result = get_next_merge()
if result["entry"] and result["entry"]["feature_id"] != "<change-id>":
    # Another feature should merge first — inform user
```

**HTTP path:**
```
GET /merge-queue/next
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

After successful merge, if `CAN_MERGE_QUEUE=true`, deregister the feature:

**MCP path:**
```
mark_merged(feature_id="<change-id>")
```

**HTTP path:**
```
POST /merge-queue/merged/<change-id>
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
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown "${CHANGE_ID}" --agent-id cleanup
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" teardown "${CHANGE_ID}" --agent-id integrator

# GC any stale worktrees
python3 "<skill-base-dir>/../worktree/scripts/worktree.py" gc
```

### 13. Final Verification

```bash
git status
pytest
```

### 14. Notify Dependent Features

If `CAN_FEATURE_REGISTRY=true` and other features were waiting on this feature's merge (PARTIAL feasibility):

**MCP path:**
```
# List active features and re-analyze conflicts for each
features = list_active_features()
for feature in features["features"]:
    report = analyze_feature_conflicts(
        candidate_feature_id=feature["feature_id"],
        candidate_claims=feature["resource_claims"]
    )
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
