# agent-identity Specification

## Purpose
TBD - created by archiving change add-coordinator-profiles. Update Purpose after archive.
## Requirements
### Requirement: Declarative Agent Configuration

`agent-coordinator/agents.yaml` SHALL remain the canonical source for every agent identity, regardless of transport. Every keyed agent SHALL declare an `api_key` placeholder and an explicit `vendor_credentials` list of canonical vendor identifiers; an empty list SHALL mean no vendor credential access. The schema SHALL reject unknown vendors, duplicate list members, duplicate agent names, and `openbao_role_id` overrides. An agent's `policy_vendor`, `catalog_vendor`, transport, CLI, or SDK configuration SHALL NOT implicitly grant vendor credentials. Existing profile and trust projections SHALL remain derived from the same registry.

The registry SHALL declare a top-level `credential_vendors` catalog of allowed vendor identifiers. Projection SHALL reject IDs outside this catalog; `policy_vendor`, `catalog_vendor`, transport, and SDK fields SHALL NOT extend the catalog or grant credential access.

#### Scenario: AI-01 Explicit vendor scope

- **WHEN** an agent declares `vendor_credentials: [openai]` and a different `policy_vendor`
- **THEN** its credential policy SHALL include only its own agent path and the OpenAI vendor path
- **AND** neither vendor field SHALL add any other path

#### Scenario: AI-02 Invalid principal declaration

- **WHEN** an entry has a duplicate or unknown vendor, or declares `openbao_role_id`
- **THEN** schema or projection validation SHALL fail before any OpenBao mutation

#### Scenario: AI-13 Unknown credential vendor

- **WHEN** an agent names a vendor absent from `credential_vendors`
- **THEN** registry projection SHALL fail before any OpenBao mutation

### Requirement: API Key Identity Generation

The coordinator SHALL build API-key identities for all keyed registry agents, regardless of transport, from each agent's own `secret/agents/<name>` KV-v2 document when OpenBao is configured. A dedicated coordinator identity-reader service principal SHALL authenticate independently and have read access only to declared agent data paths; it SHALL NOT use an agent AppRole, the egress-gateway AppRole, or a global shared secret. A missing, invalid, or duplicate key SHALL fail the complete snapshot build, never silently omit an expected agent or accept a partial snapshot. The output mapping SHALL retain `{key: {agent_id, agent_type}}`; the existing explicit `COORDINATION_API_KEY_IDENTITIES` override MAY be used only when OpenBao is not configured. Static file or environment resolution SHALL remain available only in non-OpenBao mode.

#### Scenario: AI-03 Complete identity projection

- **WHEN** all keyed agents have distinct valid keys in their own KV-v2 documents
- **THEN** one immutable identity map SHALL include every keyed registry agent, including MCP agents

#### Scenario: AI-04 Incomplete projection fails closed

- **WHEN** one agent document is missing, has a malformed key, or duplicates another agent's key
- **THEN** the complete candidate snapshot SHALL be rejected with a sanitized error identifying the affected principal(s)
- **AND** no partial candidate SHALL replace the installed map

#### Scenario: AI-05 Configured OpenBao has no static fallback

- **WHEN** OpenBao is configured and a lookup fails
- **THEN** `.secrets.yaml`, ambient key variables, and `COORDINATION_API_KEY_IDENTITIES` SHALL NOT supply that agent's identity

### Requirement: MCP Environment Generation

The agents config SHALL generate MCP registration environment variables for local agents.

- `get_mcp_env(agent_id)` SHALL return a dict of environment variables needed for MCP server registration
- The dict SHALL include `AGENT_ID`, `AGENT_TYPE`, and database connection settings from the active profile

#### Scenario: MCP env generated for local agent
- **WHEN** `get_mcp_env("claude-code-local")` is called
- **AND** the agent is defined with `transport: mcp` and `type: claude_code`
- **THEN** the result SHALL include `{"AGENT_ID": "claude-code-local", "AGENT_TYPE": "claude_code", ...}`

### Requirement: OpenBao AppRole per Agent

Each keyed registry agent SHALL project exactly one AppRole, policy, and `secret/agents/<name>` data path, independent of transport. The canonical SPIFFE ID `spiffe://coordinator.rotkohl.ai/agent/<name>` SHALL be retained for audit and authorization; a deterministic, reversible-or-recorded Bao-safe encoding SHALL produce role and policy names, and projection SHALL reject name collisions. An agent policy SHALL grant `read` only on its own `secret/data/agents/<name>` and the `secret/data/vendors/<vendor>` paths explicitly listed in `vendor_credentials`; it SHALL grant no access to another agent path, unrelated vendor path, `secret/data/coordinator`, or KV-v2 metadata/list paths. Token TTL SHALL remain bounded by the configured token policy, including revocation of any dynamic database child leases when the parent token is revoked. Expiration and renewal SHALL follow OpenBao token semantics; a single-use SecretID SHALL never be reused for a second login.

#### Scenario: AI-06 Principal isolation matrix

- **WHEN** agent A and agent B authenticate with their respective AppRoles
- **THEN** each SHALL read its own agent data path
- **AND** reads of the other agent path or any undeclared vendor path SHALL be denied

#### Scenario: AI-07 Naming collision blocks projection

- **WHEN** two canonical principals encode to the same Bao role or policy name
- **THEN** dry-run and apply SHALL fail before mutation and report both canonical identifiers without credential values

#### Scenario: AI-08 Agent has no vendor grant

- **WHEN** a keyed agent declares `vendor_credentials: []`
- **THEN** its policy SHALL contain no vendor path grants

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

### Requirement: Registry Profile Sync

The coordinator SHALL synchronize the `agent_profiles` table from `agents.yaml` at startup,
treating the table as a materialized projection of the registry.

- On startup, for each registry agent, the coordinator SHALL upsert an `agent_profiles` row
  keyed by the declared `profile` name, carrying `agent_type`, `trust_level`, and
  `allowed_operations` derived from the entry's `capabilities` and trust level
- The registry SHALL own **harness-identity** profiles only. Profiles representing roles
  rather than harness identities (e.g. `evaluator`, which has no transport and cannot be
  dispatched) SHALL be named in an explicit unmanaged-profile allowlist maintained beside
  the sync, and SHALL NOT be disabled by it
- Enabled profile rows that are neither declared by a registry entry nor named in the
  unmanaged allowlist SHALL be **disabled** (`enabled = false`), never deleted; disabling
  SHALL emit an audit event naming the row
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

#### Scenario: Unmanaged role profile survives sync
- **GIVEN** the enabled `evaluator` profile row seeded by migration 026
- **AND** `evaluator` is named in the unmanaged-profile allowlist
- **WHEN** startup sync runs against an `agents.yaml` with no evaluator entry
- **THEN** the row SHALL remain enabled and unmodified
- **AND** no disabling audit event SHALL be emitted for it

#### Scenario: Sync disabled via flag
- **WHEN** `PROFILE_SYNC_ENABLED=false`
- **THEN** startup SHALL perform no profile writes
- **AND** a warning SHALL be logged that the registry projection is not enforced

### Requirement: Registry Assignment Projection

The coordinator SHALL project `agent_profile_assignments` from the registry alongside
`agent_profiles`, so that profile resolution for a registry agent never depends on the
`agent_type` fallback ordering.

- For every registry agent, the sync SHALL maintain an assignment row binding the agent's id to
  the profile row named by its `profile` field
- Assignment rows for agents not declared by the registry SHALL be removed, and each removal
  SHALL emit an audit event naming the profile the assignment pointed at
- Assignment projection SHALL be governed by the same `PROFILE_SYNC_ENABLED` flag and SHALL be
  idempotent and convergent under concurrent worker startup

#### Scenario: Declared agent resolves to its own profile, not the oldest of its type
- **GIVEN** two registry agents share an `agent_type` and declare different trust levels
- **AND** the agent declaring the higher trust level has the newer profile row
- **WHEN** startup sync has run
- **THEN** each agent SHALL resolve to the profile row it declares
- **AND** resolution SHALL NOT depend on `created_at` ordering

#### Scenario: Stale assignment removed with audit trail
- **GIVEN** an assignment row for `gemini-local` pointing at the `gemini_local` profile
- **WHEN** startup sync runs against an `agents.yaml` with no gemini entry
- **THEN** the assignment row SHALL be removed
- **AND** an audit event SHALL record the removal and the profile it pointed at
- **AND** the `gemini_local` profile row itself SHALL be retained and disabled

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

CI SHALL verify the existing profile and identity projections and, for every keyed registry agent, exactly one deterministic AppRole, policy, agent path, and explicit vendor scope. The invariant SHALL fail on missing or extra projected principals, grants, or naming collisions. Service principals SHALL be checked separately from registry agents.

#### Scenario: AI-09 Half-onboarded credential projection

- **WHEN** a new keyed agent is added without a valid vendor scope or deterministic credential projection
- **THEN** the projection test SHALL fail and identify that agent and missing or invalid projection

### Requirement: Harness Key Coverage

Every shipped harness SHALL retain a distinct coordinator API key across its declared locations. AppRole provisioning SHALL select keyed agents regardless of transport and SHALL additionally enforce their explicit vendor scope. A registry agent without an `api_key` SHALL receive no agent AppRole.

#### Scenario: AI-10 MCP agent receives AppRole

- **WHEN** a keyed MCP agent appears in `agents.yaml`
- **THEN** the provisioner SHALL create its deterministic AppRole and policy

### Requirement: OpenBao Service Principals

Provisioning SHALL create two separate service principals: `spiffe://coordinator.rotkohl.ai/service/identity-reader` and `spiffe://coordinator.rotkohl.ai/service/egress-gateway`. The identity reader SHALL read the KV-v2 data paths of declared keyed agents only. The egress gateway SHALL read configured vendor data paths only. Neither SHALL inherit the other's grants, read `secret/data/coordinator`, or receive an agent policy. These principals SHALL receive independently wrapped, single-use bootstrap bundles under the same protection rules as agents. The egress gateway principal is the pca-02 dependency supplied to dg-08; proxy routing and per-dispatch authorization are outside this contract.

Service read paths SHALL be exact: the gateway SHALL receive the sorted union of all agents' declared `vendor_credentials`, and the identity reader SHALL receive the declared keyed agent data paths. Neither service policy SHALL use a wildcard to include undeclared paths.

#### Scenario: AI-11 Identity reader cannot read vendors

- **WHEN** the identity reader authenticates
- **THEN** it SHALL read declared agent data paths
- **AND** a vendor read SHALL be denied

#### Scenario: AI-12 Egress gateway cannot read agents

- **WHEN** the egress gateway authenticates
- **THEN** it SHALL read configured vendor data paths
- **AND** every agent data-path read SHALL be denied

#### Scenario: AI-14 Service policy projection stays exact

- **WHEN** an agent or vendor is added or retired in the registry
- **THEN** service read paths SHALL be recomputed from the complete current projection
- **AND** no undeclared agent or vendor path SHALL be added by a wildcard

### Requirement: Dispatch Principal Wire Contract

`get_dispatch_configs()` and `GET /agents/dispatch-configs` SHALL emit a canonical `principal_id` and explicit sorted `vendor_credentials` for every dispatchable registry entry, preserving existing transport fields and omitting `openbao_role_id`. Direct registry loading by the dispatcher SHALL construct the same shape. A keyless endpoint-only entry SHALL have a null principal ID and empty vendor scope. Neither wire response nor direct projection SHALL contain an API key or bootstrap token.

#### Scenario: AI-16 Keyed dispatch principal

- **WHEN** a keyed registry agent is projected into a dispatch config
- **THEN** the API and direct loader SHALL expose its canonical SPIFFE ID and explicit vendor credential scope
- **AND** neither SHALL expose `openbao_role_id` or secret material

#### Scenario: AI-17 Keyless endpoint dispatch

- **WHEN** a keyless endpoint agent is projected into a dispatch config
- **THEN** its `principal_id` SHALL be null and `vendor_credentials` SHALL be empty
