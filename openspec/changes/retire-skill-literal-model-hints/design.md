# Design: retire-skill-literal-model-hints

## Context

Phase 1 (`consolidate-model-tier-sources`) made `archetypes.yaml` the sole
authored source for tier→model (+ thinking) and task→tier. Lifecycle skills
already resolve via `try_resolve_archetype_for_phase` and pass
`model=<variable>` into harnesses. Remaining drift is **authored skill text**
that still names raw harness model ids/versions (`haiku`, `gpt-5.5`,
`sonnet` in comments, CLI `-m …`). CI (`test_skill_model_hints.py`) still
allows `{opus,sonnet,haiku}` literals.

Harnesses require concrete model ids at invoke time; archetypes mean nothing
to a harness without resolution. Design therefore separates **authored
vocabulary** (archetype/tier) from **dispatch payload** (resolved model id).

## Goals / Non-Goals

**Goals**

- Skills author archetype/tier vocabulary from `archetypes.yaml` (and phase
  mapping), not raw model names/versions as policy.
- Selection of model (+ thinking) always flows from YAML via resolve/tier map.
- CI fails new policy-shaped raw model-id pins (file + line).
- Zero false positives on plan/implement/iterate/fix-scrub resolve patterns.

**Non-goals**

- Editing `archetypes.yaml` roster or tier key vocabulary.
- Native harness `archetype=` parameters (Approach B — deferred).
- Adaptive/router selection.
- Changing `DEFAULT_PROVIDER_MODEL_MAP` emergency fallback.

## Decisions

### D1 — Authored vocabulary vs dispatch payload

Skill markdown SHALL name archetypes (`analyst`, `implementer`, …) and/or
tiers (`economy`, `standard`, `premium`, `frontier`) when describing which
model to use. At dispatch time, skills resolve to a harness model id and pass
`model=<resolved>` (or omit on failure). Skills SHALL NOT pass unresolved
archetype strings into harness APIs that only accept model ids.

### D2 — Dual cheap-tier resolution for cite-requirements

`cite-requirements` keeps dual-vendor annotation. It SHALL resolve the
**economy** (cheap/fast) tier for two distinct providers (e.g. `claude_code`
and `codex`) via the tier map / phase resolution helpers, then dispatch with
those resolved ids. Labels in output JSON MAY record resolved model ids as
*observed run metadata*, but skill instructions MUST NOT hardcode those ids
as the selection policy.

### D3 — Harden `test_skill_model_hints.py` in place

Keep presence checks (`model=` required on Task() in target lifecycle
skills; `try_resolve_archetype_for_phase` present). Replace
`VALID_MODELS = {opus,sonnet,haiku}` acceptance with: **string-literal
`model="…"` is always invalid** in those Task fences (variables OK). Extend
coverage for:

- `Agent(..., model="…")` literals in skills that document Agent dispatch
- vendor CLI `-m <literal>` in fenced dispatch examples
- optional scan of known narrative policy pins (plan-roadmap) for raw
  model-version tokens used as defaults

False-positive target: 0 on the five resolve-pattern lifecycle skills after
comment rewrites (D4).

### D4 — Illustrative comments and escape hatches

Rewrite comments like `# archetype: implementer (sonnet, or opus if
escalated)` to tier/archetype-only language (e.g. `# archetype: implementer
(standard tier; frontier on escalation)`).

Operator override env examples (e.g. `AUTOPILOT_PHASE_MODEL_OVERRIDE`) MAY
still show harness model ids **only when labeled as an explicit escape hatch
that bypasses YAML selection**, not as the default policy. Prefer documenting
override in terms of phases → resolved ids from the live map when possible.

### D5 — Spec end-state

MODIFIED `agent-archetypes` “Skill Model Hint Integration”: remove Phase 1
literal `model="sonnet"|"haiku"` as a valid end state; require resolve →
variable (or omit) and archetype/tier authored vocabulary. MODIFIED/ADDED
`skill-workflow` requirement: skill-authored dispatch examples SHALL NOT pin
raw model versions as policy.

### D6 — Stay off concurrent roster surfaces

Do not modify `archetypes.yaml`, `review_dispatcher` premium resolution, or
adaptive-router proposals. This change is skill docs + CI + specs only.

## Fitness Functions

| NFR | Verifying check | Status |
|-----|-----------------|--------|
| Compatibility (0 FP on lifecycle skills) | `test_skill_model_hints` green on five targets | extend |
| Drift prevention (literals fail) | Assert string `model="…"`, `-m <lit>`, Agent literals fail | new |
| Spec integrity | `openspec validate retire-skill-literal-model-hints --strict` | plan |

## Alternatives Considered

- Native `archetype=` on Task/Agent (Approach B) — deferred; harnesses need
  model ids without resolution support today.
- Separate anti-literal scanner + allowlist file (Approach B in early draft)
  — rejected as extra machinery for a small inventory; harden in place (D3).
- Guard-and-spec only without narrative rewrite — rejected; leaves authored
  raw versions in skills.
