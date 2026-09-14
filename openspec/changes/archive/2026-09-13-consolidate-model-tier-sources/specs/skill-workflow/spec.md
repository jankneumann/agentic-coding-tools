## ADDED Requirements

### Requirement: Review Mode Model and Thinking from Tier Map

The review dispatcher (`review_dispatcher.py`) SHALL resolve each reviewer's
model and optional thinking level from the provider tier map (YAML-backed
`model_aliases`, typically the `premium` tier for review) and SHALL inject
vendor-specific thinking/effort flags via a shared `thinking_flags` helper
when building the review CLI command.

`agents.yaml` SHALL NOT hardcode premium model ids or effort/reasoning flags
as the source of truth for review mode. Non-review dispatch modes MAY retain
`cli.model` / fallbacks for capacity retry, but review-mode model and thinking
policy SHALL come from the tier map.

#### Scenario: Review resolves premium from the tier map

- **GIVEN** `archetypes.yaml::model_aliases.<provider>.premium` defines a
  model (and optional thinking)
- **WHEN** the dispatcher builds a `--mode review` command for that provider's
  agent
- **THEN** the effective model SHALL be the premium map entry's model
- **AND** when thinking is present, vendor thinking flags SHALL be injected by
  the helper
- **AND** review SHALL NOT depend on a hardcoded premium model id in
  `agents.yaml` as policy

#### Scenario: Thinking flags are vendor-translated

- **GIVEN** a resolved thinking value for a known vendor
- **WHEN** `thinking_flags` runs
- **THEN** it SHALL return that vendor's CLI flag fragment(s) (e.g. Claude
  `--effort`, Codex `model_reasoning_effort`, Grok reasoning-effort)
- **AND** for an unknown vendor it SHALL return no flags without failing model
  selection

#### Scenario: agents.yaml does not author review premium policy

- **WHEN** review-mode configuration in `agents.yaml` is inspected for policy
  source
- **THEN** it SHALL NOT be the authored source of premium model ids or
  effort/reasoning flags for review
- **AND** changing `model_aliases.<provider>.premium` alone SHALL be
  sufficient to change review model/thinking after reload
