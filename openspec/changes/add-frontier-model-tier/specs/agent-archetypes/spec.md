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
