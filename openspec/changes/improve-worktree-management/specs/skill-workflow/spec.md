# Delta Spec: skill-workflow — improve-worktree-management

## ADDED Requirements

### Requirement: Agent-scoped worktree paths

The worktree system SHALL support an `--agent-id` flag on `setup`, `teardown`, `status`, and `heartbeat` commands. WHEN `--agent-id` is provided, the worktree path MUST be `.git-worktrees/<change-id>/<agent-id>/` and the default branch MUST be `openspec/<change-id>/<agent-id>`.

#### Scenario: Setup with agent-id

- WHEN `worktree.py setup my-change --agent-id worker-1` is invoked
- THEN the worktree MUST be created at `.git-worktrees/my-change/worker-1/`
- AND the branch MUST default to `openspec/my-change/worker-1`
- AND the registry MUST contain an entry for `(my-change, worker-1)`

#### Scenario: Setup without agent-id (backward compatible)

- WHEN `worktree.py setup my-change` is invoked without `--agent-id`
- THEN the worktree MUST be created at `.git-worktrees/my-change/`
- AND the branch MUST default to `openspec/my-change`
- AND the registry MUST contain an entry with `agent_id=null`

#### Scenario: Agent-id with prefix

- WHEN `worktree.py setup my-change --agent-id worker-1 --prefix fix-scrub` is invoked
- THEN the worktree MUST be created at `.git-worktrees/fix-scrub/my-change/worker-1/`

---

### Requirement: Worktree registry

The worktree system SHALL maintain a JSON registry at `.git-worktrees/.registry.json` tracking all managed worktrees. Each entry MUST contain: `change_id`, `agent_id` (nullable), `branch`, `worktree_path`, `created_at` (ISO 8601), `last_heartbeat` (ISO 8601), and `pinned` (boolean, default false).

#### Scenario: Registry updated on setup

- WHEN a worktree is created via `setup`
- THEN a new entry MUST be appended to the registry
- AND `created_at` and `last_heartbeat` MUST be set to the current UTC time

#### Scenario: Registry updated on teardown

- WHEN a worktree is removed via `teardown`
- THEN the corresponding entry MUST be removed from the registry

#### Scenario: Registry file missing

- WHEN the registry file does not exist
- THEN `setup` MUST create it with a single entry
- AND `list`, `status`, `gc` MUST treat the missing file as an empty registry

#### Scenario: Concurrent registry access

- WHEN two agents call `setup` simultaneously
- THEN both entries MUST appear in the registry (last-writer-wins is acceptable for advisory registry)

---

### Requirement: Heartbeat command

The worktree system SHALL provide a `heartbeat` subcommand that updates the `last_heartbeat` field for a given `change_id` and optional `agent_id`.

#### Scenario: Heartbeat updates timestamp

- WHEN `worktree.py heartbeat my-change --agent-id worker-1` is invoked
- THEN the registry entry matching `(my-change, worker-1)` MUST have its `last_heartbeat` updated to the current UTC time
- AND the exit code MUST be 0

#### Scenario: Heartbeat for unknown worktree

- WHEN `worktree.py heartbeat unknown-change` is invoked
- AND no registry entry exists for `unknown-change`
- THEN the exit code MUST be 1
- AND a diagnostic message MUST be printed to stderr

---

### Requirement: List command

The worktree system SHALL provide a `list` subcommand that displays all registered worktrees with staleness indicators.

#### Scenario: List all worktrees

- WHEN `worktree.py list` is invoked
- THEN each registered worktree MUST be printed with: change_id, agent_id, branch, path, staleness status, and pin status
- AND a worktree MUST be marked stale if `last_heartbeat` is older than 1 hour
- AND pinned worktrees MUST be indicated with a `[pinned]` marker

#### Scenario: List with no worktrees

- WHEN `worktree.py list` is invoked and the registry is empty
- THEN the output MUST indicate no active worktrees
- AND the exit code MUST be 0

---

### Requirement: Pin and unpin commands

The worktree system SHALL provide `pin` and `unpin` subcommands that mark a worktree as protected from garbage collection. Pinned worktrees MUST survive GC regardless of heartbeat age. This supports overnight pauses, waiting on human input, and multi-day review cycles.

#### Scenario: Pin a worktree

- WHEN `worktree.py pin my-change` is invoked
- THEN the registry entry for `my-change` MUST have `pinned` set to `true`
- AND the exit code MUST be 0

#### Scenario: Pin with agent-id

- WHEN `worktree.py pin my-change --agent-id worker-1` is invoked
- THEN only the registry entry matching `(my-change, worker-1)` MUST be pinned

#### Scenario: Unpin a worktree

- WHEN `worktree.py unpin my-change` is invoked
- THEN the registry entry for `my-change` MUST have `pinned` set to `false`
- AND the exit code MUST be 0

#### Scenario: Pin unknown worktree

- WHEN `worktree.py pin unknown-change` is invoked
- AND no registry entry exists for `unknown-change`
- THEN the exit code MUST be 1
- AND a diagnostic message MUST be printed to stderr

---

### Requirement: Garbage collection command

The worktree system SHALL provide a `gc` subcommand that removes stale worktrees. A worktree is stale WHEN its `last_heartbeat` is older than a configurable threshold (default: 24 hours) AND the worktree is NOT pinned. Pinned worktrees MUST be skipped unless `--force` is passed.

#### Scenario: GC removes stale worktree

- WHEN `worktree.py gc` is invoked
- AND a registered worktree has not heartbeated in 25 hours
- AND the worktree is NOT pinned
- THEN the worktree MUST be removed via `git worktree remove`
- AND the registry entry MUST be removed
- AND the corresponding branch MUST be pruned if fully merged into main

#### Scenario: GC preserves active worktree

- WHEN `worktree.py gc` is invoked
- AND a registered worktree heartbeated 30 minutes ago
- THEN the worktree MUST NOT be removed

#### Scenario: GC preserves pinned worktree

- WHEN `worktree.py gc` is invoked
- AND a registered worktree has not heartbeated in 48 hours
- AND the worktree is pinned
- THEN the worktree MUST NOT be removed

#### Scenario: GC force removes pinned worktree

- WHEN `worktree.py gc --force` is invoked
- AND a registered worktree is pinned and stale
- THEN the worktree MUST be removed
- AND the registry entry MUST be removed

#### Scenario: GC with custom threshold

- WHEN `worktree.py gc --stale-after 48h` is invoked
- THEN only unpinned worktrees with heartbeat older than 48 hours MUST be removed

#### Scenario: GC on non-existent directory

- WHEN a registry entry points to a directory that no longer exists
- THEN `gc` MUST remove the registry entry without error (regardless of pin status)

---

### Requirement: Parallel skill agent-id enforcement

The `/parallel-implement-feature` skill MUST assign a unique `agent-id` to each worker agent and pass it to `worktree.py setup`. The integrator agent MUST use agent-id `integrator`.

#### Scenario: Parallel workers get unique worktrees

- WHEN `/parallel-implement-feature` spawns 3 worker agents for change `feat-x`
- THEN each worker MUST have a distinct worktree at `.git-worktrees/feat-x/<agent-id>/`
- AND each MUST be on a distinct branch `openspec/feat-x/<agent-id>`

#### Scenario: Integrator worktree

- WHEN `/parallel-implement-feature` creates an integrator worktree
- THEN it MUST be at `.git-worktrees/feat-x/integrator/`
- AND the branch MUST be `openspec/feat-x/integrator`

---

### Requirement: Skill heartbeat integration

Skills that run long operations (implement, iterate, validate) MUST call `worktree.py heartbeat` at least once per 30 minutes while operating in a worktree.

#### Scenario: Implement skill heartbeats

- WHEN `/linear-implement-feature` runs for 45 minutes in a worktree
- THEN at least one heartbeat MUST have been sent after the initial setup

#### Scenario: Short-running skill skips heartbeat

- WHEN `/linear-cleanup-feature` teardown completes in under 5 minutes
- THEN heartbeat calls are NOT required

---

## MODIFIED Requirements

### Requirement: Cleanup skill runs GC

The `/linear-cleanup-feature` and `/parallel-cleanup-feature` skills MUST invoke `worktree.py gc` before teardown to clean stale peer worktrees from previous failed runs.

#### Scenario: Cleanup with stale peers

- WHEN `/linear-cleanup-feature` is invoked for change `feat-x`
- AND a stale worktree exists at `.git-worktrees/feat-x/old-agent/`
- THEN `gc` MUST remove the stale worktree before proceeding with the primary teardown

---

## REMOVED Requirements

### Requirement: Legacy worktree path support

The `legacy_worktree_path()` function and `../<repo>.worktrees/` fallback in `teardown` and `status` SHALL be removed. The legacy location was deprecated in change `2026-02-25-streamline-worktree-permissions`.

#### Scenario: Teardown with legacy path

- WHEN `worktree.py teardown my-change` is invoked
- AND the worktree exists only at `../<repo>.worktrees/my-change/`
- THEN the command MUST return exit code 1
- AND print a message directing the user to manually move or remove the legacy worktree
