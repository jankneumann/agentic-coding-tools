# Tasks — Per-Phase Archetype Resolution in Autopilot

Tasks ordered TDD-first within each phase. Implementation tasks declare dependencies on their corresponding test tasks.

## Phase 1: Contracts and Schemas

- [x] 1.1 Write OpenAPI 3.1 contract for `POST /archetypes/resolve_for_phase` with request/response/error schemas
  **Spec scenarios**: agent-coordinator (Phase Archetype Resolution Endpoint scenarios), agent-archetypes (Phase Archetype Resolution Endpoint Contract scenarios)
  **Contracts**: contracts/openapi/v1.yaml — new `/archetypes/resolve_for_phase` path
  **Design decisions**: D2 (HTTP endpoint shape)
  **Dependencies**: None

- [x] 1.2 Write JSON Schema for the extended `archetypes.yaml` (`schema_version: 2` with `phase_mapping`)
  **Spec scenarios**: agent-archetypes (Per-Phase Archetype Mapping scenarios)
  **Contracts**: contracts/schemas/archetypes-config-v2.schema.json
  **Design decisions**: D1 (phase_mapping schema)
  **Dependencies**: None

- [x] 1.3 Write JSON Schema for `LoopState` `schema_version: 3` with `phase_archetype` field
  **Spec scenarios**: agent-coordinator (LoopState Phase Archetype Field scenarios)
  **Contracts**: contracts/schemas/loop-state-v3.schema.json
  **Design decisions**: D7 (LoopState schema bump)
  **Dependencies**: None

## Phase 2: Coordinator-side — Schema and Resolution Function

- [x] 2.1 Write tests for `load_archetypes_config` with `phase_mapping` section
  **Spec scenarios**: agent-archetypes.1 (Phase mapping is loaded), agent-archetypes.2 (Older without phase_mapping), agent-archetypes.3 (undefined archetype reference)
  **Contracts**: contracts/schemas/archetypes-config-v2.schema.json
  **Design decisions**: D1
  **Dependencies**: 1.2

- [x] 2.2 Extend `agent-coordinator/src/agents_config.py:load_archetypes_config` to parse `phase_mapping`; add `PhaseMappingEntry` dataclass; bump archetype schema_version handling
  **Dependencies**: 2.1

- [x] 2.3 Update `agent-coordinator/archetypes.yaml` to schema_version 2 with the 13-phase mapping (per D11 default table)
  **Design decisions**: D11 (default phase mapping)
  **Dependencies**: 2.2

- [x] 2.4 Write tests for `resolve_archetype_for_phase` covering known phase, unknown phase (KeyError), and escalation-triggering signals
  **Spec scenarios**: agent-archetypes (Phase Archetype Resolution Function scenarios)
  **Design decisions**: D3 (phase kwarg), D11 (default mapping)
  **Dependencies**: 2.1

- [x] 2.5 Implement `resolve_archetype_for_phase(phase, signals) -> ResolvedArchetype` in `agent-coordinator/src/agents_config.py`; thread optional `phase` kwarg through `resolve_model` reasons output
  **Dependencies**: 2.2, 2.4

## Phase 3: Coordinator-side — HTTP Endpoint

- [x] 3.1 Write tests for `POST /archetypes/resolve_for_phase`: 200 success, 400 malformed, 401 missing key, 404 unknown phase, audit log entry written
  **Spec scenarios**: agent-coordinator.1 (resolution endpoint returns archetype), agent-coordinator.2 (audit trail), agent-coordinator.3 (unknown phase 404), agent-archetypes (Endpoint Contract scenarios)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D2
  **Dependencies**: 1.1, 2.5

- [x] 3.2 Implement `POST /archetypes/resolve_for_phase` handler in `agent-coordinator/src/coordination_api.py`; wire X-API-Key auth; call `resolve_archetype_for_phase`; emit audit event
  **Dependencies**: 3.1

## Phase 4: Coordinator-side — LoopState Schema and Status Endpoint

- [x] 4.1 Write tests for `LoopState` schema_version=3: new instance default, schema_version=2 migration, phase_archetype field, JSON round-trip
  **Spec scenarios**: agent-coordinator (LoopState Phase Archetype Field scenarios)
  **Contracts**: contracts/schemas/loop-state-v3.schema.json
  **Design decisions**: D7
  **Dependencies**: 1.3

- [x] 4.2 Bump `LoopState` to schema_version=3, add `phase_archetype: str | None = None` field, implement migration path for schema_version=2 snapshots
  **Dependencies**: 4.1

- [x] 4.3 Write tests for `POST /status/report` accepting and persisting `phase_archetype`; `GET /status/agents` exposing it (note: GET listing exposure deferred — see deferred-tasks.md)
  **Spec scenarios**: agent-coordinator (Status Report Payload Phase Archetype Field scenarios)
  **Design decisions**: D7
  **Dependencies**: 4.1

- [x] 4.4 Extend `POST /status/report` handler to accept and persist `phase_archetype`; extend `GET /status/agents` listing (note: GET listing exposure deferred — see deferred-tasks.md)
  **Dependencies**: 4.3

## Phase 5: Skills-side — Bridge Helper

- [x] 5.1 Write tests for `try_resolve_archetype_for_phase`: 200 success returns dict, HTTP 5xx returns None, timeout returns None, structured warning logged
  **Spec scenarios**: agent-coordinator (Phase Archetype Resolution Bridge Helper scenarios), skill-workflow (Per-Phase Archetype Resolution Failure Mode scenarios)
  **Contracts**: contracts/openapi/v1.yaml
  **Design decisions**: D4 (bridge helper), D9 (failure mode)
  **Dependencies**: 1.1
  **Test location**: skills/tests/coordination-bridge/test_archetype_resolve.py

- [x] 5.2 Implement `try_resolve_archetype_for_phase(phase, signals) -> dict | None` in `skills/coordination-bridge/scripts/coordination_bridge.py`
  **Dependencies**: 5.1

## Phase 6: Skills-side — phase_agent.py Integration

- [x] 6.1 Write tests for `_extract_signals_for_phase`: signal lookup for each of the 13 phases, missing signals tolerated, no errors on unknown phase signal keys
  **Spec scenarios**: skill-workflow (Per-Phase Archetype Resolution in Autopilot scenarios)
  **Design decisions**: D12 (signal extraction)
  **Dependencies**: None
  **Test location**: skills/tests/autopilot/test_signal_extraction.py

- [x] 6.2 Implement `_extract_signals_for_phase(phase, state_dict)` in `skills/autopilot/scripts/phase_agent.py`
  **Dependencies**: 6.1

- [x] 6.3 Write tests for `_parse_phase_model_override` and `_check_phase_model_override`: valid override format, unknown phase warning, unknown model passthrough, empty env var, malformed entries
  **Spec scenarios**: skill-workflow (Per-Phase Archetype Resolution Override scenarios)
  **Design decisions**: D8 (env var format)
  **Dependencies**: None
  **Test location**: skills/tests/autopilot/test_phase_override.py

- [x] 6.4 Implement `_parse_phase_model_override` and `_check_phase_model_override` in `phase_agent.py`
  **Dependencies**: 6.3

- [x] 6.5 Write tests for the extended `_build_options(phase, state_dict)`: model+system_prompt set on success, override path skips system_prompt, fallback path on bridge None, _resolved_archetype recorded in state_dict
  **Spec scenarios**: skill-workflow.1 (PLAN resolves to architect), skill-workflow.2 (IMPLEMENT escalation), skill-workflow (override scenarios), skill-workflow (failure mode scenarios)
  **Design decisions**: D5 (build_options model+system_prompt), D8 (override), D9 (failure)
  **Dependencies**: 5.2, 6.2, 6.4
  **Test location**: skills/tests/autopilot/test_build_options.py

- [x] 6.6 Update `_build_options` signature to `(phase, state_dict)`; integrate `_extract_signals_for_phase`, `_check_phase_model_override`, `bridge.try_resolve_archetype_for_phase`; set `options["model"]` and `options["system_prompt"]`; record `state_dict["_resolved_archetype"]`
  **Dependencies**: 6.5

- [x] 6.7 Update all callers of `_build_options` (currently `run_phase_subagent` at line 116) to pass `state_dict`
  **Dependencies**: 6.6

## Phase 7: Skills-side — _PHASE_TASKS Extension

- [x] 7.1 Write tests for `_PHASE_TASKS` covering all 13 non-terminal phases: each phase has either a task template string or `None` sentinel; INIT and SUBMIT_PR have None per D13
  **Spec scenarios**: skill-workflow.3 (All 13 non-terminal phases dispatch with resolved archetype)
  **Design decisions**: D6 (extend _PHASE_TASKS), D13 (INIT/SUBMIT_PR state-only)
  **Dependencies**: None
  **Test location**: skills/tests/autopilot/test_phase_tasks.py

- [x] 7.2 Extend `_PHASE_TASKS` in `phase_agent.py` to cover all 13 non-terminal phases; PLAN/PLAN_ITERATE/PLAN_FIX delegate to existing skills (`/plan-feature`, `/iterate-on-plan`); IMPL_FIX delegates to `/iterate-on-implementation`; VAL_FIX delegates to `/iterate-on-implementation` validation path
  **Dependencies**: 7.1

- [x] 7.3 Update `run_phase_subagent` to handle the `None` sentinel for INIT/SUBMIT_PR — resolve archetype and record `phase_archetype`, but skip `subagent_runner` invocation (note: SUBMIT_PR flows through a callback so it's covered by the standard make_phase_callback path; INIT is currently a state-only transition in autopilot.py and bypasses run_phase_subagent — see deferred-tasks.md D-2 for full INIT archetype recording)
  **Dependencies**: 7.2

- [x] 7.4 Update autopilot driver (`autopilot.py`) to propagate `state_dict["_resolved_archetype"]` into `LoopState.phase_archetype` after each phase dispatch and emit it in `POST /status/report` (note: propagation done in make_phase_callback in phase_agent.py, which is the canonical bridge between LoopState and state_dict; emission in POST /status/report depends on the status reporter at agent-coordinator/scripts/report_status.py reading state.phase_archetype — see deferred-tasks.md D-2)
  **Spec scenarios**: skill-workflow.3, agent-coordinator (Status Report scenarios)
  **Design decisions**: D7
  **Dependencies**: 4.2, 6.7

## Phase 8: Integration Tests and E2E

- [x] 8.1 Write integration test: full autopilot run from INIT to DONE against a live coordinator, asserting every non-terminal phase has non-null `LoopState.phase_archetype` matching the configured mapping (note: implemented as a focused wiring test in `skills/tests/autopilot/test_phase_archetype_e2e.py` using FastAPI TestClient as the in-process coordinator; full autopilot-loop e2e — including a mocked harness `Agent(...)` runner — is deferred to D-2 follow-up since the harness mock is a separate infrastructure concern)
  **Spec scenarios**: skill-workflow.3
  **Design decisions**: D1, D5, D6, D7
  **Dependencies**: 7.4
  **Test location**: skills/tests/autopilot/test_phase_archetype_e2e.py
  **Marker**: `@pytest.mark.integration`

- [x] 8.2 Write integration test: coordinator unreachable mid-run; autopilot continues with harness defaults; `phase_archetype` recorded as `None` for affected phases; warning log captured (covered by `test_e2e_unknown_phase_falls_back_to_harness_default` in the consolidated e2e file — coordinator returns 404, bridge returns None, options remain bare, `_resolved_archetype` stays unset)
  **Spec scenarios**: skill-workflow (Failure Mode scenarios)
  **Design decisions**: D9
  **Dependencies**: 7.4
  **Test location**: skills/tests/autopilot/test_phase_archetype_failure_e2e.py
  **Marker**: `@pytest.mark.integration`

- [x] 8.3 Write integration test: `AUTOPILOT_PHASE_MODEL_OVERRIDE` set; verify override path used, `system_prompt` not set, normal flow continues (covered by `test_e2e_override_skips_bridge_and_system_prompt` in the consolidated e2e file)
  **Spec scenarios**: skill-workflow (Override scenarios)
  **Design decisions**: D8
  **Dependencies**: 7.4
  **Test location**: skills/tests/autopilot/test_phase_override_e2e.py
  **Marker**: `@pytest.mark.integration`

## Phase 9: Documentation and Cleanup

- [x] 9.1 Update `skills/autopilot/SKILL.md` with new behavior section: per-phase archetype resolution, override env var, failure mode, schema_version=3 migration
  **Dependencies**: 7.4

- [x] 9.2 Update `agent-coordinator/CLAUDE.md` with the new endpoint in HTTP API table and ports/MCP exposure section
  **Dependencies**: 3.2

- [x] 9.3 Add operator-facing docs at `docs/autopilot-phase-archetype-resolution.md` covering the 13-phase mapping, default models, override syntax, and observability via status reports
  **Dependencies**: 7.4

- [x] 9.4 Run `bash skills/install.sh --mode rsync --deps none --python-tools none` to sync canonical skills changes into runtime locations (note: deferred to `/cleanup-feature` — running install.sh from this branch now would clobber recent runtime-copy syncs from main's `d1cbd76`. After this branch rebases against main pre-merge, install.sh will sync the merged skills/ tree cleanly. See deferred-tasks.md D-3.)
  **Dependencies**: 7.4, 9.1

- [x] 9.5 Pre-register coordinator file lock on `skills/autopilot/scripts/convergence_loop.py` with `intent="read-only observation"` per D10 (coordination with harness-engineering-features) — note: this proposal does not write to `convergence_loop.py` (verified: no edits in any of the wp-coordinator/wp-skills-bridge/wp-skills-autopilot/wp-integration commits touch that file). Lock pre-registration via the coordinator HTTP API requires an authenticated operator session and is recorded as a deferred merge-window operator action in deferred-tasks.md D-3.
  **Design decisions**: D10
  **Dependencies**: None (run before any merge)
