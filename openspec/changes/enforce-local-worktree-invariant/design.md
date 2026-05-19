# Design: Local Worktree Mutation Boundary

## Context

The repo already has the major primitives:

- `skills/shared/environment_profile.py` distinguishes local CLI execution from
  isolated harnesses.
- `skills/worktree/scripts/worktree.py setup` creates or adopts managed
  `.git-worktrees/<change-id>/` worktrees.
- `skills/shared/active_agents.py` guards sync-point skills against concurrent
  active worktrees.

The missing piece is a shared policy that every mutating skill can call or cite
before it writes. Today, each skill carries its own prose and some still encode
older exceptions.

## Decisions

### D1: Add `skills/shared/checkout_policy.py`

Create a small Python helper with two layers:

- `classify_checkout(cwd: Path, repo_root: Path | None = None, sync_point: bool = False, agent_id: str | None = None) -> CheckoutPolicy`
- `require_mutation_allowed(...) -> CheckoutPolicy`

The returned policy records:

- `allowed: bool`
- `reason: isolated_harness | managed_worktree | approved_sync_point | shared_checkout_blocked`
- `isolation_provided: bool`
- `cwd`
- `repo_root`
- `worktree_root`
- `message`

The helper MUST call `EnvironmentProfile.detect(agent_id)` and use the existing
cloud/local result. When `isolation_provided=true`, mutation is allowed in the
current checkout because the harness supplies isolation. In local mode, mutation
is allowed only when `cwd` is inside a managed `.git-worktrees/` checkout or the
caller declares `sync_point=true`.

### D2: Provide a CLI for SKILL.md and shell callers

Expose:

```bash
skills/.venv/bin/python skills/shared/checkout_policy.py require-mutation \
  [--sync-point] [--agent-id <id>] [--json]
```

The command exits 0 when mutation is allowed and exits 1 with a clear message
when a local CLI caller is in the shared checkout. This lets SKILL.md files use
one guard without reimplementing path logic.

### D3: Keep sync-point exceptions narrow

The helper's `--sync-point` flag only says the checkout policy permits shared
checkout mutation. The skill still must run its existing clean-tree and
active-agent checks before touching main. This preserves `/merge-pull-requests`,
`/update-specs`, and the main-touching portion of `/cleanup-feature` as explicit
sync-points.

### D4: Skill instructions remain the orchestration layer

The helper does not create worktrees by itself. Mutating skills continue to call
`worktree.py setup` first. The guard verifies that the resulting execution
context is acceptable before writes begin. This avoids duplicating branch
resolution and `OPENSPEC_BRANCH_OVERRIDE` behavior outside `worktree.py`.

### D5: Autopilot isolates every write-capable phase

Autopilot phase dispatch should treat these phases as write-capable:

- `PLAN`
- `PLAN_ITERATE`
- `PLAN_REVIEW` when it writes review checkpoints
- `PLAN_FIX`
- `IMPLEMENT`
- `IMPL_ITERATE`
- `IMPL_REVIEW` when it writes review checkpoints
- `IMPL_FIX`
- `VALIDATE`
- `VAL_REVIEW` when it writes review artifacts
- `VAL_FIX`

`INIT` and `SUBMIT_PR` remain state-only. If a phase is truly read-only in a
specific execution path, that path can still run inline, but the default dispatch
metadata must not advertise shared-checkout mutation.

### D6: Explore mode splits read-only from artifact-producing operation

`explore-feature` may run in the shared checkout only when it returns analysis in
chat and performs no writes. If it refreshes architecture, persists
`docs/feature-discovery/opportunities.json`, creates proposals, updates issues,
or writes any artifact, it must set up a worktree first.

## Implementation Notes

- Use Git introspection rather than string-only path guesses where practical:
  `git rev-parse --show-toplevel` gives the current checkout root.
- A managed local worktree is any checkout whose root is under
  `<shared-root>/.git-worktrees/`. The helper should also tolerate being called
  from a nested path inside that worktree.
- Tests should cover:
  - local shared checkout blocks mutation
  - local managed worktree allows mutation
  - cloud/harness mode allows mutation
  - sync-point flag allows mutation but reports `approved_sync_point`
  - CLI exit codes match the policy result
- Skill invariant tests should be text-level and focused. They should not assert
  exact prose, only the presence of worktree setup or checkout policy guard in
  mutating skills.

## Risks

- Some existing skills may be both diagnostic and mutating depending on flags.
  The plan should classify those modes explicitly rather than forcing all usage
  into a worktree.
- Over-broad text tests can make normal skill documentation edits noisy. Keep
  them targeted to known high-risk phrases such as "no worktree" plus
  "read-write".
- Cloud detection false positives already exist for local containers. This
  change should preserve `AGENT_EXECUTION_ENV=local` as the operator override.
