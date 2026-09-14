# Change: retire-skill-literal-model-hints

**Status**: Approved (Gate 1) — Approach A
**Created**: 2026-09-14
**Parent**: `consolidate-model-tier-sources` (PR #538, archived)

## Why

Phase 1 made `archetypes.yaml` the sole authored tier→model (+ thinking) and
task→tier source. Operators still see **raw harness model ids and versions**
in skill instructions (`model="haiku"`, `gpt-5.5`, `sonnet` in comments,
`codex exec -m …`). Those strings drift whenever the roster changes, even when
YAML is already correct.

**Underlying need (confirmed):** every model and thinking-level *selection*
comes from `archetypes.yaml`; skills reference **archetypes / tiers** named
there (or resolve through the phase→archetype→tier API), not raw model names
and versions.

## What Changes

- **INVENTORY** `skills/**/SKILL.md` (and closely related skill templates) for
  raw model id / version tokens used as policy or dispatch defaults — including
  `Task`/`Agent` literals, CLI `-m`, and narrative “default model” pins.
- **REPLACE** those with archetype or tier references plus runtime resolution
  (`try_resolve_archetype_for_phase` / tier map), including
  `cite-requirements` dual-annotation via **two cheap/fast tier resolutions**
  that preserve vendor diversity.
- **UPDATE** illustrative comments that name concrete models (e.g. “sonnet, or
  opus if escalated”) to tier/archetype language drawn from YAML vocabulary.
- **HARDEN** CI (`test_skill_model_hints.py` and/or companion assertions) so
  new raw model-id policy pins in skill dispatch/prose fail with file+line;
  keep **0 false positives** on skills that already use resolve→`model=<var>`.
- **UPDATE** `agent-archetypes` / `skill-workflow` so Phase 1 literal `model=`
  is no longer a valid end state; skills SHALL NOT author raw model versions as
  policy.
- **DO NOT** edit `archetypes.yaml` roster membership, adaptive router, or tier
  vocabulary keys (coexist with `add-adaptive-model-router` /
  `add-frontier-model-tier`).

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by |
|-----------|--------|--------|-------------|
| Compatibility | False positives on resolve-pattern lifecycle skills | 0 failures on plan/implement/iterate/fix-scrub | Guard tests |
| Drift prevention | New raw model-id policy pins in skills | CI red (file + line) | Guard tests |
| Spec integrity | `openspec validate … --strict` | Exit 0 | Plan / validate |

## Approaches Considered

### Approach A — Tier/archetype vocabulary + harden guard (Recommended)

Skills keep today’s working pattern (`resolve` → `model=<var>` or omit) for
harness dispatch, but **authored skill text** only names archetypes/tiers from
YAML (never raw model versions as policy). Inventory and rewrite remaining
hits (cite-requirements dispatch, plan-roadmap narrative defaults, illustrative
sonnet/opus comments). Harden `test_skill_model_hints.py` to ban string-literal
`model="…"`, CLI `-m <literal>`, and (with a tight pattern) other policy-shaped
raw model tokens; allow variables and archetype/tier names. Update specs
accordingly.

- **Pros**: Matches the clarified goal without requiring harnesses to grow an
  `archetype=` parameter; reuses Phase 1 resolve path; covers narrative +
  dispatch drift; stays off `archetypes.yaml` / router.
- **Cons**: Guard must distinguish policy pins from unavoidable mentions (e.g.
  historical archive quotes) — needs a small allowlist or scoped paths;
  comment rewrites touch more SKILL.md lines than dispatch-only.
- **Effort**: M

### Approach B — Native `archetype=` on Task/Agent (spec’s original Phase 2+)

Migrate skills to pass `archetype="analyst"` (etc.) and teach harnesses /
adapters to resolve archetype→model(+thinking) from YAML at dispatch time.
Ban `model=` literals *and* eventually prefer archetype params over resolved
model variables in skill text.

- **Pros**: Closest to the written Phase 2+ wording in agent-archetypes; skills
  never even pass a model string.
- **Cons**: Requires harness/adapter support beyond SKILL.md edits; larger,
  cross-cutting, likely blocked on multiple vendors; overlaps adaptive-router
  work; effort jumps to L+.
- **Effort**: L

### Approach C — Guard-and-spec only (no skill body rewrite beyond cite-requirements)

Update specs + CI to forbid raw model ids; only fix cite-requirements
dispatch; leave plan-roadmap narrative and sonnet/opus comments for later.

- **Pros**: Smallest diff.
- **Cons**: Leaves authored drift in place — fails the clarified goal that
  *all* skills reference archetypes/tiers, not raw versions.
- **Effort**: S–M

### Recommended

**Approach A** — keep resolve→`model=<var>` as the execution mechanism, but
make **authored skill vocabulary** archetype/tier-only and enforce with CI.
That delivers “selection comes from `archetypes.yaml`” without waiting on
native `archetype=` harness support (Approach B).

### Selected Approach

**Approach A** (Gate 1, 2026-09-14).

Operator clarification: harnesses still require harness-specific model ids in
their parameters — archetypes are meaningless to a harness without resolution.
Therefore skills author archetype/tier vocabulary and resolve to model ids at
dispatch time; they do **not** pass unresolved archetype names into the harness.

Demoted alternatives:
- **B** (native `archetype=`): deferred — needs cross-harness adapter work;
  may become a later follow-up if desired.
- **C** (guard-and-spec only): rejected — leaves authored raw model versions
  in skill text, missing the clarified goal.

## Impact

- Specs: `agent-archetypes` (MODIFIED), `skill-workflow` (MODIFIED)
- Code/docs: `skills/**/SKILL.md` (inventory-driven; known: cite-requirements,
  plan-roadmap + template, illustrative comments in lifecycle skills);
  `skills/validate-packages/scripts/tests/test_skill_model_hints.py`
- Layers: Execution (skill instructions) + Governance (spec/CI)
- Rollback: revert skill text + guard + spec deltas (not a runtime API break)
