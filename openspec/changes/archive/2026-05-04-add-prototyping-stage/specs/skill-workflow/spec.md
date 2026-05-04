# skill-workflow — Delta for add-prototyping-stage

## ADDED Requirements

### Requirement: Prototype Feature Skill

The system SHALL provide a `prototype-feature` skill that dispatches N parallel agents to produce competing working skeletons from an approved proposal, scores them against cheap validation phases, and records outcomes for convergence-aware refinement.

The skill SHALL accept the following arguments:
- Change-id (required; or detected from current branch name matching `openspec/<change-id>` or `$OPENSPEC_BRANCH_OVERRIDE`)
- `--variants N` (optional; default 3; bounded 2 ≤ N ≤ 6)
- `--angles "a,b,c"` (optional; default `simplest,extensible,pragmatic`; count MUST equal N)

#### Scenario: Default variant dispatch
- **WHEN** the user invokes `/prototype-feature <change-id>` without flags
- **THEN** the skill SHALL dispatch exactly 3 parallel variant agents
- **AND** each variant SHALL run in an isolated worktree on branch `prototype/<change-id>/v<n>` for n ∈ {1, 2, 3}
- **AND** each variant SHALL receive the approved `proposal.md` and spec deltas as context
- **AND** each variant SHALL receive a distinct angle prompt from the default set (`simplest`, `extensible`, `pragmatic`)

#### Scenario: Custom variant count and angles
- **WHEN** the user invokes `/prototype-feature <change-id> --variants 4 --angles "simplest,extensible,pragmatic,perf-first"`
- **THEN** the skill SHALL dispatch 4 variant agents
- **AND** the count of angles SHALL match `--variants` exactly
- **AND** if counts mismatch, the skill SHALL fail fast before dispatching

#### Scenario: Variant count out of bounds
- **WHEN** the user passes `--variants 1` or `--variants 7`
- **THEN** the skill SHALL reject the invocation with an error message referencing the allowed range (2-6)
- **AND** no worktrees SHALL be created

#### Scenario: Isolated worktree per variant
- **WHEN** variants are dispatched
- **THEN** each variant agent SHALL operate in a dedicated worktree at `.git-worktrees/<change-id>/v<n>/`
- **AND** each variant's commits SHALL land on its own `prototype/<change-id>/v<n>` branch
- **AND** variant agents SHALL NOT write to the feature branch or to each other's branches

### Requirement: Vendor Diversity Policy with Fallback

The `prototype-feature` skill SHALL attempt vendor-diverse dispatch on a best-effort basis and SHALL fall back to single-vendor dispatch with prompt-steering when insufficient vendors are reachable. The skill SHALL NEVER hard-block on vendor availability.

#### Scenario: Sufficient vendors available
- **WHEN** the skill queries vendor availability and at least N distinct vendors are reachable (where N is the requested variant count)
- **THEN** the skill SHALL assign one distinct vendor per variant
- **AND** the vendor assignment SHALL be recorded in `prototype-findings.md` per variant

#### Scenario: Insufficient vendors available
- **WHEN** fewer than N distinct vendors are reachable
- **THEN** the skill SHALL run all N variants on the most-available vendor
- **AND** the skill SHALL inject temperature and seed variation to encourage stylistic divergence
- **AND** the skill SHALL emit a warning noting the fallback
- **AND** the dispatch SHALL proceed (no hard block)

#### Scenario: Vendor policy recorded in findings
- **WHEN** variants have been dispatched (with or without fallback)
- **THEN** `prototype-findings.md` SHALL record the actual vendor for each variant
- **AND** SHALL record whether fallback was triggered

### Requirement: Variant Scoring via Validation Phases

Each variant skeleton SHALL be scored using existing `/validate-feature` phases limited to `smoke` and `spec`. Heavier phases (`deploy`, `e2e`, `security`) SHALL NOT be applied to skeletons.

#### Scenario: Smoke and spec-compliance scoring
- **WHEN** all variant agents have committed their skeletons
- **THEN** the skill SHALL invoke `/validate-feature --phase smoke,spec` on each variant branch
- **AND** the skill SHALL collect per-variant pass/fail and spec-scenario-coverage metrics

#### Scenario: Skeleton fails to deploy
- **WHEN** a variant's smoke phase fails because the skeleton is incomplete
- **THEN** the skill SHALL record the failure in `prototype-findings.md` for that variant
- **AND** scoring for other variants SHALL continue
- **AND** the human pick-and-choose step SHALL still occur with the remaining scored variants

### Requirement: Prototype Findings Artifact

The `prototype-feature` skill SHALL produce `openspec/changes/<change-id>/prototype-findings.md` capturing variant descriptors, automated scores, and human pick-and-choose selections in a format consumable by `/iterate-on-plan`.

#### Scenario: Findings artifact produced
- **WHEN** variant dispatch, scoring, and human feedback have all completed
- **THEN** `prototype-findings.md` SHALL be written to the change directory
- **AND** the file SHALL contain one section per variant with: variant_id, angle, vendor, branch, automated_scores, human_picks, synthesis_hint
- **AND** the structured data SHALL conform to the `VariantDescriptor` schema in `contracts/schemas/variant-descriptor.schema.json`

#### Scenario: Human pick-and-choose feedback
- **WHEN** variants have been scored
- **THEN** the skill SHALL present a structured choice via `AskUserQuestion` with `multiSelect=true`
- **AND** options SHALL be grouped by aspect: data model / API surface / test approach / file layout
- **AND** each aspect SHALL list per-variant options plus a "rewrite" option
- **AND** user selections SHALL be recorded per variant in the `human_picks` field of the findings artifact

### Requirement: Convergence via Iterate-on-Plan

The `iterate-on-plan` skill SHALL accept a `--prototype-context <change-id>` flag. When present, the skill SHALL load prototype outcomes as additional context and perform convergence-aware refinement of `design.md` and `tasks.md`.

#### Scenario: Convergence mode activated via flag
- **WHEN** the user invokes `/iterate-on-plan <change-id> --prototype-context <change-id>`
- **THEN** the skill SHALL load `prototype-findings.md`, variant diffs (`git diff main...prototype/<change-id>/v<n>` for each variant), and validation reports in addition to proposal/design/tasks
- **AND** the skill SHALL emit findings that include `convergence.*` types (e.g., `convergence.prefer-variant-X`, `convergence.merge-A-data-model-with-B-api`)
- **AND** refinement commits SHALL land on the feature branch (never on prototype branches)

#### Scenario: Convergence without prototype context
- **WHEN** the user invokes `/iterate-on-plan <change-id>` without `--prototype-context`
- **THEN** the skill SHALL behave identically to its pre-prototyping behavior
- **AND** SHALL NOT attempt to load prototype artifacts
- **AND** SHALL NOT emit `convergence.*` findings

#### Scenario: Missing prototype artifacts
- **WHEN** `--prototype-context` is passed but `prototype-findings.md` does not exist
- **THEN** the skill SHALL fail fast with a clear error message
- **AND** SHALL NOT produce partial refinement commits

### Requirement: Prototype Recommendation Signal

The `iterate-on-plan` skill SHALL emit a non-actionable advisory finding of type `workflow.prototype-recommended` when the current refinement batch contains at least 3 high-criticality findings across the `clarity` and `feasibility` dimensions combined.

#### Scenario: Threshold met
- **WHEN** an `iterate-on-plan` refinement batch produces ≥3 high-criticality findings in `clarity` or `feasibility`
- **THEN** the skill SHALL append a `workflow.prototype-recommended` finding to the iteration report
- **AND** the finding SHALL reference the triggering findings
- **AND** the finding SHALL suggest running `/prototype-feature <change-id>`

#### Scenario: Threshold not met
- **WHEN** high-criticality `clarity` + `feasibility` findings number fewer than 3
- **THEN** the skill SHALL NOT emit a prototype-recommended finding

#### Scenario: Advisory only — never auto-triggers
- **WHEN** a `workflow.prototype-recommended` finding is emitted
- **THEN** the skill SHALL NOT invoke `/prototype-feature` automatically
- **AND** the decision SHALL remain with the user

### Requirement: Prototype Worktree and Branch Support

The `skills/worktree/scripts/worktree.py` script SHALL support the `prototype/<change-id>/v<n>` branch naming convention and compose correctly with the `--agent-id` suffix scheme used for parallel work packages.

#### Scenario: Prototype branch creation
- **WHEN** `worktree.py setup <change-id> --agent-id v1 --branch-prefix prototype` is invoked
- **THEN** the resulting worktree SHALL be on branch `prototype/<change-id>/v1`
- **AND** the worktree SHALL be at `.git-worktrees/<change-id>/v1/`

#### Scenario: Branch override composition
- **WHEN** `OPENSPEC_BRANCH_OVERRIDE` is set AND `--branch-prefix prototype` is passed
- **THEN** the prototype prefix SHALL take precedence for prototype worktrees
- **AND** the override SHALL still govern the parent feature branch

#### Scenario: Worktree pin
- **WHEN** prototype worktrees are created
- **THEN** they SHALL be pinned to survive the default 24-hour GC timer
- **AND** they SHALL remain pinned until `/cleanup-feature` teardown

### Requirement: Variant Descriptor Schema

The `skills/parallel-infrastructure/` consensus synthesizer SHALL provide a `VariantDescriptor` schema and a `synthesize_variants(descriptors) -> synthesis_plan` function.

#### Scenario: VariantDescriptor schema published
- **WHEN** `skills/parallel-infrastructure/` is installed
- **THEN** `contracts/schemas/variant-descriptor.schema.json` (or the equivalent published location) SHALL define fields: `variant_id`, `angle`, `vendor`, `branch`, `automated_scores`, `human_picks`, `synthesis_hint`
- **AND** every field except `synthesis_hint` SHALL be required

#### Scenario: Synthesis plan generation
- **WHEN** `synthesize_variants(descriptors)` is called with a list of VariantDescriptor objects
- **THEN** the function SHALL return a synthesis plan enumerating per-aspect (data model, API, tests, layout) source-variant picks
- **AND** the plan SHALL be consumable by iterate-on-plan's `--prototype-context` loader

### Requirement: Cleanup Includes Prototype Branches

The `cleanup-feature` skill SHALL delete prototype branches (local and remote) and tear down prototype worktrees as part of feature cleanup.

#### Scenario: Prototype cleanup on merge
- **WHEN** `/cleanup-feature <change-id>` runs after PR merge
- **THEN** the skill SHALL enumerate `prototype/<change-id>/v*` branches (local and remote)
- **AND** SHALL delete them alongside the feature branch
- **AND** SHALL tear down associated worktrees

#### Scenario: Prototype branches present but no prototype-findings
- **WHEN** prototype branches exist without a corresponding `prototype-findings.md` (stale state)
- **THEN** the skill SHALL still delete the branches
- **AND** SHALL log the anomaly for operator awareness

### Requirement: Workflow Documentation Updates

The `docs/skills-workflow.md` document SHALL describe the optional prototyping stage between `/plan-feature` and `/implement-feature`, and SHALL document the design principle *"Divergence is first-class on both sides of the approval gate."* The `CLAUDE.md` workflow diagram SHALL include the optional `/prototype-feature` step.

#### Scenario: Workflow doc describes prototype stage
- **WHEN** `docs/skills-workflow.md` is read
- **THEN** the skills-flow diagram SHALL show `/prototype-feature` as an optional step between proposal approval and implementation
- **AND** a new "Divergence is first-class on both sides of the approval gate" section SHALL appear under Design Principles

#### Scenario: CLAUDE.md workflow diagram updated
- **WHEN** `CLAUDE.md` is read
- **THEN** the workflow diagram in the Workflow section SHALL include an optional `/prototype-feature <change-id>` step
- **AND** SHALL reference `/iterate-on-plan --prototype-context` as the convergence mechanism
