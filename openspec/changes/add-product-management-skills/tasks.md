# Tasks

Phase ordering is sequential at the phase level; within Phases 1 and 2, packages run in parallel.
Within each package, test tasks precede the implementation they verify. Design decisions referenced
as `Dxx` live in [`design.md`](design.md).

## Phase 0 — Scaffold the convention and seam targets (sequential, work package `wp-scaffold`)

- [ ] 0.1 Create `skills/references/prioritization-frameworks.md`
  - **Spec scenarios**: `skill-workflow.reference-installed-alongside-skills`, `skill-workflow.reference-is-cited-not-discovered`
  - **Design decisions**: D4
  - **Dependencies**: None
  - Catalogue RICE, WSJF, Kano, MoSCoW (minimum) with a one-line "use when" each; no `SKILL.md`.

- [ ] 0.2 Extend the proposal template with optional discovery sections
  - **Spec scenarios**: `product-discovery-workflow.proposal-template-accepts-discovery-sections`
  - **Design decisions**: D7
  - **Dependencies**: None
  - Add optional "Product Discovery" sections (PRD linkage, Key Assumptions, Target Outcome) to
    `openspec/schemas/feature-workflow/templates/proposal.md`; verify a proposal omitting them still
    passes `openspec validate --strict`.

- [ ] 0.3 Extend the roadmap schema/templates with optional `outcome` / `okr` fields
  - **Spec scenarios**: `product-discovery-workflow.roadmap-item-accepts-outcome-and-okr-fields`
  - **Design decisions**: D7
  - **Dependencies**: None
  - Add optional per-item `outcome` and `okr` fields to `openspec/schemas/roadmap/templates/*` and
    the roadmap schema; confirm existing `roadmap.yaml` files still validate.

- [ ] 0.4 Create the 12 new test dirs (each with a placeholder `test_skill_md.py` containing a
  trivial passing test) AND register them in `skills/pyproject.toml` `testpaths`
  - **Spec scenarios**: `skill-workflow.new-skill-test-directories-are-collected`
  - **Design decisions**: D9
  - **Dependencies**: None
  - The placeholder files MUST exist before/with the `testpaths` registration — pytest errors on a
    configured `testpaths` entry that does not exist. Verify `cd skills && uv run pytest --collect-only`
    enumerates all 12 (Phase 1 replaces the placeholders with the real tests).

- [ ] 0.5 Stub the "Product discovery" group in `docs/skills-catalogue.md`
  - **Dependencies**: None
  - Add the section header and quick-map row; the 12 rows are filled in Phase 3.

## Phase 1 — New PM skills (parallel, one work package per seam)

Each skill is authored WITH its tail block (user-invocable) and its
`skills/tests/<name>/test_skill_md.py`. Test file precedes SKILL.md in each pair.

### Phase 1.1 — Seam 1: proposal "why" (`wp-seam1-proposal-why`)

- [ ] 1.1.1 Tests for `create-prd` and `opportunity-solution-tree`
  - **Spec scenarios**: `skill-workflow.new-product-management-skill-is-auto-discovered`, `skill-workflow.frontmatter-schema-preserved`, `skill-workflow.new-user-invocable-pm-skill-ships-the-tail-block`
  - **Design decisions**: D3, D5, D9
  - **Dependencies**: 0.4
- [ ] 1.1.2 Author `skills/create-prd/SKILL.md` (output renders as a valid `proposal.md`)
  - **Spec scenarios**: `product-discovery-workflow.prd-output-is-decomposable-by-plan-roadmap`
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.1.1
- [ ] 1.1.3 Author `skills/opportunity-solution-tree/SKILL.md` (leaves = change candidates)
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.1.1

### Phase 1.2 — Seam 2: prioritization (`wp-seam2-prioritization`)

- [ ] 1.2.1 Tests for `prioritize-features` and `identify-assumptions`
  - **Spec scenarios**: tail-block + frontmatter scenarios; `skill-workflow.unresolved-reference-or-related-target-is-caught`
  - **Design decisions**: D4, D9
  - **Dependencies**: 0.1, 0.4
- [ ] 1.2.2 Author `skills/prioritize-features/SKILL.md` (cites `references/prioritization-frameworks.md`)
  - **Design decisions**: D1, D3, D4
  - **Dependencies**: 1.2.1
- [ ] 1.2.3 Author `skills/identify-assumptions/SKILL.md`
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.2.1

### Phase 1.3 — Seam 3: strategy red-team (`wp-seam3-redteam`)

- [ ] 1.3.1 Tests for `strategy-red-team` and `pre-mortem`
  - **Spec scenarios**: tail-block + frontmatter scenarios
  - **Design decisions**: D5, D9
  - **Dependencies**: 0.4
- [ ] 1.3.2 Author `skills/strategy-red-team/SKILL.md` (findings in `iterate-on-plan` shape)
  - **Spec scenarios**: `product-discovery-workflow.strategy-red-team-findings-flow-into-plan-iteration`
  - **Design decisions**: D3, D6
  - **Dependencies**: 1.3.1
- [ ] 1.3.3 Author `skills/pre-mortem/SKILL.md`
  - **Design decisions**: D3
  - **Dependencies**: 1.3.1

### Phase 1.4 — Seam 4: spec scenarios (`wp-seam4-scenarios`)

- [ ] 1.4.1 Tests for `user-stories` and `test-scenarios`
  - **Spec scenarios**: tail-block + frontmatter scenarios
  - **Design decisions**: D3, D9
  - **Dependencies**: 0.4
- [ ] 1.4.2 Author `skills/user-stories/SKILL.md` (output includes WHEN/THEN blocks)
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.4.1
- [ ] 1.4.3 Author `skills/test-scenarios/SKILL.md`
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.4.1

### Phase 1.5 — Seam 5: shipping verification (`wp-seam5-verification`)

- [ ] 1.5.1 Tests for `intended-vs-implemented` (user-invocable) and `shipping-artifacts` (infra, exempt)
  - **Spec scenarios**: `skill-workflow.user_invocable-assignment-is-honored-by-skill-discovery`, `skill-workflow.infrastructure-pm-skill-is-exempt`
  - **Design decisions**: D5, D9
  - **Dependencies**: 0.4
- [ ] 1.5.2 Author `skills/intended-vs-implemented/SKILL.md`
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.5.1
- [ ] 1.5.3 Author `skills/shipping-artifacts/SKILL.md` (`user_invocable: false`, no tail block)
  - **Design decisions**: D5
  - **Dependencies**: 1.5.1

### Phase 1.6 — Seam 6: outcome roadmaps (`wp-seam6-outcomes`)

- [ ] 1.6.1 Tests for `outcome-roadmap` and `brainstorm-okrs`
  - **Spec scenarios**: tail-block + frontmatter scenarios
  - **Design decisions**: D7, D9
  - **Dependencies**: 0.3, 0.4
- [ ] 1.6.2 Author `skills/outcome-roadmap/SKILL.md`
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.6.1
- [ ] 1.6.3 Author `skills/brainstorm-okrs/SKILL.md`
  - **Design decisions**: D1, D3
  - **Dependencies**: 1.6.1

## Phase 2 — Wire the seams into existing skills (parallel, clustered by target)

Each existing skill is edited exactly once (D6). All edits additive (D6, D7).

### Phase 2.1 — Front-end cluster (`wp-wire-frontend`)

- [ ] 2.1.1 Wire `explore-feature/SKILL.md` to consume `opportunity-solution-tree` output + outcome framing
  - **Spec scenarios**: `product-discovery-workflow.product-discovery-artifacts-feed-the-feature-pipeline`
  - **Design decisions**: D6
  - **Dependencies**: Phase 1.1, 1.6
- [ ] 2.1.2 Wire `plan-feature/SKILL.md` Gate-1 discovery to incorporate `identify-assumptions` + `strategy-red-team`
  - **Design decisions**: D6
  - **Dependencies**: Phase 1.2, 1.3
- [ ] 2.1.3 Wire seam 1 producer→consumer: `plan-roadmap`, `plan-feature`, and the proposal template consume `create-prd` / `opportunity-solution-tree` output so discovery output is a valid `proposal.md` / candidate set
  - **Spec scenarios**: `product-discovery-workflow.proposal-template-accepts-discovery-sections`
  - **Design decisions**: D6
  - **Dependencies**: Phase 1.1
- [ ] 2.1.4 Wire seam 3's `iterate-on-plan` consumer: `iterate-on-plan/SKILL.md` consumes `pre-mortem` findings (using the existing plan-review finding shape), completing the Gate-1 + iterate coverage of seam 3
  - **Spec scenarios**: `product-discovery-workflow.strategy-red-team-findings-flow-into-plan-iteration`
  - **Design decisions**: D6
  - **Dependencies**: Phase 1.3
- [ ] 2.1.5 Wire seam 4: `plan-feature` spec generation and `validate-feature` consume `user-stories` / `test-scenarios` so generated specs and validation include WHEN/THEN scenario blocks
  - **Spec scenarios**: `product-discovery-workflow.user-stories-and-test-scenarios-emit-when-then-blocks`
  - **Design decisions**: D6
  - **Dependencies**: Phase 1.4

### Phase 2.2 — Prioritization cluster (`wp-wire-prioritization`)

- [ ] 2.2.1 Wire `prioritize-proposals/SKILL.md` to compose `prioritize-features` scoring axes
  - **Spec scenarios**: `product-discovery-workflow.prioritization-composes-both-lenses`
  - **Design decisions**: D6
  - **Dependencies**: Phase 1.2

### Phase 2.3 — Verification & roadmap cluster (`wp-wire-verification-roadmap`)

- [ ] 2.3.1 Wire `validate-feature/SKILL.md` (+ a note in the OpenSpec verification workflow docs under `docs/guides/` — there is no tracked `openspec-verify-change` skill to edit) for the `intended-vs-implemented` drift check
  - **Spec scenarios**: `product-discovery-workflow.drift-check-runs-alongside-spec-compliance`, `product-discovery-workflow.drift-check-is-advisory-additive`
  - **Design decisions**: D6
  - **Dependencies**: Phase 1.5
- [ ] 2.3.2 Wire `autopilot-roadmap` / `roadmap-runtime` to reference optional `okr` fields
  - **Spec scenarios**: `product-discovery-workflow.autopilot-can-measure-against-key-results`
  - **Design decisions**: D7
  - **Dependencies**: 0.3, Phase 1.6

## Phase 3 — Integration (sequential, work package `wp-integration`)

- [ ] 3.1 Run `skills/install.sh --mode rsync` dry run; confirm all 12 skills + the reference install
  - **Spec scenarios**: `skill-workflow.new-product-management-skill-is-auto-discovered`, `skill-workflow.reference-installed-alongside-skills`
  - **Dependencies**: Phases 1–2
- [ ] 3.2 Confirm every new skill's `related:` targets resolve (install warns on none)
  - **Design decisions**: D8
  - **Dependencies**: 3.1
- [ ] 3.3 `cd skills && uv run pytest skills/tests/<12 new dirs>` green
  - **Design decisions**: D9
  - **Dependencies**: Phases 1–2
- [ ] 3.4 Fill the 12 rows in the `docs/skills-catalogue.md` "Product discovery" group; update counts
  - **Dependencies**: 3.1
- [ ] 3.5 `openspec validate add-product-management-skills --strict` passes
  - **Dependencies**: 3.1–3.4
- [ ] 3.6 Write the session log (decisions, deviations) per the session-log skill
  - **Dependencies**: 3.5
