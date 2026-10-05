## MODIFIED Requirements

### Requirement: Archetype Resolution Delegates to Adaptive Router

When the adaptive-routing feature flag is on, archetype/phase model resolution SHALL delegate to
the model-routing resolver, passing the archetype tier, phase, and escalation signals as task
signals and the static resolution as the incumbent (catalog vendor of the provider, when known,
and the static model); when the flag is off or the resolver is unavailable, resolution SHALL use the existing
static tier mapping unchanged. When the resolver reports that the incumbent was retained,
resolution SHALL return the exact static resolution object. When no provider is given, the
default provider SHALL be resolved before archetype resolution, so the incumbent names a concrete
model. A routed selection that changes the provider SHALL be dispatched to that provider; no
dispatch path SHALL pair a routed model with a different provider's runner.

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

#### Scenario: Provider-less dispatch resolves its default provider first

- **WHEN** a phase is dispatched with no explicit provider and no `AUTOPILOT_PROVIDER` or `AGENT_TYPE` in the environment
- **THEN** the default provider (`claude_code`) SHALL be applied before archetype resolution
- **AND** the incumbent SHALL name that provider's concrete model, not a tier alias

#### Scenario: Dispatch honors the routed provider

- **WHEN** resolution returns a provider different from the caller's (a routed challenger or a configured fallback)
- **THEN** every dispatch path SHALL send the work to that provider's runner with the routed model
- **AND** no dispatch SHALL pair the routed model with the caller's original provider

#### Scenario: Retained incumbent returns the exact static object

- **WHEN** the flag is on and the resolver response has `retention.retained == true`
- **THEN** resolution SHALL return the identical static resolution object

#### Scenario: Empty catalog evidence changes no phase

- **WHEN** the flag is on, no catalog candidate has posterior samples or a positive benchmark prior, and every incumbent is feasible or no `fallback.vendor_order` is configured
- **THEN** every archetype/phase resolution SHALL equal its static resolution
