# agent-archetypes Delta: add-local-model-provider-tier

## MODIFIED Requirements

### Requirement: Archetype Definition Schema

The system SHALL support an `archetypes.yaml` configuration file that defines named agent archetypes. Each archetype SHALL specify:

- A logical model tier or legacy model alias.
- `system_prompt`: role-specific instruction prefix composed with task prompts.
- `escalation`: optional rules for complexity-based tier or model upgrade.

Archetype model values SHALL be resolved through provider-aware model mapping before dispatch. Legacy Claude aliases (`opus`, `sonnet`, `haiku`) SHALL remain valid for Claude Code compatibility, but non-Claude providers SHALL receive provider-specific model IDs.

Archetype names SHALL match the pattern `^[a-z][a-z0-9_-]{0,31}$` and SHALL be validated at all system boundaries.

Provider-aware resolution SHALL cover exactly the supported roster: `claude_code`, `codex`, `antigravity`, `grok`, `pi`, and `local`. Resolution SHALL fail with a structured configuration error for the retired `gemini` provider rather than silently falling back to a Claude alias.

The `local` provider roster SHALL define at minimum the `standard` and `economy` tiers. Tiers omitted by the `local` roster SHALL resolve through the existing graceful-degradation rule (an omitted tier resolves to the provider's best defined tier). Resolution output for providers other than `local` SHALL be byte-identical to resolution output before this change.

#### Scenario: Archetype resolves for local provider

- **WHEN** `runner` resolves under provider `local`
- **THEN** the logical role SHALL remain `runner`
- **AND** the dispatch model SHALL be a model identifier from the `local` roster in provider mapping
- **AND** no Claude alias SHALL be dispatched to the `local` provider

#### Scenario: Local roster omits a tier

- **WHEN** an archetype whose tier is `frontier` or `premium` resolves under provider `local`
- **THEN** resolution SHALL degrade to the best tier the `local` roster defines
- **AND** the resolution reasons SHALL record the degradation

#### Scenario: Existing providers are unaffected

- **WHEN** any archetype resolves under `claude_code`, `codex`, `antigravity`, `grok`, or `pi`
- **THEN** the resolved model, system prompt, and reasons SHALL be identical to resolution before the `local` roster existed
- **AND** no `local` roster entry SHALL influence the result

## ADDED Requirements

### Requirement: Local Roster Hardware Matching

The `local` provider roster SHALL be selected by model architecture against the serving host's memory-bandwidth constraint, not by parameter count fitting host memory. Each `local` roster entry MUST declare its total and active parameter counts in a roster comment, MUST respect the configured active-parameter ceiling for the host class (GB10-class default: 12B active), and MUST carry an operator-signed review date. Dense models at or above 30B parameters MUST NOT be roster entries on bandwidth-bound host classes even when they fit in host memory.

#### Scenario: MoE roster entry accepted

- **WHEN** the roster adds a mixture-of-experts model whose declared active parameter count is at or below the host-class ceiling
- **THEN** roster validation SHALL accept the entry
- **AND** the entry SHALL record total parameters, active parameters, and a review date

#### Scenario: Dense large model rejected

- **WHEN** the roster adds a dense model at or above 30B parameters for a bandwidth-bound host class
- **THEN** roster validation SHALL fail with a structured error naming the hardware-matching rule
- **AND** coordinator startup SHALL surface the error rather than serving the invalid roster

### Requirement: Local Provider Archetype Trust Boundary

Archetype resolution SHALL permit the `local` provider only for archetypes whose output is cheap to discard or verified downstream: `runner`, `analyst`, `documenter`, and `validator`. Resolution for `architect`, `reviewer`, and `gatekeeper` archetypes MUST NOT return provider `local`, and a dispatch request pairing those archetypes with provider `local` SHALL fail with a structured error before any dispatch is attempted.

#### Scenario: Permitted archetype resolves locally

- **WHEN** phase INIT resolves archetype `runner` under provider `local`
- **THEN** resolution SHALL succeed
- **AND** the resolution reasons SHALL note the local trust boundary was checked

#### Scenario: Boundary archetype refused

- **WHEN** a dispatch requests archetype `reviewer` with provider `local`
- **THEN** resolution SHALL fail with a structured error naming the trust boundary and the permitted archetype list
- **AND** no dispatch SHALL be attempted
- **AND** the refusal SHALL be recorded in the audit log
