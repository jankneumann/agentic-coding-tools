# agent-archetypes Specification (delta)

## ADDED Requirements

### Requirement: Archetype Resolution Delegates to Adaptive Router

When the adaptive-routing feature flag is on, archetype/phase model resolution SHALL delegate to
the model-routing resolver, passing the archetype tier, phase, and escalation signals as task
signals; when the flag is off or the resolver is unavailable, resolution SHALL preserve the
existing effective tier behavior by resolving the static model chain owned by `archetypes.yaml`
for the selected agent harness and dispatch kind.

#### Scenario: Flag off preserves static behavior

- **WHEN** `ROUTING_ADAPTIVE` is off and a phase resolves its archetype model
- **THEN** the selected `ModelSpec` chain and capacity order SHALL be behaviorally equivalent
  to the characterized pre-migration static resolution

#### Scenario: Escalation signals become task signals

- **WHEN** a phase resolves with escalation signals (complexity, write-dir count) and the flag is on
- **THEN** those signals SHALL be forwarded to the resolver as task-type inputs

### Requirement: Endpoint Kind in Agent Registry

The agent registry schema (`agents.yaml`) SHALL support `endpoint_kind` and `base_url` fields so
local and OpenRouter-served endpoints are declarable alongside CLI and SDK dispatch modes, with
config validation rejecting unknown kinds.

#### Scenario: Local endpoint declared in registry

- **WHEN** an agent entry declares `endpoint_kind: local` with a `base_url`
- **THEN** config loading SHALL accept it and register the endpoint for catalog health probing

### Requirement: Static Model Policy Has One Authority

`agents.yaml` SHALL describe agent identity, eligibility, transport, credentials, endpoint
metadata, and harness invocation mechanics only. It SHALL reject concrete `model` and
`model_fallbacks` selections under both `cli` and `sdk`, while retaining `model_flag` as
the harness-specific syntax used to inject a separately resolved model.

`archetypes.yaml` SHALL be the sole curated static source of concrete primary models, thinking
levels, and ordered capacity fallbacks. For every dispatch-capable agent entry, every configured
dispatch kind, and every archetype that agent declares, the composition
task/phase -> archetype -> tier -> agent harness + dispatch kind SHALL resolve to a non-empty
ordered `ModelSpec` chain before dispatch. Dispatch-capable agents SHALL declare a non-empty
archetype list. Cross-file validation SHALL reject missing routes, orphan harness routes, concrete
model IDs in Python defaults, and model flags whose values are embedded in dispatch-mode args.

#### Scenario: Agent registry rejects concrete model policy

- **WHEN** a CLI or SDK entry in `agents.yaml` declares `model` or `model_fallbacks`
- **THEN** configuration validation SHALL fail and identify the forbidden field
- **AND** `model_flag` without a model value SHALL remain valid invocation metadata

#### Scenario: Legacy model values are migrated before removal

- **GIVEN** an existing CLI or SDK entry has a primary model and ordered `model_fallbacks`
- **AND** task 4.7 has characterized its effective selection and retry order
- **WHEN** the harness-aware `archetypes.yaml` route is seeded
- **THEN** it SHALL preserve the same ordered `ModelSpec` behavior before any legacy field is removed
- **AND** removal SHALL be blocked when the parity characterization fails

#### Scenario: Every eligible harness and task resolves

- **WHEN** `agents.yaml` and `archetypes.yaml` are loaded together
- **THEN** every eligible `(agent_id, dispatch_kind, archetype)` combination SHALL resolve its
  archetype tier to a non-empty ordered model chain
- **AND** a missing or orphan mapping SHALL fail before any subprocess or SDK request

#### Scenario: Static fallback never uses an ambient harness default

- **WHEN** adaptive routing is disabled, times out, or fails
- **THEN** dispatch SHALL use the ordered static chain resolved from `archetypes.yaml`
- **AND** it SHALL NOT use an implicit CLI default, SDK default, or Python model literal

## MODIFIED Requirements

### Requirement: Fallback Chain Integration

Archetype model selection SHALL resolve one ordered `ModelSpec` chain from `archetypes.yaml`
for the active agent harness, dispatch kind, and task-selected tier. Before adaptive resolution,
the caller SHALL supply that route's `agent_id` and `dispatch_kind`. If adaptive routing selects
a candidate, it MAY replace only the primary `ModelSpec`; the effective chain SHALL contain the
adaptive selection followed by the static route with the selected model removed to avoid a
duplicate attempt. The same effective chain SHALL be passed to synchronous CLI, asynchronous CLI,
and SDK dispatch. Capacity errors SHALL advance only through those static capacity fallbacks;
ranked adaptive alternatives SHALL require a separate routing decision, as SHALL changing
providers or agent harnesses.

The resolution order SHALL be:

1. Task/phase selects an archetype and logical tier.
2. Agent harness plus dispatch kind resolves the tier to its complete static `ModelSpec` chain.
3. Adaptive routing may replace the primary; static entries other than that model become fallbacks.
4. Capacity errors try only the effective chain's ordered `capacity_fallbacks`.

#### Scenario: Archetype model exhausted falls back inside the selected route

- **WHEN** a Codex agent route resolves `reviewer` to a primary model plus ordered fallbacks
- **AND** the primary model dispatch returns an `ErrorClass.CAPACITY` error
- **THEN** the dispatcher SHALL try the next model in the resolved `archetypes.yaml` chain
- **AND** it SHALL NOT change provider, harness, dispatch kind, or archetype unless the router
  makes a separate selection

#### Scenario: Adaptive primary retains the selected route's static fallbacks

- **GIVEN** a harness route resolves static chain `[A, B, C]`
- **WHEN** adaptive routing selects model `X` for that same harness and dispatch kind
- **THEN** the effective chain SHALL be `[X, A, B, C]`
- **AND** if `X` equals a static entry it SHALL appear only once
- **AND** ranked adaptive alternatives SHALL NOT be consumed as capacity retries

#### Scenario: Missing SDK route fails before invocation

- **WHEN** an agent declares SDK dispatch but its selected tier has no SDK model chain
- **THEN** configuration SHALL fail before the SDK method is called
- **AND** the system SHALL NOT invent an SDK model default
