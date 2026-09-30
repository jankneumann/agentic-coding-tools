# skill-workflow Specification (delta)

## MODIFIED Requirements

### Requirement: Per-Phase Archetype Resolution in Autopilot

The autopilot state machine SHALL resolve an archetype for every non-terminal phase before dispatching phase work, SHALL build a provider-neutral phase dispatch payload for sub-agent-capable phases, SHALL apply the resolved archetype on the production execution path, and SHALL record a dispatch record for every dispatch.

The resolution SHALL:

1. Be performed inside `skills/autopilot/scripts/phase_agent.py:_build_options(phase, state_dict)` or a compatibility wrapper that preserves that public behavior.
2. Extract per-phase signals from `state_dict` based on the `signals` field of the phase mapping.
3. Call the coordinator endpoint `POST /archetypes/resolve_for_phase` via `coordination_bridge.try_resolve_archetype_for_phase(phase, signals, provider=<selected provider>)`.
4. Resolve a logical archetype and model tier to a provider-specific model identifier for the selected provider.
5. Record the resolved archetype name in `state_dict["_resolved_archetype"]` for downstream use by `LoopState.phase_archetype`.
6. Copy `thinking` from the resolution into `options["thinking"]` and carry it into the dispatch payload as `thinking`, alongside `model`.
7. Write a dispatch record (per the `usage-accounting` Dispatch Record requirement) via `coordination_bridge.try_record_dispatch(...)` before invoking the adapter. Failure to write the record SHALL be logged and SHALL NOT block the dispatch.

   The `agent_id` patch SHALL NOT be performed by `build_phase_dispatch_kwargs`. That helper runs
   **before** the adapter is invoked and never sees its result, so a patch located there can only
   ever write a NULL it already wrote. The patch SHALL instead be performed on the return path that
   observes the adapter's result — the same `apply-outcome` step that records `outcome` and
   `handoff_id` — which SHALL therefore also carry the returned sub-agent id.

   Without that, no code path carries the sub-agent id back at all: every dispatch record keeps
   `agent_id = null`, the `(session_id, agent_id)` join matches nothing, and the ledger reports
   100% of dispatched work as unattributed while appearing to function.

The 14 non-terminal phases SHALL be: `INIT`, `GATEKEEPER`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR` — exactly `agents_config.NON_TERMINAL_PHASES`, which is the authority. `GATEKEEPER` is dispatched as a judge sub-agent (autopilot SKILL.md step 1.5) and was omitted from an earlier draft of this list and of `dispatch-record.schema.json`; a ledger that claims to record every dispatch cannot silently drop one.

The `skills/autopilot/SKILL.md` orchestration prose SHALL dispatch the following 7 phases through the provider-neutral dispatch adapter when an adapter is available: `PLAN_ITERATE`, `PLAN_REVIEW`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `VALIDATE`, `VAL_REVIEW` (when enabled). For these phases the dispatch SHALL pass the provider-specific model ID and thinking level and SHALL fold the resolved `system_prompt` into the prompt text using the fixed separator `\n\n---\n\n`.

State-only phases (`INIT`, `PLAN`, `SUBMIT_PR`) SHALL still record `LoopState.phase_archetype` for their resolved archetype via a state-only resolver, even though they do not dispatch a phase sub-agent, and SHALL write a dispatch record with `agent_id = null` **and `record_kind = "state_only"`**.

`record_kind` is what keeps mismatch accounting honest. The usage-accounting requirement flags any
dispatch with no joined usage as `unattributed`, and that join is on `(session_id, agent_id)` where
SQL NULLs never match. A state-only record has a NULL `agent_id` *by design*, so without an
explicit exclusion these three phases would be reported as failures on every single run — the
mismatch report would be pure noise from its first day, and a real unattributed dispatch would be
indistinguishable from the permanent background. `/usage/mismatches` SHALL therefore consider only
records with `record_kind = "dispatched"`.

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

- **GIVEN** autopilot is running under provider `antigravity`
- **AND** a work package with `loc_estimate=250` is being processed
- **WHEN** autopilot enters the `IMPLEMENT` phase
- **THEN** the phase resolver SHALL extract `loc_estimate` from `state_dict` and pass it as a signal
- **AND** the resolved archetype SHALL be `"implementer"`
- **AND** the model tier SHALL escalate from `standard` to `premium`
- **AND** the provider-specific model SHALL be an antigravity model ID from the configured antigravity mapping

#### Scenario: Production autopilot run dispatches through provider adapter

- **GIVEN** a real autopilot run executing from `/autopilot <change-id>` against an available coordinator
- **AND** the active provider is `codex`
- **WHEN** the run reaches the `IMPLEMENT` phase
- **THEN** the SKILL.md dispatch block SHALL invoke the provider-neutral dispatch adapter
- **AND** the adapter SHALL receive a payload conforming to `contracts/phase-dispatch-contract.md`
- **AND** the payload's `model` SHALL be provider-specific for Codex
- **AND** the payload's `thinking` SHALL equal the resolved thinking level
- **AND** the prompt passed to the adapter SHALL begin with the resolved `system_prompt` followed by `\n\n---\n\n` followed by the per-phase task prompt
- **AND** after the adapter returns, `LoopState.phase_archetype` in `loop-state.json` SHALL equal `"implementer"`
- **AND** `LoopState.last_handoff_id` SHALL be updated to the `handoff_id` returned from the dispatched provider result

#### Scenario: Dispatch record written and patched

- **GIVEN** autopilot dispatches `IMPL_REVIEW` under provider `claude_code`
- **WHEN** the dispatch adapter returns sub-agent id `abc123`
- **THEN** a dispatch record SHALL exist in the coordinator with `phase = "IMPL_REVIEW"`, `intended_model`, `intended_thinking`, and `agent_id = "abc123"`
- **AND** `.phase-resolution-cache.json` SHALL contain the same `dispatch_id`

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
- The resolver SHALL still be called so that the archetype, system prompt, and thinking are known, and the dispatch record SHALL be written with `override_source = "env"` and the overridden `intended_model`.
- Unknown phase names in the override string SHALL be logged as warnings and ignored.
- Unknown model names SHALL pass through only to the selected provider adapter, which is responsible for provider-specific validation or failure reporting.

#### Scenario: Override forces a Codex model for a phase

- **GIVEN** `AUTOPILOT_PROVIDER=codex`
- **AND** `AUTOPILOT_PHASE_MODEL_OVERRIDE=PLAN=gpt-5.4`
- **WHEN** autopilot enters the `PLAN` phase
- **THEN** the dispatch model SHALL be `"gpt-5.4"`
- **AND** the resolved archetype SHALL remain `"architect"`
- **AND** the dispatch record SHALL have `override_source = "env"` and `archetype = "architect"`

## ADDED Requirements

### Requirement: Thinking Forwarded To Vendor Flags

When a provider declares `cli.thinking_flag` but the resolved `thinking` is null, the dispatcher SHALL omit the flag entirely rather than rendering the placeholder. D11 defines cases where thinking legitimately resolves to `None`; rendering it would put a literal `None` into vendor argv (e.g. `model_reasoning_effort=None`), which breaks the dispatch outright instead of degrading to the vendor default.

#### Scenario: Template declared but thinking is null

- **GIVEN** a provider whose `cli.thinking_flag` template is declared
- **AND** the resolved `thinking` for the phase is null
- **WHEN** the dispatcher builds the vendor argv
- **THEN** no thinking flag SHALL appear in the argv
- **AND** no warning SHALL be emitted, because this is a valid resolution rather than a missing template

The provider dispatch layer (`skills/autopilot/scripts/provider_dispatch.py` and
`skills/parallel-infrastructure/scripts/review_dispatcher.py`) SHALL translate the resolved
`thinking` level into the vendor's reasoning-effort mechanism using a per-provider template declared
in `agents.yaml` under `cli.thinking_flag` (for example `["-c", "model_reasoning_effort={thinking}"]`
for Codex, `["--reasoning-effort", "{thinking}"]` for Grok, and an effort-suffixed model id for
Antigravity). When a provider declares no template the dispatcher SHALL log a structured warning
`thinking_not_forwarded` once per dispatch and proceed. For the Claude harness `Agent(...)` path,
which exposes no thinking parameter, the dispatcher SHALL record the intended thinking in the
dispatch record so the ledger can compare it with the observed `effort`.

#### Scenario: Codex tiers dispatch with distinct reasoning effort

- **GIVEN** `codex.frontier.thinking = "xhigh"` and `codex.premium.thinking = "medium"`
- **WHEN** the same phase is dispatched once at each tier
- **THEN** the Codex argv SHALL contain `model_reasoning_effort=xhigh` for the first and `model_reasoning_effort=medium` for the second

#### Scenario: Provider without a template warns and proceeds

- **GIVEN** a provider whose `agents.yaml` entry has no `cli.thinking_flag`
- **WHEN** a phase with `thinking = "high"` is dispatched
- **THEN** the dispatcher SHALL emit a `thinking_not_forwarded` warning naming the provider
- **AND** the dispatch SHALL proceed with the model flag only

### Requirement: Review Dispatch Applies Archetype Model

`review_dispatcher.py` SHALL resolve the `reviewer` archetype for the active provider before
dispatching a review panel member and SHALL pass the resolved model and thinking to the adapter's
`dispatch(...)` call via `archetype_model` and `archetype_thinking`, so that the reviewer tier in
`archetypes.yaml` governs review-panel model selection instead of the `agents.yaml` default.

#### Scenario: Reviewer tier reaches the CLI

- **GIVEN** `reviewer.model = "premium"` and `codex.premium.model = "gpt-5.6-sol"`
- **WHEN** a Codex review panel member is dispatched
- **THEN** the adapter argv SHALL contain the Codex model flag followed by `gpt-5.6-sol`
- **AND** the review dispatch record SHALL carry `archetype = "reviewer"`
