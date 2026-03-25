---
name: worktree
description: "Worktree lifecycle management scripts — setup, teardown, heartbeat, pin, GC, merge"
category: Infrastructure
tags: [worktree, git, infrastructure, merge]
user_invocable: false
---

# Worktree Infrastructure Skill

Non-user-invocable infrastructure skill that bundles worktree lifecycle management scripts. Referenced by SDLC skills via sibling-relative paths.

## Scripts

### scripts/worktree.py

Git worktree lifecycle manager for the launcher invariant (shared checkout is read-only).

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/worktree.py" <command> [args]
```

**Commands**:
| Command | Arguments | Description |
|---------|-----------|-------------|
| `setup` | `<change-id> [--agent-id ID]` | Create worktree at `.git-worktrees/<change-id>/` |
| `teardown` | `<change-id> [--agent-id ID]` | Remove worktree and clean branch |
| `status` | `<change-id> [--agent-id ID]` | Print worktree path and branch |
| `detect` | | Auto-detect if CWD is inside a worktree |
| `heartbeat` | `<change-id> [--agent-id ID]` | Update last-active timestamp (prevents GC) |
| `list` | | List all registered worktrees |
| `pin` | `<change-id>` | Protect worktree from GC |
| `unpin` | `<change-id>` | Remove GC protection |
| `gc` | `[--force]` | Garbage collect stale worktrees (24h default) |

**Stdout** (setup): `WORKTREE_PATH=<path>`, `BRANCH_CREATED=<branch>`, `CREATED=true|false`
**Exit codes**: 0 = success, 1 = error

### scripts/merge_worktrees.py

Merges parallel agent branches into the feature branch.

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/merge_worktrees.py" <change-id> <pkg-id>... [--json]
```

**Arguments**:
- `<change-id>` — Feature change ID
- `<pkg-id>...` — One or more package IDs to merge
- `--json` — Output merge results as JSON

**Exit codes**: 0 = all merged, 1 = conflict or error

### scripts/git-parallel-setup.sh

Configures local git for parallel agent development (rerere, zdiff3, histogram diff).

**Usage**:
```bash
bash "<skill-base-dir>/scripts/git-parallel-setup.sh"
```
