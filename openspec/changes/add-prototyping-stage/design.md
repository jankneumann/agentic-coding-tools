# Design — Add Prototyping Stage

## Context

See `proposal.md` for motivation (Uber AI prototyping blog post; divergence gap on the generation side of the approval gate).

This document records architectural decisions with stable IDs (`D1`..`Dn`) so test tasks can reference them and catch drift at implementation time.

## Architecture Overview

```
/plan-feature              ──► proposal.md approved (Gate 1 in plan-feature)
                                     │
                                     │ user opts in (or iterate-on-plan suggests)
                                     ▼
/prototype-feature         ──► dispatches N variants in parallel worktrees
     (NEW skill)                  prototype/<change-id>/v1 ──► skeleton v1
                                  prototype/<change-id>/v2 ──► skeleton v2
                                  prototype/<change-id>/v3 ──► skeleton v3
                                     │
                                     │ each skeleton scored via
                                     │ /validate-feature --phase smoke,spec
                                     ▼
                              prototype-findings.md + variant diffs
                                     │
                                     │ human pick-and-choose via AskUserQuestion
                                     ▼
/iterate-on-plan              ──► loads prototype context via --prototype-context
  --prototype-context             synthesizes best-of into design.md + tasks.md
     (EXTENDED)                    on FEATURE_BRANCH (not prototype branches)
                                     │
                                     ▼
/implement-feature         ──► normal flow from here
```

## Decisions

### D1: Convergence via iterate-on-plan (not a new skill)

**Decision**: `/iterate-on-plan` gains a `--prototype-context <change-id>` flag. When present, it loads `prototype-findings.md`, variant diffs, and validation reports as additional context and performs convergence-aware refinement. No new `/synthesize-prototypes` skill.

**Rationale**: iterate-on-plan already loads proposal artifacts, applies structured finding detection, iterates to fixed point, and commits refinements. Extending context-loading reuses all of that machinery. Single commit history for design refinement regardless of input source.

**Alternatives rejected**:
- Dedicated `/synthesize-prototypes` skill — duplicates iterate-on-plan's iteration loop and finding conventions.
- Inline synthesis in `/prototype-feature` — mixes generation and refinement concerns; cannot re-synthesize after human feedback without re-dispatching variants.

**Consequences**: iterate-on-plan's finding taxonomy grows to include `convergence.*` types. Its skill doc must document that convergence mode is load-context-only; the iteration loop is unchanged.

### D2: Default 3 variants, configurable via --variants

**Decision**: `/prototype-feature` defaults to N=3. Operators override with `--variants N` where `2 ≤ N ≤ 6`. Values outside the range are rejected.

**Rationale**: 2 variants risks false dichotomy (synthesis collapses to pick-one). 4+ variants increases cost and the risk of Franken-merge during synthesis. 3 is the smallest N that forces genuine synthesis rather than binary choice.

**Consequences**: cost is 3x solo-agent baseline. Post-adoption review: if >30% of invocations use `--variants=2` or `--variants=4`, revisit default.

### D3: Best-effort vendor diversity with single-vendor fallback

**Decision**: At dispatch time, query vendor availability via `vendor-status`. If ≥N distinct vendors reachable, assign one variant per vendor. Otherwise, run all variants on the most-available vendor with distinct angle prompts + temperature/seed variation for stylistic divergence. Never hard-block on vendor availability.

**Rationale**: strict diversity would make the skill unrunnable in common single-vendor environments (e.g., the current harness session has only Claude reachable). Fallback preserves the angle-prompt divergence benefit while losing the "different architectural instincts" benefit of multi-vendor dispatch.

**Alternatives rejected**:
- Strict: require ≥2 distinct vendors — unrunnable in solo-vendor sessions.
- Single-vendor only: never attempt diversity — loses the genuine benefit when vendors are available.

**Consequences**: `prototype-findings.md` records the actual vendor per variant so synthesis can account for "all from same vendor" cases when weighing variant divergence.

### D4: Branch retention through feature lifecycle

**Decision**: Prototype branches (`prototype/<change-id>/v<n>`) persist from `/prototype-feature` through `/cleanup-feature`. Local worktrees pinned to survive the 24h GC timer. `/cleanup-feature` deletes them as part of feature cleanup (local + remote).

**Rationale**: maximum auditability during the pattern's early lifetime. The synthesized `design.md` must be traceable back to variant source material until the feature is merged.

**Trade-off accepted**: N extra branches per change clutters `git branch --list`. Acceptable cost for provenance. Revisit retention policy once the pattern is mature.

### D5: Angle prompts are design values, not personas

**Decision**: Variants are differentiated by **angle prompts** — short phrases describing a design value, not personas. Default angles:

- `simplest` — minimum abstractions, fewest new files, lean on standard library
- `extensible` — plugin points and interfaces first, anticipate future variation
- `pragmatic` — reuse existing patterns in this codebase, minimize new dependencies

Operators override with `--angles "a,b,c"`. The number of angles must match `--variants`.

**Rationale**: fixed personas ("the extensible agent") bias outputs toward caricature. Angle prompts describe *what the variant optimizes for*, letting the model choose structure freely within that constraint.

**Consequences**: default angles live in `skills/prototype-feature/angles.yaml` for per-project override via `openspec/project.md` reference (deferred to post-adoption).

### D6: Scoring uses existing validation phases, not new infrastructure

**Decision**: Each variant skeleton is scored via `/validate-feature --phase smoke,spec`. Results populate `prototype-findings.md`. No new scoring infrastructure.

**Rationale**: heavy phases (deploy, e2e, security) are inappropriate for incomplete skeletons. Smoke + spec-compliance cheaply answer "does this skeleton cover the approved requirements?"

**Consequences**: `/validate-feature` must accept `--phase smoke,spec` on skeleton branches (proposal.md and spec deltas already exist, so spec-compliance can evaluate). If skeletons don't deploy cleanly, smoke phase reports will surface that explicitly — itself a signal.

### D7: Human feedback is pick-and-choose, not pick-one-winner

**Decision**: After variant generation and automated scoring, the human approval step asks: *"Which elements from each variant should carry forward?"* Implementation: `AskUserQuestion` with `multiSelect=true`, options grouped by variant aspect:
- Data model: from v1 / v2 / v3 / rewrite
- API surface: from v1 / v2 / v3 / rewrite
- Test approach: from v1 / v2 / v3 / rewrite
- File layout: from v1 / v2 / v3 / rewrite

**Rationale**: Uber's core insight is that the best design is usually a **synthesis**, not a winner. Forcing pick-one discards partial wins.

**Consequences**: synthesis instructions to `/iterate-on-plan` are richer than "use variant X" — they enumerate cross-variant picks. The `VariantDescriptor` schema carries these selections as structured data.

### D8: Opt-in gating via iterate-on-plan suggestion

**Decision**: `/prototype-feature` never auto-triggers. `/iterate-on-plan` emits a `workflow.prototype-recommended` finding (non-actionable, advisory) when clarity or feasibility findings in the current refinement batch meet a threshold — default: ≥3 high-criticality findings in those two dimensions combined.

**Rationale**: unconditional prototyping is expensive. Gating by uncertainty signals (which is what prototyping addresses) concentrates spend where it's valuable. Explicit user invocation is always primary; the suggestion is informational.

**Consequences**: iterate-on-plan gains one new finding type and one threshold constant. No enforcement logic — humans decide whether to act on the suggestion.

### D9: VariantDescriptor schema extends consensus synthesizer

**Decision**: `skills/parallel-infrastructure/` gains a `VariantDescriptor` schema alongside its existing `ReviewFinding` schema. Fields:

```yaml
variant_id: "v1"              # str
angle: "simplest"             # str
vendor: "claude-opus-4-6"     # str
branch: "prototype/add-foo/v1"
automated_scores:
  smoke:     {pass: true, report: "..."}
  spec:      {covered: 4, total: 5, missing: ["scenario-3"]}
human_picks:
  data_model: true            # bool per aspect
  api:        false
  tests:      true
  layout:     false
synthesis_hint: "prefer this variant's data model for convergence"
```

The consensus synthesizer gains a `synthesize_variants(descriptors) -> synthesis_plan` function that emits a structured plan consumable by iterate-on-plan's `--prototype-context` loader.

**Rationale**: reuses the parallel-infrastructure consensus machinery; keeps variant-aware logic out of individual skills.

**Alternatives rejected**: bespoke schema inside `skills/prototype-feature/` — duplicates synthesizer conventions; reviewers and variants should share structured-finding DNA.

## Open Questions

- Should default angles be tuneable per-project via `openspec/project.md`? Deferred to post-adoption observation.
- What is the minimum proposal size below which prototyping adds no value? Deferred; expect a pattern to emerge from usage.
- Should `/prototype-feature` support re-dispatching a single variant (`--only v2`) after human feedback? Deferred; add if usage demands.
