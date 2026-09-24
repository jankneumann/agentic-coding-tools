# Change: consolidate-model-tier-sources

**Status**: Approved (Gate 1)
**Created**: 2026-09-13

## Why

Tier→model and task→tier mappings are authored twice today: once in
`agent-coordinator/archetypes.yaml` (`model_aliases`, `archetypes`,
`phase_mapping`) and again as `DEFAULT_PROVIDER_MODEL_MAP` in
`agents_config.py`, with "keep in sync" comments on both sides. Review
dispatch also hardcodes premium model ids and effort flags in
`agents.yaml`, so a YAML tier edit does not reach review mode. Drift is
manual and recurring; tests that assert Python-map literals punish
legitimate roster tuning.

## What Changes

- **KEEP** both conceptual maps in `archetypes.yaml` only:
  - `model_aliases` = tier → model (+ optional thinking)
  - `archetypes` + `phase_mapping` = task/phase → tier
- **DELETE** dual authorship of the tier→model roster in
  `DEFAULT_PROVIDER_MODEL_MAP` — that constant becomes an emergency
  fallback used only when YAML cannot be loaded.
- **UPDATE** `review_dispatcher` to derive review premium model and thinking
  from the loaded tier map, injecting vendor thinking flags via a shared
  helper.
- **UPDATE** `agents.yaml` so review mode does not hardcode premium model
  ids or effort/reasoning flags.
- **UPDATE** schema/docs/tests so the stable contract describes YAML as the
  authored source and the Python map as fallback-shaped.
- **DEFER** skill `Task()` literal model hints to follow-up change
  `retire-skill-literal-model-hints` (Phase 2).

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by |
|-----------|--------|--------|-------------|
| Single authored source | Grep / contract tests for dual roster authorship | Zero "keep in sync" obligations; tests derive expectations from loaded YAML | WP1 + WP4 tests |
| Review/YAML parity | Review dispatch model+thinking vs `model_aliases.<provider>.premium` | Byte-equal for every roster provider | WP3 tests |
| Fallback safety | Behavior when YAML missing/unreadable | `DEFAULT_PROVIDER_MODEL_MAP` used; structured warning | WP1 tests |

## Approaches Considered

### Approach A — YAML sole author; Python emergency fallback (Recommended)

Keep both definitions in `archetypes.yaml`. Demote
`DEFAULT_PROVIDER_MODEL_MAP` to load-failure fallback. Review derives
premium+thinking from YAML; thinking flags injected at dispatch.

- **Pros**: One edit site for roster/tier policy; matches existing
  `load_archetypes_config` path; preserves offline/boot safety.
- **Cons**: Fallback can still drift from YAML (acceptable — emergency
  only; tests must not treat it as authored).
- **Effort**: M

### Approach B — Delete Python map; fail closed without YAML

Remove `DEFAULT_PROVIDER_MODEL_MAP` entirely; resolution fails if YAML
is absent.

- **Pros**: Absolute single source.
- **Cons**: Breaks tests/tools that import resolution before a path is
  wired; worse boot failure mode.
- **Effort**: S–M

### Approach C — Generate Python map from YAML at build/install

Keep a generated constant checked into git or produced by `install.sh`.

- **Pros**: Import-time availability without runtime YAML read.
- **Cons**: Regenerates dual authorship as a build artifact; still two
  trees to reconcile in PRs.
- **Effort**: M

### Selected Approach

**Approach A** — keep both definitions in `archetypes.yaml`
(`model_aliases` = tier→model; `archetypes`+`phase_mapping` = task→tier);
delete dual `DEFAULT_PROVIDER_MODEL_MAP` authorship; `review_dispatcher`
derives premium+thinking from YAML; Phase 2 follow-up
`retire-skill-literal-model-hints` for skill `Task()` literals.

## Impact

- Specs: `agent-archetypes` (MODIFIED), `skill-workflow` (MODIFIED)
- Code: `agent-coordinator/src/agents_config.py`,
  `agent-coordinator/archetypes.yaml`, `agent-coordinator/agents.yaml`,
  `skills/parallel-infrastructure/scripts/review_dispatcher.py` (+ helper),
  related tests, `openspec/schemas/provider-model-map.schema.json` (docs/shape catch-up)
- Out of scope: skill `SKILL.md` `Task(model=…)` literals (follow-up)
