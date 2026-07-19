# llm-gateway Specification (delta)

## ADDED Requirements

### Requirement: Data Plane Is a Separate Deployable

The LLM gateway (inference data plane) SHALL run as a separate deployable process (a pinned
LiteLLM proxy container), never inside the coordination API process. The coordinator SHALL
administer the gateway but SHALL NOT proxy `/chat/completions` or `/embeddings` traffic through its
own process. OpenRouter and local endpoints (Ollama/vLLM) SHALL be configured as upstreams behind
the gateway.

#### Scenario: Coordination outage does not stop inference

- **WHEN** the coordination API process is stopped while the gateway container runs
- **THEN** in-flight and new inference requests carrying a valid virtual key SHALL continue to be
  served by the gateway

#### Scenario: Coordinator does not relay inference

- **WHEN** an agent performs a completion or embedding through the gateway
- **THEN** the request SHALL NOT transit the coordination API process
- **AND** no coordination endpoint SHALL appear in the request path

### Requirement: Coordinator-Issued Scoped Virtual Keys

The coordinator SHALL issue short-lived virtual keys scoped to a budget, a model allowlist, and a
TTL, minted from provider master keys held in the secret vault. Agents SHALL receive only the
virtual key; provider master keys SHALL NOT be exposed to agents. The maximum issuable budget and
model set SHALL be bounded by the requesting agent's trust level.

#### Scenario: Agent receives a scoped key, not a master key

- **WHEN** an agent calls `issue_llm_key` with a budget and model list within its trust bound
- **THEN** the response SHALL contain a virtual key usable only for the allowed models and budget
- **AND** the response SHALL NOT contain any provider master key

#### Scenario: Trust level bounds the issuable scope

- **WHEN** an agent requests a budget or model outside its trust-level bound
- **THEN** issuance SHALL be refused with a scope error

#### Scenario: Vault unavailable fails closed

- **WHEN** the secret vault is unreachable at issuance time
- **THEN** `issue_llm_key` SHALL fail without minting a key
- **AND** SHALL NOT fall back to handing the agent a provider master key

### Requirement: Inline Budget Enforcement

For traffic that flows through the gateway, budgets SHALL be enforced at request time: once a
virtual key's spend crosses its budget, the gateway SHALL reject further calls on that key. Budget
enforcement SHALL NOT depend on post-hoc reconciliation.

#### Scenario: Exhausted budget blocks further calls

- **WHEN** a virtual key's accumulated spend reaches its `budget_usd`
- **THEN** the next call on that key SHALL be rejected by the gateway (HTTP 429/402)
- **AND** the rejection SHALL occur without a coordinator round-trip

### Requirement: Single Spend Source of Truth

The gateway SHALL NOT maintain an independent spend ledger. Budgets SHALL be derived from the
`add-adaptive-model-router` policy, and actual spend SHALL be reported back into that same ledger
via the gateway's spend callback. The only new coordinator-owned table SHALL be a key-issuance
audit, not a spend store.

#### Scenario: Spend reconciles into the router ledger

- **WHEN** a proxied call completes with a cost
- **THEN** the gateway's spend callback SHALL record the cost into the router's existing spend
  ledger
- **AND** no duplicate spend table SHALL be created by this capability

#### Scenario: Callback outage does not drop spend

- **WHEN** the router ledger is temporarily unreachable for a spend callback
- **THEN** the gateway SHALL buffer and later reconcile the spend rather than discard it

### Requirement: Coverage Boundary Is Explicit

The capability SHALL document that it covers only meterable traffic (metered provider APIs, local
endpoints, embeddings). Subscription-CLI dispatch (Claude Code / Codex / Gemini CLIs) SHALL remain
on vendor authentication and the router's advisory path. Documentation and metrics SHALL NOT
present the gateway as a universal choke point for all LLM traffic.

#### Scenario: Subscription-CLI traffic is out of scope

- **WHEN** a subscription-CLI session performs inference
- **THEN** that traffic SHALL NOT be required to route through the gateway
- **AND** the capability docs SHALL state this boundary explicitly

### Requirement: Embedding Endpoint for Semantic Code Search

The gateway SHALL expose an embedding endpoint usable as the reachable embedder for
`add-semantic-code-search`. The code-search embedder SHALL be configurable to call the gateway
`/embeddings` with a coordinator-issued key, and the model it serves SHALL be recorded in
`code_search_registry.embedder_model`.

#### Scenario: Code search embeds via the gateway

- **WHEN** the code-search service is configured to use the gateway and holds a valid key
- **THEN** its query embedding SHALL be produced by a call to the gateway `/embeddings`
- **AND** the registry's recorded embedder model SHALL match the gateway-served model
