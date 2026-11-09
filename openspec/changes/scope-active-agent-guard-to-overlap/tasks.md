# Tasks: Scope the active-agent guard to overlapping work

> Change ID: `scope-active-agent-guard-to-overlap`

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Tasks

### 1. Shared predicate and posture key

- [ ] 1.1 Add `OverlapScope` and the `scope` keyword to `check_no_active_agents`; add `--branch` and `--change-id` (repeatable) to the CLI; include the scope in `--json` output. Repo-wide behaviour when `scope is None` or both flags are absent.
  - Files: `skills/shared/active_agents.py`, `skills/shared/tests/test_active_agents.py`
  - Traces: skill-workflow "Sync-point skill touches main" (overlap scenarios)
- [ ] 1.2 Add `GuardMode` (`repo-wide | overlap | off`), the optional `sync_point.active_agent_guard` front-matter key, `active_agent_guard_mode(posture)`, validation of unknown values, and the `overlap` default for absent key or absent file. Include the key in `posture_digest`.
  - Files: `skills/shared/trust_posture.py`, `openspec/schemas/trust-posture.schema.json`, `skills/shared/tests/test_trust_posture_sync_point.py` (new)
  - Traces: trust-posture "Sync-Point Guard Scope Declaration"
  - Dependencies: none
- [ ] 1.3 Add `resolve_guard(repo_root, scope, *, scheduled: bool) -> GuardDecision` to `active_agents.py` that reads the posture mode, applies `repo-wide` / `overlap` / `off`, forces `overlap` when `scheduled=True`, and returns the mode and scope it applied. This is the one function every call site below calls.
  - Files: `skills/shared/active_agents.py`, `skills/shared/tests/test_active_agents.py`
  - Dependencies: 1.1, 1.2

### 2. Call sites

- [ ] 2.1 `default_sync_point_guard(repo_root, *, scope=None, scheduled=False)` calls `resolve_guard`; the returned dict carries `scope` and `mode`. Fail-closed on import error is unchanged.
  - Files: `skills/merge-pull-requests/scripts/execution_safety.py`, `skills/tests/merge-pull-requests/test_execution_safety.py` (new)
  - Dependencies: 1.3
- [ ] 2.2 `execute_plan.py` passes `scope=OverlapScope(branches={live head branch})` and the run's scheduled flag; `sync_point_blocked` output includes the scope.
  - Files: `skills/merge-pull-requests/scripts/execute_plan.py`, `skills/tests/merge-pull-requests/test_execute_plan_guard.py` (new)
  - Dependencies: 2.1
- [ ] 2.3 `main_convergence.check_active_agents` accepts `scope` and `scheduled`; `converge` builds the scope from the branches merged in this run and the change ids handed to cleanup. Layer 2 (coordinator lock) unchanged.
  - Files: `skills/merge-pull-requests/scripts/main_convergence.py`, `skills/tests/merge-pull-requests/test_convergence_outcomes.py`, `skills/tests/merge-pull-requests/test_convergence_locking.py`
  - Dependencies: 1.3
- [ ] 2.4 `expedite.check_active_agents(repo_root, change_id)` builds the scope from the change id and that change's registry branches; the `--force` hint stays.
  - Files: `skills/expedite/scripts/expedite.py`, `skills/tests/expedite/test_expedite_guard.py` (new)
  - Dependencies: 1.3
- [ ] 2.5 Move the predicate into a dependency-free `active_agents_core.py`, vendor it into `agent-coordinator/src/`, make `sync_points.py` use it with optional `branches` and `change_ids` parameters, and add a byte-parity test between the two copies.
  - Files: `skills/shared/active_agents_core.py`, `skills/shared/active_agents.py`, `agent-coordinator/src/active_agents_core.py`, `agent-coordinator/src/sync_points.py`, `agent-coordinator/tests/test_sync_points.py` (new), `skills/tests/_shared/test_active_agents_parity.py`, `agent-coordinator/Dockerfile` (COPY coverage check)
  - Dependencies: 1.1

### 3. Prototype worktrees

- [ ] 3.1 `/prototype-feature` unpins every variant worktree when it records the human pick; `cleanup-feature` keeps its existing teardown. Document in both SKILL.md files.
  - Files: `skills/prototype-feature/SKILL.md`, `skills/prototype-feature/scripts/collect_outcomes.py` (call `worktree.py unpin` per variant once the pick is recorded), `skills/cleanup-feature/SKILL.md`, `skills/tests/prototype-feature/`
  - Dependencies: none

### 4. Contract and docs

- [ ] 4.1 Add the `sync_point` block, commented, to `TRUST_POSTURE.template.md`; set `sync_point.active_agent_guard: overlap` explicitly in `TRUST_POSTURE.md` with a one-line "why" row in its table.
  - Files: `TRUST_POSTURE.md`, `TRUST_POSTURE.template.md`
  - Dependencies: 1.2
- [ ] 4.2 Rewrite the preflight guard sections of the three sync-point SKILL.md files to the overlap condition, show the `--branch` / `--change-id` invocation, and state the posture key and its default. Update `skills/tests/merge-pull-requests/test_skill_md.py` expectations.
  - Files: `skills/merge-pull-requests/SKILL.md`, `skills/update-specs/SKILL.md`, `skills/cleanup-feature/SKILL.md`, `skills/tests/merge-pull-requests/test_skill_md.py`
  - Dependencies: 1.1
- [ ] 4.3 Add decision entries to the capability timelines.
  - Files: `docs/decisions/skill-workflow.md`, `docs/decisions/trust-posture.md`
  - Dependencies: none
- [ ] 4.4 Run `install.sh` sync so `.claude/skills/` and `.agents/skills/` carry the updated shared helpers.
  - Files: `.claude/skills/shared/*`, `.agents/skills/shared/*`
  - Dependencies: 1.1, 1.2, 1.3, 2.5

### 5. Verification

- [ ] 5.1 End-to-end fixture: registry with an active worktree on `openspec/A`; `execute_plan.py --execute` (dry) for a PR on `openspec/B` proceeds; for a PR on `openspec/A` returns `sync_point_blocked` naming the worktree; same fixture under `repo-wide` blocks both; under `off` with `scheduled=True` blocks `openspec/A`.
  - Files: `skills/tests/merge-pull-requests/test_guard_overlap_e2e.py` (new)
  - Dependencies: 2.1, 2.2, 1.2
- [ ] 5.2 Run `openspec validate scope-active-agent-guard-to-overlap`, the skills and coordinator test suites, `ruff`, and `mypy --strict` on the coordinator.
  - Dependencies: all above
