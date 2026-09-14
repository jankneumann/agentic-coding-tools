## ADDED Requirements

### Requirement: Skill-Authored Model Vocabulary from Archetypes

Skills under `skills/**/SKILL.md` (and skill-owned templates that instruct
dispatch) SHALL treat `agent-coordinator/archetypes.yaml` as the vocabulary
source for model and thinking selection. When describing which model to use,
skills SHALL name archetypes and/or tiers from that file (via phase mapping
or explicit tier), not raw harness model names or versions as default policy.

Dispatch examples that invoke a harness (`Task`, `Agent`, or vendor CLI) SHALL
resolve to harness-specific model ids at runtime and MUST NOT embed those ids
as the authored selection policy. Observed resolved ids MAY appear in run
artifacts or escape-hatch override documentation when clearly labeled as
non-default.

#### Scenario: Dispatch examples do not hardcode model versions

- **WHEN** a skill documents a fenced harness dispatch that selects a model
- **THEN** the selection policy in that example SHALL reference archetype/tier
  resolution (or an already-resolved variable produced by that resolution)
- **AND** SHALL NOT use a string-literal raw model id as the policy source

#### Scenario: Narrative defaults use tier or vendor-role language

- **WHEN** a skill describes a default generator or annotator model in prose
- **THEN** it SHALL name an archetype, tier, or vendor role resolved from the
  tier map
- **AND** SHALL NOT present a concrete model version string as the standing
  default

#### Scenario: Dual-vendor annotation resolves two economy tiers

- **WHEN** `cite-requirements` (or similar) dispatches two annotators for
  diversity
- **THEN** each annotator’s model SHALL be obtained by resolving a cheap/fast
  (`economy`) tier for a distinct provider
- **AND** the skill SHALL NOT hardcode the two model ids as selection policy
