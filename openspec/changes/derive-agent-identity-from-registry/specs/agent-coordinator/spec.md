# agent-coordinator Delta — derive-agent-identity-from-registry

## MODIFIED Requirements

### Requirement: Agent Profiles

The system SHALL support configurable agent profiles that define capabilities, trust levels,
and operational constraints, resolved fail-loud for agents declared in the registry.

- Profiles SHALL specify allowed operations and tools
- Profiles SHALL define trust level (0–4), referencing the Unified Trust Scale defined by
  the `agent-identity` capability rather than a local literal range
- Profiles SHALL configure resource limits (max files, execution time, API calls)
- Profiles SHALL be assignable per agent_id or agent_type
- Profiles for registry-declared agents SHALL be materialized by the startup registry sync;
  hand-authored default rows SHALL NOT be required for registry agents
- Trust resolution SHALL distinguish two miss cases:
  - a principal **not present** in the registry SHALL receive the default trust level
    (existing behavior, unchanged)
  - a **registry-declared** agent whose profile row is missing or disabled SHALL cause a
    hard resolution error and an audit event — never a silent default

#### Scenario: Agent with restricted profile
- **WHEN** agent with "reviewer" profile attempts file modification
- **THEN** system checks if "write_file" is in profile's allowed_operations
- **AND** rejects operation if not permitted with `{success: false, error: "operation_not_permitted"}`

#### Scenario: Resource limit enforcement
- **WHEN** agent exceeds profile's max_file_modifications limit
- **THEN** system blocks further modifications
- **AND** returns `{success: false, error: "resource_limit_exceeded", limit: "max_file_modifications"}`

#### Scenario: Trust level verification
- **WHEN** agent attempts operation requiring trust_level >= 3
- **AND** agent's profile has trust_level < 3
- **THEN** system rejects with `{success: false, error: "insufficient_trust_level"}`

#### Scenario: Registry agent with broken projection fails loud
- **WHEN** `grok-local` is declared in `agents.yaml`
- **AND** its `grok_local` profile row is missing or disabled
- **THEN** trust resolution SHALL return an error (not the default trust level)
- **AND** an audit event SHALL record the failed resolution

#### Scenario: Unknown principal still defaults low
- **WHEN** a principal absent from the registry authenticates via an explicitly configured
  env-var identity
- **THEN** trust resolution SHALL return the configured default trust level
- **AND** no error SHALL be raised

#### Profile Trust Levels

| Level | Name | Typical Capabilities |
|-------|------|---------------------|
| 0 | Untrusted | Read-only, no network, all changes require manual review |
| 1 | Limited | Read-write with locks, documentation domains only |
| 2 | Standard | Full file access, approved domains, automated verification |
| 3 | Elevated | Skip Tier 0-1 verification, extended resource limits |
| 4 | Admin | Full access, can modify policies and profiles |

This table is the human-readable rendering of the Unified Trust Scale; the programmatic
definition lives in the trust-scale module and the two SHALL be asserted equal in tests.
