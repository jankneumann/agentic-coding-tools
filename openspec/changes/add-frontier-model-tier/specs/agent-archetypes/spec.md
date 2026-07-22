# agent-archetypes — delta for add-frontier-model-tier

## ADDED Requirements

### Requirement: Frontier Model Tier

The system SHALL support an optional `frontier` model tier above `premium` in the provider
model map. Providers MAY define a `frontier` model; the base tiers (`premium`, `standard`,
`economy`) SHALL remain required for every provider. When an archetype resolves to
`frontier` for a provider that defines no `frontier` mapping, resolution SHALL fall back to
that provider's `premium` model rather than failing; resolution SHALL fail with a structured
error only when the `premium` mapping is also absent.

The provider model map contract SHALL live at `openspec/schemas/provider-model-map.schema.json`
(`schema_version: 2`), and contract tests SHALL resolve it from that stable path.

Tier entries SHALL be either a bare model-id string or an object pairing a model id with a
thinking/reasoning level (`{model, thinking}`), because thinking level materially shifts both
cost and capability — tiers are tuned for cost per successful task, not cost per token, and
the same model id MAY serve two tiers at different thinking levels. Resolution SHALL surface
the thinking level alongside the model id so dispatch adapters can translate it to
vendor-specific flags.

Tests SHALL derive expected models and thinking levels from the configured map
(`archetypes.yaml` / the default map) rather than asserting model-id literals, so tier tuning
does not invalidate tests.

#### Scenario: Archetype requests frontier from a provider that defines it

- **GIVEN** the `architect` archetype with `model: frontier`
- **WHEN** a planning phase resolves for provider `claude_code`
- **THEN** the resolved model SHALL be the provider's configured frontier model

#### Scenario: Frontier falls back to premium when unmapped

- **GIVEN** a provider whose `model_aliases` entry defines no `frontier` key
- **WHEN** an archetype with `model: frontier` resolves for that provider
- **THEN** the resolved model SHALL be that provider's `premium` model
- **AND** resolution SHALL NOT raise a provider model mapping error

#### Scenario: Frontier tier is optional in configuration

- **WHEN** `archetypes.yaml` `model_aliases` is validated
- **THEN** a provider entry without `frontier` SHALL validate
- **AND** a provider entry missing any base tier SHALL fail validation

#### Scenario: Tier entry pairs a model with a thinking level

- **GIVEN** a provider whose `frontier` and `premium` tiers name the same model id at
  different thinking levels
- **WHEN** each tier resolves for that provider
- **THEN** both SHALL resolve to that model id
- **AND** the resolved thinking levels SHALL differ, distinguishing the tiers
- **AND** a bare-string tier entry SHALL resolve with no thinking level
