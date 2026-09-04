# agent-identity — delta for extend-coordinator-keys-to-new-harnesses

Keys the whole roster: coordinator credentials are declared per agent regardless of
transport, and every derivation that consumes them follows the credential rather than
the transport.

## MODIFIED Requirements

### Requirement: Declarative Agent Configuration

The coordinator SHALL support a declarative `agents.yaml` file as the single source of truth for agent identity, trust levels, permissions, and API key mapping.

- `agents.yaml` SHALL reside at `agent-coordinator/agents.yaml`
- Each agent entry SHALL declare: `type`, `profile` (matching `agent_profiles.name` in DB), `trust_level`, `transport` (`mcp` or `http`), `capabilities` (list), and `description`
- Any agent MAY declare `api_key: ${VAR}` referencing a secret, whatever its `transport`. The `api_key` is the agent's coordinator credential (presented as `X-API-Key`), distinct from the vendor model credential named in `sdk.api_key_env`
- Each declared `api_key` SHALL reference a distinct variable — two agents sharing one credential collapse into a single identity
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

#### Scenario: Local harness declares a coordinator key
- **WHEN** `agents.yaml` defines `grok-local` with `transport: mcp` and `api_key: ${GROK_LOCAL_API_KEY}`
- **THEN** the entry SHALL validate
- **AND** the resolved key SHALL be available for identity generation

### Requirement: API Key Identity Generation

`get_api_key_identities()` SHALL generate `COORDINATION_API_KEY_IDENTITIES` from every agent that declares an `api_key`, and SHALL support resolving those keys from OpenBao when enabled.

- Identity rows SHALL be derived from the presence of an `api_key`, NOT from `transport`. A `transport: mcp` agent still authenticates over HTTP — through the session hooks (`register_agent`, `report_status`, `precompact_handoff`), through `http_proxy` when the local database is unreachable, and for all coordination calls when the coordinator is hosted rather than run as a local MCP server
- When OpenBao is enabled and an agent's `api_key` field references a `${VAR}` placeholder, the value SHALL be resolved from OpenBao instead of `.secrets.yaml`
- The output format (`{key: {agent_id, agent_type}}` JSON dict) SHALL remain identical
- When `COORDINATION_API_KEY_IDENTITIES` is set as an explicit env var, it SHALL still override agents.yaml (existing precedence preserved)

#### Scenario: Local harness receives an identity row
- **WHEN** `grok-local` (`transport: mcp`) declares a resolved `api_key`
- **THEN** `get_api_key_identities()` SHALL include that key mapped to `{"agent_id": "grok-local", "agent_type": "grok"}`

#### Scenario: Agent without a key is excluded
- **WHEN** an agent declares no `api_key`
- **THEN** it SHALL contribute no identity row, whatever its transport

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

## ADDED Requirements

### Requirement: Harness Key Coverage

Every harness in the shipped roster SHALL carry its own coordinator key, covering the
locations that harness runs in, and every derivation over those credentials SHALL
select on the credential rather than on transport.

- `claude_code`, `codex`, and `grok` SHALL be keyed in both locations (local and remote)
- `antigravity` and `pi` SHALL be keyed local-only; no remote entry SHALL exist for them
- AppRole creation (`bao_seed.py`) SHALL select agents by the presence of `api_key`, so the
  AppRole set and the identity map cover the same agents
- A remote entry MAY omit `cli` when its dispatch shape has not been verified against the
  real CLI; such an entry provides identity and credential only

#### Scenario: Roster is fully keyed
- **WHEN** `agents.yaml` is loaded
- **THEN** every agent entry SHALL declare an `api_key`
- **AND** no two entries SHALL reference the same key variable

#### Scenario: AppRoles follow the credential
- **WHEN** `seed_approles()` runs against an `agents.yaml` where `grok-local` declares an `api_key` and `transport: mcp`
- **THEN** an AppRole SHALL be created for `grok-local`

#### Scenario: Agent without a key gets no AppRole
- **WHEN** `seed_approles()` runs against an `agents.yaml` entry that declares no `api_key`
- **THEN** no AppRole SHALL be created for it, whatever its transport
