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
dispatch path SHALL pair a routed model with a different provider's runner, and a runner that
cannot serve the routed provider SHALL fail rather than substitute its own. A `local` lane SHALL
advertise only archetypes in `LOCAL_TRUSTED_ARCHETYPES`, so the resolver never selects `local`
for an untrusted archetype, and resolution SHALL guard the routed provider with the same
boundary the static path applies.

#### Scenario: Flag off preserves static behavior

- **WHEN** `ROUTING_ADAPTIVE` is off and a phase resolves its archetype model
- **THEN** the result SHALL equal the pre-change static tier resolution for a caller with a provider
- **AND** for a provider-less caller it SHALL equal the static tier resolution under the default provider (`claude_code`): same provider as before, the tier's concrete alias as the model

#### Scenario: Resolver unavailable preserves static behavior

- **WHEN** `ROUTING_ADAPTIVE` is on and the resolver is unavailable, errors, or times out
- **THEN** archetype/phase resolution SHALL equal the pre-change static tier resolution for a caller with a provider
- **AND** for a provider-less caller it SHALL equal the static tier resolution under the default provider (`claude_code`): same provider as before, the tier's concrete alias as the model

#### Scenario: Escalation signals become task signals

- **WHEN** a phase resolves with escalation signals (complexity, write-dir count) and the flag is on
- **THEN** those signals SHALL be forwarded to the resolver as task-type inputs

#### Scenario: Static resolution is forwarded as the incumbent

- **WHEN** the flag is on and a phase resolves with a known provider
- **THEN** the request SHALL carry `incumbent = {vendor: <provider's catalog_vendor>, model: <static model>}`
- **AND** when the provider is unknown, the request SHALL carry `incumbent = {vendor: null, model: <static model>}`

#### Scenario: Provider-less dispatch resolves its default provider first

- **WHEN** a phase is dispatched with no explicit provider and no `AUTOPILOT_PROVIDER` or `AGENT_TYPE` in the environment (or the variable is whitespace only)
- **THEN** the default provider (`claude_code`) SHALL be applied before archetype resolution
- **AND** the incumbent SHALL name that provider's concrete model (the tier's alias, e.g. `standard` → `sonnet`), not a tier alias
- **AND** with the flag off, or with the incumbent retained, the dispatched provider SHALL equal the pre-change provider and the dispatched model SHALL be that provider's concrete alias of the pre-change tier

#### Scenario: Dispatch honors the routed provider

- **WHEN** resolution returns a provider different from the caller's (a routed challenger or a configured fallback), whether the caller's provider came from an explicit argument or the environment
- **THEN** `run_phase_subagent` SHALL pass that provider to its runner as `options["provider"]`, `build_phase_dispatch_kwargs` SHALL emit it as `provider`, and `smoke_provider_dispatch` SHALL pair it with the routed model
- **AND** no dispatch SHALL pair the routed model with the caller's original provider
- **AND** `smoke_provider_dispatch` SHALL apply its Claude-alias and `local` trust-boundary checks to the routed provider and report both `provider` (the caller's) and `resolved_provider`

#### Scenario: Runner cannot serve the routed provider

- **WHEN** `options["provider"]` names a provider the runner cannot dispatch to
- **THEN** the runner SHALL raise `UnservableProviderError`, and `run_phase_subagent` SHALL treat the attempt as failed under its existing retry budget and then raise `PhaseEscalationError`
- **AND** the runner SHALL NOT invoke the routed model under its own provider

#### Scenario: Retained incumbent returns the exact static object

- **WHEN** the flag is on and the resolver response has `retention.retained == true`
- **THEN** resolution SHALL return the identical static resolution object

#### Scenario: Routed selection onto the local provider respects the trust boundary

- **WHEN** the flag is on, a `local` lane is registered, and the phase's archetype is not in `LOCAL_TRUSTED_ARCHETYPES`
- **THEN** the lane SHALL be excluded by the resolver with `lane:archetype-ineligible`, so the persisted decision never selects `local` for that archetype
- **AND** if a response nevertheless names `local` as the routed provider (by `assignment.vendor_type` or by catalog-vendor mapping), resolution SHALL return a resolution equal to the static one plus a reason naming the refusal (`adaptive routing refused: provider=local outside LOCAL_TRUSTED_ARCHETYPES (archetype=<name>)`) and log a warning
- **AND** for an archetype in `LOCAL_TRUSTED_ARCHETYPES` the `local` selection SHALL be returned as routed

#### Scenario: Empty catalog evidence changes no phase

- **WHEN** the flag is on, no catalog candidate has posterior samples or a positive benchmark prior, and the configured-fallback scenario of `model-routing` does not apply to any phase (every incumbent is feasible, or no `fallback.vendor_order` is configured, or the incumbent's exclusion is permanent, or no candidate is eligible)
- **THEN** every archetype/phase resolution SHALL equal its static resolution
