# Proposal: Conditional Worktree Generation

**Change ID**: `conditional-worktree-generation`
**Status**: Draft
**Branch**: `claude/conditional-worktree-generation-3gcmy` (cloud-harness-mandated)

## Why

Today the OpenSpec skill suite (`plan-feature`, `implement-feature`, `cleanup-feature`) assumes every execution environment is a **local multi-agent filesystem** and unconditionally invokes `skills/worktree/scripts/worktree.py setup` to create an isolated git worktree at `.git-worktrees/<change-id>/[<agent-id>/]`. Worktrees solve a real problem locally: when multiple agents run concurrently against the same checkout, they would otherwise clobber each other's working-tree state.

In the **cloud harness** (Claude Code on the web, Codex cloud, and similar) this assumption is wrong:

1. Each agent already runs in its own ephemeral container with an exclusive checkout. Filesystem isolation is provided by the harness, not by git.
2. The harness pre-checks out a mandated branch (e.g., `claude/<slug>-<id>`) at the repo root. `git worktree add` on that branch **fails with** `fatal: '<branch>' is already used by worktree at '/home/user/…'`. Every plan/implement/cleanup run in a cloud session hits this error and falls back to ad-hoc in-place work — silent technical debt: the skills claim to operate in an isolated worktree but don't.
3. Teardown/merge/gc operations designed to clean up a local `.git-worktrees/` tree are wasted work in cloud mode (the container will be destroyed by the harness anyway).

We need one **execution-environment signal** that tells every worktree operation whether the caller already has isolation, and we need it threaded through every call site so the skills do the right thing without per-skill environment detection.

Concrete evidence from this very planning session: `OPENSPEC_BRANCH_OVERRIDE=claude/conditional-worktree-generation-3gcmy python3 skills/worktree/scripts/worktree.py setup conditional-worktree-generation` exits 128 with the "already used by worktree" error before we've written a single artifact.

## What Changes

### Behavioral changes
- **Add an execution-environment detector** (`isolation_provided: bool`) that returns `true` when the harness/container is the isolation boundary.
- **Every `worktree.py` subcommand becomes environment-aware.** When `isolation_provided=true`:
  - `setup` emits `WORKTREE_PATH=$(git rev-parse --show-toplevel) WORKTREE_BRANCH=$(git branch --show-current)` and exits 0 without creating `.git-worktrees/` entries.
  - `teardown`, `pin`, `unpin`, `heartbeat`, `gc` return success silently (no-op).
  - `list`, `status`, `resolve-branch` still work — they're read-only introspection that should continue to function (they just report the in-place checkout as the "worktree").
- **`merge_worktrees.py` becomes environment-aware.** In cloud mode, each work-package already produced its own branch in its own container; merging happens via PR, not via local worktree integration. The script short-circuits with a clear message.
- **`OPENSPEC_BRANCH_OVERRIDE` remains fully independent** of the new signal. Operators can still set the override locally without disabling worktree isolation.
- **Parallel work-packages in cloud mode** map one-container-per-package. The harness spawns a new container per package agent; each container sees `isolation_provided=true` and short-circuits worktree setup. Branch composition (`<parent>--<agent-id>`) still applies so merges via PR work identically to local mode.

### Detection precedence (highest to lowest)
1. **Explicit env var**: `AGENT_EXECUTION_ENV=cloud` (forces cloud) or `AGENT_EXECUTION_ENV=local` (forces local). Also accepts legacy `CLAUDE_CODE_CLOUD=1` as cloud.
2. **Coordinator report**: when the coordinator is reachable and the current agent-id is registered, query the coordinator's discovery service for `isolation_provided`. Cloud-container agents are registered with that flag by the harness's SessionStart hook.
3. **Container heuristic**: presence of `/.dockerenv` OR non-empty `KUBERNETES_SERVICE_HOST` OR `CODESPACES=true`. Heuristic-only decisions are logged so operators can override.

If all three produce no signal, default to `isolation_provided=false` (current behavior — create worktrees). This preserves backward compatibility for local single-agent runs.

### Artifacts and scripts added
- `skills/shared/environment_profile.py` — single source of truth for the detector. Returns a small dataclass `EnvironmentProfile(isolation_provided: bool, source: str, details: dict)`. Source is one of `env_var`, `coordinator`, `heuristic`, `default`.
- `skills/worktree/scripts/worktree.py` — every `cmd_*` short-circuits on `isolation_provided`.
- `skills/worktree/scripts/merge_worktrees.py` — short-circuits; emits guidance to use PR-based integration.
- `skills/tests/worktree/test_environment_profile.py` — unit tests for each detection layer and precedence.
- `skills/tests/worktree/test_worktree_cloud_mode.py` — end-to-end test that `setup`/`teardown`/`merge` no-op under `AGENT_EXECUTION_ENV=cloud`.
- `docs/cloud-vs-local-execution.md` — operator-facing doc describing the signal, precedence, and troubleshooting.

### Scripts/skills updated (no new call-site churn)
- No changes needed to `plan-feature`, `implement-feature`, or `cleanup-feature` SKILL.md files — the short-circuit lives in `worktree.py` itself so all existing `worktree.py setup|teardown|merge|gc` call sites transparently become environment-aware.
- `check_coordinator.py` gains an optional `--isolation-provided` probe so the coordinator layer can report the flag without requiring the skills to query twice.

## Approaches Considered

### Approach A — In-place detection in `worktree.py` (Recommended)

**Description**: Extract a small `environment_profile.py` helper into `skills/shared/`. Every `cmd_*` in `worktree.py` (and the two integration points in `merge_worktrees.py`) calls `EnvironmentProfile.detect()` early and short-circuits to a success stub when `isolation_provided=true`. Call sites in skills (`plan-feature`, `implement-feature`, `cleanup-feature`) do **not** change.

**Pros**:
- Zero churn in SKILL.md files. All three skills already use `eval "$(worktree.py setup …)"`; they keep doing so and transparently get the new behavior.
- Single source of truth — one place to audit the detection logic.
- Reversible: set `AGENT_EXECUTION_ENV=local` to force the old behavior even in a cloud container.
- Fits the "compose: env var > coordinator > heuristic" answer directly.

**Cons**:
- Environment-detection logic lives inside a module that was purely git-plumbing. Mitigated by extracting the detector into `skills/shared/environment_profile.py` and importing it.
- Harder to mock than a strategy-pattern abstraction, but the helper is small and pure; unit tests use env var injection.

**Effort**: M (≈2 work-packages: helper + worktree.py integration, docs + tests)

### Approach B — Thin wrapper script + new call sites

**Description**: Introduce `skills/worktree/scripts/worktree_wrapper.py` that consults `EnvironmentProfile` and either dispatches to `worktree.py` or returns no-op stubs. Update all three SKILL.md files to call the wrapper instead of `worktree.py` directly.

**Pros**:
- Keeps `worktree.py` free of environment-detection concerns — it remains a pure git-plumbing tool.
- The wrapper is naturally testable in isolation; easy to mock.

**Cons**:
- Requires editing 3 SKILL.md files plus `merge_worktrees.py` call sites in parallel-infrastructure. More review surface.
- Introduces two scripts with overlapping responsibilities — future maintainers have to remember which to call.
- Call-site churn raises the risk of missing a skill (e.g., `autopilot`, `cleanup-feature`, `iterate-on-plan`) that also invokes `worktree.py` directly.

**Effort**: M-L (wrapper + 5+ SKILL.md edits + tests)

### Approach C — Strategy protocol (`IsolationProvider`)

**Description**: Mirror the `TestEnvironment` protocol pattern already established by `live-service-testing`. Define an `IsolationProvider` protocol with `setup/teardown/merge/pin/heartbeat/gc` methods. Implement `GitWorktreeIsolation` (current behavior) and `HarnessContainerIsolation` (all no-ops). `EnvironmentProfile` becomes a factory that returns the right provider. `worktree.py` becomes a thin CLI shim over whichever provider is selected.

**Pros**:
- Mirrors an in-repo precedent the team already understands.
- Extensible — a future devcontainer or remote-SSH isolation provider slots in without modifying existing providers.
- Cleanest tests: each provider is tested in isolation against the protocol contract.

**Cons**:
- Largest refactor. Risk of drift between `worktree.py`'s current CLI surface (13 subcommands) and the protocol methods.
- Overengineered given only two providers exist near-term. YAGNI risk.
- Adds a second pattern (two strategy protocols) that readers must learn.

**Effort**: L (protocol + 2 implementations + shim + tests + doc)

### Recommended: Approach A

Matches the user's explicit discovery answers most directly: a single composed detector that makes every worktree op a no-op when the harness provides isolation, with `OPENSPEC_BRANCH_OVERRIDE` left untouched. Smallest reversible change, no call-site churn across 5+ skills, and the extracted `environment_profile.py` helper is available for future reuse (e.g., validation skills that want to know whether to spin up Docker stacks). If a third isolation mechanism emerges, we can escalate to Approach C later with the helper already in place.

### Selected Approach (Gate 1 outcome)

**Approach A — In-place detection in `worktree.py`** selected by user at Gate 1.

Downstream artifacts (specs, tasks, design, contracts, work-packages) implement Approach A specifically:

- New module `skills/shared/environment_profile.py` is the single source of truth for `isolation_provided` detection. Precedence: `AGENT_EXECUTION_ENV` env var → coordinator discovery query → container heuristic → default (`false`).
- `skills/worktree/scripts/worktree.py` imports the helper; every `cmd_*` short-circuits early when `isolation_provided=true`. `setup` emits `WORKTREE_PATH=$(git rev-parse --show-toplevel)` and `WORKTREE_BRANCH=$(git branch --show-current)`. `teardown`, `pin`, `unpin`, `heartbeat`, `gc` exit 0 silently. `list`, `status`, `resolve-branch` continue to function (read-only introspection).
- `skills/worktree/scripts/merge_worktrees.py` short-circuits with a clear message directing operators to PR-based integration.
- Approaches B (wrapper + SKILL.md edits) and C (strategy protocol) are **not** implemented; work-packages intentionally scope out call-site churn and protocol abstractions to keep the change minimal and reversible.

## Out of Scope

- Multi-container orchestration in the cloud harness. Today the harness spawns one container per agent; if and when that changes, parallel work-package execution may need a coordinator-driven dispatch layer. This proposal assumes the harness handles container lifecycle.
- Refactoring `worktree.py` to use a strategy protocol (Approach C). We can revisit if a third isolation provider appears.
- Changing the coordinator's discovery schema. We add an `isolation_provided` field on agent registration but keep it optional; cloud harnesses opt in by setting it.
- Changing `OPENSPEC_BRANCH_OVERRIDE` semantics. The two signals stay orthogonal per Gate 1 discovery.

## Impact

| Area | Impact |
|---|---|
| Local single-agent runs | No behavior change. `EnvironmentProfile.detect()` returns `isolation_provided=false` via default path. |
| Local parallel runs | No behavior change. Worktrees continue to provide filesystem isolation per agent. |
| Cloud single-agent runs | **Fixes current bug**. `setup` no longer errors with "already used by worktree"; all ops no-op. |
| Cloud parallel runs | Each work-package runs in its own container; per-agent worktrees unnecessary. Branch composition (`<parent>--<agent-id>`) unchanged. |
| Coordinator | Optional extension: `isolation_provided` on agent registration. Coordinator continues to work if cloud harnesses don't populate it (falls through to heuristic). |
| Existing in-progress changes | Minor overlap with `harness-engineering-features` (session scope) and `specialized-workflow-agents` (archetype routing). Detector is orthogonal — those changes can adopt it later if they need environment-aware behavior. |
