## ADDED Requirements

### Requirement: Declarative Lane Auth and Subscription Headless Policy

Every `cli` block in `agent-coordinator/agents.yaml` SHALL declare `auth` with exactly one of
`subscription`, `api_key`, or `none`; `AGENTS_SCHEMA` SHALL reject any other value and
`agents_config.validate` SHALL reject a `cli` block without it. A `cli` block declaring
`auth: api_key` SHALL also declare a non-empty `api_key_env`, and its agent's `vendor_credentials`
SHALL be non-empty. `CliConfig` SHALL carry the value and `get_dispatch_configs()` SHALL include
`auth` in every lane's `cli` payload.

The registry MAY declare `policies.subscription_headless` with `allow` (a list of objects with
required `vendor`, `basis`, and `reviewed` keys) and optional `review_after_days` (positive
integer, default 180). `vendor` SHALL equal the `policy_vendor` of at least one agent, `basis`
SHALL be a non-empty string, `reviewed` SHALL be an ISO date not in the future, and a vendor SHALL
NOT appear twice; validation SHALL fail otherwise. `get_dispatch_configs()` SHALL include the
resolved allow list as `policies.subscription_headless.allow` (vendor names only) so a dispatcher
loading configuration over HTTP applies the same policy as one loading the file.

#### Scenario: A cli block without auth is rejected at load
- **WHEN** an agent declares a `cli` block with no `auth` key
- **THEN** loading `agents.yaml` SHALL fail validation naming the agent

#### Scenario: An api_key lane without a key variable is rejected
- **WHEN** an agent declares `cli: {auth: api_key}` and no `api_key_env`
- **THEN** loading `agents.yaml` SHALL fail validation

#### Scenario: An allow entry without a basis is rejected
- **WHEN** `policies.subscription_headless.allow` contains `{vendor: codex, reviewed: 2026-11-20}`
- **THEN** loading `agents.yaml` SHALL fail validation naming the missing `basis`

#### Scenario: An allow entry for an unknown vendor is rejected
- **WHEN** an allow entry names a vendor that is no agent's `policy_vendor`
- **THEN** loading `agents.yaml` SHALL fail validation

#### Scenario: Dispatch configs carry auth and the allow list
- **WHEN** `get_dispatch_configs()` is called for a registry that allows `grok`
- **THEN** every lane's `cli` payload SHALL contain `auth` and the result SHALL contain `policies.subscription_headless.allow` equal to `["grok"]`

#### Scenario: Declaring lane auth grants no credentials
- **WHEN** an agent declares `cli: {auth: api_key, api_key_env: ANTHROPIC_API_KEY}` and `vendor_credentials: []`
- **THEN** loading `agents.yaml` SHALL fail validation, and no credential policy SHALL be derived from the `auth` field
