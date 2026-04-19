# Design: Conditional Worktree Generation

## Goals

- One function, `EnvironmentProfile.detect()`, is the single source of truth for "does this environment already provide filesystem isolation?"
- Every `worktree.py` and `merge_worktrees.py` entrypoint short-circuits cleanly when `isolation_provided=true`, leaving `$PWD`/`HEAD` untouched.
- Zero changes to SKILL.md call sites. Every existing `eval "$(worktree.py setup …)"` invocation in plan/implement/cleanup/autopilot/iterate skills transparently gets the new behavior.
- `OPENSPEC_BRANCH_OVERRIDE` semantics are untouched; the two signals compose without coupling.
- Local single-agent and local-parallel workflows are byte-for-byte unchanged when no cloud signal fires.

## Non-Goals

- **No new isolation providers** (container-based, devcontainer, remote-SSH). If we need those later, we can escalate to the strategy-protocol approach (C) with `environment_profile.py` already extracted.
- **No SKILL.md refactors**. We don't "upgrade" plan-feature / implement-feature / cleanup-feature to use a new wrapper.
- **No changes to `OPENSPEC_BRANCH_OVERRIDE`** semantics, parsing, or precedence.
- **No coordinator schema changes** beyond an *optional* `isolation_provided` field on agent registration. The coordinator continues to work if cloud harnesses don't populate the field.

## Key Decisions

### D1 — Detection lives in `skills/shared/environment_profile.py`, not inside `worktree.py`

**Decision**: Extract a new module `skills/shared/environment_profile.py` that exposes a pure function `detect() -> EnvironmentProfile`. `worktree.py` and `merge_worktrees.py` import it.

**Rationale**: Keeps detection unit-testable without mocking `git worktree`. Lets future callers (e.g., `validate-feature`, which may also want to know whether to spin up a Docker stack) reuse the helper without creating a circular dependency through the worktree module.

**Rejected alternative**: Define the function inline in `worktree.py`. Smaller diff but couples an env-detection concern to a git-plumbing module and makes reuse awkward.

### D2 — Precedence: env var > coordinator > heuristic > default (false)

**Decision**: Evaluate signals strictly in order; the first definitive answer wins.

**Rationale**: Aligns with user's Gate-1 discovery answer ("compose: env var > coordinator > heuristic"). Explicit operator intent (env var) always beats automated detection. Coordinator report beats unreliable container heuristics (which fire incorrectly in local dev containers). Heuristic is the last-resort fallback before defaulting to "no isolation" — the safe default that preserves legacy behavior.

**Rejected alternative**: Unanimous vote (all three must agree). Too conservative; would fail to skip worktrees in the common cloud case where only the harness sets the env var.

### D3 — `isolation_provided=true` makes write ops no-op, not error

**Decision**: `setup`, `teardown`, `pin`, `unpin`, `heartbeat`, `gc` all exit 0 silently (with a single stderr log line) when `isolation_provided=true`. `merge_worktrees.py` does the same with a guidance message pointing to PR-based integration.

**Rationale**: Errors break existing skill flows that call `worktree.py` without guards. A success-stub makes the feature a pure addition — flip the env var and everything continues working.

**Rejected alternative**: Error with a clear message ("worktrees not needed under isolation_provided=true"). Forces every skill to add a guard, defeating the "no SKILL.md changes" goal.

### D4 — Read-only operations (`list`, `status`, `resolve-branch`) continue to function

**Decision**: `list`, `status`, and `resolve-branch` execute normally regardless of `isolation_provided`. Under cloud mode, `status` reports the in-place checkout as the current worktree.

**Rationale**: Callers (e.g., `merge_worktrees.py` in local mode, cleanup scripts that query registry state) need these introspection commands to work. They don't mutate state, so they're safe.

### D5 — `setup` under `isolation_provided=true` emits `WORKTREE_PATH=git-rev-parse-show-toplevel`

**Decision**: In cloud mode, `worktree.py setup` emits:
```
WORKTREE_PATH=$(git rev-parse --show-toplevel)
WORKTREE_BRANCH=$(git branch --show-current)
```

**Rationale**: Skill call sites do `eval "$(worktree.py setup …)"` and then `cd "$WORKTREE_PATH"`. Setting these to the repo root and the currently-checked-out branch means the subsequent `cd` is a no-op (we're already there) and downstream `git` commands see the expected state. The cloud harness is responsible for ensuring the correct branch is checked out before invoking the skill — in practice, this is the `claude/<slug>-<id>` branch from the harness's branch-override mechanism.

**Rejected alternative**: Emit empty/null paths and require skills to detect the cloud case. Defeats the transparent-upgrade goal.

### D6 — Heuristic uses a conservative set of container markers

**Decision**: The heuristic returns `isolation_provided=true` when ANY of:
- `/.dockerenv` exists (standard Docker marker)
- `KUBERNETES_SERVICE_HOST` is non-empty (K8s pod)
- `CODESPACES=true` (GitHub Codespaces)

**Rationale**: These three markers cover the main cloud-harness substrates. We intentionally do *not* use hostname patterns or `/proc/1/cgroup` parsing — those are noisy in local dev containers where operators DO want worktree isolation (they're testing multi-agent workflows in a container).

**Rejected alternative**: Also check `HOSTNAME` matches a cloud pattern. Too brittle — local devs often run in named containers that match arbitrary patterns.

### D7 — Coordinator integration is optional and non-blocking

**Decision**: The coordinator query (`GET /agents/<agent-id>` or MCP equivalent) has a short timeout (500ms). On timeout, missing agent-id, or any error, the detector falls through to the heuristic layer.

**Rationale**: We must not introduce a coordinator hard-dependency into `worktree.py`. The coordinator can be unreachable (network hiccup) or simply not deployed (local single-agent run with no coordinator). Failing through to the next layer means detection degrades gracefully.

**Rejected alternative**: Require coordinator for cloud mode. Creates a chicken-and-egg problem where the harness must have the coordinator online before it can tell skills to skip worktrees.

### D8 — `merge_worktrees.py` short-circuit exits 0 with guidance, not error

**Decision**: When `isolation_provided=true`, `merge_worktrees.py` exits 0 after printing guidance pointing to PR-based integration.

**Rationale**: Cloud mode uses one-container-per-package (Gate 1 answer). Each package agent pushes its own branch; integration happens when the PR lands, not via local git-merge. An error would break `/cleanup-feature` which calls this script unconditionally.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ skills/shared/environment_profile.py                     │
│                                                          │
│ EnvironmentProfile(                                      │
│   isolation_provided: bool,                              │
│   source: Literal["env_var","coordinator",               │
│                   "heuristic","default"],                │
│   details: dict,                                         │
│ )                                                        │
│                                                          │
│ detect() -> EnvironmentProfile:                          │
│   1. env_var layer   (AGENT_EXECUTION_ENV, legacy)       │
│   2. coordinator layer (HTTP/MCP, 500ms timeout)         │
│   3. heuristic layer (/.dockerenv, K8s, Codespaces)      │
│   4. default        (isolation_provided=false)           │
└─────────────────────────────────────────────────────────┘
          ▲                       ▲
          │ imports               │ imports
          │                       │
┌─────────┴────────────┐ ┌────────┴────────────────┐
│ skills/worktree/     │ │ skills/worktree/         │
│   scripts/worktree.py│ │   scripts/merge_worktrees│
│                      │ │     .py                  │
│ Every cmd_*:         │ │                          │
│   profile = detect() │ │ main():                  │
│   if profile.        │ │   profile = detect()     │
│     isolation_       │ │   if profile.            │
│     provided:        │ │     isolation_provided:  │
│     <short-circuit>  │ │     <guidance> exit 0    │
│   else:              │ │   else: <original merge> │
│     <original op>    │ │                          │
└──────────────────────┘ └──────────────────────────┘
          ▲
          │ calls via eval
          │
┌─────────┴─────────────────────────────────────────────┐
│ SKILL.md files (plan-feature, implement-feature,       │
│ cleanup-feature, autopilot, iterate-on-*, …)           │
│                                                        │
│ UNCHANGED. They keep doing:                            │
│   eval "$(worktree.py setup <change-id> [--agent-id])" │
│   cd "$WORKTREE_PATH"                                  │
└────────────────────────────────────────────────────────┘
```

## Error Handling

| Condition | Behavior |
|---|---|
| `AGENT_EXECUTION_ENV` has an unrecognized value | Log warning to stderr; fall through to coordinator layer |
| Coordinator unreachable / 500ms timeout | Fall through to heuristic layer; one stderr log line with `coordinator_error=<reason>` |
| Coordinator returns agent-id not found | Fall through to heuristic layer silently |
| `/.dockerenv` read fails (permissions) | Treat as absent; continue heuristic evaluation |
| `git rev-parse --show-toplevel` fails in cloud mode | Propagate the error — we're not in a git repo, short-circuit is meaningless |

## Testing Strategy

- **Unit tests** (`skills/tests/worktree/test_environment_profile.py`): Per-layer detection with env-var injection (via `monkeypatch`), mocked coordinator responses (using `responses` / `pytest-httpx`), and tmp-path heuristics (monkeypatched `/.dockerenv` path).
- **Behavior tests** (`skills/tests/worktree/test_worktree_cloud_mode.py`): Invoke `worktree.py setup|teardown|pin|gc` as subprocess under `AGENT_EXECUTION_ENV=cloud`; assert `.git-worktrees/` remains empty and `WORKTREE_PATH` matches `git rev-parse --show-toplevel`.
- **Regression tests** (`skills/tests/worktree/test_worktree_local_mode.py`): Same subcommands under `AGENT_EXECUTION_ENV=local` (explicit) assert pre-change behavior — `.git-worktrees/<change-id>/` is created and populated.
- **Merge short-circuit test** (`skills/tests/worktree/test_merge_cloud_mode.py`): Invoke `merge_worktrees.py` under cloud mode; assert exit 0, no `git merge` invocation, guidance message on stderr.

## Observability

Every short-circuit emits exactly one stderr line of the form:
```
worktree: skipped <op> (isolation_provided=true, source=<env_var|coordinator|heuristic>)
```

This is intentionally one line per operation — not per invocation — to keep log volume predictable in long-running cloud sessions. Operators who want to debug detection can export `WORKTREE_DEBUG=1` to get the full `EnvironmentProfile` dict on stderr.

## Rollout

The change is a pure addition. Deployment steps:

1. Land `environment_profile.py` with 100% default-path coverage.
2. Land `worktree.py` short-circuits (all cmd_* plus introspection pass-throughs).
3. Land `merge_worktrees.py` short-circuit.
4. Land optional coordinator `isolation_provided` field (non-breaking).
5. Document in `docs/cloud-vs-local-execution.md` + update project.md's "MCP for local, HTTP for cloud" note to cross-reference.
6. Cloud harness (separate repo) starts setting `AGENT_EXECUTION_ENV=cloud` on session start.

Until step 6 ships in the harness, the heuristic layer (`/.dockerenv`) will correctly fire in cloud containers as a safety net, so the fix is effective before the harness change lands.
