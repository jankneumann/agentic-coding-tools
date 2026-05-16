## MODIFIED Requirements

### Requirement: Archetype Definition Schema

The system SHALL support an `archetypes.yaml` configuration file that defines named agent archetypes. Each archetype SHALL specify:

- A logical model tier or legacy model alias.
- `system_prompt`: role-specific instruction prefix composed with task prompts.
- `escalation`: optional rules for complexity-based tier or model upgrade.

Archetype model values SHALL be resolved through provider-aware model mapping before dispatch. Legacy Claude aliases (`opus`, `sonnet`, `haiku`) SHALL remain valid for Claude Code compatibility, but non-Claude providers SHALL receive provider-specific model IDs.

Archetype names SHALL match the pattern `^[a-z][a-z0-9_-]{0,31}$` and SHALL be validated at all system boundaries.

#### Scenario: Archetype resolves for Codex provider

- **WHEN** `architect` resolves under provider `codex`
- **THEN** the logical role SHALL remain `architect`
- **AND** the dispatch model SHALL be a Codex model ID from provider mapping
- **AND** the raw Claude alias `opus` SHALL NOT be dispatched to Codex unless explicitly configured as a Codex model alias

#### Scenario: Archetype resolves for Gemini provider

- **WHEN** `reviewer` resolves under provider `gemini`
- **THEN** the logical role SHALL remain `reviewer`
- **AND** the dispatch model SHALL be a Gemini model ID from provider mapping

### Requirement: Predefined Archetypes

The system SHALL ship with predefined archetypes for `architect`, `analyst`, `implementer`, `reviewer`, `runner`, and `documenter`.

Each predefined archetype SHALL include a `system_prompt` tuned to its role. Each archetype SHALL map to a logical model tier that can be translated to provider-specific model IDs for Claude Code, Codex, and Gemini/Jules.

#### Scenario: Architect archetype maps per provider

- **WHEN** a phase dispatch requests archetype `architect`
- **THEN** Claude Code SHALL receive its configured premium Claude model
- **AND** Codex SHALL receive its configured premium Codex model
- **AND** Gemini/Jules SHALL receive its configured premium Gemini model

#### Scenario: Runner archetype maps per provider

- **WHEN** a validation phase dispatch requests archetype `runner`
- **THEN** each provider SHALL receive its configured economy or validation-appropriate model
- **AND** the system prompt SHALL contain role guidance for executing and reporting commands

### Requirement: Fallback Chain Integration

Archetype model selection SHALL integrate with the existing `agents.yaml` model fallback chain rather than defining independent fallback sequences.

The resolution order SHALL be:

1. Provider-specific archetype model for the active provider.
2. `agents.yaml` `cli.model_fallbacks` for the active provider agent.
3. `agents.yaml` `sdk.model` and `sdk.model_fallbacks` when SDK dispatch is available.

#### Scenario: Archetype model exhausted falls back inside same provider

- **WHEN** provider `codex` resolves `reviewer` to a primary Codex model
- **AND** the primary model dispatch returns an `ErrorClass.CAPACITY` error
- **THEN** the dispatcher SHALL try the next Codex model in that agent's `cli.model_fallbacks`
- **AND** it SHALL NOT fall back to a Claude model unless the selected provider explicitly changes

### Requirement: Work Queue Archetype Routing

The coordinator work queue SHALL support archetype-aware task routing and provider-aware model selection.

The `submit_work()` operation SHALL accept optional `agent_requirements` containing:

- `archetype`: preferred archetype name.
- `provider`: optional provider preference.
- `min_trust_level`: optional minimum trust level.

The claim operation SHALL filter available tasks by the claiming agent's declared archetype compatibility and provider identity when those requirements are present.

#### Scenario: Provider preference routes to matching agent

- **WHEN** a task is submitted with `agent_requirements.archetype = "implementer"` and `agent_requirements.provider = "gemini"`
- **AND** a Gemini agent with `archetypes: ["implementer"]` calls claim
- **THEN** the agent SHALL be eligible to claim the task
- **AND** a Codex-only agent SHALL NOT claim that provider-constrained task
