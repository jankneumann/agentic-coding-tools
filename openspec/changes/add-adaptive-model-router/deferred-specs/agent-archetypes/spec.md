# agent-archetypes Specification (delta)

## ADDED Requirements

### Requirement: Archetype Resolution Delegates to Adaptive Router

When the adaptive-routing feature flag is on, archetype/phase model resolution SHALL delegate to
the model-routing resolver, passing the archetype tier, phase, and escalation signals as task
signals; when the flag is off or the resolver is unavailable, resolution SHALL use the existing
static tier mapping unchanged.

#### Scenario: Flag off preserves static behavior

- **WHEN** `ROUTING_ADAPTIVE` is off and a phase resolves its archetype model
- **THEN** the result SHALL equal the pre-change static tier resolution

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
