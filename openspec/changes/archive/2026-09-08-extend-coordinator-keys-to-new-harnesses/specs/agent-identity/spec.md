# agent-identity — delta for extend-coordinator-keys-to-new-harnesses

Keys the whole roster: coordinator credentials are declared per agent regardless of
transport, and every derivation that consumes them follows the credential rather than
the transport.

> **Rebased 2026-09-08 against the archived `derive-agent-identity-from-registry`.**
> This delta was authored before that change landed. The 2026-09-08 archive sweep
> stopped here because a `MODIFIED` block replaces the whole requirement, and the
> original blocks — written against the older spec — would have deleted three
> scenarios `derive-agent-identity-from-registry` had since added
> (`MCP-transport agent receives identity projection`, `Full-roster identity map`,
> `Duplicate key rejected`).
>
> Re-reading both showed the overlap was near-total: that change had already landed
> this one's intent in a stronger, transport-independent form. The original
> `MODIFIED` block for `Declarative Agent Configuration` is therefore dropped
> entirely — every clause in it is on `main`, and `main`'s duplicate-credential rule
> is strictly stronger (it compares *resolved values*, not variable names). What
> survives is the single assertion nothing on `main` covers: an agent declaring no
> `api_key` contributes no identity row. The `MODIFIED` block below is `main`'s
> current text plus that one scenario, so archiving it is lossless.

## MODIFIED Requirements

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

#### Scenario: Agent without a key is excluded
- **WHEN** an agent declares no `api_key`
- **THEN** it SHALL contribute no identity row, whatever its transport

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
