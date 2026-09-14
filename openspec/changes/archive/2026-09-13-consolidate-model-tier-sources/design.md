# Design: consolidate-model-tier-sources

## Context

`archetypes.yaml` already holds `model_aliases`, `archetypes`, and
`phase_mapping`. `agents_config.load_archetypes_config` already prefers
YAML for the live provider map. The remaining defect is dual *authorship*
(Python constant + YAML kept "in sync") plus review-path hardcoding in
`agents.yaml` / dispatch args that bypass the tier map's thinking field.

## Goals / Non-Goals

**Goals**

- One authored tier→model map: `archetypes.yaml::model_aliases`.
- One authored task→tier map: `archetypes.yaml` archetypes + `phase_mapping`.
- Review dispatch consumes that map for premium model + thinking.
- Vendor thinking CLI flags come from one helper, not per-agent literals.

**Non-goals**

- Retiring skill `Task()` model literals (follow-up
  `retire-skill-literal-model-hints`).
- Changing tier vocabulary or roster membership.
- Adaptive/router selection (`add-adaptive-model-router`).

## Decisions

### D1 — YAML sole tier map

`archetypes.yaml::model_aliases` is the only place operators author
tier→model (+thinking). `DEFAULT_PROVIDER_MODEL_MAP` remains as an
**emergency fallback** when YAML cannot be loaded; it is not a second
roster to maintain. Comments and tests that require "keep in sync" are
removed. Tests derive expectations from the loaded YAML map.

### D2 — Phase signals from YAML

Task/phase → tier continues to live only in `archetypes` +
`phase_mapping`. Consumers (resolve-for-phase, status reporting, skill
bridges) MUST load YAML (or the coordinator endpoint that does) rather
than hardcoding phase→model or phase→tier tables.

### D3 — Review derives premium

For `--mode review`, `review_dispatcher` resolves each vendor's model
(and thinking) from the provider tier map's `premium` entry (or the
reviewer archetype's resolved tier when that path is already wired),
instead of trusting hardcoded `cli.model` / effort args as the policy
source. `agents.yaml` MAY keep non-review defaults and fallbacks, but
SHALL NOT hardcode premium model ids or effort flags as the review-mode
source of truth.

### D4 — `thinking_flags` helper

A shared helper translates a resolved `thinking` value into vendor CLI
flag fragments (Claude `--effort`, Codex `model_reasoning_effort`, Grok
reasoning-effort, etc.). Review (and later other modes) inject those
flags at command build time rather than baking them into
`dispatch_modes.*.args`.

### D5 — Schema catch-up

`openspec/schemas/provider-model-map.schema.json` (and contract tests)
document the authored source as YAML `model_aliases` normalized to the
schema shape; the Python default is fallback-shaped. No new API contract
surface.

## Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Single authored source | Tests + grep: no keep-in-sync dual authorship; expectations from YAML | new |
| Review/YAML parity | Dispatcher tests: review model+thinking == map premium | new |
| Fallback safety | Unit test: missing YAML → DEFAULT map + warning | new |

## Alternatives Considered

- Fail-closed without YAML (Approach B) — rejected; breaks import-time
  and degraded-boot paths.
- Generated Python map (Approach C) — rejected; reintroduces dual trees.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Fallback drifts silently | Document emergency-only; tests never assert DEFAULT == YAML as policy |
| Vendor flag vocab differs | Helper owns translation; unknown vendor → no flag, model still applied |
| agents.yaml residual model fields confuse readers | Comments state review overrides from tier map; non-review may still use cli.model |

## Migration Plan

1. WP1–WP2: coordinator sole-source + consumer load path (behavior
   unchanged when YAML present).
2. WP3: review derivation + thinking_flags; strip review hardcodes.
3. WP4: schema/docs/tests catch-up.
4. Rollback: restore prior `agents.yaml` review args and dispatcher
   model selection; fallback path already preserves boot.
