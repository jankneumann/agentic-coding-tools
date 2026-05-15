## ADDED Requirements

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
- **AND** it SHALL discover Claude Code, Codex, and Gemini agents declared there
- **AND** it SHALL NOT require `~/.claude.json`

#### Scenario: Explicit config path wins

- **GIVEN** `AGENTS_YAML=/tmp/custom-agents.yaml` is set
- **WHEN** dispatch config discovery runs
- **THEN** it SHALL load the explicit file first
- **AND** it SHALL log the source of the loaded config

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, and Gemini/Jules so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `contracts/provider-model-map.schema.json`.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, and `gemini`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs

#### Scenario: Non-Claude provider rejects unmapped Claude alias

- **GIVEN** provider `codex`
- **AND** an archetype resolves to legacy alias `opus`
- **WHEN** no Codex mapping exists for that alias or tier
- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
- **AND** the error SHALL identify the missing provider model mapping
