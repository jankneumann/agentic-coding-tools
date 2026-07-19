# agent-coordinator Specification (delta)

## ADDED Requirements

### Requirement: LLM Gateway Control Surface

The coordinator SHALL expose LLM-gateway control operations on both agent surfaces backed by a
single service module (`src/llm_gateway.py`): MCP tools `issue_llm_key`, `revoke_llm_key`,
`get_llm_budget`, `get_llm_spend`, and matching HTTP endpoints (`POST /llm/keys/issue`,
`POST /llm/keys/revoke`, `GET /llm/budget/{agent_id}`, `GET /llm/spend/{agent_id}`). Key issuance
and revocation SHALL be classified reversible-write; budget and spend reads SHALL be classified
read. These operations administer the separate gateway deployable — they SHALL NOT proxy inference.

#### Scenario: Both surfaces expose the same operations

- **WHEN** `issue_llm_key` is invoked via MCP and via `POST /llm/keys/issue` with equivalent input
- **THEN** both SHALL return an equivalent scoped-key payload from the same service

#### Scenario: Reads are classified read, issuance is reversible-write

- **WHEN** the operation kinds are inspected
- **THEN** `get_llm_budget` and `get_llm_spend` SHALL be `read`
- **AND** `issue_llm_key` and `revoke_llm_key` SHALL be `reversible-write` and emit an audit event

### Requirement: LLM Gateway Feature Flag

Control-surface registration SHALL be gated by `LLM_GATEWAY_ENABLED` (default off). While disabled,
the MCP key tools SHALL NOT be listed, the HTTP key routes SHALL return 404, and consumers SHALL
use their existing direct-dispatch configuration. No behavior SHALL change while the flag is off.

#### Scenario: Disabled flag hides the surface

- **WHEN** `LLM_GATEWAY_ENABLED` is unset and the MCP tool list is requested
- **THEN** `issue_llm_key` SHALL NOT appear
- **AND** `POST /llm/keys/issue` SHALL return 404

### Requirement: Key Issuance Audit Table

The coordinator SHALL record issued keys in an additive `llm_gateway_keys` table
(key_id, agent_id, budget_usd, model_allowlist, issued_at, expires_at, revoked_at) for revocation
and audit. This table SHALL NOT store spend — spend remains in the `add-adaptive-model-router`
ledger.

#### Scenario: Issuance and revocation are auditable

- **WHEN** a key is issued and later revoked
- **THEN** `llm_gateway_keys` SHALL contain the issuance row with `revoked_at` set on revocation
- **AND** SHALL contain no spend columns
