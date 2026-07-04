# Design: Add Product-Management Skills

Design decisions referenced by `tasks.md` as `Dxx`. These record *why* the change is shaped the
way it is, not the task-by-task mechanics.

## D1 — Seam test as the inclusion criterion

A PM skill is included only if its output is consumed by, or its input produced by, an existing
skill (the "seam test", see the gap-analysis doc). This keeps the change from importing an island
of PM tooling and forces every ported skill to have a wiring in Phase 2. 12 of 68 skills pass;
the rest are non-goals. **Consequence:** the unit of work is the *seam*, not the *skill* — Phase 1
authors skills, Phase 2 proves they are consumed.

## D2 — Two capabilities, not one

The skill-suite mechanics (porting, `user_invocable`, tail block, tests) extend the existing
`skill-workflow` capability, matching the `add-engineering-methodology-skills` precedent. The
*seam contracts* (artifact flows into orchestrators, template/schema extensions, verification seam)
are a genuinely new capability, `product-discovery-workflow`, because they describe a new pipeline
stage rather than a property of the skills system. Splitting keeps each spec delta coherent and
lets the discovery capability evolve independently later.

## D3 — Adopt content, keep our schema (localization over wholesale import)

`phuryn/pm-skills` uses a marketplace/plugin format with minimal frontmatter. We keep our richer
schema (`triggers` for discovery, `requires` for gating, `user_invocable` for palette control,
`related` for the graph) and re-express each skill's output in our artifacts: `create-prd` renders
a `proposal.md`; `opportunity-solution-tree` leaves are change candidates; red-team/pre-mortem
findings use the `iterate-on-plan` finding shape; `user-stories`/`test-scenarios` emit WHEN/THEN
scenarios. **Consequence:** each port is an authoring task, not a copy — but it plugs in with zero
adapter code.

## D4 — `prioritization-frameworks` is a reference, not a skill

It is a lookup table of methods (RICE/WSJF/Kano/MoSCoW), not a workflow with a trigger. It ships
under `skills/references/` (existing library) and is cited by the two seam-2 skills. This avoids a
palette entry that would only ever be read, and reuses the `references/` install path already
validated by `install.sh`.

## D5 — `user_invocable` assignments

Eleven of twelve are `true`: each is something an operator triggers ad-hoc at a decision point
(write a PRD, red-team a plan, prioritize, author stories, check drift). Only `shipping-artifacts`
is `false` — it is loaded by `cleanup-feature` at ship time, not invoked standalone, matching how
`browser-testing-with-devtools` is orchestrator-loaded by `validate-feature`.

## D6 — Seam wirings are additive and single-touch

Every adaptation to an existing skill is **additive** (a new optional step / scoring lens / template
section) and never removes or reorders existing behavior — a proposal with no PRD still validates,
a prioritization with no PM scoring still ranks. Each existing skill is edited exactly once
(Phase 2 clusters by target file) to avoid double-touch conflicts, per the methodology precedent.

## D7 — Template extensions are optional sections

The proposal and roadmap template edits add *optional* sections/fields. Existing changes and
roadmaps remain valid without them (backward compatible). This is what lets Phase 2 wirings land
without a migration of in-flight changes.

## D8 — No new install mechanism

`related:` validation and `references/` rsync already exist (shipped by the methodology change).
This change only *adds data* to those mechanisms; `install.sh` is touched only if a new `related:`
target needs the existing validator re-run. No runtime, coordinator, DB, or MCP surface changes.

## D9 — Test strategy reuses the shared content-invariant framework

Each new skill's `test_skill_md.py` invokes the existing `skills/tests/_shared/conftest.py`
assertions. No new test framework; the only new test data is the 12 skill dirs and the
`prioritization-frameworks.md` reference. Content invariants (tail block present & ordered,
frontmatter parses, `related:`/`references:` resolve) run in CI-eligible unit scope (no DB).

## Phasing rationale (scaffold-then-content, Approach C)

Phase 0 ships the convention and the seam *targets* (template sections, reference doc, testpath
placeholders) before content, so Phase 1 skills are born correct and Phase 2 wirings have something
to wire into. Phases 1 and 2 fan out one work package per seam / per target-cluster. Phase 3
integrates (install dry-run, `related:` resolution, `openspec validate --strict`, catalogue, log).
This is the same structure that shipped `add-engineering-methodology-skills` successfully.
