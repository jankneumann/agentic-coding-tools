# Design: Software Factory Tooling

**Change ID**: `add-software-factory-tooling`

## Goals

- Make software-factory practices reusable by external projects, not just by this repository
- Add first-class support for public vs holdout scenarios
- Add a DTU-lite path that starts from public docs and becomes gate-worthy only after fidelity checks
- Turn validation failures into structured rework artifacts
- Mine archived OpenSpec changes into reusable exemplars and scenario seeds
- Dogfood the full flow on this repository

## Non-Goals

- Fully autonomous “no human in the loop” operation
- Perfect third-party system emulation
- A separate parallel workflow outside OpenSpec
- Replacing existing validation-report, change-context, or session-log artifacts

## Design Decisions

### D1: Scenario visibility is modeled in a manifest, not inferred from paths

**Decision**: Add a scenario-pack manifest that records visibility (`public`, `holdout`), provenance, determinism, ownership, and promotion status for each scenario or scenario group. Path layout may still separate packs on disk, but behavior is driven by manifest metadata.

**Rationale**: File naming conventions are too weak for workflow gating. Visibility must be queryable by gen-eval, validation, and archive mining without heuristic guessing.

**Rejected alternatives**:
- Infer visibility solely from directory names like `scenarios/public/` and `scenarios/holdout/`
- Store visibility only in scenario YAML frontmatter

### D2: Holdout enforcement happens at workflow boundaries, not inside authoring tools alone

**Decision**: Public scenarios are allowed in planning, implementation, and iterative repair contexts. Holdout scenarios are excluded from implementation prompts and only executed in validation, cleanup, and merge gates.

**Rationale**: The value of holdouts comes from preventing the implementation loop from directly optimizing against them. Enforcement must therefore live in workflow gates and context assembly, not just scenario creation.

### D3: DTUs start as “DTU-lite” scaffolds with mandatory fidelity reports

**Decision**: DTU generation from public SDK/API docs produces a scaffold, not a trusted oracle. Every DTU gets a fidelity report describing:
- sources ingested
- unsupported areas
- probe results
- conformance score
- holdout eligibility

**Rationale**: Public docs are useful for bootstrapping but insufficient for blind trust. The fidelity report is the contract that says whether a twin is only suitable for public/dev scenarios or strong enough to back holdouts.

**Rejected alternative**: Treat doc-derived twins as production-grade immediately.

### D4: Validation emits a machine-readable rework report

**Decision**: `/validate-feature` produces `rework-report.json` with deterministic routing fields:
- failed scenario IDs
- visibility
- likely requirement refs
- likely package/file owners
- implicated interfaces
- recommended next action (`iterate`, `revise-spec`, `defer`, `block-cleanup`)

`/iterate-on-implementation` consumes that artifact rather than reparsing freeform validation prose.

**Rationale**: The workflow already has iteration skills, but they need a machine-readable control signal if validation is going to drive rework reliably.

### D5: Process analysis is a first-class optional artifact

**Decision**: Add `process-analysis.md` and `process-analysis.json` as optional OpenSpec artifacts generated after validation/cleanup. They summarize convergence behavior: loops taken, findings addressed, flaky scenarios, time to first pass, churn, and failure classes.

**Rationale**: Archive mining is much more valuable when process outcomes are explicit instead of inferred from commit history and prose alone.

### D6: Archive mining uses deterministic normalization before advanced retrieval

**Decision**: The first archive miner pass produces a deterministic normalized registry from archived OpenSpec artifacts:
- `scenario_seeds.json`
- `repair_patterns.json`
- `dtu_edge_cases.json`
- `exemplars.json`

Only after the deterministic layer is solid should more advanced retrieval or embedding-based ranking be added.

**Rationale**: Deterministic extraction is easier to validate, easier to test, and safer for dogfooding.

### D7: Dogfooding focuses on boundary-heavy coordinator scenarios first

**Decision**: This repository dogfoods the feature on the most software-factory-relevant surfaces:
- cross-interface coordinator scenarios
- multi-agent contention
- GitHub PR/check/review flows
- auth/transport degradation

**Rationale**: Those are exactly the kinds of behaviors that benefit from public/holdout separation, DTUs, and structured rework.

## Component Interactions

```text
OpenSpec Specs / Contracts / Docs / Incidents / Archived Changes
                     |
                     v
           Scenario Pack Bootstrap + Manifest
                     |
         +-----------+-----------+
         |                       |
         v                       v
   Public Scenario Packs    Holdout Scenario Packs
         |                       |
         v                       v
 /implement-feature         /validate-feature, /cleanup-feature, merge
 /iterate-on-implementation        |
         |                         v
         |                  rework-report.json
         |                         |
         +-----------+-------------+
                     v
        iterate-on-implementation / spec revision / block gate

Public SDK Docs / Examples
          |
          v
      DTU Scaffold -----> Fidelity Report -----> Holdout eligibility

Archived OpenSpec Changes
          |
          v
  Archive Miner + Exemplar Registry
          |
          +--> /explore-feature
          +--> /plan-feature
          +--> /gen-eval-scenario
          +--> project bootstrap
```

## Planned Artifact Surface

### Scenario Pack Artifacts

- `evaluation/gen_eval/manifests/scenario-pack.yaml`
- `evaluation/gen_eval/manifests/public.yaml`
- `evaluation/gen_eval/manifests/holdout.yaml`

### DTU Artifacts

- `evaluation/gen_eval/dtu/<system>/descriptor.seed.yaml`
- `evaluation/gen_eval/dtu/<system>/fixtures/`
- `evaluation/gen_eval/dtu/<system>/fidelity-report.json`

### Workflow Artifacts

- `openspec/changes/<change-id>/rework-report.json`
- `openspec/changes/<change-id>/process-analysis.md`
- `openspec/changes/<change-id>/process-analysis.json`

### Archive Intelligence Artifacts

- `docs/factory-intelligence/archive-index.json`
- `docs/factory-intelligence/exemplars.json`
- `docs/factory-intelligence/scenario-seeds.json`

## Dogfood Rollout

### Stage 1: Scenario Visibility

- Classify current `agent-coordinator` gen-eval scenarios into public and holdout
- Preserve current scenario content, add manifest metadata first

### Stage 2: DTU-Lite Fixtures

- Add GitHub PR/check/review fixture pack
- Add transport degradation and auth degradation fixture packs

### Stage 3: Rework And Archive Intelligence

- Route dogfood validation failures into `rework-report.json`
- Generate the first `process-analysis` artifacts
- Mine archived changes and feed exemplars back into `/explore-feature`

## Open Questions

- Should holdout visibility be enforced solely by skill logic, or also by a dedicated filesystem/path policy?
- Should `process-analysis` be generated in `/validate-feature`, `/cleanup-feature`, or both with incremental updates?
- How far should the first DTU-lite bootstrap go for SDK docs before probing live systems becomes mandatory?
