# Wire Autopilot Per-Phase Sub-Agent Dispatch into Production

## Why

Per-phase archetype resolution shipped under
`2026-05-03-add-per-phase-archetype-resolution`, but the wiring is incomplete:

- `skills/autopilot/scripts/phase_agent.py::make_phase_callback` is built and
  unit-tested, yet **no production code path imports it**. The only callers
  are tests under `skills/tests/phase-record-compaction/`.
- `skills/autopilot/scripts/autopilot.py::run_loop` accepts callbacks
  (`implement_fn`, `iterate_impl_fn`, `validate_fn`, …) but is never invoked
  from production code — there is no CLI entry point and no skill imports it.
- `skills/autopilot/SKILL.md` is prose-driven: it tells the orchestrator
  agent to *"invoke `/implement-feature`"*, *"invoke `/iterate-on-implementation`"*
  inline. Those invocations run in the orchestrator's own context, so the
  archetype-mapped `model` (e.g. opus for review phases, sonnet for
  implementation) is never actually applied.
- `LoopState.phase_archetype` exists in the v3 schema but stays `null` in
  every real run because nothing on the production path writes it.
- `agent-coordinator/scripts/report_status.py` does not read
  `state.phase_archetype` from `loop-state.json` and does not include it in
  the POST body (deferred D-2 from the archived change).
- `agent-coordinator/src/discovery.py::AgentInfo` has no `phase_archetype`
  field, so `GET /discovery/agents` cannot expose what archetype each agent
  is currently running under (deferred D-1).

The net effect: every claim in `archetypes.yaml::phase_mapping` (architect
on PLAN, reviewer on REVIEW, implementer on IMPLEMENT, …) is currently a
**design intent that never executes**. Autopilot runs use a single model for
the entire pipeline — whatever the operator started the session with.

This proposal closes the wiring gap end-to-end so per-phase archetypes
become real on every autopilot run.

## What Changes

1. **SKILL.md dispatch contract** — Replace the prose
   "invoke `/implement-feature`" instructions in `skills/autopilot/SKILL.md`
   with explicit per-phase `Agent(...)` dispatch blocks. Each block:
   - Calls `phase_agent.build_phase_dispatch_kwargs(phase, state)` to obtain
     `{prompt, model, system_prompt, isolation}` from the resolved archetype.
   - Invokes the harness `Agent(prompt=..., model=..., isolation=...)` tool
     directly, with `system_prompt` either pre-pended into `prompt` or passed
     through if the harness exposes it.
   - Captures `(outcome, handoff_id)` and feeds it back through
     `make_phase_callback`'s state-update protocol so
     `LoopState.phase_archetype` and `LoopState.last_handoff_id` are written
     on the production path.

2. **New helper `phase_agent.build_phase_dispatch_kwargs`** — A pure-Python
   helper that returns the dispatch payload as a dict. SKILL.md prose copies
   the values into the actual `Agent(...)` call. Exposed because shelling
   out to Python from SKILL.md prose is the established pattern for
   structured option assembly in this repo.

3. **Inline fallback** — When `try_resolve_archetype_for_phase` returns
   `None` (coordinator unreachable) OR when `AGENT_EXECUTION_ENV` indicates
   the harness `Agent(...)` tool is not available, SKILL.md falls through
   to the existing prose path: invoke `/implement-feature`,
   `/iterate-on-implementation`, etc. inline. `LoopState.phase_archetype`
   is recorded as `null` for those phases (already supported today).

4. **D-2: status reporter wiring** — Extend
   `agent-coordinator/scripts/report_status.py` to read
   `state.phase_archetype` from `loop-state.json` and include it in the
   `POST /status/report` body. Add a parallel INIT-phase archetype
   recorder (`_resolve_phase_archetype_for_state_only`) so even state-only
   phases populate the field.

5. **D-1: AgentInfo persistence** — Add `phase_archetype: str | None` to
   `agent-coordinator/src/discovery.py::AgentInfo`. Add SQL migration
   adding `phase_archetype TEXT` to the agent-status table. Extend
   `DiscoveryService.heartbeat` to accept and persist the value. Surface
   it in the `GET /discovery/agents` response.

6. **Tests** — End-to-end test that runs autopilot through one full
   loop with a mocked `Agent(...)` runner, asserts every non-terminal
   phase's `LoopState.phase_archetype` matches `archetypes.yaml::phase_mapping`,
   and verifies `report_status.py` POSTs the field correctly. Plus a
   manual-run validation script that counts opus vs sonnet calls in the
   audit log to cross-check the model resolution executed.

7. **Specs**
   - MODIFY `specs/skill-workflow/spec.md` — *"Per-Phase Archetype Resolution
     in Autopilot"* requirement: add a scenario asserting that the
     production autopilot path (not just unit-tested helpers) writes
     non-null `phase_archetype` for every non-terminal phase in a real
     run, and that the resolved model is actually invoked by the harness.
   - MODIFY `specs/agent-coordinator/spec.md` — *"Status Report Payload Phase
     Archetype Field"* requirement: add `GET /discovery/agents` round-trip
     scenario (the deferred D-1 scenario from the original archived spec).

## Approaches Considered

### Approach A — All-phase wiring in one change (Recommended)

**Description**: SKILL.md gets a single new "Per-Phase Sub-Agent Dispatch"
section with explicit `Agent(...)` blocks for IMPLEMENT, IMPL_ITERATE,
IMPL_REVIEW, VALIDATE, and PLAN_ITERATE/PLAN_REVIEW. `phase_agent.build_phase_dispatch_kwargs`
returns a dict the orchestrator unpacks into the `Agent(...)` call. D-1 and
D-2 ship in the same change.

- **Pros**:
  - One coordinated change closes the entire deferred-tasks list (D-1, D-2
    plus the missing wiring).
  - Observability lands at the same time as wiring — operators can verify
    the rollout by looking at coordinator logs + `loop-state.json` on the
    very first real run.
  - Minimal new Python infrastructure: just `build_phase_dispatch_kwargs`
    and SKILL.md prose. Matches the repo convention (every other
    parallel-execution skill is SKILL.md-driven).
- **Cons**:
  - Larger blast radius — touches `skills/autopilot/`, `agent-coordinator/`,
    and the SQL migrations directory in one PR.
  - Manual run required for the audit-log cross-check (success criterion
    can't be fully automated until Langfuse/audit integration exists).
- **Effort**: M (estimated 4 work packages, ~600-800 LOC + 1 SQL migration)

### Approach B — Phased rollout: IMPLEMENT first, rest next change

**Description**: This proposal wires only the IMPLEMENT phase through
`Agent(...)` dispatch. Observe in production for a few cycles, then ship
a follow-up that extends to IMPL_ITERATE, IMPL_REVIEW, VALIDATE,
PLAN_ITERATE, PLAN_REVIEW. D-1 and D-2 stay in this change so observability
lands once (not twice).

- **Pros**:
  - Smallest blast radius — only the implementation phase changes how it
    dispatches. Easy to measure latency/quality impact.
  - Lower risk if `system_prompt` injection has unexpected interactions
    with downstream skills like `/implement-feature`.
- **Cons**:
  - Two PRs instead of one for a feature that's already conceptually
    complete in design.
  - Half-finished state during the gap: real runs show non-null
    `phase_archetype` only for IMPLEMENT and `null` for review/validate
    phases — confusing for operators reading `loop-state.json`.
  - The `/iterate-on-implementation` skill internally dispatches its own
    sub-agents, so wiring IMPLEMENT first doesn't actually buy much
    isolation testing (the sub-agent it dispatches is the implementer
    archetype either way).
- **Effort**: S for this proposal (~250 LOC) + M for the follow-up

### Approach C — Python-driven `run_loop` orchestration

**Description**: Build a new `skills/autopilot/scripts/runner.py` that
constructs the `subagent_runner` callable from a CLI-flavored adapter
(`claude --print --model=...`, `codex run --system-prompt=...`), then calls
`autopilot.run_loop(implement_fn=make_phase_callback("IMPLEMENT", runner=...), ...)`.
SKILL.md becomes thin: it just executes `python3 runner.py <change-id>`.

- **Pros**:
  - Fully deterministic — no orchestrator-prose interpretation step.
  - The `run_loop()` state machine becomes the actual driver, matching the
    original design D6.
- **Cons**:
  - Breaks repo convention — every other parallel skill in this codebase is
    SKILL.md-prose-driven, not subprocess-driven. We'd be introducing a
    second pattern.
  - Adds vendor-CLI dependency for autopilot itself (today autopilot only
    needs them transitively via `convergence_loop.py`).
  - Doesn't compose with the harness `Agent(...)` tool's worktree isolation
    primitives — we'd need to re-implement worktree management around
    subprocess calls.
  - User explicitly chose the SKILL.md prompt-layer approach in discovery.
- **Effort**: L (~1200 LOC + new infra)

## Selected Approach

**Approach A — All-phase wiring in one change.**

Approved at Gate 1. Rationale:

- Closes the entire deferred-tasks list (D-1 and D-2) at the same time as
  the core wiring, so observability lands together with capability — operators
  can verify the rollout from the very first real run by reading
  `loop-state.json` and the coordinator audit log together.
- Matches repo convention (every other parallel-execution skill is
  SKILL.md-driven) and the runner-mode answer from discovery.
- Smallest new Python surface (just `build_phase_dispatch_kwargs`); the
  rest is SKILL.md prose plus existing helpers.

Approaches B and C are demoted to historical alternatives in this
proposal's history. B was rejected because the half-finished state
(non-null `phase_archetype` only for IMPLEMENT) actively hurts operator
debugging during the gap. C was rejected because it contradicts the
SKILL.md-prompt-layer answer at discovery and would introduce a second
parallel-execution pattern the repo doesn't currently use.

## Rollout

1. Land all 4 work packages in one PR (rebase-merge to preserve granular
   commit history).
2. Run the OpenSpec-driven mock-Agent end-to-end test in CI.
3. Manual validation run: kick off `/autopilot` against a small change,
   inspect `loop-state.json` for non-null `phase_archetype` per phase,
   inspect coordinator audit log for opus-vs-sonnet call distribution.
4. Once a real run validates the wiring, archive this change and close
   the deferred-tasks D-1 and D-2 tickets.

## Risks

- **Prompt-size pressure**: Pre-pending `system_prompt` to the per-phase
  task instruction may push individual `Agent()` calls toward token
  limits, especially for IMPL_REVIEW which carries large change context.
  Mitigation: phase_token_meter already tracks per-phase prompt tokens;
  add a CI check that flags phases trending toward 80% of budget.
- **Harness `system_prompt` semantics**: The harness `Agent(...)` tool
  may not honor `system_prompt` as an option. If so, we fold `system_prompt`
  into the `prompt` text. Mitigation: confirm during work-package
  wp-skills-autopilot-runner.
- **Discovery migration backfill**: Existing rows in the agent-status
  table will have `NULL` for the new `phase_archetype` column. That's
  semantically correct (we don't know historical archetypes) and
  forward-compatible. No backfill required.
