# Deferred Tasks — add-per-phase-archetype-resolution

Tasks moved out of the implementation scope and deferred to a follow-up
proposal. Each entry records *why* the deferral was made so a future
proposal can pick it up.

## D-1: Expose `phase_archetype` in `GET /discovery/agents` listing

**Origin**: tasks.md 4.3, 4.4 (the `GET /status/agents` listing portion).
**Spec**: `specs/agent-coordinator/spec.md` — Status Report Payload Phase
Archetype Field, scenario "subsequent calls to GET /status/agents SHALL return
phase_archetype: 'architect' for that agent".

**What this implementation does**: `POST /status/report` accepts and forwards
the optional `phase_archetype` field through the coordinator event bus
(`coordinator_status` channel, in the event `context` dict). Subscribers
that consume the event stream (notification daemons, observability dashboards
listening on the channel) see the `phase_archetype` value alongside `phase`.

**What this implementation does NOT do**: Persist `phase_archetype` on the
`AgentInfo` discovery record so that `GET /discovery/agents` returns it as
part of each agent's current-phase summary.

**Why deferred**:
1. The persistence path requires extending the `discovery` service
   (`agent-coordinator/src/discovery.py`) and likely the
   `database/migrations/*.sql` files to add a `phase_archetype` column on
   the agent-status table. Both are **outside the wp-coordinator scope**
   declared in `work-packages.yaml` (`write_allow` covers `agents_config.py`,
   `coordination_api.py`, `archetypes.yaml`, and `tests/`).
2. Forcing the discovery extension into wp-coordinator would require also
   amending the work-package's `write_allow` and re-running plan validation,
   and would add migration coordination concerns to a change that was
   designed to be additive.
3. Operationally, autopilot's primary consumers of the value (the runner
   that emits status reports, downstream notification subscribers) get
   the value via the event bus today. The dashboard/listing exposure is a
   nice-to-have for retrospective queries.

**Pickup criteria** (for the follow-up):
- Extend `AgentInfo` dataclass with `phase_archetype: str \| None = None`.
- Add a database migration adding `phase_archetype TEXT` to the agent-status
  table.
- Extend `DiscoveryService.heartbeat` (or add a new `update_phase_archetype`
  method) so `POST /status/report` can persist the value.
- Extend `GET /discovery/agents` to surface `phase_archetype` in the response
  dict.
- Update the corresponding test in
  `agent-coordinator/tests/test_phase_archetype_resolution.py` to assert
  `GET /discovery/agents` round-trips the value.

---

## D-2: Wire INIT phase archetype recording + status reporter emission

**Origin**: tasks.md 7.3 (INIT none-sentinel handling) and 7.4 (status report
emission of `phase_archetype`).
**Spec**: `specs/skill-workflow/spec.md` — Per-Phase Archetype Resolution in
Autopilot, scenario "All 13 non-terminal phases dispatch with resolved
archetype".

**What this implementation does**:

1. `LoopState.phase_archetype` is set on every phase that flows through
   `make_phase_callback` (PLAN/PLAN_ITERATE/PLAN_REVIEW/PLAN_FIX/IMPLEMENT/
   IMPL_ITERATE/IMPL_REVIEW/IMPL_FIX/VALIDATE/VAL_REVIEW/VAL_FIX/SUBMIT_PR
   when each is bound to a callback by the SKILL.md prompt layer).
2. The `phase_agent._PHASE_TASKS` registry has entries for all 13
   non-terminal phases, with `None` sentinels for INIT and SUBMIT_PR per
   design D13. `_phase_task_instructions` correctly handles the None
   sentinel.
3. `coordination_api.report_status` accepts `phase_archetype` in the
   `StatusReportRequest` body and forwards it through the
   `coordinator_status` event bus context dict.

**What this implementation does NOT do**:

1. **INIT phase archetype recording**: INIT is currently a pure state
   transition in `autopilot.run_loop` (no callback dispatch). To record
   `phase_archetype` for INIT, a small `_resolve_state_only_archetype`
   helper would need to run at INIT phase entry inside `run_loop`. The
   spec scenario "every non-terminal phase has non-null phase_archetype"
   is therefore not strictly satisfied for INIT.
2. **Status reporter emission**: The autopilot's status reporter at
   `agent-coordinator/scripts/report_status.py` (the Stop-hook script
   that calls `POST /status/report`) does not yet read
   `state.phase_archetype` from `loop-state.json` and include it in the
   POST body. Its modification is **outside the wp-skills-autopilot scope**
   declared in `work-packages.yaml` (`write_allow` covers `phase_agent.py`,
   `autopilot.py`, `skills/tests/autopilot/**`).

**Why deferred**:
1. Wiring INIT through `run_phase_subagent` requires restructuring the
   state-machine dispatch table in `autopilot.run_loop`, which touches
   broader autopilot mechanics than this proposal scoped to.
2. The status reporter modification belongs to a hook-script package
   that wasn't decomposed into this proposal's work-packages.
3. Operationally, the primary in-flight value of `phase_archetype` is
   already realized: `LoopState.phase_archetype` is set on disk for all
   active phases, and the coordinator endpoint accepts the field today —
   so a future follow-up that wires the reporter is a one-line addition.

**Pickup criteria** (for the follow-up):
- Add `_resolve_phase_archetype_for_state_only(state, phase)` helper in
  `autopilot.run_loop` that calls
  `coordination_bridge.try_resolve_archetype_for_phase` and sets
  `state.phase_archetype` for INIT (and any other state-only phases
  added later).
- Extend `agent-coordinator/scripts/report_status.py` to read
  `state.phase_archetype` from the loaded `LoopState` and include it
  in the POST body (alongside `phase`).
- Update `skills/tests/autopilot/test_phase_archetype_e2e.py` (added
  by wp-integration) to assert the round-trip end-to-end.
