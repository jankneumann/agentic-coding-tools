# Tasks: Conditional Worktree Generation

All task groups are TDD-ordered: tests before the implementation they verify. Every test task references the spec scenarios, contracts (none for this skill-only change), and design decisions it validates.

## Phase 1 — EnvironmentProfile helper

- [x] **1.1** Write unit tests for `EnvironmentProfile.detect()` env-var layer — asserts `AGENT_EXECUTION_ENV=cloud|local` and legacy `CLAUDE_CODE_CLOUD=1` map to the correct `(isolation_provided, source)` tuple; unrecognized values fall through.
  - **Spec scenarios**: worktree-isolation.2 (env var overrides coordinator and heuristic), worktree-isolation.3 (coordinator overrides heuristic), worktree-isolation.4 (heuristic fires when env var and coordinator silent)
  - **Design decisions**: D2 (precedence), D6 (heuristic markers)
  - **Dependencies**: None

- [x] **1.2** Create `skills/shared/__init__.py` and `skills/shared/environment_profile.py` — implement `EnvironmentProfile` dataclass and `detect()` env-var layer only.
  - **Dependencies**: 1.1

- [x] **1.3** Write unit tests for the coordinator layer — mocked HTTP response (200 with `isolation_provided`, 200 without the field, 404 agent-id not found, 500ms timeout). Assert precedence over heuristic and fall-through on missing data.
  - **Spec scenarios**: worktree-isolation.3 (coordinator overrides heuristic)
  - **Design decisions**: D7 (coordinator integration is optional and non-blocking)
  - **Dependencies**: 1.2

- [x] **1.4** Extend `environment_profile.py` with the coordinator layer — 500ms timeout, silent fall-through on error, one stderr log line on error. Reuse `check_coordinator.py`'s URL/health logic where possible.
  - **Dependencies**: 1.3

- [x] **1.5** Write unit tests for the heuristic layer — tmp-path fake `/.dockerenv`, `KUBERNETES_SERVICE_HOST` env var, `CODESPACES=true`. Assert each independently triggers `isolation_provided=true, source="heuristic"` and that absence of all three falls through to default.
  - **Spec scenarios**: worktree-isolation.4 (heuristic fires when env var and coordinator silent)
  - **Design decisions**: D6 (conservative heuristic markers)
  - **Dependencies**: 1.4

- [x] **1.6** Extend `environment_profile.py` with the heuristic layer and default fall-through; add `WORKTREE_DEBUG=1` opt-in verbose logging.
  - **Dependencies**: 1.5

## Phase 2 — `worktree.py` short-circuits

- [x] **2.1** Write behavior tests for `worktree.py setup` under `AGENT_EXECUTION_ENV=cloud` — subprocess invocation asserts `.git-worktrees/<change-id>/` is NOT created, stdout matches `WORKTREE_PATH=<toplevel>\nWORKTREE_BRANCH=<current>`, exit code 0, one stderr log line. Also assert same-branch cloud harness scenario (branch already checked out at repo root) succeeds where it previously failed with `fatal: already used by worktree`.
  - **Spec scenarios**: worktree-isolation.2 (cloud harness short-circuits setup), worktree-isolation.8 (cloud signal without branch override short-circuits)
  - **Design decisions**: D3 (no-op not error), D5 (emit toplevel/current-branch)
  - **Dependencies**: 1.6

- [x] **2.2** Write regression tests for `worktree.py setup` under `AGENT_EXECUTION_ENV=local` — asserts `.git-worktrees/<change-id>/` IS created, registry entry written, `WORKTREE_PATH` points at the new worktree.
  - **Spec scenarios**: worktree-isolation.1 (local single-agent default), worktree-isolation.9 (existing local single-agent unchanged), worktree-isolation.10 (local-parallel unchanged)
  - **Dependencies**: 1.6

- [x] **2.3** Integrate `EnvironmentProfile.detect()` into `worktree.py cmd_setup` — short-circuit with stdout stub and stderr log line when `isolation_provided=true`; unchanged behavior otherwise.
  - **Dependencies**: 2.1, 2.2

- [x] **2.4** Write behavior tests for `teardown`, `pin`, `unpin`, `heartbeat`, `gc` short-circuits — each invoked under cloud mode asserts no registry writes, no `.git-worktrees/` mutations, exit 0, single stderr log line naming the op.
  - **Spec scenarios**: worktree-isolation.3 (teardown/pin/etc. no-op under cloud mode)
  - **Design decisions**: D3 (no-op not error)
  - **Dependencies**: 2.3

- [x] **2.5** Integrate `EnvironmentProfile.detect()` into `worktree.py cmd_teardown`, `cmd_pin`, `cmd_unpin`, `cmd_heartbeat`, `cmd_gc` — each short-circuits when `isolation_provided=true`.
  - **Dependencies**: 2.4

- [x] **2.6** Write tests for read-only pass-through — `list`, `status`, `resolve-branch` execute normally under cloud mode; `status` reports the in-place checkout as the current worktree.
  - **Spec scenarios**: worktree-isolation.4 (read-only introspection continues to function)
  - **Design decisions**: D4 (read-only ops unchanged)
  - **Dependencies**: 2.5

- [x] **2.7** Verify `list`, `status`, `resolve-branch` need no change beyond documentation — they are inherently read-only and `resolve-branch` already honors `OPENSPEC_BRANCH_OVERRIDE` per existing behavior. Add an assertion comment in each function documenting the invariant.
  - **Dependencies**: 2.6

## Phase 3 — `merge_worktrees.py` short-circuit

- [x] **3.1** Write behavior tests for `merge_worktrees.py` under cloud mode — invoked with a change-id and package-ids, asserts no `git merge` subprocess is spawned, no registry reads, exit 0, guidance message on stderr matching the exact format in the spec.
  - **Spec scenarios**: worktree-isolation.6 (cloud merge short-circuits with guidance)
  - **Design decisions**: D8 (merge exits 0 with guidance, not error)
  - **Dependencies**: 2.7

- [x] **3.2** Integrate `EnvironmentProfile.detect()` into `merge_worktrees.py` `main()` — short-circuit before any branch resolution or `git merge` invocation.
  - **Dependencies**: 3.1

## Phase 4 — Backward compatibility and override orthogonality

- [x] **4.1** Write integration tests asserting `OPENSPEC_BRANCH_OVERRIDE` behavior under both modes — (a) override + local mode creates worktree on override branch; (b) override + cloud mode still short-circuits but preserves whatever branch the harness checked out; (c) neither override nor cloud signal uses default branch.
  - **Spec scenarios**: worktree-isolation.7 (branch override without cloud signal creates worktree), worktree-isolation.8 (cloud signal without override short-circuits)
  - **Dependencies**: 3.2

- [x] **4.2** Validate no SKILL.md changes are needed — audited `plan-feature`, `implement-feature`, `cleanup-feature`, `fix-scrub`, `openspec-beads-worktree`, and `worktree/SKILL.md`. All `setup`/`resolve-branch` call sites use `eval "$(…)"` and expect `WORKTREE_PATH=`/`WORKTREE_BRANCH=` key=value output — compatible with the cloud-mode stub. All `teardown`/`gc`/`pin`/`unpin`/`heartbeat`/`merge_worktrees.py` calls are plain subprocess invocations that only check exit code — compatible with the no-op success return. No SKILL.md edits required.
  - **Dependencies**: 4.1

## Phase 5 — Optional coordinator extension

- [ ] **5.1** **(deferred — follow-up PR)** Write coordinator integration tests — register an agent-id with `isolation_provided=true`; assert `EnvironmentProfile.detect()` returns `source="coordinator"` when queried under that agent-id. The coordinator layer in `environment_profile.py` is implemented and unit-tested with mocks; end-to-end coordinator registration is deferred pending the schema change in 5.2.
  - **Spec scenarios**: worktree-isolation.3 (coordinator overrides heuristic)
  - **Design decisions**: D7 (optional, non-blocking)
  - **Dependencies**: 4.2

- [ ] **5.2** **(deferred — follow-up PR)** Add optional `isolation_provided` field to the coordinator's agent registration schema — non-breaking (default `null`, treated as unknown). Add to the agent-registration API/MCP tool signature behind the existing `CAN_DISCOVER` capability flag. Deferred to a coordinator-side PR since this repo's worktree.py already consumes the field if the coordinator reports it.
  - **Dependencies**: 5.1

## Phase 6 — Documentation and rollout

- [x] **6.1** Write `docs/cloud-vs-local-execution.md` — operator-facing doc covering detection precedence, env var values, troubleshooting, and `WORKTREE_DEBUG=1` usage.
  - **Dependencies**: 5.2

- [x] **6.2** Update `CLAUDE.md` Worktree Management section — document the new detection precedence as a subsection; cross-reference `docs/cloud-vs-local-execution.md`.
  - **Dependencies**: 6.1

- [x] **6.3** Update `openspec/project.md` — expand the "MCP for local, HTTP for cloud" line into a brief reference to the execution-environment signal.
  - **Dependencies**: 6.1

- [x] **6.4** Run full test suite (`skills/.venv/bin/python -m pytest skills/tests/`) and capture output in change's evidence directory.
  - **Dependencies**: 6.1, 6.2, 6.3
