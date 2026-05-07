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

The `skills/autopilot/SKILL.md` orchestration prose SHALL invoke the harness `Agent(...)` tool for the following 7 phases: `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `VAL_REVIEW` (when enabled). For these phases the dispatch SHALL pass the resolved `model` and SHALL fold the resolved `system_prompt` into the agent's prompt text using the fixed separator `\n\n---\n\n` (the literal four-character newline-newline-three-dashes-newline-newline string, asserted verbatim).

State-only phases (`INIT`, `SUBMIT_PR`) SHALL still record `LoopState.phase_archetype` for their resolved archetype via a state-only resolver in `autopilot.run_loop`, even though they do not dispatch a sub-agent.

Convergence-loop-driven phases (`PLAN_FIX`, `IMPL_FIX`, `VAL_FIX`) SHALL record `LoopState.phase_archetype` for audit purposes via the convergence loop's existing audit path, but SHALL NOT receive a separate `Agent(...)` dispatch block in SKILL.md (the convergence loop in `convergence_loop.py` handles their dispatch internally).

The skill-delegated `PLAN` phase (which invokes `/plan-feature`) SHALL NOT receive an explicit `Agent(...)` dispatch block; it SHALL continue to dispatch via the existing skill-invocation path because `/plan-feature` itself manages sub-agent dispatch internally.

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

#### Scenario: 10 of 13 non-terminal phases set phase_archetype

- **WHEN** autopilot completes a full state machine run from INIT to DONE
- **THEN** the following 10 phases SHALL have set `LoopState.phase_archetype` to a non-null value matching `phase_mapping`: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `VAL_REVIEW`, `SUBMIT_PR`
- **AND** the convergence-loop-driven phases (`PLAN_FIX`, `IMPL_FIX`, `VAL_FIX`) SHALL inherit `phase_archetype` from their preceding REVIEW phase via the shared `LoopState` (no separate write — convergence_loop never overwrites the field)
- **AND** if a `_FIX` phase runs without a preceding successful REVIEW (e.g. quorum lost on round 1), `LoopState.phase_archetype` MAY be `null` for that phase — this is acceptable per the design and SHALL NOT cause autopilot to escalate

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

1. **`build_phase_dispatch_kwargs(phase: str, change_id: str) -> dict`** — returns a JSON-serializable dict containing `{prompt, model, system_prompt, isolation, archetype}` for the given phase. The function SHALL:
   - Validate `change_id` against the regex `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` and raise `ValueError` on failure.
   - Read `loop-state.json` from `openspec/changes/<change_id>/loop-state.json`.
   - Hydrate or bootstrap an incoming `PhaseRecord` from `state.last_handoff_id`.
   - Call `_build_options(phase, state_dict)` and `_build_prompt(phase, ...)` internally.
   - Atomically write `openspec/changes/<change_id>/.phase-resolution-cache.json` containing `{schema_version, change_id, phase, archetype, checksum}` where `checksum` is the SHA-256 of `change_id + phase + archetype`.

2. **`apply_phase_outcome(change_id: str, phase: str, outcome: str, handoff_id: str) -> None`** — updates `loop-state.json` with the new `last_handoff_id`, appends to `handoff_ids` (skipping if already present), and sets `phase_archetype` from the cache file. The function SHALL:
   - Be idempotent — calling twice with the same `(change_id, phase, outcome, handoff_id)` leaves `loop-state.json` in the same final state, with `handoff_id` appearing exactly once in `handoff_ids` and `phase_archetype` preserving the value written by the first call (NOT overwritten with `None` on the second call even though the cache file was deleted by the first).
   - Detect replay via the rule: if loaded `state.last_handoff_id == handoff_id` AND `state.previous_phase == phase` (or `state.current_phase == phase`), treat the call as a replay. In replay mode, preserve `phase_archetype` and skip the cache validation (cache is allowed to be missing — the prior successful call deleted it).
   - When NOT a replay, validate the cache file's `change_id`, `phase`, and `checksum`. On any mismatch (parse error, missing file, change-id mismatch, phase mismatch, checksum mismatch), set `phase_archetype = None`, log a structured warning, and continue without raising.
   - On successful non-replay apply, delete the cache file (atomic rename to a temp path then unlink, so a crash mid-delete leaves the cache discoverable).

Both helpers SHALL be invocable as CLI scripts via `runner.py` so SKILL.md prose can shell out to them with structured arguments. The CLI surface is `runner.py build-dispatch --phase X --change-id Y` and `runner.py apply-outcome --phase X --change-id Y --outcome Z --handoff-id H`.

#### Scenario: build_phase_dispatch_kwargs returns dispatch-ready dict

- **GIVEN** an autopilot run is at the `IMPLEMENT` phase with a resolved archetype
- **WHEN** `python3 runner.py build-dispatch --phase IMPLEMENT --change-id <id>` is invoked
- **THEN** stdout SHALL be a single JSON object containing `prompt`, `model`, `system_prompt`, `isolation`, and `archetype` keys
- **AND** `model` SHALL match the resolved archetype's model
- **AND** `isolation` SHALL be `"worktree"` (since IMPLEMENT is in `_WORKTREE_PHASES`)
- **AND** `openspec/changes/<id>/.phase-resolution-cache.json` SHALL contain `{"phase": "IMPLEMENT", "archetype": "implementer", "change_id": "<id>"}`

#### Scenario: apply_phase_outcome updates loop state and is idempotent under replay

- **GIVEN** `loop-state.json` exists at version 3 and the cache file `.phase-resolution-cache.json` is present with phase=IMPLEMENT, archetype=implementer
- **WHEN** `python3 runner.py apply-outcome --change-id <id> --phase IMPLEMENT --outcome continue --handoff-id h-abc` is invoked
- **THEN** `LoopState.last_handoff_id` SHALL equal `"h-abc"`, `LoopState.handoff_ids` SHALL contain `"h-abc"`, `LoopState.phase_archetype` SHALL equal `"implementer"`, and the cache file SHALL be deleted
- **WHEN** the same command is invoked a second time (replay scenario — cache file is now absent because the first call deleted it)
- **THEN** `apply_phase_outcome` SHALL detect the replay via `state.last_handoff_id == "h-abc"` AND `state.previous_phase == "IMPLEMENT"`
- **AND** `LoopState.phase_archetype` SHALL still equal `"implementer"` (preserved, NOT overwritten with `null`)
- **AND** `LoopState.handoff_ids` SHALL contain `"h-abc"` exactly once (no duplicate append)
- **AND** the missing cache file SHALL NOT cause an error or warning

#### Scenario: PLAN_FIX inherits phase_archetype from PLAN_REVIEW

- **GIVEN** autopilot just completed `PLAN_REVIEW` with `LoopState.phase_archetype = "reviewer"` and convergence did not converge
- **WHEN** the loop transitions to `PLAN_FIX`
- **THEN** `LoopState.phase_archetype` SHALL still equal `"reviewer"` after PLAN_FIX completes (convergence_loop never overwrites the field)
- **AND** the convergence loop SHALL NOT call `build_phase_dispatch_kwargs` for the PLAN_FIX phase

#### Scenario: apply_phase_outcome with mismatched cache writes null archetype

- **GIVEN** `.phase-resolution-cache.json` contains `{"phase": "PLAN", "archetype": "architect", "change_id": "<id>"}`
- **WHEN** `apply_phase_outcome` is called with `--phase IMPLEMENT --change-id <id>`
- **THEN** `LoopState.phase_archetype` SHALL be set to `None`
- **AND** a structured warning SHALL be logged identifying the cache/phase mismatch

#### Scenario: Joined prompt preserves phase task instructions even when phase prompt contains "---"

- **GIVEN** an archetype's `system_prompt` is `"You are the implementer. Follow contracts."`
- **AND** the resolved phase prompt for IMPLEMENT contains the substring `"\n---\n"` (e.g., a markdown rule inside task instructions)
- **WHEN** `build_phase_dispatch_kwargs("IMPLEMENT", "<id>")` is called
- **THEN** the returned `prompt` SHALL begin with the system_prompt followed by exactly one occurrence of the literal separator `"\n\n---\n\n"`
- **AND** the original phase-prompt content SHALL appear in the returned `prompt` unchanged after the separator
- **AND** all key task-instruction tokens (e.g., `"change_id"`, `"submit"`, `"complete"`) from the phase prompt SHALL appear in the returned `prompt`

#### Scenario: build_phase_dispatch_kwargs rejects path-traversal change_id

- **GIVEN** an attacker-controlled `change_id` value `"../../etc/passwd"`
- **WHEN** `build_phase_dispatch_kwargs("IMPLEMENT", "../../etc/passwd")` is called
- **THEN** the function SHALL raise `ValueError` before any filesystem access
- **AND** no file SHALL be created or read outside `openspec/changes/`

#### Scenario: Joined prompt token budget is enforced

- **GIVEN** the joined prompt for any phase exceeds 75% of the resolved model's context window
- **WHEN** the wp-skills-autopilot token-budget CI check runs across all 7 sub-agent-dispatching phases
- **THEN** the check SHALL fail with a non-zero exit code
- **AND** the failure message SHALL identify the phase, the joined-prompt token count, and the model context window
- **AND** at the 60-75% range the check SHALL emit a warning but exit zero
