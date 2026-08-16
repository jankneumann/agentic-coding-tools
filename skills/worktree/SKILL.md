---
name: worktree
description: "Worktree lifecycle management scripts — fenced setup, leases, recovery, retention, GC, merge"
category: Infrastructure
tags: [worktree, git, infrastructure, merge]
user_invocable: false
---

# Worktree Infrastructure Skill

Non-user-invocable infrastructure skill that bundles worktree lifecycle management scripts. Referenced by SDLC skills via sibling-relative paths.

## Scripts

### `<skill-base-dir>/scripts/worktree.py`

Git worktree lifecycle manager for the launcher invariant (shared checkout is read-only).

**Usage**:
```bash
python3 "<skill-base-dir>/scripts/worktree.py" <command> [args]
```

Registry writes are schema v2, serialized through
`.git-worktrees/.registry.lock`, and atomically replace the registry. Readers
also normalize schema v1 without rewriting it. Automatic lifecycle operations
are fenced by the exact `(owner, lease_id, controller_instance_id)` triple and
the entry generation. A lease expires after 30 minutes by default; expiry ends
activity but never grants deletion authority.

Agent-scoped worktrees use the sibling path
`.git-worktrees/<change-id>--<agent-id>/`. They are never nested inside the
feature checkout because a nested repository would pollute its Git status.

**Commands**:

| Command | Arguments | Description |
|---------|-----------|-------------|
| `setup` | `<change-id> [--agent-id ID] [--durability-remote R --durability-ref REF]` | Compatibility setup; publishes an unleased entry with a fresh generation |
| `setup-and-acquire` | `<change-id> --setup-id S --durability-remote R --durability-ref REF --owner O --lease-id L --controller-instance-id C --phase P --reason R` | Crash-reconciled reservation, checkout, evidence, and first lease |
| `setup reconcile` | `<setup-id> --entry-generation G --actor A --reason R --confirm-terminated` | Audit and reconcile an expired unfinished setup |
| `lease acquire|resume|renew|assert-owned|release|status` | operation-specific exact fence | Manage one controller-bound activity lease |
| `lease release-owner|release-session` | exact owner or non-empty session | Quarantine preserved checkouts before bulk lease clearing |
| `recovery adopt|force-adopt` | new fence and recovery evidence | Explicitly adopt quarantined work; force-adopt is audited |
| `recovery bind-target` | exact generation/fence plus remote/ref | Bind durability after a manual null-target recovery push |
| `teardown` | `<change-id> --entry-generation G --owner O --lease-id L --controller-instance-id C` | Safe automatic teardown before release; unsafe state is quarantined |
| `recovery teardown` | exact unleased generation, attribution, termination confirmation | Dispose only clean durable or missing state and append an audit event |
| `recovery force-teardown` | exact generation, attribution, termination and discard confirmations | Separately named audited destructive compatibility path |
| `status` | `<change-id> [--agent-id ID]` | Print worktree path and branch |
| `detect` | | Auto-detect if CWD is inside a worktree |
| `inspect` / `migration-report` | `[--json]` | Read lifecycle categories or preview deterministic v1 normalization without mutation |
| `retention set|clear` | `<change-id> [--agent-id ID]` | Manage GC retention independently from activity |
| `heartbeat` | `<change-id> [--agent-id ID]` | Legacy compatibility heartbeat only |
| `list` | | List all registered worktrees |
| `pin` / `unpin` | `<change-id>` | Compatibility aliases for retention; never acquire or release activity |
| `gc` | `[--force]` | Collect stale compatibility entries; automatic, leased, recovery, and reservation state is excluded |

Bare `teardown --force` is rejected with migration guidance. Automatic callers
must never invoke either force-adopt or force-teardown.

**Stdout** (setup): `WORKTREE_PATH=<path>`, `WORKTREE_BRANCH=<branch>`,
`ENTRY_GENERATION=<generation>`, `BOOTSTRAPPED=true|false`

**Exit codes**: 0 success/idempotent, 1 arguments/not found, 2 corrupt
registry, 3 other live owner, 4 owner mismatch, 5 lock timeout, 6 fence or
expiry mismatch, 7 recovery required.

### `<skill-base-dir>/scripts/merge_worktrees.py`

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

### `<skill-base-dir>/scripts/git-parallel-setup.sh`

Configures local git for parallel agent development (rerere, zdiff3, histogram diff).

**Usage**:
```bash
bash "<skill-base-dir>/scripts/git-parallel-setup.sh"
```
