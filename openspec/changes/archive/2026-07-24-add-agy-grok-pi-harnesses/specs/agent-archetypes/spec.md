# agent-archetypes — delta for add-agy-grok-pi-harnesses

Replaces the retired `gemini` provider with the `antigravity`, `grok`, and `pi` harnesses
across archetype resolution, predefined archetype tier maps, and work-queue provider routing.

## MODIFIED Requirements

### Requirement: Archetype Definition Schema

The system SHALL support an `archetypes.yaml` configuration file that defines named agent archetypes. Each archetype SHALL specify:

- A logical model tier or legacy model alias.
- `system_prompt`: role-specific instruction prefix composed with task prompts.
- `escalation`: optional rules for complexity-based tier or model upgrade.

Archetype model values SHALL be resolved through provider-aware model mapping before dispatch. Legacy Claude aliases (`opus`, `sonnet`, `haiku`) SHALL remain valid for Claude Code compatibility, but non-Claude providers SHALL receive provider-specific model IDs.

Archetype names SHALL match the pattern `^[a-z][a-z0-9_-]{0,31}$` and SHALL be validated at all system boundaries.

Provider-aware resolution SHALL cover exactly the supported roster: `claude_code`, `codex`, `antigravity`, `grok`, and `pi`. Resolution SHALL fail with a structured configuration error for the retired `gemini` provider rather than silently falling back to a Claude alias.

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

### Requirement: Predefined Archetypes

The system SHALL ship with predefined archetypes for `architect`, `analyst`, `implementer`, `reviewer`, `runner`, and `documenter`.

Each predefined archetype SHALL include a `system_prompt` tuned to its role. Each archetype SHALL map to a logical model tier that can be translated to provider-specific model IDs for Claude Code, Codex, antigravity, grok, and pi.

#### Scenario: Architect archetype maps per provider

- **WHEN** a phase dispatch requests archetype `architect`
- **THEN** Claude Code SHALL receive its configured premium Claude model
- **AND** Codex SHALL receive its configured premium Codex model
- **AND** antigravity SHALL receive its configured premium antigravity model
- **AND** grok SHALL receive its configured premium grok model
- **AND** pi SHALL receive its configured premium OpenRouter model slug

#### Scenario: Runner archetype maps per provider

- **WHEN** a validation phase dispatch requests archetype `runner`
- **THEN** each provider SHALL receive its configured economy or validation-appropriate model
- **AND** the system prompt SHALL contain role guidance for executing and reporting commands

### Requirement: Work Queue Archetype Routing

The coordinator work queue SHALL support archetype-aware task routing and provider-aware model selection.

The `submit_work()` operation SHALL accept optional `agent_requirements` containing:

- `archetype`: preferred archetype name.
- `provider`: optional provider preference.
- `min_trust_level`: optional minimum trust level.

The claim operation SHALL filter available tasks by the claiming agent's declared archetype compatibility and provider identity when those requirements are present.

#### Scenario: Provider preference routes to matching agent

- **WHEN** a task is submitted with `agent_requirements.archetype = "implementer"` and `agent_requirements.provider = "grok"`
- **AND** a grok agent with `archetypes: ["implementer"]` calls claim
- **THEN** the agent SHALL be eligible to claim the task
- **AND** a Codex-only agent SHALL NOT claim that provider-constrained task
