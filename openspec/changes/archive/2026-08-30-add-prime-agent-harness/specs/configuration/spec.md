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
- **AND** it SHALL discover Claude Code, Codex, antigravity, grok, pi, and prime agents declared there
- **AND** it SHALL NOT discover any `gemini` agent, because no such entry remains
- **AND** it SHALL NOT require `~/.claude.json`

#### Scenario: Explicit config path wins

- **GIVEN** `AGENTS_YAML=/tmp/custom-agents.yaml` is set
- **WHEN** dispatch config discovery runs
- **THEN** it SHALL load the explicit file first
- **AND** it SHALL log the source of the loaded config

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, pi, and prime so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 3: provider key set closed to the six roster keys, all six required).

The `pi` provider SHALL resolve to OpenRouter model slugs, and its default model SHALL be `qwen/qwen3-coder`, selected so the roster reaches models outside the subscription harnesses.

The `prime` provider SHALL resolve to Prime Inference model slugs and SHALL NOT include Anthropic model IDs: Claude models are reserved to the `claude_code` subscription harness, and prime-agent's Anthropic OAuth path is metered rather than subscription-backed. Tier models for `prime` SHALL be selected to minimize underlying-model overlap with the `pi` tiers, so vendor diversity implies training-distribution diversity.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, `pi`, and `prime`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
- **AND** it SHALL NOT include an entry for `gemini`

#### Scenario: pi maps to OpenRouter slugs

- **WHEN** the `pi` provider entry is loaded
- **THEN** every tier value SHALL be an OpenRouter model slug in `<publisher>/<model>` form
- **AND** the `standard` tier SHALL be `qwen/qwen3-coder`

#### Scenario: prime maps to non-Anthropic Prime Inference slugs

- **WHEN** the `prime` provider entry is loaded
- **THEN** every tier value SHALL be a model slug available on Prime Inference
- **AND** no tier value SHALL be an Anthropic model ID

#### Scenario: prime and pi are distinct providers

- **WHEN** dispatch configuration is loaded with both `pi` and `prime` entries
- **THEN** the two SHALL resolve to distinct providers with distinct `cli.command` values
- **AND** no roster gate or fixture SHALL match one vendor key via an unanchored substring of the other

#### Scenario: Non-Claude provider rejects unmapped Claude alias

- **GIVEN** provider `codex`
- **AND** an archetype resolves to legacy alias `opus`
- **WHEN** no Codex mapping exists for that alias or tier
- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
- **AND** the error SHALL identify the missing provider model mapping

## ADDED Requirements

### Requirement: CLI Dispatch Cleanup Configuration

Provider dispatch configuration SHALL support an optional CLI cleanup object with a
non-empty argument vector and a bounded timeout. The coordinator SHALL preserve this
object losslessly from `agents.yaml` through the canonical parser and the shared
HTTP/MCP dispatch-config projection. Configurations that omit cleanup SHALL retain
their existing behavior.

Cleanup arguments SHALL be data, not shell syntax: consumers SHALL append them to the
configured CLI command and execute with shell interpretation disabled.

#### Scenario: Cleanup configuration round-trips through every discovery path

- **GIVEN** an agent CLI config declares `cleanup.args: ["shutdown"]`
- **AND** `cleanup.timeout_seconds: 10`
- **WHEN** the config is loaded locally or returned by the HTTP or MCP dispatch-config endpoint
- **THEN** the consumer SHALL receive the same argument vector and timeout
- **AND** no parser or serializer SHALL rename, flatten, or drop either value

#### Scenario: Cleanup configuration is optional and strictly typed

- **WHEN** an existing agent config omits `cleanup`
- **THEN** loading and projecting that config SHALL succeed without adding a cleanup command
- **AND** a scalar cleanup value, an empty argument vector, or an out-of-range timeout SHALL fail schema validation before dispatch
