## MODIFIED Requirements

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, and pi so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 2: provider key set closed to the five roster keys, all five required).

The `pi` provider SHALL resolve to OpenRouter model slugs, selected so the roster reaches models outside the subscription harnesses. The specific slug bound to each tier is configuration, not a spec requirement: it SHALL be changeable in `archetypes.yaml` and `agents.yaml` without a spec amendment.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, and `pi`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
- **AND** it SHALL NOT include an entry for `gemini`

#### Scenario: pi maps to OpenRouter slugs

- **WHEN** the `pi` provider entry is loaded
- **THEN** every tier value SHALL be an OpenRouter model slug in `<publisher>/<model>` form
- **AND** no tier value SHALL be required to name a particular publisher or model

#### Scenario: Non-Claude provider rejects unmapped Claude alias

- **GIVEN** provider `codex`
- **AND** an archetype resolves to legacy alias `opus`
- **WHEN** no Codex mapping exists for that alias or tier
- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
- **AND** the error SHALL identify the missing provider model mapping
