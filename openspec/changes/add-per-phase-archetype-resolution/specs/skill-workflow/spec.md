# Spec Delta — skill-workflow (per-phase archetype resolution in autopilot)

## ADDED Requirements

### Requirement: Per-Phase Archetype Resolution in Autopilot

The autopilot state machine SHALL resolve an archetype for every non-terminal phase before dispatching the phase's sub-agent, and SHALL inject the resolved `model` and `system_prompt` into the sub-agent dispatch options.

The resolution SHALL:
1. Be performed inside `skills/autopilot/scripts/phase_agent.py:_build_options(phase, state_dict)`.
2. Extract per-phase signals from `state_dict` based on the `signals` field of the phase mapping.
3. Call the coordinator endpoint `POST /archetypes/resolve_for_phase` via `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)`.
4. Set `options["model"]` and `options["system_prompt"]` from the response.
5. Record the resolved archetype name in `state_dict["_resolved_archetype"]` for downstream use by `LoopState.phase_archetype`.

The 13 non-terminal phases SHALL be: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR`.

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

---

### Requirement: Per-Phase Archetype Resolution Override

The system SHALL support an environment variable `AUTOPILOT_PHASE_MODEL_OVERRIDE` that forces specific models for specific phases, overriding the resolved archetype's model.

Format: `<PHASE>=<model>[,<PHASE>=<model>]*` (e.g., `PLAN=opus,IMPL_REVIEW=sonnet`).

Override behavior:
- Override SHALL take precedence over archetype-resolved model.
- Override SHALL set `options["model"]` only; `options["system_prompt"]` SHALL NOT be set when an override is in effect (harness default applies).
- Unknown phase names in the override string SHALL be logged as warnings and ignored.
- Unknown model names SHALL pass through (validated downstream by the harness).

#### Scenario: Override forces a specific model for a phase

- **GIVEN** `AUTOPILOT_PHASE_MODEL_OVERRIDE=PLAN=opus`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** `options["model"]` SHALL be `"opus"`
- **AND** `options` SHALL NOT contain `"system_prompt"`

#### Scenario: Override with unknown phase logs warning

- **GIVEN** `AUTOPILOT_PHASE_MODEL_OVERRIDE=BOGUS=opus,PLAN=sonnet`
- **WHEN** autopilot starts
- **THEN** a warning SHALL be logged identifying `BOGUS` as an unknown phase
- **AND** the `PLAN=sonnet` override SHALL be honored normally

---

### Requirement: Per-Phase Archetype Resolution Failure Mode

If the coordinator endpoint is unreachable or returns an error, autopilot SHALL fall back to the harness default model+system_prompt for that phase and continue.

Fallback behavior:
- `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)` SHALL return `None` on any failure (network error, timeout, 4xx, 5xx, malformed response).
- When `None` is returned, `_build_options` SHALL NOT set `options["model"]` or `options["system_prompt"]`.
- `LoopState.phase_archetype` SHALL be set to `None` for that phase.
- A structured warning SHALL be logged including the phase name, the error reason, and a hint that operators can use `AUTOPILOT_PHASE_MODEL_OVERRIDE` as a temporary mitigation.
- The phase SHALL still dispatch and complete normally.

#### Scenario: Coordinator unreachable, autopilot continues

- **GIVEN** the coordinator returns HTTP 503 for `POST /archetypes/resolve_for_phase`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** `_build_options("PLAN", state_dict)` SHALL return options without `model` or `system_prompt` keys
- **AND** the phase SHALL dispatch normally with the harness default
- **AND** `LoopState.phase_archetype` SHALL be `None` for that phase
- **AND** a structured warning SHALL be logged

#### Scenario: Network timeout falls back gracefully

- **GIVEN** `coordination_bridge.try_resolve_archetype_for_phase` raises `TimeoutError`
- **WHEN** the bridge call is made
- **THEN** the function SHALL return `None`
- **AND** autopilot SHALL NOT crash or retry the resolution within the same phase dispatch
