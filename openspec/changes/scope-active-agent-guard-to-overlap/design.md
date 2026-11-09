# Design: Scope the active-agent guard to overlapping work

## Context

Five call sites read `.git-worktrees/.registry.json` and refuse to touch main
while any entry is pinned or has a heartbeat under one hour old:

| Site | Entry point | Override today |
|---|---|---|
| merge plan execution | `execution_safety.default_sync_point_guard` via `execute_plan.py` | none (kernel) |
| main convergence kernel | `main_convergence.check_active_agents` (layer 1 of 3) | none |
| expedite readiness gate | `expedite.check_active_agents` | reports `--force` for cleanup |
| SKILL.md preflight | `active_agents.py` CLI in merge-pull-requests and update-specs | `--force` |
| observability | `agent-coordinator/src/sync_points.py` (own copy of the predicate) | n/a |

All five share one semantic: active means "exists". None of them look at what
the worktree is for. This design replaces that with an overlap test and routes
the choice through the trust posture contract, which is already the single
place where unattended behaviour is authorized.

## Decisions

### D1: Overlap is defined on branch and change id, nothing else

A worktree entry overlaps a sync-point operation when either holds:

- `entry.branch` is one of the branches the operation will merge or rewrite, or
- `entry.change_id` is one of the changes the operation will archive, clean up,
  or write specs for.

Path overlap was considered and rejected. The registry does not record which
files a worktree touches, computing it would need a diff per worktree at every
sync point, and the coordinator's file locks already cover the file level for
agents that use them.

`check_no_active_agents` gains a keyword `scope: OverlapScope | None`.
`OverlapScope` is a frozen dataclass with `branches: frozenset[str]` and
`change_ids: frozenset[str]`. `scope=None` keeps today's repo-wide behaviour so
no caller changes meaning until it opts in. An empty scope (both sets empty)
is a valid overlap scope that blocks on nothing except lock contention; it is
what main convergence passes when it merged no PR and archived no change.

### D2: The posture key selects the mode; the call site supplies the scope

`TRUST_POSTURE.md` front matter gains an optional top-level mapping:

```yaml
sync_point:
  active_agent_guard: overlap   # repo-wide | overlap | off
```

- Absent key, absent mapping, or absent file: `overlap`. This differs from
  gates, where absence fails closed to `block`, and it is deliberate: the guard
  is a liveness check, not an authorization, and the plan's owner decision is
  that overlap is the correct default. `off` is never a default.
- `repo-wide`: every call site ignores the scope it was given and behaves as
  today. This is the rollback lever.
- `off`: the worktree check is skipped for user-invoked runs. The coordinator
  lock check is not affected by this key.
- A scheduled invocation (one that passed `authorize_sync_window`) treats
  `off` as `overlap`, because the skill-workflow requirement already says a
  scheduled run SHALL NOT relax the active-agent guard.

`trust_posture.py` exposes `active_agent_guard_mode(posture) -> GuardMode` and
validates the value with the same malformed-contract path as `sync_windows`:
an unknown value is a `PostureValidationError`, never a silent fallback.

### D3: Each call site computes its own scope from what it is about to do

| Site | Scope |
|---|---|
| `execute_plan.py` | `branches={live PR head branch}` |
| `main_convergence.converge` | `branches=` heads of PRs merged in this run, `change_ids=` changes handed to cleanup in deferred-commit mode |
| `expedite.py` | `change_ids={change_id}`, `branches={openspec/<change_id>, openspec/<change_id>--*}` resolved from the registry's own entries for that change |
| SKILL.md preflight CLI | `--branch` and `--change-id`, both repeatable; omitting both keeps repo-wide |
| `sync_points.py` | optional `branches` and `change_ids` query parameters; omitted keeps repo-wide so existing frontends do not change |

`default_sync_point_guard(repo_root)` becomes
`default_sync_point_guard(repo_root, *, scope=None)`. The guard result dict
gains `"scope": {"mode": ..., "branches": [...], "change_ids": [...]}` so a
blocked execution tells the operator what was checked.

### D4: The coordinator lock stays as it is

Layer 2 of main convergence (`sync-point:main-convergence`) is unchanged.
Contention still blocks and absence still degrades with a warning. This change
narrows layer 1 only. The two layers now have distinct jobs: layer 1 protects
in-flight worktrees on the branches being merged, layer 2 serializes writers to
main.

### D5: Prototype worktrees unpin on pick, not on teardown

`worktree.py setup` auto-pins `proto/` worktrees so the GC timer cannot delete
them while a human compares variants. That pin also makes every prototype an
active agent forever under the old guard. The pin is kept, but
`/prototype-feature` calls `worktree.py unpin` for every variant when it
records the human pick. The picked variant's branch is then merged like any
other PR, and the overlap guard sees it only if a heartbeat is fresh.

### D6: `sync_points.py` imports the predicate instead of copying it

`agent-coordinator/src/sync_points.py` carries its own `_check_active_worktrees`
that "mirrors" the skills helper. Two copies of a predicate that is about to
change is how the frontends and the skills drift apart. The coordinator cannot
import from `skills/` at runtime (separate venv, separate Dockerfile COPY set),
so the shared predicate moves to a dependency-free module `active_agents_core.py`
that both trees vendor, and a parity test asserts the two copies are
byte-identical. The existing `check_docker_imports.py` gate keeps the vendored
copy honest.

## Alternatives considered

- **Keep repo-wide, lower the stale threshold.** Does not help: a change in
  active implementation heartbeats every few minutes by design.
- **Drop the guard and rely on the coordinator lock alone.** Rejected by the
  existing design of main convergence: the coordinator is absent often enough
  on solo hosts that a lock-only guard is missing exactly when it matters.
- **Scope by file overlap.** Rejected in D1.
- **Make `--force` available to the kernel.** Rejected: it would make the
  default path a manual override instead of fixing the predicate.

## Rollback

Set `sync_point.active_agent_guard: repo-wide` in `TRUST_POSTURE.md`. No code
revert is needed; every call site honours the key on its next run. If the key
itself is the problem, reverting the change restores the previous files, since
no registry format or lock key changes.

## Migration

None. The registry format is unchanged. Existing pinned prototype worktrees
remain pinned until their change is picked or cleaned up; the operator may
unpin them by hand with `worktree.py unpin <change-id>`.
