# Tasks: consolidate-model-tier-sources

TDD order within each WP: tests before implementation. None complete yet.

## WP1 — YAML sole tier map (D1)

- [x] 1.1 Write tests: `get_provider_model_map()` / resolution prefer loaded
  `archetypes.yaml::model_aliases`; when YAML is missing/unreadable, fall back
  to `DEFAULT_PROVIDER_MODEL_MAP` with a structured warning; expectations derive
  from YAML fixtures, not Python-map literals as authored policy
  **Spec scenarios**: agent-archetypes — YAML is sole authored tier map;
  emergency fallback when YAML unavailable
  **Design decisions**: D1
  **Dependencies**: None
  **Files**: `agent-coordinator/tests/test_agents_config.py`,
  `skills/tests/vendor-neutral-autopilot/test_contracts.py`

- [x] 1.2 Demote `DEFAULT_PROVIDER_MODEL_MAP` to emergency-fallback semantics;
  remove "keep in sync" authorship comments from Python and
  `archetypes.yaml`; ensure load path remains YAML-first
  **Dependencies**: 1.1
  **Files**: `agent-coordinator/src/agents_config.py`,
  `agent-coordinator/archetypes.yaml`

- [x] 1.3 Checkpoint: coordinator + vendor-neutral-autopilot contract tests green

## WP2 — Phase signals from YAML (D2)

- [x] 2.1 Write tests: phase→archetype→tier resolution and any status/reporting
  consumers read `phase_mapping` / archetypes from YAML (or coordinator), with
  no hardcoded phase→model table as policy
  **Spec scenarios**: agent-archetypes — consumers MUST load YAML for
  task→tier
  **Design decisions**: D2
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/tests/test_phase_archetype_resolution.py`,
  related consumer tests

- [x] 2.2 Remove or rewire hardcoded phase/tier mirrors so consumers load YAML
  (or the resolve-for-phase API that does)
  **Dependencies**: 2.1
  **Files**: consumers under `agent-coordinator/` / skills bridges as found by 2.1

- [x] 2.3 Checkpoint: phase-resolution suite green

## WP3 — Review derives premium + thinking_flags (D3, D4)

- [x] 3.1 Write tests for `thinking_flags` helper: maps thinking values to
  vendor CLI fragments (Claude effort, Codex reasoning effort, Grok, …);
  unknown vendor yields no flags
  **Spec scenarios**: skill-workflow — inject vendor thinking flags
  **Design decisions**: D4
  **Dependencies**: None (can start after 1.2 in sequence)
  **Files**: `skills/tests/parallel-infrastructure/` (new or existing helper tests)

- [x] 3.2 Write tests: review-mode dispatch resolves model+thinking from tier
  map premium (YAML-backed); does not rely on hardcoded premium ids / effort
  in `agents.yaml` as source of truth
  **Spec scenarios**: skill-workflow — review dispatcher resolves from tier
  map; agents.yaml SHALL NOT hardcode premium review model/effort
  **Design decisions**: D3, D4
  **Dependencies**: 3.1
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`,
  `skills/tests/parallel-infrastructure/`

- [x] 3.3 Implement `thinking_flags` helper and wire `review_dispatcher` to
  resolve premium+thinking from the tier map and inject flags at command build
  **Dependencies**: 3.1, 3.2
  **Files**: `skills/parallel-infrastructure/scripts/` (helper +
  `review_dispatcher.py`)

- [x] 3.4 Strip review-mode hardcoded premium model ids and effort/reasoning
  flags from `agents.yaml`; document that review overrides come from the tier
  map
  **Dependencies**: 3.3
  **Files**: `agent-coordinator/agents.yaml`

- [x] 3.5 Checkpoint: review_dispatcher + parallel-infrastructure tests green

## WP4 — Schema catch-up (D5)

- [x] 4.1 Write/adjust contract tests: provider-model-map schema describes
  YAML-normalized shape; DEFAULT map is fallback-only; no dual-authorship
  assertion
  **Spec scenarios**: agent-archetypes — consumers load YAML; schema shape
  **Contracts**: `openspec/schemas/provider-model-map.schema.json`
  **Design decisions**: D5
  **Dependencies**: 1.2, 3.4
  **Files**: `skills/tests/vendor-neutral-autopilot/test_contracts.py`

- [x] 4.2 Update `provider-model-map.schema.json` description (and any related
  docs comments) for sole-authored YAML + emergency Python fallback; no new
  API contracts
  **Dependencies**: 4.1
  **Files**: `openspec/schemas/provider-model-map.schema.json`,
  `openspec/changes/consolidate-model-tier-sources/contracts/README.md`

- [x] 4.3 Final verify: coordinator suite, parallel-infrastructure,
  vendor-neutral-autopilot, `openspec validate consolidate-model-tier-sources --strict`

## Follow-up (out of scope)

- [ ] F1 File/plan `retire-skill-literal-model-hints` — replace skill
  `Task(model=…)` literals with archetype/tier resolution (Phase 2)
