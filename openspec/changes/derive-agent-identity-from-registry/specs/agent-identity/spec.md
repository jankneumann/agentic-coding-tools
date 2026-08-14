# agent-identity Delta — derive-agent-identity-from-registry

## MODIFIED Requirements

### Requirement: Declarative Agent Configuration

The coordinator SHALL treat `agents.yaml` as the single source of truth for agent identity,
trust levels, permissions, and API key mapping — for **every** agent, regardless of declared
transport. All runtime authorization state (identity map entries, `agent_profiles` rows,
policy tier inputs) SHALL be derived projections of this file, never independently authored.

- `agents.yaml` SHALL reside at `agent-coordinator/agents.yaml`
- Each agent entry SHALL declare: `type`, `profile` (matching `agent_profiles.name` in DB),
  `trust_level` (0–4 per the Unified Trust Scale), `transport` (`mcp` or `http`),
  `capabilities` (list), and `description`
- `transport` SHALL describe the agent's preferred channel only; it SHALL NOT gate whether
  the agent receives an identity or profile projection (MCP agents reach the HTTP API via
  the proxy fallback and are therefore HTTP principals)
- Agents MAY declare `api_key: ${VAR}` referencing a secret
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

#### Scenario: MCP-transport agent receives identity projection
- **WHEN** `agents.yaml` defines `grok-local` with `transport: mcp` and a resolvable `api_key`
- **THEN** `get_api_key_identities()` SHALL include the resolved key mapped to
  `{"agent_id": "grok-local", "agent_type": "grok"}`

### Requirement: API Key Identity Generation

`get_api_key_identities()` SHALL generate identity mappings for all agents with resolvable
API keys, regardless of transport, and SHALL support resolving API keys from OpenBao when
enabled.

- The identity map SHALL include every agent whose `api_key` resolves to a concrete value;
  the former restriction to `transport: "http"` agents is removed
- When OpenBao is enabled and an agent's `api_key` field references a `${VAR}` placeholder,
  the value SHALL be resolved from OpenBao instead of `.secrets.yaml`
- The output format (`{key: {agent_id, agent_type}}` JSON dict) SHALL remain identical
- When `COORDINATION_API_KEY_IDENTITIES` is set as an explicit env var, it SHALL still
  override agents.yaml (existing precedence preserved — this is also the rollback lever)
- Unresolved `${VAR}` placeholders SHALL be excluded from the identity map
- Duplicate resolved keys across agents SHALL be rejected at load time with an error
  identifying both agents (replacing the current last-writer-wins warning)

#### Scenario: Full-roster identity map
- **WHEN** `agents.yaml` declares five local and two remote agents, all with resolvable keys
- **THEN** `get_api_key_identities()` SHALL return seven entries

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

#### Scenario: Duplicate key rejected
- **WHEN** two agents' `api_key` fields resolve to the same value
- **THEN** identity generation SHALL fail with an error naming both agents

## REMOVED Requirements

### Requirement: Profile Seeding from Config

**Reason**: Replaced by the ADDED "Registry Profile Sync" requirement. The explicit,
additive-only seeding design was never implemented in the five months since it was specified
(across two shipped changes), and its additive-only posture preserves authorization state for
retired principals. The replacement reverses both properties deliberately: sync is automatic
at startup and orphaned profiles are disabled (see design D1/D2 and the Gate 1 selection in
`proposal.md`).

**Migration**: No code migrates (the function never existed). Existing hand-seeded rows are
adopted by the first startup sync: matching rows are reconciled, orphans are disabled with an
audit event.

## ADDED Requirements

### Requirement: Registry Profile Sync

The coordinator SHALL synchronize the `agent_profiles` table from `agents.yaml` at startup,
treating the table as a materialized projection of the registry.

- On startup, for each registry agent, the coordinator SHALL upsert an `agent_profiles` row
  keyed by the declared `profile` name, carrying `agent_type`, `trust_level`, and
  `allowed_operations` derived from the entry's `capabilities`
- Enabled profile rows whose name is not declared by any registry entry SHALL be **disabled**
  (`enabled = false`), never deleted; disabling SHALL emit an audit event naming the row
- The sync SHALL be idempotent and safe under concurrent startup of multiple API workers
- The sync SHALL be guarded by `PROFILE_SYNC_ENABLED` (default: enabled); disabling it
  restores pre-sync runtime behavior (rollback lever)
- Sync failures at startup SHALL fail coordinator boot loudly; they SHALL NOT degrade to
  the previous silent state

#### Scenario: Sync creates missing profile
- **WHEN** `agents.yaml` defines `grok-local` with `profile: grok_local` and `trust_level: 3`
- **AND** no `grok_local` profile exists in the DB
- **THEN** startup sync SHALL insert the row with trust_level 3 and derived allowed_operations

#### Scenario: Sync updates drifted profile
- **WHEN** `agents.yaml` declares `trust_level: 3` for a profile stored with `trust_level: 2`
- **THEN** startup sync SHALL update the row to `trust_level: 3`
- **AND** an audit event SHALL record the change

#### Scenario: Orphan profile disabled with audit trail
- **GIVEN** an enabled `gemini_local` profile row from a prior seed
- **WHEN** startup sync runs against an `agents.yaml` with no gemini entry
- **THEN** the row SHALL be set `enabled = false` and retained
- **AND** an audit event SHALL record the disabling

#### Scenario: Sync disabled via flag
- **WHEN** `PROFILE_SYNC_ENABLED=false`
- **THEN** startup SHALL perform no profile writes
- **AND** a warning SHALL be logged that the registry projection is not enforced

### Requirement: Unified Trust Scale

The system SHALL define the agent trust scale exactly once, as the 0–4 scale already named
by the `agent-coordinator` spec (0 Untrusted, 1 Limited, 2 Standard, 3 Elevated, 4 Admin),
in a single Python module consumed by every validator and enforcement point.

- The `agents.yaml` JSON schema bounds for `trust_level` SHALL derive from this module
  (replacing the divergent 1–5 range)
- The `agent_profiles` CHECK constraint SHALL match the same bounds
- Policy-engine action-tier thresholds (read/write/admin) SHALL reference named levels from
  this module rather than integer literals

#### Scenario: Out-of-scale registry value rejected
- **WHEN** an `agents.yaml` entry declares `trust_level: 5`
- **THEN** schema validation SHALL fail, naming the valid range

#### Scenario: Single definition consumed everywhere
- **WHEN** the trust-scale module's bounds are compared against the YAML schema, the DB
  constraint, and the policy-engine thresholds in tests
- **THEN** all three SHALL be derived from (or asserted equal to) the module's definition

### Requirement: Registry Projection Invariant

CI SHALL enforce that every agent declared in `agents.yaml` fully materializes its runtime
projections, so that a half-onboarded harness is a test failure rather than a runtime
surprise.

- A test SHALL assert, for every registry agent: (a) profile sync produces an enabled
  `agent_profiles` row with the declared trust level, (b) an identity map entry exists or
  the agent's key is explicitly declared unresolvable in the test environment, (c) the
  `profile` name referenced by the entry resolves after sync
- The test SHALL assert that no enabled profile rows exist that are not declared by the
  registry (post-sync)
- The test SHALL fail when a new harness is added to `agents.yaml` without the projections
  materializing

#### Scenario: Half-onboarded harness caught in CI
- **WHEN** a new agent entry is added referencing a profile the sync cannot derive
  (e.g., malformed capabilities)
- **THEN** the registry-projection test SHALL fail identifying the agent and the missing
  projection

#### Scenario: Ghost profile caught in CI
- **WHEN** a migration seeds an enabled profile row for a type absent from the registry
- **THEN** the registry-projection test SHALL fail identifying the orphan row
