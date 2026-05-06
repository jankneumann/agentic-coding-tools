# Skill Workflow — Spec Delta: Wire Autopilot Per-Phase Sub-Agent Dispatch

## MODIFIED Requirements

### Requirement: Per-Phase Archetype Resolution in Autopilot

The autopilot state machine SHALL resolve an archetype for every non-terminal phase before dispatching the phase's sub-agent, SHALL inject the resolved `model` and `system_prompt` into the sub-agent dispatch options, AND SHALL apply the resolved archetype on the **production execution path** (not only in unit tests of `phase_agent`).

The resolution SHALL:
1. Be performed inside `skills/autopilot/scripts/phase_agent.py:_build_options(phase, state_dict)`.
2. Extract per-phase signals from `state_dict` based on the `signals` field of the phase mapping.
3. Call the coordinator endpoint `POST /archetypes/resolve_for_phase` via `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)`.
4. Set `options["model"]` and `options["system_prompt"]` from the response.
5. Record the resolved archetype name in `state_dict["_resolved_archetype"]` for downstream use by `LoopState.phase_archetype`.

The 13 non-terminal phases SHALL be: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR`.

The `skills/autopilot/SKILL.md` orchestration prose SHALL invoke the harness `Agent(...)` tool for at least the following phases: `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `PLAN_ITERATE`, `PLAN_REVIEW`. The dispatch SHALL pass the resolved `model` and SHALL fold the resolved `system_prompt` into the agent's prompt text using the separator `\n\n---\n\n`.

State-only phases (`INIT`, `SUBMIT_PR`) SHALL still record `LoopState.phase_archetype` for their resolved archetype via a state-only resolver in `autopilot.run_loop`, even though they do not dispatch a sub-agent.

#### Scenario: PLAN phase resolves to architect archetype

- **WHEN** autopilot enters the `PLAN` phase
- **AND** `phase_mapping.PLAN.archetype` is `"architect"`
- **THEN** `_build_options("PLAN", state_dict)` SHALL return options containing `"model": "opus"` and `"system_prompt"` matching the architect's system prompt
- **AND** the sub-agent dispatch SHALL receive these options verbatim

#### Scenario: IMPLEMENT phase resolves with escalation signals

- **GIVEN** a work package with `loc_estimate=250` is being processed
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** `_build_options("IMPLEMENT", state_dict)` SHALL extract `loc_estimate` from `state_dict` and pass it as a signal
- **AND** the resolved `model` SHALL be `"opus"` (escalated from `sonnet`)
- **AND** `state_dict["_resolved_archetype"]` SHALL be `"implementer"`

#### Scenario: All 13 non-terminal phases dispatch with resolved archetype

- **WHEN** autopilot completes a full state machine run from INIT to DONE
- **THEN** every non-terminal phase transition SHALL have set `LoopState.phase_archetype` to a non-null value before dispatch
- **AND** the values for `INIT, PLAN, PLAN_ITERATE, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW, VAL_FIX, SUBMIT_PR` SHALL each match the configured `phase_mapping` archetype

#### Scenario: Production autopilot run dispatches harness Agent with resolved model

- **GIVEN** a real autopilot run executing from `/autopilot <change-id>` against an available coordinator
- **WHEN** the run reaches the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL invoke the harness `Agent(...)` tool with `model` set to the resolved `phase_mapping.IMPLEMENT.model`
- **AND** the prompt passed to `Agent(...)` SHALL begin with the resolved `system_prompt` followed by `\n\n---\n\n` followed by the per-phase task prompt
- **AND** after the `Agent(...)` call returns, `LoopState.phase_archetype` in `loop-state.json` SHALL equal `"implementer"`
- **AND** `LoopState.last_handoff_id` SHALL be updated to the `handoff_id` returned from the dispatched sub-agent

#### Scenario: INIT phase records archetype despite being state-only

- **WHEN** autopilot enters the `INIT` phase
- **THEN** `autopilot._resolve_phase_archetype_for_state_only(state, "INIT")` SHALL be called
- **AND** `LoopState.phase_archetype` SHALL be set to `"runner"` (per phase_mapping)
- **AND** no harness `Agent(...)` call SHALL be made for INIT

---

### Requirement: Per-Phase Archetype Resolution Failure Mode

If the coordinator endpoint is unreachable or returns an error, OR if the harness `Agent(...)` tool is not available in the executing orchestrator, autopilot SHALL fall back to the existing inline-prose execution path for that phase and continue.

Fallback behavior:
- `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)` SHALL return `None` on any failure (network error, timeout, 4xx, 5xx, malformed response).
- When `None` is returned, `_build_options` SHALL NOT set `options["model"]` or `options["system_prompt"]`.
- `LoopState.phase_archetype` SHALL be set to `None` for that phase.
- A structured warning SHALL be logged including the phase name, the error reason, and a hint that operators can use `AUTOPILOT_PHASE_MODEL_OVERRIDE` as a temporary mitigation.
- The phase SHALL still complete normally — the SKILL.md dispatch block SHALL fall through to the existing inline slash-command path (`/iterate-on-implementation`, `/implement-feature`, etc.) instead of `Agent(...)` dispatch.

#### Scenario: Coordinator unreachable, autopilot continues

- **GIVEN** the coordinator returns HTTP 503 for `POST /archetypes/resolve_for_phase`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** `_build_options("PLAN", state_dict)` SHALL return options without `model` or `system_prompt` keys
- **AND** the SKILL.md dispatch block SHALL fall through to the inline `/plan-feature` invocation
- **AND** `LoopState.phase_archetype` SHALL be `None` for that phase
- **AND** a structured warning SHALL be logged

#### Scenario: Network timeout falls back gracefully

- **GIVEN** `coordination_bridge.try_resolve_archetype_for_phase` raises `TimeoutError`
- **WHEN** the bridge call is made
- **THEN** the function SHALL return `None`
- **AND** autopilot SHALL NOT crash or retry the resolution within the same phase dispatch

#### Scenario: Harness Agent tool not exposed, fallback to inline path

- **GIVEN** the orchestrator session does not expose the harness `Agent(...)` tool (e.g., minimal API-only execution)
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL detect the missing tool and SHALL fall through to the inline `/implement-feature <change-id>` invocation
- **AND** `LoopState.phase_archetype` SHALL be `None` for that phase
- **AND** a structured warning SHALL be logged identifying that `Agent(...)` was unavailable

## ADDED Requirements

### Requirement: Sub-Agent Dispatch Protocol Helpers

`skills/autopilot/scripts/phase_agent.py` SHALL expose two pure-Python helper entry points that the SKILL.md orchestration prose calls across the prose/Python boundary:

1. **`build_phase_dispatch_kwargs(phase, change_id)`** — returns a JSON-serializable dict containing `{prompt, model, system_prompt, isolation, archetype}` for the given phase. The function SHALL be a pure read of LoopState plus a single bridge call to `try_resolve_archetype_for_phase`. It SHALL also write the resolved archetype name to `openspec/changes/<change-id>/.phase-resolution-cache.json` so the apply-outcome helper can read it.

2. **`apply_phase_outcome(change_id, phase, outcome, handoff_id)`** — updates `loop-state.json` with the new `last_handoff_id`, appends to `handoff_ids`, and sets `phase_archetype` from the cache file. SHALL be idempotent (safe to call twice with the same `handoff_id`).

Both helpers SHALL be invocable as CLI scripts via `runner.py` so SKILL.md prose can shell out to them with structured arguments.

#### Scenario: build_phase_dispatch_kwargs returns dispatch-ready dict

- **GIVEN** an autopilot run is at the `IMPLEMENT` phase with a resolved archetype
- **WHEN** `python3 runner.py build-dispatch --phase IMPLEMENT --change-id <id>` is invoked
- **THEN** stdout SHALL be a single JSON object containing `prompt`, `model`, `system_prompt`, `isolation`, and `archetype` keys
- **AND** `model` SHALL match the resolved archetype's model
- **AND** `isolation` SHALL be `"worktree"` (since IMPLEMENT is in `_WORKTREE_PHASES`)
- **AND** `openspec/changes/<id>/.phase-resolution-cache.json` SHALL contain `{"phase": "IMPLEMENT", "archetype": "implementer", "change_id": "<id>"}`

#### Scenario: apply_phase_outcome updates loop state and is idempotent

- **GIVEN** `loop-state.json` exists at version 3
- **WHEN** `python3 runner.py apply-outcome --change-id <id> --phase IMPLEMENT --outcome continue --handoff-id h-abc` is invoked twice in succession
- **THEN** after both calls `LoopState.last_handoff_id` SHALL be `"h-abc"`
- **AND** `LoopState.handoff_ids` SHALL contain `"h-abc"` exactly once
- **AND** `LoopState.phase_archetype` SHALL match the cached archetype for IMPLEMENT

#### Scenario: apply_phase_outcome with mismatched cache writes null archetype

- **GIVEN** `.phase-resolution-cache.json` contains `{"phase": "PLAN", "archetype": "architect", "change_id": "<id>"}`
- **WHEN** `apply_phase_outcome` is called with `--phase IMPLEMENT --change-id <id>`
- **THEN** `LoopState.phase_archetype` SHALL be set to `None`
- **AND** a structured warning SHALL be logged identifying the cache/phase mismatch
