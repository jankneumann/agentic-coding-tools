# Tasks — migrate discovery generators to emit candidate-work stubs

Tests precede implementation (RED → GREEN). All tasks are XS, S, or M; none are L
or XL. Capability abbreviations: `sw` = skill-workflow, `ro` = roadmap-orchestration.

## Phase 0 — contract and fixtures

- [ ] 0.1 Test: add representative canonical fixtures for bug-scrub, improve-harness,
      and explore-feature plus a mixed batch; prove they pass the ri-11 validator — **S**
      **Spec scenarios**: sw *Mixed producer batch is ranked*
      **Contracts**: `contracts/README.md`, canonical candidate-work schema
      **Dependencies**: None
- [ ] 0.2 Document the additive sidecar paths, atomic write rule, and approved intake
      mapping in `contracts/README.md` — **XS**
      **Design decisions**: D1, D2, D5
      **Dependencies**: 0.1
- [ ] Checkpoint: fixture validation green; review the diff and contract scope

## Phase 1 — producer adapters

- [ ] 1.1 Test: bug-scrub maps an eligible finding to a schema-valid stub with stable
      provenance/priority/effort/slug, writes byte-stable JSON, and leaves no partial
      file on validation failure — **S**
      **Spec scenarios**: sw *Bug-scrub promotes a finding*, *Candidate batch validation fails*
      **Design decisions**: D1-D3
      **Dependencies**: 0.1
- [ ] 1.2 Implement bug-scrub candidate projection and CLI/output wiring — **S**
      **Dependencies**: 1.1
- [ ] 1.3 Test: improve-harness maps a ranked gap to a schema-valid stub and retains the
      legacy markdown proposal helper/flag — **S**
      **Spec scenarios**: sw *Improve-harness emits a capability-gap candidate*
      **Design decisions**: D1-D3
      **Dependencies**: 0.1
- [ ] 1.4 Implement improve-harness candidate projection/output with compatibility wrapper — **S**
      **Dependencies**: 1.3
- [ ] 1.5 Test: explore-feature projects only untracked shortlist items, preserves rich
      opportunities, validates the sidecar, and skips existing/scaffolded entries — **S**
      **Spec scenarios**: sw *Explore-feature emits shortlist candidates*
      **Design decisions**: D1-D3
      **Dependencies**: 0.1
- [ ] 1.6 Implement explore-feature projection helper and update its output contract — **S**
      **Dependencies**: 1.5
- [ ] Checkpoint: all three producer suites green; review cumulative diff and scopes

## Phase 2 — candidate prioritization

- [ ] 2.1 Test: a mixed three-generator batch is validated, ranked exactly once per
      stub, retains provenance, has stable ties, and fails closed on a malformed member — **S**
      **Spec scenarios**: sw *Mixed producer batch is ranked*, *Mixed batch contains a malformed stub*
      **Design decisions**: D4
      **Dependencies**: 1.2, 1.4, 1.6
- [ ] 2.2 Implement the explicit candidate-work loader/ranker and CLI/report integration
      in prioritize-proposals — **M**
      **Dependencies**: 2.1
- [ ] Checkpoint: prioritize-proposals suite green; validate mixed fixture twice for stable order

## Phase 3 — approved roadmap intake

- [ ] 3.1 Test: approved stub plus acceptance outcomes maps to one valid new-roadmap item,
      preserves exact change ID/provenance, and resolves dependencies — **S**
      **Spec scenarios**: ro *Approved stub creates a new-roadmap item*
      **Design decisions**: D5
      **Dependencies**: 0.1
- [ ] 3.2 Test: existing-roadmap intake emits a refine add request; missing acceptance
      outcomes and unresolved dependencies fail before any write — **S**
      **Spec scenarios**: ro *Approved stub targets an existing roadmap*, *Approved stub omits acceptance outcomes*, *Candidate dependency cannot be resolved*
      **Design decisions**: D5, D6
      **Dependencies**: 3.1
- [ ] 3.3 Implement the plan-roadmap candidate intake helper/CLI and document the
      refine-roadmap/new-roadmap routing — **M**
      **Dependencies**: 3.1, 3.2
- [ ] Checkpoint: plan-roadmap/refine-roadmap focused suites green; inspect for direct active-roadmap writes

## Phase 4 — integration and documentation

- [ ] 4.1 Test: exercise representative outputs from all three producers through mixed
      ranking and approved-stub roadmap intake without hand-edited intermediate data — **S**
      **Spec scenarios**: all sw/ro scenarios
      **Dependencies**: 2.2, 3.3
- [ ] 4.2 Update the five skill documents and installed mirrors to describe the shipped
      flags, paths, failure semantics, and ri-13 handoff boundary — **S**
      **Design decisions**: D1-D6
      **Dependencies**: 4.1
- [ ] 4.3 Run focused suites, full skills suite, ruff, package validation, and strict
      OpenSpec validation; append implementation/validation records; commit and push — **S**
      **Dependencies**: 4.2
- [ ] Checkpoint: all gates green; diff maps only to ri-12; branch is pushed
