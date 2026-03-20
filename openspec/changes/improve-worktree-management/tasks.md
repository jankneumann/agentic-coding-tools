# Tasks: improve-worktree-management

## 1. Core worktree.py changes

- [ ] 1.1 Add registry module: JSON read/write/update for `.git-worktrees/.registry.json`
  **Dependencies**: None
  **Files**: `scripts/worktree.py`
  **Traces**: Worktree registry requirement
  **Tests**: Registry CRUD, missing file creation, concurrent write tolerance

- [ ] 1.2 Add `--agent-id` flag to `setup` and update path/branch computation
  **Dependencies**: 1.1
  **Files**: `scripts/worktree.py`
  **Traces**: Agent-scoped worktree paths requirement
  **Tests**: Path with agent-id, path without agent-id (backward compat), path with prefix+agent-id

- [ ] 1.3 Add `--agent-id` flag to `teardown` and update registry on removal
  **Dependencies**: 1.1, 1.2
  **Files**: `scripts/worktree.py`
  **Traces**: Agent-scoped worktree paths requirement, Worktree registry requirement
  **Tests**: Teardown with agent-id removes entry, teardown without agent-id backward compat

- [ ] 1.4 Add `heartbeat` subcommand
  **Dependencies**: 1.1
  **Files**: `scripts/worktree.py`
  **Traces**: Heartbeat command requirement
  **Tests**: Heartbeat updates timestamp, heartbeat for unknown entry returns error

- [ ] 1.5 Add `list` subcommand with staleness indicator
  **Dependencies**: 1.1
  **Files**: `scripts/worktree.py`
  **Traces**: List command requirement
  **Tests**: List with entries, list empty, staleness marking at 1-hour threshold

- [ ] 1.6 Add `pin` and `unpin` subcommands
  **Dependencies**: 1.1
  **Files**: `scripts/worktree.py`
  **Traces**: Pin and unpin commands requirement
  **Tests**: Pin sets flag, unpin clears flag, pin with agent-id, pin unknown entry returns error

- [ ] 1.7 Add `gc` subcommand with configurable stale threshold (default 24h) and pin awareness
  **Dependencies**: 1.1, 1.3, 1.6
  **Files**: `scripts/worktree.py`
  **Traces**: Garbage collection command requirement
  **Tests**: GC removes stale, preserves active, preserves pinned, --force overrides pin, custom threshold, orphaned registry entry cleanup

- [ ] 1.8 Remove `legacy_worktree_path()` and legacy fallback from teardown/status
  **Dependencies**: 1.3
  **Files**: `scripts/worktree.py`
  **Traces**: Legacy worktree path support removal
  **Tests**: Teardown with only legacy path returns error with helpful message

- [ ] 1.9 Update `status` to support `--agent-id` and show agent-scoped info
  **Dependencies**: 1.1, 1.2
  **Files**: `scripts/worktree.py`
  **Traces**: Agent-scoped worktree paths requirement
  **Tests**: Status for specific agent-id, status listing all agents under a change-id

## 2. Tests

- [ ] 2.1 Add registry unit tests
  **Dependencies**: 1.1
  **Files**: `scripts/tests/test_worktree.py`
  **Traces**: Worktree registry requirement

- [ ] 2.2 Add agent-id path computation tests
  **Dependencies**: 1.2
  **Files**: `scripts/tests/test_worktree.py`
  **Traces**: Agent-scoped worktree paths requirement

- [ ] 2.3 Add heartbeat, list, pin/unpin, and gc command tests
  **Dependencies**: 1.4, 1.5, 1.6, 1.7
  **Files**: `scripts/tests/test_worktree.py`
  **Traces**: Heartbeat, List, Pin/Unpin, GC requirements

- [ ] 2.4 Remove legacy path tests, add legacy-removal error message test
  **Dependencies**: 1.8
  **Files**: `scripts/tests/test_worktree.py`
  **Traces**: Legacy worktree path support removal

## 3. Skill updates (parallelizable group — no file overlaps)

- [ ] 3.1 Update `linear-implement-feature/SKILL.md` — agent-id propagation + heartbeat
  **Dependencies**: 1.2, 1.4
  **Files**: `skills/linear-implement-feature/SKILL.md`
  **Traces**: Skill heartbeat integration, Agent-scoped worktree paths

- [ ] 3.2 Update `linear-cleanup-feature/SKILL.md` — gc before teardown + agent-id
  **Dependencies**: 1.3, 1.7
  **Files**: `skills/linear-cleanup-feature/SKILL.md`
  **Traces**: Cleanup skill runs GC

- [ ] 3.3 Update `linear-iterate-on-implementation/SKILL.md` — agent-id detection
  **Dependencies**: 1.2
  **Files**: `skills/linear-iterate-on-implementation/SKILL.md`
  **Traces**: Agent-scoped worktree paths

- [ ] 3.4 Update `linear-validate-feature/SKILL.md` + `start-worktree-api.sh` — agent-id detection
  **Dependencies**: 1.2
  **Files**: `skills/linear-validate-feature/SKILL.md`, `skills/linear-validate-feature/scripts/start-worktree-api.sh`
  **Traces**: Agent-scoped worktree paths

- [ ] 3.5 Update `parallel-implement-feature/SKILL.md` — require agent-id per worker, integrator pattern
  **Dependencies**: 1.2
  **Files**: `skills/parallel-implement-feature/SKILL.md`
  **Traces**: Parallel skill agent-id enforcement

- [ ] 3.6 Update `parallel-cleanup-feature/SKILL.md` — gc across all agent worktrees
  **Dependencies**: 1.7
  **Files**: `skills/parallel-cleanup-feature/SKILL.md`
  **Traces**: Cleanup skill runs GC, Garbage collection command

- [ ] 3.7 Update `fix-scrub/SKILL.md` — agent-id with prefix
  **Dependencies**: 1.2
  **Files**: `skills/fix-scrub/SKILL.md`
  **Traces**: Agent-scoped worktree paths

- [ ] 3.8 Update `openspec-beads-worktree/SKILL.md` — new naming scheme
  **Dependencies**: 1.2
  **Files**: `skills/openspec-beads-worktree/SKILL.md`
  **Traces**: Agent-scoped worktree paths, Parallel skill agent-id enforcement

## 4. Bootstrap and config

- [ ] 4.1 Update `scripts/worktree-bootstrap.sh` to accept and propagate agent-id
  **Dependencies**: 1.2
  **Files**: `scripts/worktree-bootstrap.sh`
  **Traces**: Agent-scoped worktree paths

- [ ] 4.2 Add `.git-worktrees/.registry.json` to `.gitignore`
  **Dependencies**: None
  **Files**: `.gitignore`
  **Traces**: Worktree registry requirement

## 5. Documentation

- [ ] 5.1 Update `CLAUDE.md` worktree management section
  **Dependencies**: 1.2, 1.6, 1.7
  **Files**: `CLAUDE.md`
  **Traces**: All requirements (documentation)

- [ ] 5.2 Update `docs/lessons-learned.md` with parallel worktree best practices
  **Dependencies**: None
  **Files**: `docs/lessons-learned.md`
  **Traces**: Parallel skill agent-id enforcement

- [ ] 5.3 Update `docs/two-level-parallel-agentic-development.md` worktree section
  **Dependencies**: None
  **Files**: `docs/two-level-parallel-agentic-development.md`
  **Traces**: Agent-scoped worktree paths, Parallel skill agent-id enforcement

## Parallel execution graph

```
Group A (no deps):     4.2, 5.2, 5.3
Group B (after 1.1):   1.2, 1.4, 1.5, 1.6, 2.1
Group C (after 1.2):   1.3, 1.9, 4.1, 3.1, 3.3, 3.4, 3.5, 3.7, 3.8, 2.2
Group D (after 1.3+1.6): 1.7, 1.8
Group E (after 1.7):   2.3, 3.2, 3.6
Group F (after 1.8):   2.4
Group G (after all):   5.1
```

Maximum parallel width: 10 (Group C)
Total tasks: 24
