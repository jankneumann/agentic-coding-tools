# agent-identity Specification

## Purpose
TBD - created by archiving change add-coordinator-profiles. Update Purpose after archive.
## Requirements
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

**MODIFIED**: `get_api_key_identities()` SHALL support resolving API keys from OpenBao when enabled.

- When OpenBao is enabled and an agent's `api_key` field references a `${VAR}` placeholder, the value SHALL be resolved from OpenBao instead of `.secrets.yaml`
- The output format (`{key: {agent_id, agent_type}}` JSON dict) SHALL remain identical
- When `COORDINATION_API_KEY_IDENTITIES` is set as an explicit env var, it SHALL still override agents.yaml (existing precedence preserved)

#### Scenario: API key resolved from OpenBao
- **WHEN** OpenBao is enabled (`BAO_ADDR` set)
- **AND** an agent's `api_key` is `${CODEX_KEY}` with `openbao_role_id` set
- **THEN** `get_api_key_identities()` SHALL resolve the key from OpenBao
- **AND** the identity map SHALL contain the resolved key mapped to the agent

#### Scenario: API key resolution falls back without OpenBao
- **WHEN** OpenBao is not enabled
- **AND** an agent's `api_key` is resolved from `.secrets.yaml`
- **THEN** `get_api_key_identities()` SHALL use the statically resolved key
- **AND** unresolved `${VAR}` placeholders SHALL be excluded from the identity map

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

Because seeding is additive, retiring a harness from `agents.yaml` SHALL NOT delete its previously seeded profile rows. Removal of orphaned profiles SHALL be an explicit operator action.

#### Scenario: Seed creates new profile
- **WHEN** `agents.yaml` defines `grok-local` with `profile: grok_local` and `trust_level: 3`
- **AND** no `grok_local` profile exists in the DB
- **THEN** a new `agent_profiles` row SHALL be inserted with the declared trust level and capabilities

#### Scenario: Seed updates existing profile
- **WHEN** `agents.yaml` declares `trust_level: 3` for a profile that exists with `trust_level: 2`
- **THEN** the DB row SHALL be updated to `trust_level: 3`

#### Scenario: Retired harness profile survives seeding
- **GIVEN** a `gemini_local` profile row exists from a prior seed
- **WHEN** `seed_profiles_from_config()` runs against an `agents.yaml` with no gemini entry
- **THEN** the `gemini_local` row SHALL remain in the table untouched
- **AND** no error SHALL be raised

### Requirement: OpenBao AppRole per Agent

The agent identity system SHALL support mapping each agent declaration in `agents.yaml` to an OpenBao AppRole, enabling per-agent credential scoping and automatic revocation.

- Each agent entry in `agents.yaml` MAY declare an `openbao_role_id` field
- When `openbao_role_id` is present and OpenBao is enabled, the agent SHALL authenticate to OpenBao using that AppRole
- AppRole policies SHALL grant each agent read access to the coordinator secrets path (shared `secret/data/coordinator` for MVP; per-agent sub-path scoping is a future enhancement)
- Agent tokens obtained via AppRole auth SHALL have a TTL configured via `BAO_TOKEN_TTL` (default: 1 hour, max: 24 hours)
- `BAO_TOKEN_TTL` SHALL be configurable per-agent via `agents.yaml` or globally via environment variable
- Token revocation relies on OpenBao's built-in TTL expiry: when the token TTL elapses without renewal, the token and its child leases are automatically revoked by OpenBao — no explicit coordinator action is required
- For early revocation (agent crash or explicit session end), the coordinator MAY call the OpenBao token revoke API, but this is a best-effort optimization, not a required behavior

#### Scenario: Agent authenticates via AppRole
- **WHEN** `agents.yaml` defines `codex-cloud` with `openbao_role_id: "codex-cloud"`
- **AND** OpenBao is enabled (`BAO_ADDR` set)
- **THEN** the agent identity system SHALL authenticate to OpenBao with the `codex-cloud` AppRole
- **AND** the resulting token SHALL only have access to secrets scoped by the `codex-cloud` policy

#### Scenario: Agent without openbao_role_id uses shared credentials
- **WHEN** `agents.yaml` defines `claude-code-local` without `openbao_role_id`
- **AND** OpenBao is enabled
- **THEN** the agent SHALL use the coordinator's shared OpenBao token for secret resolution
- **AND** no per-agent scoping SHALL be applied

#### Scenario: Agent token expires and credentials revoke
- **WHEN** an agent's OpenBao token TTL elapses without renewal
- **THEN** OpenBao SHALL automatically revoke the token
- **AND** any dynamic database credentials generated by that token SHALL become invalid
- **AND** no coordinator action SHALL be required for revocation

### Requirement: Dynamic Database Credentials per Agent

The agent identity system SHALL support per-agent dynamic PostgreSQL credentials via the OpenBao database secrets engine, replacing static shared database passwords.

- The OpenBao database secrets engine is considered "configured" when the `database/` mount is enabled in OpenBao AND the `coordinator-agent` role exists (both set up by `bao-seed.py --with-db-engine`)
- When the database secrets engine is configured, `POSTGRES_DSN` SHALL be resolved dynamically per agent
- Dynamic credentials SHALL have a configurable TTL (default: 1 hour) with max renewal (default: 24 hours)
- Each agent SHALL receive a unique PostgreSQL role, enabling per-agent audit in the database
- When the OpenBao database engine is not configured, `POSTGRES_DSN` SHALL continue to be resolved via static interpolation (existing behavior)

#### Scenario: Agent receives dynamic database credentials
- **WHEN** OpenBao database secrets engine is configured for PostgreSQL
- **AND** agent `codex-cloud` requests database access
- **THEN** OpenBao SHALL generate a unique PostgreSQL role (e.g., `v-codex-cloud-coord-abc123`)
- **AND** the `POSTGRES_DSN` for this agent SHALL use the generated credentials
- **AND** the credentials SHALL expire after the configured TTL

#### Scenario: Dynamic credential renewal
- **WHEN** an agent's database credential has less than 25% of its TTL remaining
- **AND** the agent session is still active
- **THEN** the profile loader SHALL renew the credential lease up to the max renewal period
- **AND** existing database connections using the credential SHALL remain valid during renewal

#### Scenario: Dynamic credential renewal exceeds max TTL
- **WHEN** an agent's database credential reaches the max renewal period (default: 24 hours)
- **AND** the agent session is still active
- **THEN** the lease renewal SHALL fail
- **AND** the system SHALL generate new credentials via the database secrets engine
- **AND** a warning SHALL be logged indicating credential rotation occurred

#### Scenario: Database engine not configured (fallback)
- **WHEN** OpenBao is enabled but the database secrets engine is not configured
- **THEN** `POSTGRES_DSN` SHALL be resolved via static `${DB_PASSWORD}` interpolation as before
- **AND** no dynamic credentials SHALL be generated

