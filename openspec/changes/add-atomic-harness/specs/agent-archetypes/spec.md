# agent-archetypes — delta for add-atomic-harness

Extends provider-aware archetype resolution to cover registered experimental providers
(with optional tier maps) while keeping fail-loud behavior for unknown providers.

## MODIFIED Requirements

### Requirement: Archetype Definition Schema

The system SHALL support an `archetypes.yaml` configuration file that defines named agent archetypes. Each archetype SHALL specify:

- A logical model tier or legacy model alias.
- `system_prompt`: role-specific instruction prefix composed with task prompts.
- `escalation`: optional rules for complexity-based tier or model upgrade.

Archetype model values SHALL be resolved through provider-aware model mapping before dispatch. Legacy Claude aliases (`opus`, `sonnet`, `haiku`) SHALL remain valid for Claude Code compatibility, but non-Claude providers SHALL receive provider-specific model IDs.

Archetype names SHALL match the pattern `^[a-z][a-z0-9_-]{0,31}$` and SHALL be validated at all system boundaries.

Provider-aware resolution SHALL cover the supported first-class roster (`claude_code`, `codex`, `antigravity`, `grok`, and `pi`) plus providers registered as experimental with a declared tier map. Resolution SHALL fail with a structured configuration error for the retired `gemini` provider and for any provider that is neither first-class nor registered experimental, rather than silently falling back to a Claude alias. For an experimental provider without a tier map, resolution SHALL return no model mapping together with a structured warning, so the dispatch layer falls back to the agent entry's configured CLI model.

#### Scenario: Archetype resolves for Codex provider

- **WHEN** `architect` resolves under provider `codex`
- **THEN** the logical role SHALL remain `architect`
- **AND** the dispatch model SHALL be a Codex model ID from provider mapping
- **AND** the raw Claude alias `opus` SHALL NOT be dispatched to Codex unless explicitly configured as a Codex model alias

#### Scenario: Archetype resolves for antigravity provider

- **WHEN** `reviewer` resolves under provider `antigravity`
- **THEN** the logical role SHALL remain `reviewer`
- **AND** the dispatch model SHALL be an antigravity model ID from provider mapping

#### Scenario: Archetype resolves for grok provider

- **WHEN** `reviewer` resolves under provider `grok`
- **THEN** the logical role SHALL remain `reviewer`
- **AND** the dispatch model SHALL be a grok model ID from provider mapping

#### Scenario: Archetype resolves for pi provider

- **WHEN** `implementer` resolves under provider `pi`
- **THEN** the logical role SHALL remain `implementer`
- **AND** the dispatch model SHALL be an OpenRouter model slug from provider mapping

#### Scenario: Archetype resolves for Gemini provider

- **WHEN** archetype resolution is requested under provider `gemini`
- **THEN** resolution SHALL fail with a structured configuration error naming `gemini` as unsupported (the gemini provider harness is retired)
- **AND** the error SHALL list the supported roster
- **AND** no dispatch SHALL be attempted

#### Scenario: Archetype resolves for experimental atomic provider with tier map

- **GIVEN** `atomic` is registered experimental with a declared tier map
- **WHEN** `reviewer` resolves under provider `atomic`
- **THEN** the logical role SHALL remain `reviewer`
- **AND** the dispatch model SHALL be an OpenRouter model slug from the experimental tier map, distinct from the `pi` mapping

#### Scenario: Experimental provider without tier map warns and defers to CLI model

- **GIVEN** an experimental provider registered without a tier map
- **WHEN** archetype resolution is requested under that provider
- **THEN** resolution SHALL return no model mapping and a structured warning identifying the unmapped experimental provider
- **AND** no error SHALL be raised, so the dispatch layer can use the agent entry's configured CLI model
