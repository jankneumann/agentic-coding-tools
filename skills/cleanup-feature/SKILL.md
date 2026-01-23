---
name: cleanup-feature
description: Merge approved PR, archive OpenSpec proposal, and cleanup branches
category: Git Workflow
tags: [openspec, archive, cleanup, merge]
triggers:
  - "cleanup feature"
  - "merge feature"
  - "finish feature"
  - "archive feature"
  - "close feature"
---

# Cleanup Feature

Merge an approved PR, archive the OpenSpec proposal, and cleanup branches.

## Arguments

`$ARGUMENTS` - OpenSpec change-id (optional, will detect from current branch or open PR)

## Prerequisites

- PR has been approved
- All CI checks passing
- Run `/implement-feature` first if PR doesn't exist

## Steps

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

### 5. Archive OpenSpec Proposal

```
/openspec-archive <change-id>
```

This will:
- Validate the change is ready for archive
- Run `openspec archive <change-id> --yes`
- Move proposal to `openspec/changes/archive/<change-id>/`
- Apply spec deltas to `openspec/specs/`
- Validate with `openspec validate --strict`

### 6. Verify Archive

```bash
# Confirm specs updated
openspec list --specs

# Confirm change archived
ls openspec/changes/archive/<change-id>/

# Validate everything
openspec validate --strict
```

### 7. Cleanup Local Branches

```bash
# Delete local feature branch (if not already deleted)
git branch -d openspec/<change-id> 2>/dev/null || true

# Prune remote tracking branches
git fetch --prune
```

### 8. Final Verification

```bash
# Confirm clean state
git status

# Run tests on main
pytest
```

### 9. Clear Session State

- Clear todo list
- Document any lessons learned in `CLAUDE.md` if applicable

## Output

- PR merged to main
- OpenSpec proposal archived
- Specs updated in `openspec/specs/`
- Branches cleaned up
- Repository in clean state

## Complete Workflow Reference

```
/plan-feature <description>     # Create proposal → approval gate
/implement-feature <change-id>  # Build + PR → review gate
/cleanup-feature <change-id>    # Merge + archive → done
```
