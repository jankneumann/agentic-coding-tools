# Spec Delta: Skill Workflow — SDK Dispatch Fallback

## ADDED Requirements

### Requirement: SDK Vendor Dispatch Adapter

The system SHALL provide a `SdkVendorAdapter` that can dispatch review prompts to vendor APIs (Anthropic, OpenAI, Google) via their Python SDKs when the vendor's CLI is not installed.

- The `SdkVendorAdapter` SHALL implement the same `dispatch()` → `ReviewResult` interface as `CliVendorAdapter`.
- The `SdkVendorAdapter` SHALL only support the `review` dispatch mode (read-only). It SHALL NOT support `alternative` mode (write access).
- The `SdkVendorAdapter` SHALL lazy-import vendor SDK packages to avoid import errors when SDKs are not installed.

#### Scenario: SDK dispatch to Anthropic API

- GIVEN the `claude` CLI is not installed
- AND an API key is resolvable for Anthropic (via OpenBao or `ANTHROPIC_API_KEY` env var)
- WHEN the dispatcher selects reviewers
- THEN it creates a `SdkVendorAdapter` for `claude-remote`
- AND dispatches the review prompt via `anthropic.Anthropic().messages.create()`
- AND parses the JSON findings from the response

#### Scenario: SDK dispatch with model fallback

- GIVEN SDK dispatch to the primary model returns a 429 (rate limit) error
- WHEN the adapter retries with the next model in `model_fallbacks`
- THEN it succeeds with the fallback model
- AND `ReviewResult.models_attempted` contains both model names

#### Scenario: SDK package not installed

- GIVEN `openai` package is not installed in the Python environment
- WHEN `SdkVendorAdapter.can_dispatch("review")` is called for an OpenAI adapter
- THEN it returns False
- AND the vendor is skipped without error

### Requirement: Three-Tier Dispatch Selection

The `ReviewOrchestrator` SHALL select reviewers using a three-tier waterfall, evaluated per vendor:

1. **Tier 1 (Local CLI)**: If the vendor's CLI binary is installed on PATH, use `CliVendorAdapter` with the `*-local` agent config.
2. **Tier 2 (SDK/API)**: If the CLI is not installed but the vendor's Python SDK is importable AND an API key is resolvable, use `SdkVendorAdapter` with the `*-remote` agent config.
3. **Tier 3 (Skip)**: If neither CLI nor SDK dispatch is available, skip this vendor silently.

- The dispatcher SHALL select at most one reviewer per vendor type (no double dispatch).
- The dispatcher SHALL log which tier was selected for each vendor.

#### Scenario: Mixed CLI and SDK dispatch

- GIVEN `claude` CLI is installed but `codex` CLI is not
- AND an OpenAI API key is resolvable for `codex-remote`
- WHEN the dispatcher selects reviewers
- THEN it selects `claude-local` via CLI (Tier 1) and `codex-remote` via SDK (Tier 2)
- AND dispatches to both vendors

#### Scenario: No vendors available

- GIVEN no vendor CLIs are installed AND no API keys are resolvable
- WHEN the dispatcher selects reviewers
- THEN it returns an empty list
- AND logs a warning

#### Scenario: CLI always preferred over SDK for same vendor

- GIVEN `claude` CLI is installed AND Anthropic API key is resolvable
- WHEN the dispatcher selects reviewers for Anthropic/Claude
- THEN it selects `claude-local` via CLI (Tier 1)
- AND does NOT also dispatch via SDK

### Requirement: API Key Resolution via OpenBao

API keys for SDK dispatch SHALL be resolved securely at runtime. Keys SHALL NOT be stored in `agents.yaml`, git history, or any committed file.

- The `ApiKeyResolver` SHALL attempt OpenBao resolution first using the agent's `openbao_role_id`.
- If OpenBao is unavailable (no `OPENBAO_ADDR` set), the resolver SHALL fall back to the environment variable specified in `sdk.api_key_env`.
- If neither source provides a key, the resolver SHALL return `None` and the vendor SHALL be skipped.
- Resolved keys SHALL be cached for the lifetime of the resolver instance to avoid repeated vault lookups within a single dispatch cycle.

#### Scenario: API key resolved from OpenBao

- GIVEN `OPENBAO_ADDR` is set and the vault contains a secret for `openbao_role_id: claude-code-web`
- WHEN the resolver attempts to resolve the Anthropic API key
- THEN it reads the secret from OpenBao and returns the API key

#### Scenario: API key fallback to environment variable

- GIVEN `OPENBAO_ADDR` is not set
- AND `ANTHROPIC_API_KEY` environment variable is set
- WHEN the resolver attempts to resolve the Anthropic API key
- THEN it returns the value of `ANTHROPIC_API_KEY`

#### Scenario: No API key available

- GIVEN `OPENBAO_ADDR` is not set AND `ANTHROPIC_API_KEY` is not set
- WHEN the resolver attempts to resolve the Anthropic API key
- THEN it returns None
- AND the dispatcher skips the Anthropic vendor

### Requirement: SDK Configuration in agents.yaml

Each agent entry in `agents.yaml` SHALL support an optional `sdk` section specifying: `package` (Python SDK package name), `method` (API method to call), `model` (primary model), `model_fallbacks` (ordered fallback list), `api_key_env` (environment variable name for fallback key resolution), and `max_tokens` (maximum response tokens).

- Agents without an `sdk` section SHALL be excluded from SDK dispatch.
- The `get_dispatch_configs()` function SHALL include `sdk` configuration in its output when present.

#### Scenario: Agent with SDK config

- GIVEN agents.yaml contains a `sdk` section for `codex-remote` with `package: openai` and `model: gpt-5.4`
- WHEN `get_dispatch_configs()` is called
- THEN the output includes the `sdk` configuration for `codex-remote`

#### Scenario: Agent without SDK config

- GIVEN agents.yaml does not contain a `sdk` section for `codex-local`
- WHEN `get_dispatch_configs()` is called
- THEN the output for `codex-local` has `sdk: null`
