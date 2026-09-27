## MODIFIED Requirements

### Requirement: Archetype Resolution Delegates to Adaptive Router

When the adaptive-routing feature flag is on, archetype/phase model resolution SHALL delegate to
the model-routing resolver, passing the archetype tier, phase, and escalation signals as task
signals and the static resolution as the incumbent (catalog vendor of the provider, when known,
and the static model); when the flag is off or the resolver is unavailable, resolution SHALL use the existing
static tier mapping unchanged. When the resolver reports that the incumbent was retained,
resolution SHALL return the exact static resolution object.

#### Scenario: Flag off preserves static behavior

- **WHEN** `ROUTING_ADAPTIVE` is off and a phase resolves its archetype model
- **THEN** the result SHALL equal the pre-change static tier resolution

#### Scenario: Resolver unavailable preserves static behavior

- **WHEN** `ROUTING_ADAPTIVE` is on and the resolver is unavailable, errors, or times out
- **THEN** archetype/phase resolution SHALL equal the pre-change static tier resolution

#### Scenario: Escalation signals become task signals

- **WHEN** a phase resolves with escalation signals (complexity, write-dir count) and the flag is on
- **THEN** those signals SHALL be forwarded to the resolver as task-type inputs

#### Scenario: Static resolution is forwarded as the incumbent

- **WHEN** the flag is on and a phase resolves with a known provider
- **THEN** the request SHALL carry `incumbent = {vendor: <provider's catalog_vendor>, model: <static model>}`
- **AND** when the provider is unknown, the request SHALL carry `incumbent = {vendor: null, model: <static model>}`

#### Scenario: Retained incumbent returns the exact static object

- **WHEN** the flag is on and the resolver response has `retention.retained == true`
- **THEN** resolution SHALL return the identical static resolution object

#### Scenario: Empty catalog evidence changes no phase

- **WHEN** the flag is on and no catalog candidate has posterior samples or a positive benchmark prior
- **THEN** every archetype/phase resolution SHALL equal its static resolution
