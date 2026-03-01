# Delta Spec: Agent Identity — Declarative Agent Configuration

## ADDED Requirements

### Requirement: Declarative Agent Configuration

The coordinator SHALL support a declarative `agents.yaml` file as the single source of truth for agent identity, trust levels, permissions, and API key mapping.

- `agents.yaml` SHALL reside at `agent-coordinator/agents.yaml`
- Each agent entry SHALL declare: `type`, `profile` (matching `agent_profiles.name` in DB), `trust_level`, `transport` (`mcp` or `http`), `capabilities` (list), and `description`
- HTTP agents MAY declare `api_key: ${VAR}` referencing a secret
- The file SHALL be validated against a JSON schema (following the `teams.py` pattern)
- Duplicate agent names SHALL be rejected

#### Scenario: agents.yaml loads and validates
- **WHEN** `agents.yaml` exists with valid entries
- **THEN** the config SHALL parse all agent definitions
- **AND** each agent SHALL be accessible via `get_agent_config(agent_id)`

#### Scenario: Duplicate agent name rejected
- **WHEN** `agents.yaml` contains two entries with the same name
- **THEN** a `ValueError` SHALL be raised identifying the duplicate

#### Scenario: agents.yaml missing (graceful)
- **WHEN** `agents.yaml` does not exist
- **THEN** the system SHALL fall back to env-var-based identity (`AGENT_ID`, `AGENT_TYPE`)
- **AND** no error SHALL be raised

### Requirement: API Key Identity Generation

The agents config SHALL generate `COORDINATION_API_KEY_IDENTITIES` from HTTP agent definitions.

- `get_api_key_identities()` SHALL collect all agents with `transport: http` and a resolved `api_key`
- The output SHALL be a JSON dict mapping API key values to `{"agent_id": ..., "agent_type": ...}`
- `ApiConfig.from_env()` SHALL auto-populate `api_key_identities` from `agents.yaml` when no explicit `COORDINATION_API_KEY_IDENTITIES` env var is set

#### Scenario: API key identities generated from agents.yaml
- **WHEN** agents.yaml defines `codex-cloud` with `transport: http` and `api_key: ${CODEX_API_KEY}`
- **AND** `.secrets.yaml` contains `CODEX_API_KEY: "key123"`
- **THEN** `get_api_key_identities()` SHALL return `{"key123": {"agent_id": "codex-cloud", "agent_type": "codex"}}`

#### Scenario: Explicit env var overrides agents.yaml
- **WHEN** `COORDINATION_API_KEY_IDENTITIES` is set as an environment variable
- **THEN** the env var value SHALL be used instead of generating from agents.yaml

### Requirement: MCP Environment Generation

The agents config SHALL generate MCP registration environment variables for local agents.

- `get_mcp_env(agent_id)` SHALL return a dict of environment variables needed for MCP server registration
- The dict SHALL include `AGENT_ID`, `AGENT_TYPE`, and database connection settings from the active profile

#### Scenario: MCP env generated for local agent
- **WHEN** `get_mcp_env("claude-code-local")` is called
- **AND** the agent is defined with `transport: mcp` and `type: claude_code`
- **THEN** the result SHALL include `{"AGENT_ID": "claude-code-local", "AGENT_TYPE": "claude_code", ...}`

### Requirement: Profile Seeding from Config

The agents config SHALL optionally seed the `agent_profiles` database table from YAML definitions.

- `seed_profiles_from_config()` SHALL insert or update profiles matching `agents.yaml` entries
- Existing profiles not in `agents.yaml` SHALL NOT be deleted (additive only)
- Seeding SHALL be an explicit action invoked by the setup-coordinator skill, NOT automatic on startup

#### Scenario: Seed creates new profile
- **WHEN** `agents.yaml` defines `gemini-cloud` with `profile: gemini_cloud_worker` and `trust_level: 2`
- **AND** no `gemini_cloud_worker` profile exists in the DB
- **THEN** a new `agent_profiles` row SHALL be inserted with the declared trust level and capabilities

#### Scenario: Seed updates existing profile
- **WHEN** `agents.yaml` declares `trust_level: 3` for a profile that exists with `trust_level: 2`
- **THEN** the DB row SHALL be updated to `trust_level: 3`
