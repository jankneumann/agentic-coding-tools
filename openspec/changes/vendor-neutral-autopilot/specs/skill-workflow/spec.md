## MODIFIED Requirements

### Requirement: Per-Phase Archetype Resolution in Autopilot

The autopilot state machine SHALL resolve an archetype for every non-terminal phase before dispatching phase work, SHALL build a provider-neutral phase dispatch payload for sub-agent-capable phases, and SHALL apply the resolved archetype on the production execution path.

The resolution SHALL:

1. Be performed inside `skills/autopilot/scripts/phase_agent.py:_build_options(phase, state_dict)` or a compatibility wrapper that preserves that public behavior.
2. Extract per-phase signals from `state_dict` based on the `signals` field of the phase mapping.
3. Call the coordinator endpoint `POST /archetypes/resolve_for_phase` via `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)`.
4. Resolve a logical archetype and model tier to a provider-specific model identifier for the selected provider.
5. Record the resolved archetype name in `state_dict["_resolved_archetype"]` for downstream use by `LoopState.phase_archetype`.

The 13 non-terminal phases SHALL be: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR`.

The `skills/autopilot/SKILL.md` orchestration prose SHALL dispatch the following 7 phases through the provider-neutral dispatch adapter when an adapter is available: `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `VAL_REVIEW` (when enabled). For these phases the dispatch SHALL pass the provider-specific model ID and SHALL fold the resolved `system_prompt` into the prompt text using the fixed separator `\n\n---\n\n`.

State-only phases (`INIT`, `PLAN`, `SUBMIT_PR`) SHALL still record `LoopState.phase_archetype` for their resolved archetype via a state-only resolver, even though they do not dispatch a phase sub-agent.

Convergence-loop-driven phases (`PLAN_FIX`, `IMPL_FIX`, `VAL_FIX`) SHALL inherit or record `LoopState.phase_archetype` for audit purposes via the convergence loop's existing path, but SHALL NOT receive a separate provider-adapter dispatch block in SKILL.md.

#### Scenario: PLAN phase resolves to provider-specific architect model

- **GIVEN** autopilot is running under provider `codex`
- **AND** `phase_mapping.PLAN.archetype` is `"architect"`
- **AND** the provider model map resolves `architect` or its tier to `gpt-5.5`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** the resolved phase metadata SHALL contain `"archetype": "architect"`
- **AND** the dispatch metadata SHALL contain `"model": "gpt-5.5"`
- **AND** the dispatch metadata SHALL NOT contain Claude-only model aliases unless the Codex mapping explicitly declares them

#### Scenario: IMPLEMENT phase resolves with provider-specific escalation

- **GIVEN** autopilot is running under provider `gemini`
- **AND** a work package with `loc_estimate=250` is being processed
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** the phase resolver SHALL extract `loc_estimate` from `state_dict` and pass it as a signal
- **AND** the resolved archetype SHALL be `"implementer"`
- **AND** the model tier SHALL escalate from `standard` to `premium`
- **AND** the provider-specific model SHALL be a Gemini model ID from the configured Gemini mapping

#### Scenario: Production autopilot run dispatches through provider adapter

- **GIVEN** a real autopilot run executing from `/autopilot <change-id>` against an available coordinator
- **AND** the active provider is `codex`
- **WHEN** the run reaches the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL invoke the provider-neutral dispatch adapter
- **AND** the adapter SHALL receive a payload conforming to `contracts/phase-dispatch-contract.md`
- **AND** the payload's `model` SHALL be provider-specific for Codex
- **AND** the prompt passed to the adapter SHALL begin with the resolved `system_prompt` followed by `\n\n---\n\n` followed by the per-phase task prompt
- **AND** after the adapter returns, `LoopState.phase_archetype` in `loop-state.json` SHALL equal `"implementer"`
- **AND** `LoopState.last_handoff_id` SHALL be updated to the `handoff_id` returned from the dispatched provider result

#### Scenario: Claude remains supported

- **GIVEN** autopilot is running under provider `claude_code`
- **AND** the Claude dispatch adapter is available
- **WHEN** autopilot dispatches a phase that previously used `Agent(...)`
- **THEN** the provider-neutral adapter MAY invoke the existing Claude harness `Agent(...)` surface internally
- **AND** the public SKILL.md contract SHALL still describe the provider-neutral adapter rather than requiring non-Claude providers to expose `Agent(...)`

### Requirement: Per-Phase Archetype Resolution Override

The system SHALL support an environment variable `AUTOPILOT_PHASE_MODEL_OVERRIDE` that forces specific provider model IDs for specific phases, overriding the resolved provider-specific model.

Format: `<PHASE>=<model>[,<PHASE>=<model>]*`.

Override behavior:

- Override SHALL take precedence over archetype-resolved model.
- Override SHALL set only the dispatch model value; it SHALL NOT change the resolved archetype.
- Unknown phase names in the override string SHALL be logged as warnings and ignored.
- Unknown model names SHALL pass through only to the selected provider adapter, which is responsible for provider-specific validation or failure reporting.

#### Scenario: Override forces a Codex model for a phase

- **GIVEN** `AUTOPILOT_PROVIDER=codex`
- **AND** `AUTOPILOT_PHASE_MODEL_OVERRIDE=PLAN=gpt-5.4`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** the dispatch model SHALL be `"gpt-5.4"`
- **AND** the resolved archetype SHALL remain `"architect"`

### Requirement: Per-Phase Archetype Resolution Failure Mode

If the coordinator endpoint is unreachable or returns an error, OR if no provider adapter is available in the executing orchestrator, autopilot SHALL fall back to the existing inline-prose execution path for that phase and continue.

Fallback behavior:

- `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)` SHALL return `None` on any failure.
- When `None` is returned, phase dispatch SHALL omit provider-specific model and system prompt values unless an override is present.
- `LoopState.phase_archetype` SHALL be set to `None` for that phase.
- A structured warning SHALL be logged including the phase name, selected provider, error reason, and a hint that operators can use `AUTOPILOT_PHASE_MODEL_OVERRIDE` or provider config as temporary mitigation.
- The phase SHALL still complete normally by falling through to the existing inline slash-command path.

#### Scenario: Provider adapter unavailable falls back gracefully

- **GIVEN** `AUTOPILOT_PROVIDER=gemini`
- **AND** no Gemini/Jules dispatch adapter is configured in the current runtime
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL detect the missing adapter
- **AND** it SHALL fall through to the inline `/implement-feature <change-id>` invocation
- **AND** `LoopState.phase_archetype` SHALL be `None` for that phase
- **AND** a structured warning SHALL identify the selected provider and adapter unavailability

### Requirement: Sub-Agent Dispatch Protocol Helpers

`skills/autopilot/scripts/phase_agent.py` SHALL expose pure-Python helper entry points that the SKILL.md orchestration prose calls across the prose/Python boundary:

1. `build_phase_dispatch_kwargs(phase: str, change_id: str) -> dict` SHALL remain backward compatible and return a JSON-serializable dict containing at least `{prompt, model, system_prompt, isolation, archetype}` for the given phase.
2. `build_phase_dispatch_payload(phase: str, change_id: str, provider: str | None = None) -> dict` SHALL return a provider-neutral payload conforming to `contracts/phase-dispatch-contract.md`.
3. `apply_phase_outcome(change_id: str, phase: str, outcome: str, handoff_id: str) -> None` SHALL continue to update `loop-state.json` with the new `last_handoff_id`, append to `handoff_ids`, and set `phase_archetype` from the resolution cache.

The helper surface SHALL validate `change_id`, read `loop-state.json`, hydrate or bootstrap incoming handoff context, atomically write the phase-resolution cache, and remain idempotent under replay.

#### Scenario: build_phase_dispatch_payload returns provider-neutral payload

- **GIVEN** an autopilot run is at the `IMPLEMENT` phase with provider `codex`
- **WHEN** `python3 runner.py build-dispatch --phase IMPLEMENT --change-id <id> --provider codex` is invoked
- **THEN** stdout SHALL contain a single JSON object with `prompt`, `model`, `system_prompt`, `isolation`, `archetype`, `provider`, `phase`, and `expected_outcomes`
- **AND** `model` SHALL be a Codex model ID from provider mapping
- **AND** `isolation` SHALL be `"worktree"` because IMPLEMENT is worktree-isolated
- **AND** the resolution cache SHALL still contain the logical archetype for `apply_phase_outcome`

#### Scenario: Joined prompt token budget is provider aware

- **GIVEN** the joined prompt for any phase exceeds 75% of the selected provider model's context window
- **WHEN** the autopilot token-budget CI check runs across all sub-agent-dispatching phases
- **THEN** the check SHALL fail with a non-zero exit code
- **AND** the failure message SHALL identify the phase, provider, provider-specific model, joined-prompt token count, and context window
- **AND** at the 60-75% range the check SHALL emit a warning but exit zero

### Requirement: Lifecycle Skills Use Provider-Neutral Dispatch Terminology

The lifecycle skills called by `/autopilot` SHALL describe phase or task delegation using provider-neutral dispatch terminology rather than Claude-only `Agent(...)` terminology.

This requirement applies to:

- `skills/autopilot/SKILL.md`
- `skills/plan-feature/SKILL.md`
- `skills/implement-feature/SKILL.md`
- `skills/iterate-on-plan/SKILL.md`
- `skills/iterate-on-implementation/SKILL.md`
- `skills/parallel-review-plan/SKILL.md`
- `skills/parallel-review-implementation/SKILL.md`
- `skills/validate-feature/SKILL.md`

#### Scenario: Skill docs do not make Agent the canonical cross-provider path

- **WHEN** lifecycle skill docs are scanned for provider-dispatch instructions
- **THEN** Claude-specific `Agent(...)` references SHALL be labeled as Claude adapter internals or examples
- **AND** the canonical instruction SHALL refer to the provider-neutral dispatch adapter or inline fallback
- **AND** Codex and Gemini/Jules SHALL be described as first-class providers where adapters are configured

### Requirement: Manual Provider Smoke Path

The system SHALL provide an end-to-end smoke path that can be manually triggered by an operator from a specific agent CLI and verifies `/autopilot` provider-neutral dispatch behavior.

The smoke path SHALL:

- Accept a provider selector.
- Use a fixture or minimal change-id.
- Exercise the same provider model mapping used by real phase dispatch.
- Exercise the provider dispatch adapter in dry-run or real mode.
- Verify normalized `outcome` and `handoff_id` handling.
- Fail if a non-Claude provider receives `opus`, `sonnet`, or `haiku` without explicit mapping.

#### Scenario: Codex CLI smoke succeeds

- **GIVEN** the operator runs the smoke path with provider `codex`
- **WHEN** the smoke reaches the provider dispatch step
- **THEN** the dispatch payload SHALL contain a Codex model ID
- **AND** the dispatch result SHALL normalize to `(outcome, handoff_id)`
- **AND** the smoke SHALL report a pass/fail summary suitable for manual verification

#### Scenario: Gemini CLI smoke succeeds in configured mode

- **GIVEN** the operator runs the smoke path with provider `gemini`
- **AND** Gemini/Jules dispatch is configured for dry-run, sync CLI, or async polling
- **WHEN** the smoke reaches the provider dispatch step
- **THEN** the dispatch payload SHALL contain a Gemini model ID
- **AND** the dispatch result SHALL normalize to `(outcome, handoff_id)`
- **AND** the smoke SHALL report any adapter limitations as warnings rather than silently skipping the provider
