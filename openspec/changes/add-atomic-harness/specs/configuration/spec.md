# configuration — delta for add-atomic-harness

Introduces the experimental provider class and exempts experimental tier maps from the
closed first-class provider-model-map enum, without weakening first-class roster
integrity.

## ADDED Requirements

### Requirement: Experimental Provider Class

The system SHALL support declaring a provider as **experimental** in `agents.yaml` via
`experimental: true` on the agent entry. An experimental provider SHALL be dispatchable
through the config-driven `CliVendorAdapter` and eligible for review rotation and
`/quick-task`, but SHALL be exempt from first-class roster parity: no
`provider-model-map.schema.json` enum membership, no evaluation-framework backend
requirement, and no first-class listing in the manual provider smoke path.

An experimental provider SHALL default to `counts_toward_quorum: false` in
vendor-diversity policy: its findings are recorded and surfaced but SHALL NOT satisfy
review quorum on their own until the provider is promoted to first-class by a separate
change.

Removing an experimental provider SHALL require only deleting its `agents.yaml` entry
and associated adapters; no schema or first-class spec change SHALL be needed.

#### Scenario: Experimental vendor dispatches through the generic adapter

- **GIVEN** `agents.yaml` declares `atomic-local` with `experimental: true` and a `cli` block
- **WHEN** `ReviewOrchestrator` discovers reviewers
- **THEN** `atomic-local` SHALL be discoverable and dispatchable via `CliVendorAdapter`
- **AND** its dispatch SHALL use the same command-construction, timeout, and error-classification machinery as first-class vendors

#### Scenario: Experimental findings do not satisfy quorum alone

- **GIVEN** only the experimental vendor `atomic-local` returned findings in a review round
- **WHEN** quorum is evaluated with `min_vendors: 2`
- **THEN** the round SHALL NOT count `atomic-local` toward the quorum threshold
- **AND** the shortfall SHALL be reported with the same below-quorum handling as when the vendor had not responded

#### Scenario: Unknown non-experimental provider still fails loudly

- **GIVEN** a provider name that is neither in the first-class roster nor declared experimental in `agents.yaml`
- **WHEN** dispatch or resolution is requested for it
- **THEN** the system SHALL fail with a structured error naming the supported roster and registered experimental providers
- **AND** no dispatch SHALL be attempted

## MODIFIED Requirements

### Requirement: Provider Model Mapping Configuration

Provider dispatch configuration SHALL define model mappings for Claude Code, Codex, antigravity, grok, and pi so logical archetypes can resolve to provider-specific model IDs.

The model mapping SHALL conform to `openspec/schemas/provider-model-map.schema.json` (schema_version 2: provider key set closed to the five roster keys, all five required).

The `pi` provider SHALL resolve to OpenRouter model slugs, and its default model SHALL be `qwen/qwen3-coder`, selected so the roster reaches models outside the subscription harnesses.

Experimental providers SHALL NOT be added to the closed first-class key set. An
experimental provider MAY declare a tier map in a sibling `experimental_providers`
mapping whose per-tier entries conform to the same tier-entry shape (bare model string
or `{model, thinking}`) and are resolved through the same
`resolve_provider_model_spec` path. The `atomic` experimental provider SHALL resolve to
OpenRouter model slugs distinct from the `pi` tier map, so the two OpenRouter-backed
harnesses add model diversity rather than duplicating each other; final slugs SHALL be
fixed by the network-permitted re-probe recorded in this change's `design.md` (finding
A18) before live dispatch is enabled.

#### Scenario: Provider map includes all first-class providers

- **WHEN** the default provider model map is loaded
- **THEN** it SHALL include entries for `claude_code`, `codex`, `antigravity`, `grok`, and `pi`
- **AND** each entry SHALL define `premium`, `standard`, and `economy` model IDs
- **AND** it SHALL NOT include an entry for `gemini`
- **AND** it SHALL NOT include a first-class entry for `atomic`

#### Scenario: pi maps to OpenRouter slugs

- **WHEN** the `pi` provider entry is loaded
- **THEN** every tier value SHALL be an OpenRouter model slug in `<publisher>/<model>` form
- **AND** the `standard` tier SHALL be `qwen/qwen3-coder`

#### Scenario: Non-Claude provider rejects unmapped Claude alias

- **GIVEN** provider `codex`
- **AND** an archetype resolves to legacy alias `opus`
- **WHEN** no Codex mapping exists for that alias or tier
- **THEN** dispatch resolution SHALL fail with a structured configuration error before invoking Codex
- **AND** the error SHALL identify the missing provider model mapping

#### Scenario: Experimental tier map resolves without schema enum membership

- **GIVEN** `experimental_providers.atomic` declares `standard` and `economy` tier entries
- **WHEN** `resolve_provider_model_spec` runs with provider `atomic`
- **THEN** it SHALL return the mapped `ModelSpec` (model and optional thinking) for the requested tier
- **AND** schema validation of `provider-model-map.schema.json` SHALL still require exactly the five first-class keys

#### Scenario: Experimental provider with no tier map falls back to agent default model

- **GIVEN** an experimental provider entry with a `cli.model` but no `experimental_providers` tier map
- **WHEN** tier resolution is requested for it
- **THEN** resolution SHALL return no tier-mapped model and the dispatch layer SHALL use the agent entry's configured `cli.model` and `model_fallbacks`
- **AND** a structured warning SHALL record that tier resolution was skipped for an unmapped experimental provider
