# Change: retire-skill-literal-model-hints

> Change ID: `retire-skill-literal-model-hints`
> Effort: M
> Parent: `consolidate-model-tier-sources` (PR #538, archived 2026-09-14)
> Status: Scaffold — migrated during post-merge cleanup; needs `/plan-feature` completion before implement

## Follow-up Lineage

Phase 1 (`consolidate-model-tier-sources`) made `archetypes.yaml` the sole
authored source for tier→model and task/phase→tier, and wired review dispatch
to derive premium+thinking from that map. Skill `SKILL.md` files that still
embed literal model ids in `Task(...)` / `Agent(...)` / CLI `-m` examples were
explicitly deferred to this change.

This scaffold was created by `/cleanup-feature consolidate-model-tier-sources
--post-merge --pr 538` so the open F1 task is not lost in the archive.

## Why

Several skills already resolve models via
`coordination_bridge.try_resolve_archetype_for_phase(...)` and pass
`model=<resolved>` (or omit `model=` when resolution fails). Others still
document or dispatch with hardcoded harness ids (e.g. `model="haiku"`,
`codex exec -m gpt-5.6-luna`, narrative mentions of `gpt-5.5` /
`gemini-3.1-pro` as defaults). Those literals reintroduce roster drift: a YAML
tier edit does not update skill prose or example dispatches.

## What Changes

- **INVENTORY** every `SKILL.md` (and closely related skill scripts that embed
  dispatch examples) for literal model / effort hints in `Task`, `Agent`, and
  vendor CLI examples.
- **REPLACE** literals with archetype/phase resolution (same pattern as
  `plan-feature` / `implement-feature` / `iterate-on-*`), falling back to
  omitting `model=` when resolution is unavailable.
- **UPDATE** docs/comments that present a hardcoded model as policy rather than
  an illustrative example.
- **ADD** contract or grep-guard tests so new literal `model="…"` / `-m …`
  policy pins in skills fail CI (allowlist illustrative non-dispatch prose if
  needed).
- **UPDATE** `agent-archetypes` / `skill-workflow` specs as required once the
  inventory defines the exact SHALL statements (this scaffold sets
  `skip_specs: true` until planning completes).

## Non-goals

- Changing `archetypes.yaml` roster membership or tier vocabulary.
- Adaptive/router selection (`add-adaptive-model-router`).
- Re-authoring `DEFAULT_PROVIDER_MODEL_MAP` (emergency fallback only; Phase 1).

## Impact (preliminary)

- Specs: likely `skill-workflow` (MODIFIED); possibly `agent-archetypes`
- Code/docs: `skills/**/SKILL.md` with dispatch examples; any shared resolution
  helper docs; optional CI grep guard under `skills/tests/`
- Known starting hits: `skills/cite-requirements/SKILL.md` (`model="haiku"`,
  `codex exec -m gpt-5.6-luna`); narrative defaults in `skills/plan-roadmap/SKILL.md`

## Next

Run `/plan-feature` (or `/iterate-on-plan`) against this change-id to expand
design, tasks, and spec deltas before `/implement-feature`.
