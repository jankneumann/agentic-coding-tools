## ADDED Requirements

### Requirement: Product-Discovery Artifacts Feed the Feature Pipeline

The feature-workflow SHALL accept product-discovery artifacts as inputs to its existing planning
and prioritization skills, wiring the six seams identified in the gap analysis. Each wiring SHALL
be **additive**: the consuming skill SHALL retain its prior behavior when no discovery artifact is
supplied.

The six seam wirings SHALL be:

| Seam | Producer skill | Consumer skill / artifact | Contract |
|---|---|---|---|
| 1 | `create-prd`, `opportunity-solution-tree` | `plan-roadmap`, `plan-feature`, proposal template | discovery output is a valid `proposal.md` / candidate set |
| 2 | `prioritize-features`, `identify-assumptions` | `prioritize-proposals`, `explore-feature` | scoring axes compose with code-signal ranking |
| 3 | `strategy-red-team`, `pre-mortem` | `plan-feature` (Gate 1), `iterate-on-plan` | findings use the existing plan-review finding shape |
| 4 | `user-stories`, `test-scenarios` | `plan-feature` spec generation, `validate-feature` | output includes WHEN/THEN scenario blocks |
| 5 | `intended-vs-implemented` | `validate-feature`, `openspec-verify-change` | complementary drift check, does not replace spec-compliance |
| 6 | `outcome-roadmap`, `brainstorm-okrs` | `plan-roadmap`, `autopilot-roadmap`, `roadmap.yaml` | optional outcome/OKR fields per item |

#### Scenario: Proposal template accepts discovery sections

**WHEN** `openspec/schemas/feature-workflow/templates/proposal.md` is read
**THEN** it SHALL contain optional sections for PRD linkage, key assumptions, and target outcome
**AND** a proposal that omits those sections SHALL still pass `openspec validate --strict`

#### Scenario: PRD output is decomposable by plan-roadmap

**WHEN** `create-prd` produces a discovery artifact
**THEN** the artifact SHALL be a Markdown proposal that `plan-roadmap` can decompose without manual
reformatting (it SHALL satisfy `plan-roadmap`'s proposal-readiness check)

#### Scenario: Prioritization composes both lenses

**WHEN** `prioritize-proposals` runs with `prioritize-features` scoring available
**THEN** the ranking SHALL incorporate the impact/effort/risk/alignment axes alongside the existing
code-signal ranking
**AND** when `prioritize-features` scoring is absent, `prioritize-proposals` SHALL produce its prior
code-signal ranking unchanged

#### Scenario: Strategy red-team findings flow into plan iteration

**WHEN** `strategy-red-team` or `pre-mortem` emits findings for a proposal
**THEN** the findings SHALL conform to the plan-review finding shape consumed by `iterate-on-plan`
**AND** `iterate-on-plan` SHALL be able to iterate on them without a schema adapter

---

### Requirement: Intended-vs-Implemented Verification Seam

The validation workflow SHALL include an `intended-vs-implemented` drift check that compares the
behavior documented in a change's proposal/specs against the behavior actually shipped. This check
SHALL be **complementary** to the existing spec-compliance verification in `openspec-verify-change`
and `validate-feature`; it SHALL NOT replace it, and a failure of one SHALL NOT be masked by a pass
of the other.

#### Scenario: Drift check runs alongside spec compliance

**WHEN** `validate-feature` runs on an implemented change
**THEN** the `intended-vs-implemented` check SHALL report any documented-but-unimplemented or
implemented-but-undocumented behavior
**AND** the existing spec-compliance verification SHALL still run and report independently

#### Scenario: Drift check is advisory-additive

**WHEN** a change has no `intended-vs-implemented` artifact
**THEN** `validate-feature` SHALL still complete its existing verification steps
**AND** SHALL note the drift check as skipped rather than failing the validation

---

### Requirement: Roadmap Items Carry Optional Outcome Framing

The roadmap schema and templates SHALL accept optional `outcome` and `okr` fields per roadmap item,
supplied by `outcome-roadmap` and `brainstorm-okrs`. Existing `roadmap.yaml` files without these
fields SHALL remain valid.

#### Scenario: Roadmap item accepts outcome and okr fields

**WHEN** a `roadmap.yaml` item declares optional `outcome` and `okr` fields
**THEN** roadmap validation SHALL accept them
**AND** an item omitting both fields SHALL still validate

#### Scenario: Autopilot can measure against key results

**WHEN** `autopilot-roadmap` runs a roadmap whose items carry `okr` fields
**THEN** its learning-feedback loop SHALL be able to reference the key results as measurable targets
**AND** a roadmap without `okr` fields SHALL run unchanged
