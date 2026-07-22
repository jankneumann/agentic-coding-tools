# configuration — delta for add-agy-grok-pi-harnesses

Retargets provider dispatch discovery and the provider model map from the retired `gemini`
harness to `antigravity`, `grok`, and `pi`.

## MODIFIED Requirements

### Requirement: Provider Dispatch Configuration Discovery

The system SHALL discover provider dispatch configuration without depending on Claude-specific configuration files.

Discovery order SHALL be:

1. Explicit environment or CLI path to dispatch config.
2. HTTP coordinator dispatch-config endpoint.
3. Local repo `agent-coordinator/agents.yaml`.
4. Provider-native config discovery.
5. Empty config with structured warning.

#### Scenario: Local agents.yaml fallback

- **GIVEN** HTTP coordinator dispatch-config discovery is unavailable
- **AND** `agent-coordinator/agents.yaml` exists in the repository
- **WHEN** `ReviewOrchestrator.from_coordinator()` or equivalent config discovery runs
- **THEN** it SHALL load dispatch config from the local `agents.yaml`
- **AND** it SHALL discover Claude Code, Codex, antigravity, grok, and pi agents declared there
- **AND** it SHALL NOT discover any `gemini` agent, because no such entry remains
- **AND** it SHALL NOT require `~/.claude.json`

#### Scenario: Explicit config path wins

- **GIVEN** `AGENTS_YAML=/tmp/custom-agents.yaml` is set
- **WHEN** dispatch config discovery runs
- **THEN** it SHALL load the explicit file first
- **AND** it SHALL log the source of the loaded config

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, and pi so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 2: provider key set closed to the five roster keys, all five required).

The `pi` provider SHALL resolve to OpenRouter model slugs, and its default model SHALL be `qwen/qwen3-coder`, selected so the roster reaches models outside the subscription harnesses.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, and `pi`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
- **AND** it SHALL NOT include an entry for `gemini`

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
