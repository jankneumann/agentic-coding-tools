
# Project Guidelines

## Workflow

Unified skills with **tiered execution** — each skill auto-selects its tier at startup based on coordinator availability and feature complexity:

| Tier | When | Planning Artifacts | Execution |
|------|------|-------------------|-----------|
| **Coordinated** | Coordinator available | Contracts + work-packages + resource claims | Multi-agent DAG via coordinator |
| **Local parallel** | No coordinator, complex feature | Contracts + work-packages (no claims) | DAG via built-in Agent parallelism |
| **Sequential** | Simple feature | Tasks.md + contracts + work-packages (single package) | Single-agent sequential |

```
/explore-feature [focus-area] (optional)               → Candidate shortlist for next work
/plan-feature <description>                            → Proposal approval gate
  /iterate-on-plan <change-id> (optional)              → Refines plan before approval
  /parallel-review-plan <change-id> (optional)         → Independent plan review (vendor-diverse)
/implement-feature <change-id>                         → PR review gate (runs spec + evidence validation)
  /iterate-on-implementation <change-id> (optional)    → Refinement complete
  /parallel-review-implementation <change-id> (optional) → Per-package review (vendor-diverse)
/cleanup-feature <change-id>                           → Done (runs deploy + security validation before merge)

# Roadmap orchestration (multi-change decomposition + iterative execution)
/plan-roadmap <proposal-path>                          → Decompose proposal into prioritized roadmap
/autopilot-roadmap <workspace-path>                    → Execute roadmap items with learning feedback
```

Validation is automatic: `/implement-feature` runs environment-safe checks (spec, evidence), `/cleanup-feature` and `/merge-pull-requests` run Docker-dependent checks (deploy, smoke, security, E2E) before merge. Both delegate to `/validate-feature` with `--phase` selectors. `/validate-feature` can also be invoked directly for a full manual pass.

Old `linear-*` and `parallel-*` prefixed names are accepted as trigger aliases (e.g., "parallel plan feature" triggers `/plan-feature` with at least local-parallel tier).

### Infrastructure Skills

- **`coordination-bridge`** — Coordinator detection (`check_coordinator.py`) and HTTP fallback bridge
- **`parallel-infrastructure`** — Shared parallel execution scripts: DAG scheduler, review dispatcher, consensus synthesizer, scope checker
- **`roadmap-runtime`** — Shared roadmap library: artifact models, checkpoint management, learning-log helpers, sanitization, context assembly
- **`validate-feature`** — Validation phases (spec, evidence, deploy, smoke, security, e2e); called by implement-feature, cleanup-feature, and merge-pull-requests with `--phase` selectors
- **`parallel-review-plan`** / **`parallel-review-implementation`** — Vendor-diverse review utilities (used by implement-feature and autopilot)

See [Parallel Agentic Development](docs/parallel-agentic-development.md) for the full implementation reference.

## Python Environment

- **uv for all Python environments**: Use `uv` (not pip, pipenv, or poetry) for dependency management and virtual environments across all Python projects. CI uses `astral-sh/setup-uv@v5`.
- **agent-coordinator**: `cd agent-coordinator && uv sync --all-extras` to install. Venv at `agent-coordinator/.venv`.
- **skills (infrastructure)**: `cd skills && uv sync --all-extras` to install. Venv at `skills/.venv`. Covers worktree, validation, architecture, and other infrastructure skill scripts.
- **Running tools**: Activate the relevant venv first (`source .venv/bin/activate`) or use the venv's Python directly (e.g., `skills/.venv/bin/python -m pytest`).

## Git Conventions

- **Branch naming**: `openspec/<change-id>` for OpenSpec-driven features
- **Commit format**: Reference the OpenSpec change-id in commit messages
- **Commit quality**: Agent-authored PRs use rebase-merge (commits appear individually on main). Write logical, conventional commits — one per task, no WIP fragments. Use `feat(scope):`, `fix(scope):`, `test(scope):`, `docs(scope):` prefixes.
- **Merge strategy (hybrid)**: Strategy varies by PR origin. Agent PRs (`openspec`, `codex`) default to **rebase-merge** to preserve granular history. Dependency updates (`dependabot`, `renovate`) and automation PRs (`sentinel`, `bolt`, `palette`) default to **squash-merge**. Manual PRs default to squash. Operator can override per-PR via `--strategy` flag.
- **PR template**: Include link to `openspec/changes/<change-id>/proposal.md`
- **Push plan refinement commits promptly**: `/iterate-on-plan` commits to local main. Push these to remote before other PRs merge, or they cause divergence during `/cleanup-feature`. Alternatively, make plan refinements on the feature branch.
- **Rebase ours/theirs inversion**: During `git rebase`, `--ours` = the branch being rebased ONTO (upstream), `--theirs` = the commit being replayed. This is the opposite of `git merge`. When resolving rebase conflicts to keep upstream, use `git checkout --ours`.

## Skills

- **Canonical source**: `skills/` at repo root. ALWAYS edit skills here.
- **Runtime copies**: `.claude/skills/` and `.agents/skills/` are generated by `skills/install.sh` and will be **overwritten** on next sync. Current Codex repo-scoped skill discovery uses `.agents/skills/`. NEVER edit these directly — changes will be lost.
- **Sync command**: `bash skills/install.sh --mode rsync --deps none --python-tools none` (add `--force` only if destinations have conflicting types, e.g. symlinks from old installs)
- **Tests**: Place at `skills/tests/<skill-name>/` (not inside skill directories). This keeps shipped skill dirs clean — `install.sh` excludes `tests/` and `__pycache__/` during rsync. Run all skill tests: `skills/.venv/bin/python -m pytest skills/tests/`

## Worktree Management

- **Launcher invariant**: The shared checkout is **read-only** in local multi-agent execution. Every skill that modifies git state (plan, implement, cleanup) MUST work in a worktree, never the shared checkout. This prevents conflicts when multiple agents run from the same directory. In cloud-harness environments (each agent gets its own ephemeral container), this invariant is provided by the container itself — see **Execution-environment detection** below; worktree write ops become no-ops and skills operate directly on the harness-provided checkout.
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
- **Execution-environment detection**: `skills/shared/environment_profile.py` exposes `detect() -> EnvironmentProfile` with `isolation_provided: bool`. When true (cloud harness, Codespaces, K8s pod), every `worktree.py` write command (`setup|teardown|pin|unpin|heartbeat|gc`) and `merge_worktrees.py` short-circuit to a silent success. Read-only commands (`list|status|resolve-branch`) are unchanged. Detection precedence: `AGENT_EXECUTION_ENV` (cloud|local) → coordinator `GET /agents/<id>` → `/.dockerenv`/`KUBERNETES_SERVICE_HOST`/`CODESPACES` heuristic → default false. Set `WORKTREE_DEBUG=1` to see the decision layer. Full operator guide: [docs/cloud-vs-local-execution.md](docs/cloud-vs-local-execution.md). `OPENSPEC_BRANCH_OVERRIDE` remains orthogonal — it controls branch naming, not whether worktrees are created.

### Sync-Point Skills

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

## Documentation

- [Lessons Learned](docs/lessons-learned.md) — Skill design patterns, parallelization, OpenSpec integration, validation, cross-skill Python patterns
- [Architecture Artifacts](docs/architecture-artifacts.md) — Auto-generated codebase analysis, key files, refresh commands
- [Skills Workflow](docs/skills-workflow.md) — Workflow guide, stage-by-stage explanation, design principles
- [Agent Coordinator](docs/agent-coordinator.md) — Architecture overview, capabilities, design pointers
- [OpenBao Secret Management](docs/openbao-secret-management.md) — Setup options, seeding, API key resolution for SDK dispatch
- [Cross-Repo Setup](docs/cross-repo-setup.md) — Using skills, scripts, and MCP servers in other repositories

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
