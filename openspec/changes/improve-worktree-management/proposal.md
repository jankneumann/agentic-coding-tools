# Change: improve-worktree-management

## Why

The current worktree system (`scripts/worktree.py`) uses `.git-worktrees/<change-id>/` as the sole path key, which means two agents working on the same change-id collide on the same directory. There is no registry of active worktrees, no heartbeat-based stale detection, and no enforcement of the "one agent, one worktree, one branch" rule. As parallel multi-agent workflows become the default (via `/parallel-implement-feature` and `openspec-beads-worktree`), these gaps create real risks: silent filesystem corruption, orphaned worktrees accumulating, and branch confusion when agents share checkouts.

This change upgrades `worktree.py` and the 8 skills that call it to support agent-scoped worktree isolation, a lightweight file-based registry, and deterministic cleanup.

## What Changes

### Core: `scripts/worktree.py`

- Add `--agent-id` flag to `setup` and `teardown` commands. When provided, the worktree path becomes `.git-worktrees/<change-id>/<agent-id>/` and the branch becomes `openspec/<change-id>/<agent-id>`. When omitted, behavior is unchanged (backward compatible).
- Add `--agent-id` support to `status` — show all agent worktrees under a change-id, or a specific one.
- **Add worktree registry** at `.git-worktrees/.registry.json` — a JSON file tracking `{change_id, agent_id, branch, worktree_path, created_at, last_heartbeat}` per entry. Updated on setup/teardown. Registry is advisory (not a lock).
- Add `list` subcommand — list all registered worktrees with owner, branch, staleness indicator (no heartbeat in >1 hour), and pin status.
- Add `gc` subcommand — remove worktrees whose heartbeat is older than a configurable threshold (default: 24 hours) and whose owning process is gone. Pinned worktrees are exempt from GC unless `--force` is passed. Prune corresponding branches if fully merged.
- Add `heartbeat` subcommand — update the `last_heartbeat` timestamp for a given change-id/agent-id pair.
- Add `pin` and `unpin` subcommands — mark a worktree as protected from garbage collection. Pinned worktrees survive indefinitely regardless of heartbeat age, useful for overnight pauses or waiting on human input. Pin state is stored in the registry as a boolean `pinned` field.
- **BREAKING**: Remove `legacy_worktree_path()` and `../<repo>.worktrees/` fallback from `teardown` and `status`. The legacy location has been deprecated since 2026-02-25. A one-time migration note will be added to the changelog.

### Skills updates (8 files)

- **`linear-implement-feature`**: Pass `--agent-id` when `AGENT_ID` env var is set. Add periodic heartbeat call during long-running implementation.
- **`linear-cleanup-feature`**: Call `gc` before teardown to clean stale peers. Pass `--agent-id` on teardown.
- **`linear-iterate-on-implementation`**: Detect worktree with agent-id awareness.
- **`linear-validate-feature`**: Detect worktree with agent-id awareness. Update `start-worktree-api.sh` to resolve agent-scoped paths.
- **`parallel-implement-feature`**: Require `--agent-id` for all worker agents. Each DAG task node gets a unique agent-id. Integrator uses `<change-id>/integrator`.
- **`parallel-cleanup-feature`**: Run `gc` across all agent worktrees for the change. Tear down in reverse creation order.
- **`fix-scrub`**: Pass `--agent-id` with `--prefix fix-scrub` to avoid collision with concurrent fix-scrub runs.
- **`openspec-beads-worktree`**: Update Phase 3 worktree creation to use `<change-id>/<task-agent-id>` instead of `<proposal>-<task-num>`.

### Bootstrap and configuration

- Update `scripts/worktree-bootstrap.sh` to accept and propagate agent-id context.
- Ensure `.git-worktrees/` remains in `.gitignore` (already present).
- Add `.git-worktrees/.registry.json` to `.gitignore` explicitly.

### Documentation

- Update `CLAUDE.md` worktree management section with new `--agent-id` flag and naming convention.
- Update `docs/lessons-learned.md` worktree entries with parallel best practices.
- Update `docs/two-level-parallel-agentic-development.md` worktree section.

### Tests

- Extend `scripts/tests/test_worktree.py` with tests for: agent-id path computation, registry CRUD, `gc` command, `list` command, `heartbeat` command, `pin`/`unpin` commands.
- Remove legacy path tests (matching the legacy removal).

## Impact

### Affected specs

| Spec | Capability | Delta |
|------|-----------|-------|
| `skill-workflow` | Worktree lifecycle in implement/cleanup/iterate/validate skills | Update requirements for agent-id propagation |
| `agent-coordinator` | No direct changes (coordinator already has agent identity) | None |

### Affected layers

- **Execution**: Worktree creation, bootstrap, teardown paths change
- **Coordination**: Registry provides lightweight coordination primitive for worktree ownership (file-based, no coordinator dependency)

### Affected code

| File | Change type |
|------|------------|
| `scripts/worktree.py` | Major refactor — add agent-id, registry, gc, list, heartbeat, pin/unpin |
| `scripts/worktree-bootstrap.sh` | Minor — accept agent-id |
| `scripts/tests/test_worktree.py` | Major — new test cases, remove legacy tests |
| `skills/linear-implement-feature/SKILL.md` | Minor — agent-id propagation |
| `skills/linear-cleanup-feature/SKILL.md` | Minor — gc + agent-id teardown |
| `skills/linear-iterate-on-implementation/SKILL.md` | Minor — detect with agent-id |
| `skills/linear-validate-feature/SKILL.md` | Minor — detect with agent-id |
| `skills/linear-validate-feature/scripts/start-worktree-api.sh` | Minor — agent-scoped path resolution |
| `skills/parallel-implement-feature/SKILL.md` | Moderate — require agent-id for workers |
| `skills/parallel-cleanup-feature/SKILL.md` | Moderate — gc across agent worktrees |
| `skills/fix-scrub/SKILL.md` | Minor — agent-id with prefix |
| `skills/openspec-beads-worktree/SKILL.md` | Moderate — new naming scheme |
| `CLAUDE.md` | Minor — update worktree docs |
| `docs/lessons-learned.md` | Minor — parallel worktree guidance |
| `docs/two-level-parallel-agentic-development.md` | Minor — worktree section update |
| `.gitignore` | Trivial — add registry file pattern |

### Rollback plan (for BREAKING legacy removal)

If agents are discovered still using `../<repo>.worktrees/`, restore `legacy_worktree_path()` and the teardown/status fallback. The function is small (~10 lines) and can be re-added without schema changes.

### Non-goals

- Coordinator-managed worktree locks (coordinator already has `acquire_lock`; the registry is intentionally file-based and standalone)
- Changing the `.git-worktrees/` root location (already the agreed-upon standard)
- Cross-machine worktree coordination (out of scope; agents share a local filesystem)
