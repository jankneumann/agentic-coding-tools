## MODIFIED Requirements

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, and pi so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 2). The provider key set SHALL be closed to the five roster keys, all five required, plus two optional keys: `local` and `openrouter`. `openrouter` holds the model aliases of the endpoint-only `openrouter-review` lane, and is not a roster vendor.

The `pi` provider SHALL resolve to OpenRouter model slugs, and its default model SHALL be `qwen/qwen3-coder`, selected so the roster reaches models outside the subscription harnesses.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, and `pi`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
- **AND** it SHALL NOT include an entry for `gemini`

#### Scenario: Optional provider keys are allowed but not required

- **WHEN** a provider model map carries an `openrouter` entry or a `local` entry
- **THEN** it SHALL validate, provided the entry defines `premium`, `standard`, and `economy`
- **AND** a map without either entry SHALL also validate
- **AND** a map with any other provider key SHALL fail validation

#### Scenario: pi maps to OpenRouter slugs

- **WHEN** the `pi` provider entry is loaded
- **THEN** every tier value SHALL be an OpenRouter model slug in `<publisher>/<model>` form
- **AND** the `standard` tier SHALL be `qwen/qwen3-coder`

#### Scenario: Non-Claude provider rejects unmapped Claude alias

- **GIVEN** provider `codex`
- **AND** an archetype resolves to legacy alias `opus`
- **WHEN** no Codex mapping exists for that alias or tier
- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
- **AND** the error SHALL identify the missing provider model mapping
