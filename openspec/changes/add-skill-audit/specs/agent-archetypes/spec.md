# agent-archetypes — delta for add-skill-audit

Adds an optional `procedure_mode` field to each archetype so tier-dependent
procedure density is declared in the roster and injected at resolution time,
instead of being implied by skill prose that every tier reads identically.

## MODIFIED Requirements

### Requirement: Archetype Definition Schema

The system SHALL support an `archetypes.yaml` configuration file that defines named agent archetypes. Each archetype SHALL specify:

- A logical model tier or legacy model alias.
- `system_prompt`: role-specific instruction prefix composed with task prompts.
- `escalation`: optional rules for complexity-based tier or model upgrade.
- `procedure_mode`: optional, one of `verbatim`, `guided`, or `goal-directed`, declaring how much of a skill's written procedure an agent running under this archetype is expected to follow. When omitted the archetype SHALL behave as `guided`. `schema_version: 4` introduces the field; files at `schema_version: 3` SHALL continue to validate and load with every archetype treated as `guided`.

Archetype model values SHALL be resolved through provider-aware model mapping before dispatch. Legacy Claude aliases (`opus`, `sonnet`, `haiku`) SHALL remain valid for Claude Code compatibility, but non-Claude providers SHALL receive provider-specific model IDs.

Archetype names SHALL match the pattern `^[a-z][a-z0-9_-]{0,31}$` and SHALL be validated at all system boundaries.

Provider-aware resolution SHALL cover exactly the supported roster: `claude_code`, `codex`, `antigravity`, `grok`, `pi`, and `local`. Resolution SHALL fail with a structured configuration error for the retired `gemini` provider rather than silently falling back to a Claude alias.

The `local` provider roster SHALL define at minimum the `standard` and `economy` tiers. Tiers omitted by the `local` roster SHALL resolve through the existing graceful-degradation rule (an omitted tier resolves to the provider's best defined tier). Resolution output for providers other than `local` SHALL be byte-identical to resolution output before this change.

The JSON schema at `skills/autopilot/install_assets/openspec/schemas/archetypes.schema.json` SHALL accept `procedure_mode` with the enumerated values and SHALL continue to reject any other unknown key on an archetype.

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

#### Scenario: procedure_mode absent loads as guided

- **WHEN** an `archetypes.yaml` at `schema_version: 3` with no `procedure_mode` keys is loaded
- **THEN** loading SHALL succeed
- **AND** every `ArchetypeConfig.procedure_mode` SHALL equal `guided`

#### Scenario: Unknown procedure_mode is rejected

- **WHEN** an archetype declares `procedure_mode: strict`
- **THEN** schema validation SHALL fail naming the archetype and the offending value
- **AND** `load_archetypes_config` SHALL raise a structured configuration error

#### Scenario: Unknown archetype keys are still rejected

- **WHEN** an archetype declares a key other than `model`, `system_prompt`, `write_capable`, `escalation`, or `procedure_mode`
- **THEN** schema validation SHALL fail

## ADDED Requirements

### Requirement: Procedure Mode Prompt Injection

`resolve_archetype_for_phase` SHALL append exactly one fixed sentence to the
returned `system_prompt` according to the resolved archetype's
`procedure_mode`, separated from the archetype prompt by a blank line, and
SHALL include `procedure_mode` as a field of `ResolvedArchetype` and of the
`POST /archetypes/resolve_for_phase` response. For `guided` no sentence SHALL
be appended and the response SHALL be byte-identical to the response before
this change apart from the added `procedure_mode` field. The sentences SHALL
be defined once, as module-level constants in `agents_config.py`:

- `verbatim`: "Follow the skill's written procedure step by step; do not skip, reorder, or merge steps."
- `goal-directed`: "Satisfy the skill's acceptance probes by whatever route is sound; where you deviate from the written procedure, record each deviation as a session-log Decision with capability `skill-procedure-deviation`."

Escalation SHALL NOT change `procedure_mode`: the mode is a property of the
archetype, not of the model tier the archetype escalates to. The coordination
bridge `try_resolve_archetype_for_phase` SHALL pass `procedure_mode` through
when present and SHALL NOT require it, so older coordinators keep working.

The authored roster SHALL set `runner` to `verbatim` and `architect` to
`goal-directed`; tests SHALL derive expectations from the YAML rather than
asserting those literals.

#### Scenario: Verbatim archetype gets the verbatim sentence

- **WHEN** `resolve_archetype_for_phase("INIT", {})` runs against a roster where `runner.procedure_mode` is `verbatim`
- **THEN** `system_prompt` SHALL end with the `verbatim` sentence
- **AND** `procedure_mode` SHALL equal `verbatim`

#### Scenario: Goal-directed archetype names the deviation ledger

- **WHEN** `resolve_archetype_for_phase("PLAN", {})` runs against a roster where `architect.procedure_mode` is `goal-directed`
- **THEN** `system_prompt` SHALL end with the `goal-directed` sentence
- **AND** that sentence SHALL contain `skill-procedure-deviation`

#### Scenario: Guided archetype is unchanged

- **WHEN** `resolve_archetype_for_phase("IMPLEMENT", {})` runs against a roster where `implementer` has no `procedure_mode`
- **THEN** `system_prompt` SHALL equal the implementer's `system_prompt` exactly
- **AND** `procedure_mode` SHALL equal `guided`

#### Scenario: Escalation preserves the mode

- **WHEN** `implementer` escalates to `premium` on a `loc_estimate` signal
- **THEN** `procedure_mode` in the result SHALL be the implementer's declared mode, not the mode of any other archetype

#### Scenario: Bridge tolerates an older coordinator

- **WHEN** the coordinator response lacks `procedure_mode`
- **THEN** `try_resolve_archetype_for_phase` SHALL return the response unchanged
- **AND** callers SHALL treat the mode as `guided`
