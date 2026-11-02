# Scope the active-agent guard to overlapping work

> Parent roadmap: none (workstream 1a of `docs/proposals/continuous-integration-for-agentic-teams.md`)
> Change ID: `scope-active-agent-guard-to-overlap`
> Effort: M
> Priority: 1

## Summary

Replace the repo-wide active-agent guard at every sync point with an overlap guard. Today `check_no_active_agents` in `skills/shared/active_agents.py` blocks `/merge-pull-requests`, `/update-specs`, `/cleanup-feature`, `/expedite`, and the main-convergence kernel whenever any worktree in `.git-worktrees/.registry.json` is pinned or has a heartbeat under one hour old, regardless of what that worktree is working on. With ten changes in flight the guard is effectively always on, and the only way through is `--force`, which the operator has to type by hand and which the kernel does not accept at all. After this change a sync point blocks only when an active worktree sits on a branch it is about to merge, when an active worktree belongs to a change it is about to archive or clean up, or when another sync-point writer holds the `sync-point:main-convergence` coordinator lock. Worktrees for unrelated changes no longer block. The scope is declared in the trust posture contract as `sync_point.active_agent_guard: repo-wide | overlap | off`, defaulting to `overlap` when the key is absent, so an operator can restore the old behaviour by editing one line.

## Dependencies

- None. `openrouter-review-lane` and the merge-queue change in the same plan are independent of this one.

## Acceptance Outcomes

- With an active (fresh heartbeat) worktree registered for change A on branch `openspec/A`, `execute_plan.py --execute` merges a PR whose head is `openspec/B` without `--force`, and the guard result names the scope it checked.
- With an active worktree registered on branch `openspec/B`, the same execution stops with `sync_point_blocked`, and the reason names that worktree's change id, agent id, and branch.
- With an active worktree registered for change C, the main-touching portion of `/cleanup-feature` for change C blocks, while cleanup of change D proceeds.
- `active_agents.py --branch openspec/B` exits `1` when an active worktree is on `openspec/B` and `0` when the only active worktree is on another branch; with no `--branch` or `--change-id` the CLI keeps its current repo-wide behaviour.
- `TRUST_POSTURE.md` with `sync_point: {active_agent_guard: repo-wide}` restores today's behaviour at every call site; `off` skips the worktree check for user-invoked runs only, and a scheduled invocation under `off` runs the overlap check.
- A prototype worktree is unpinned when `/prototype-feature` records the human pick, not when `/cleanup-feature` tears it down, so a finished prototype stops blocking its own merge.
- `agent-coordinator/src/sync_points.py` reports blockers using the same overlap semantics as the skills, given the same scope, so the observability frontends and the skills never disagree about whether a sync point is blocked.
- The requirement "Main Receives Work Through PR Sync Points" in `openspec/specs/skill-workflow/spec.md` and the three SKILL.md files that quote it describe the overlap condition, and the `trust-posture` spec describes the posture key.

## Rationale

The guard exists so that a sync point does not rewrite the shared checkout under an agent that is still working. That risk is real only when the two touch the same branch or the same change directory. A worktree on an unrelated branch is not endangered by a merge of someone else's PR, and blocking on it converts a safety check into a throughput ceiling that scales with the number of concurrent agents. The plan in `docs/proposals/continuous-integration-for-agentic-teams.md` identifies this guard as the first of three blockers to continuous landing and this change is its first workstream.

## Impact

- `skill-workflow`: MODIFIED requirement "Main Receives Work Through PR Sync Points" (`specs/skill-workflow/spec.md`).
- `trust-posture`: ADDED requirement "Sync-Point Guard Scope Declaration" (`specs/trust-posture/spec.md`).
- Code: `skills/shared/active_agents.py`, `skills/shared/trust_posture.py`, `openspec/schemas/trust-posture.schema.json`, `skills/merge-pull-requests/scripts/execution_safety.py`, `skills/merge-pull-requests/scripts/execute_plan.py`, `skills/merge-pull-requests/scripts/main_convergence.py`, `skills/expedite/scripts/expedite.py`, `skills/worktree/scripts/worktree.py`, `agent-coordinator/src/sync_points.py`.
- Docs: `TRUST_POSTURE.md`, `TRUST_POSTURE.template.md`, `skills/merge-pull-requests/SKILL.md`, `skills/update-specs/SKILL.md`, `skills/cleanup-feature/SKILL.md`, `skills/prototype-feature/SKILL.md`, `docs/decisions/skill-workflow.md`, `docs/decisions/trust-posture.md`.
