# Cloud vs Local Execution

OpenSpec skills use git worktrees (`.git-worktrees/<change-id>/`) to isolate concurrent agent work on a single filesystem. Cloud execution environments (Claude Code on the web, Codespaces, ephemeral Kubernetes pods) already provide that isolation at the container level — running `git worktree add` there either fails outright (when the harness has already checked out a branch) or creates redundant state that the container will destroy anyway.

The `skills/worktree/scripts/worktree.py` helper detects this at runtime and turns every mutating subcommand into a silent no-op when the caller already has isolation. Nothing in the SKILL.md files changes.

## The signal: `EnvironmentProfile.detect()`

Defined in `skills/shared/environment_profile.py`. Returns a dataclass:

```python
EnvironmentProfile(
    isolation_provided: bool,
    source: Literal["env_var", "coordinator", "heuristic", "default"],
    details: dict[str, Any],
)
```

`isolation_provided=True` means "this environment already isolates agents, skip worktree creation." It is consumed by `worktree.py` (setup/teardown/pin/unpin/heartbeat/gc) and `merge_worktrees.py` (full short-circuit with PR-guidance).

## Detection precedence

Evaluated top-down; the first definitive answer wins.

| Priority | Layer | Signal |
|---|---|---|
| 1 | **Env var** | `AGENT_EXECUTION_ENV=cloud` (force cloud) or `AGENT_EXECUTION_ENV=local` (force local). Legacy `CLAUDE_CODE_CLOUD=1` accepted as cloud. |
| 2 | **Coordinator** | When `agent_id` is known AND `COORDINATOR_URL` is set, `GET /agents/<agent-id>` returns `isolation_provided`. 500ms timeout; errors fall through. |
| 3 | **Heuristic** | Any of: `/.dockerenv` exists, `KUBERNETES_SERVICE_HOST` set, `CODESPACES=true`. |
| 4 | **Default** | `isolation_provided=false` — the legacy behavior. |

Unrecognized values of `AGENT_EXECUTION_ENV` (e.g. typos) emit a stderr warning and fall through to the next layer rather than defaulting to no-isolation. This keeps detection useful when operators fat-finger the env var.

## What changes when `isolation_provided=true`

| Subcommand | Behavior under cloud mode |
|---|---|
| `worktree.py setup` | Emits `WORKTREE_PATH=$(git rev-parse --show-toplevel)` + `WORKTREE_BRANCH=$(git branch --show-current)`. Does NOT create `.git-worktrees/`. |
| `worktree.py teardown` | Prints `REMOVED=skipped`; exits 0. |
| `worktree.py pin` | Exits 0 with `skipped pin` stderr line. |
| `worktree.py unpin` | Exits 0 with `skipped unpin` stderr line. |
| `worktree.py heartbeat` | Exits 0 silently (apart from the standard `skipped` log line). |
| `worktree.py gc` | Exits 0; container lifecycle is the harness's concern. |
| `worktree.py list` / `status` / `resolve-branch` | **Unchanged** — these are read-only introspection. `status` reports the in-place checkout as the current worktree. |
| `merge_worktrees.py` | Exits 0 with a guidance line directing callers to PR-based integration. JSON output reports `{"skipped": true, "reason": "isolation_provided"}`. |

## OPENSPEC_BRANCH_OVERRIDE stays orthogonal

The new signal does NOT read `OPENSPEC_BRANCH_OVERRIDE` and the branch-override path does NOT imply cloud mode. Operators can set the override locally (e.g. to work on a review branch) without disabling worktree isolation. The two signals compose:

| `AGENT_EXECUTION_ENV` | `OPENSPEC_BRANCH_OVERRIDE` | Behavior |
|---|---|---|
| unset | unset | Create `.git-worktrees/<change-id>/` on `openspec/<change-id>` |
| unset | `claude/x` | Create `.git-worktrees/<change-id>/` on `claude/x` |
| `cloud` | unset | No worktree; emit the currently checked-out branch |
| `cloud` | `claude/x` | No worktree; the harness must have already checked out `claude/x` |

## Troubleshooting

**Q: I'm in a local Docker Compose dev loop and setup is skipping my worktree.**
The heuristic sees `/.dockerenv` and assumes cloud. Export `AGENT_EXECUTION_ENV=local` in your shell to force worktree isolation.

**Q: I want to see which layer made the decision.**
Export `WORKTREE_DEBUG=1`. Every call to `detect()` dumps the full profile (layer source, details) to stderr.

**Q: The coordinator is misreporting `isolation_provided`.**
Set `AGENT_EXECUTION_ENV` explicitly — env var beats coordinator. Then fix the coordinator registration separately.

**Q: Setup succeeded and created a worktree on the wrong branch.**
Set `OPENSPEC_BRANCH_OVERRIDE=<your-branch>` at plan time AND implement time. The override must be set for the entire session or plan/implement will diverge onto different branches.

**Q: Why doesn't `list` / `status` short-circuit?**
They're read-only. They continue to function normally and report the in-place checkout as the current worktree — this keeps introspection working in cloud sessions.

## For harness authors

If you're building a cloud harness that provides its own isolation, the recommended integration is:

1. Set `AGENT_EXECUTION_ENV=cloud` in the container's environment (fastest, zero coordinator coupling).
2. Optionally register each agent with the coordinator and set `isolation_provided=true` on the agent record (falls-through cleanly if the coordinator is unreachable).

The `/.dockerenv` heuristic means the fix works for vanilla Docker containers even without a harness-side change — but explicit signaling is more reliable and documents your intent.

## See also

- `skills/shared/environment_profile.py` — the detector
- `skills/worktree/scripts/worktree.py` — the write-op short-circuits
- `skills/worktree/scripts/merge_worktrees.py` — the merge short-circuit
- `openspec/changes/conditional-worktree-generation/` — the full design and task history
