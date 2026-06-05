# Worktree Management

- **Launcher invariant**: In local CLI execution, the shared checkout is an orchestration surface, not a work surface. Every skill that creates, modifies, deletes, formats, commits, pushes, or otherwise mutates repository files or git state MUST work in a managed worktree, never the shared checkout, unless it is an explicit sync-point skill. In cloud-harness environments (each agent gets its own ephemeral container), this invariant is provided by the container itself — see **Execution-environment detection** below; worktree write ops become no-ops and skills operate directly on the harness-provided checkout.
- **Location**: `.git-worktrees/<change-id>/` for single-agent, `.git-worktrees/<change-id>/<agent-id>/` for parallel
- **Registry**: `.git-worktrees/.registry.json` tracks owner, branch, heartbeat, pin status
- **Commands**: `python3 skills/worktree/scripts/worktree.py setup|teardown|status|detect|heartbeat|list|pin|unpin|gc`
- **Merge**: `python3 skills/worktree/scripts/merge_worktrees.py <change-id> <pkg-id>...` merges package branches into feature branch
- **Agent-id**: Pass `--agent-id` for parallel disambiguation. Omit for single-agent (backward compatible)
- **Pin**: Use `pin` to protect worktrees from GC during overnight pauses or waiting on input
- **GC**: Default 24h stale threshold. Pinned worktrees survive GC unless `--force`
- **Branch naming**: Agent branches use `--` separator: `openspec/<change-id>--<agent-id>`. Git cannot have both `refs/heads/a/b` and `refs/heads/a/b/c`, so `/` between change-id and agent-id would conflict with the feature branch `openspec/<change-id>`.
- **Rule**: One agent, one worktree, one branch. Never share a worktree between agents
- **Operator branch override**: Set `OPENSPEC_BRANCH_OVERRIDE=<branch>` in the environment to force `worktree.py setup` to use that branch instead of the default `openspec/<change-id>`. This is how the Claude cloud harness (or any operator) mandates a specific branch like `claude/fix-<slug>` for an entire session.
  - **Precedence**: explicit `--branch` flag > `OPENSPEC_BRANCH_OVERRIDE` env var > `openspec/<change-id>` default.
  - **Session stability**: The override must stay set for every phase (plan → implement → cleanup) or phases will diverge onto different branches.
  - **Agent-id composition**: When both the override AND `--agent-id` are passed, they compose as `<override>--<agent-id>` (e.g. `claude/op-9P9o1--wp-backend`). This preserves the existing parallel-disambiguation scheme so work-package agents don't clobber each other's commits. The `--` separator avoids the git ref storage collision that `/` would cause.
  - **Parent vs agent branch**: Two branch variables matter for skills that operate on both:
    - `$WORKTREE_BRANCH` (emitted by `worktree.py setup` via stdout `eval`) — this worktree's own branch, which for parallel agents is `<parent>--<agent-id>`.
    - `$FEATURE_BRANCH` (query via `worktree.py resolve-branch <change-id> --parent`) — the PARENT feature/session branch, used for `git push`, `gh pr create/merge`, `git branch -d`, and lock cleanup.
    In single-agent mode they're equal; in parallel mode they differ.
  - **Branch resolution sharing**: `merge_worktrees.py` imports `resolve_branch`/`resolve_parent_branch` from `worktree.py` so both scripts always agree on what branch a given `(change-id, agent-id)` pair resolves to. Don't introduce a third copy of this logic elsewhere — call into `worktree.py` or use the `resolve-branch` CLI subcommand.
- **Execution-environment detection**: `skills/shared/environment_profile.py` exposes `detect() -> EnvironmentProfile` with `isolation_provided: bool`. When true (cloud harness, Codespaces, K8s pod), every `worktree.py` write command (`setup|teardown|pin|unpin|heartbeat|gc`) and `merge_worktrees.py` short-circuit to a silent success. Read-only commands (`list|status|resolve-branch`) are unchanged. Detection precedence: `AGENT_EXECUTION_ENV` (cloud|local) → coordinator `GET /agents/<id>` → `/.dockerenv`/`KUBERNETES_SERVICE_HOST`/`CODESPACES` heuristic → default false. Set `WORKTREE_DEBUG=1` to see the decision layer. Full operator guide: [docs/cloud-vs-local-execution.md](../cloud-vs-local-execution.md). `OPENSPEC_BRANCH_OVERRIDE` remains orthogonal — it controls branch naming, not whether worktrees are created.
- **Mutation guard**: Mutating skills SHOULD call `skills/.venv/bin/python skills/shared/checkout_policy.py require-mutation` after `worktree.py setup` and before their first write. The guard allows isolated harnesses, managed local worktrees, and explicit sync-point operations; it rejects local shared-checkout mutation.

## Sync-Point Skills

Some skills operate directly on the shared checkout / main branch rather than in worktrees. These are **sync-point skills** — convergence operations that integrate work back into main.

| Skill | Why main is safe |
|---|---|
| `/merge-pull-requests` | User-invoked merge of approved PRs; inherently sequential |
| `/update-specs` | Post-merge documentation commit; no concurrent conflict risk |
| `/cleanup-feature` | Uses a worktree internally but touches main at the end |

**Contract for sync-point skills:**
- **Exclusive access**: Must not run while other agents hold active worktrees. Use `shared.check_no_active_agents()` to verify before proceeding.
- **User-invoked only**: Never triggered automatically by the coordinator or other skills.
- **Dirty-state check**: Must verify the working directory is clean before touching main.
- **`--force` escape hatch**: Allow the user to override the active-agent guard when they know it's safe (e.g., stale registry entries from crashed agents).

The active-agent guard checks `.git-worktrees/.registry.json` for non-stale entries (heartbeat within the last hour). If active agents are found, it aborts with guidance on how to proceed.
