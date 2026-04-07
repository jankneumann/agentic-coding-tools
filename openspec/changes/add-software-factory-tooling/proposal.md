# Proposal: Software Factory Tooling

**Change ID**: `add-software-factory-tooling`
**Status**: Draft
**Created**: 2026-04-06

## Why

This repository already provides strong foundations for agentic software delivery: OpenSpec planning artifacts, multi-agent coordination, live-service validation, and descriptor-driven generator-evaluator testing. What it does **not** yet provide is a first-class product surface for the hardest parts of the software-factory pattern that other projects will need to adopt:

1. **Scenario authoring remains too manual**. Projects can write gen-eval scenarios, but there is no opinionated workflow for deriving them from specs, contracts, incidents, or archived changes.
2. **No public vs holdout split exists today**. Validation can run scenarios, but implementation-visible development scenarios and validation-only holdout scenarios are not modeled separately.
3. **No DTU scaffolding workflow exists**. Projects integrating with external SDKs and APIs still need to hand-build boundary twins from public docs and examples.
4. **Validation findings do not yet drive structured rework**. We have validation reports and iteration skills, but no machine-readable artifact that tells the workflow what failed, why it matters, and what should be reworked next.
5. **Archived OpenSpec changes are under-used as learning data**. Proposal, design, tasks, change-context, validation-report, session-log, and future process-analysis artifacts are rich training material for scenario seeds, repair patterns, and exemplars, but the repository has no miner or registry for them.

If this repository is meant to help other projects implement strong agentic software practices, it should provide those capabilities as productized workflow primitives instead of leaving them as methodology.

## What Changes

### Feature 1: Scenario Pack Management

Add first-class scenario-pack support for external projects:

- Introduce a machine-readable scenario-pack manifest with visibility metadata (`public` vs `holdout`), provenance (`spec`, `contract`, `incident`, `archive`, `manual`), determinism, and ownership.
- Extend scenario authoring so projects can bootstrap scenarios from:
  - OpenSpec spec deltas
  - contract artifacts
  - public SDK/API docs
  - archived OpenSpec exemplars
  - incidents and escaped defects
- Teach gen-eval to filter, report, and gate by scenario visibility.

Scenarios are organized into `public/` and `holdout/` directories, with manifest metadata confirming visibility and skill logic enforcing the boundary at runtime. This makes “dev-spec vs test holdout” a native workflow concept with three reinforcing layers: directory structure, manifest metadata, and runtime filtering.

### Feature 2: DTU Scaffold From Public Docs

Add a DTU-lite scaffold flow for other projects integrating with third-party systems:

- Ingest public SDK/API docs, examples, auth rules, and error tables
- Produce a project-local boundary twin scaffold:
  - descriptor seed
  - fixture corpus
  - error-mode catalog
  - conformance/fidelity report
- Require a fidelity report before DTU-backed scenarios can be promoted to holdout

The goal is not to perfectly clone external systems. The goal is to make boundary simulation and scenario authoring fast enough that teams actually do it.

### Feature 3: Validation-Driven Rework

Add workflow artifacts and gates that turn validation into a control loop:

- `/validate-feature` writes `rework-report.json` mapping failed scenarios to likely owners, requirements, files, and recommended next actions
- `/implement-feature` and `/iterate-on-implementation` consume public scenario failures as a soft rework loop
- `/cleanup-feature` and merge-time validation consume holdout failures as a hard gate
- Add `process-analysis.md` / `process-analysis.json` as optional workflow artifacts summarizing convergence behavior, churn, flakiness, and loop effectiveness

This keeps human review focused on scope and approval decisions while letting behavior drive routine rework.

### Feature 4: Archive Intelligence And Exemplar Mining

Add an archive miner and exemplar registry over completed OpenSpec changes:

- Mine archived `proposal.md`, `design.md`, `tasks.md`, spec deltas, `change-context.md`, `validation-report.md`, `session-log.md`, merge logs, and `process-analysis.*`
- Normalize them into reusable artifacts:
  - scenario seeds
  - recurring failure signatures
  - rework patterns
  - DTU edge cases
  - implementation exemplars (“gene transfusion” source material)
- Feed the resulting registry into:
  - `/explore-feature`
  - `/plan-feature`
  - `/gen-eval-scenario`
  - project bootstrap flows

This turns archived OpenSpec work from static documentation into an active learning system for future projects.

### Feature 5: Dogfooding On This Repository

Use this repository as the first reference implementation:

- Split existing `agent-coordinator/evaluation/gen_eval/scenarios/` into public and holdout packs
- Add DTU-lite dogfood fixtures for:
  - GitHub PR/check/review state flows
  - transport/auth degradation scenarios
  - git/worktree contention patterns
- Seed the archive miner from existing archived OpenSpec changes and use the registry to improve `/explore-feature` and scenario generation

This gives the feature immediate product pressure and produces a reference example for downstream adopters.

## Impact

Affected capability specs and planned delta files:

- **`gen-eval-framework`**: `openspec/changes/add-software-factory-tooling/specs/gen-eval-framework/spec.md`
- **`skill-workflow`**: `openspec/changes/add-software-factory-tooling/specs/skill-workflow/spec.md`
- **`software-factory-tooling`** (new capability): `openspec/changes/add-software-factory-tooling/specs/software-factory-tooling/spec.md`

Expected repository impact:

- New scenario-pack and archive-intelligence primitives for external projects
- New workflow artifacts (`rework-report`, `process-analysis`)
- Stronger validation gates without requiring “no-human-review” policy
- Better dogfood coverage for this repository’s own workflows and coordinator surfaces

## Approaches Considered

### Approach A: Incremental Extension Of Existing Workflow (Recommended)

**Description**: Extend `gen-eval`, `validate-feature`, `iterate-on-implementation`, `explore-feature`, and OpenSpec artifacts with software-factory capabilities while preserving the current workflow model.

**Pros**:
- Reuses the existing OpenSpec artifact lifecycle and validation phases
- Keeps external-project adoption simple: one workflow, richer capabilities
- Lets dogfooding happen on real features immediately
- Fits naturally with `gen-eval` descriptors, session logs, and feature discovery artifacts already in the repo

**Cons**:
- Cross-cutting implementation touches several skill families and schemas
- Requires careful gating to prevent holdout leakage into implementation context
- Archive mining adds a new layer of product surface area

**Effort**: L

### Approach B: Standalone “Factory Mode” Subsystem

**Description**: Build a separate factory-specific subsystem with its own commands, scenario storage, mining pipeline, and DTU tooling, loosely integrated with OpenSpec.

**Pros**:
- Clear conceptual boundary
- Easier to experiment rapidly without changing core workflow behavior
- Could evolve independently if the approach changes significantly

**Cons**:
- Duplicates planning, validation, and artifact concepts already present
- Harder for external projects to know whether to use core workflow or “factory mode”
- Increases maintenance burden with two overlapping systems

**Effort**: L

### Approach C: Documentation-Only Pattern Library

**Description**: Add docs, templates, and examples showing teams how to do public/holdout scenarios, DTUs, and archive mining manually without changing tooling.

**Pros**:
- Fastest path to initial guidance
- Very low implementation risk
- Useful as immediate reference material

**Cons**:
- Fails the main goal: other projects still have to hand-roll the difficult parts
- No enforcement or machine-readable workflow integration
- No path for validation-triggered rework or automated mining

**Effort**: S

### Selected Approach

**Approach A: Incremental Extension Of Existing Workflow** — selected because the repository already has the right primitives: descriptor-driven gen-eval, OpenSpec artifacts, validation phases, session logs, and feature discovery artifacts. The right move is to make the software-factory pattern easy to apply in other projects by extending those primitives, not by creating a parallel workflow.

## Dependencies

- Existing `gen-eval-framework` implementation and descriptor model
- Existing feature workflow artifacts (`change-context`, `validation-report`, `session-log`)
- Archived OpenSpec change corpus for initial exemplar mining

No external repository dependency is required for the first implementation pass.

## Risks

- **Holdout leakage**: If holdout scenarios appear in implementation context, the split loses value. Mitigation: visibility filtering must be enforced in workflow and prompt assembly, not just naming.
- **DTU overconfidence**: Doc-derived twins can drift from reality. Mitigation: require fidelity reports and prevent low-fidelity twins from becoming holdout gates.
- **Rework noise**: Poor routing of failures to likely owners could create churn. Mitigation: make rework-report generation deterministic and tie it to changed files, requirement refs, and package scopes.
- **Archive miner relevance**: Mining low-signal artifacts could create noisy exemplars. Mitigation: normalize aggressively, score confidence, and start with deterministic extraction before adding more advanced retrieval.
