# Tasks — migrate discovery generators to emit candidate-work stubs

Tests precede implementation (RED → GREEN). All tasks are XS, S, or M; none are L
or XL. Capability abbreviations: `sw` = skill-workflow, `ro` = roadmap-orchestration.

## Phase 0 — contract and fixtures

- [ ] 0.1 Test: add representative canonical fixtures for bug-scrub, improve-harness,
      and explore-feature plus a mixed batch; prove they pass the ri-11 validator — **S**
      **Spec scenarios**: sw *Mixed producer batch is ranked*
      **Contracts**: `contracts/README.md`, canonical candidate-work schema
      **Dependencies**: None
- [ ] 0.2 Test and implement the shared candidate-work validator, canonical batch
      serializer, duplicate guard, and atomic writer; retain the ri-11 CLI wrapper;
      declare every new shared-runtime consumer in `skills/install-manifest.json` — **S**
      **Design decisions**: D1, D2
      **Dependencies**: 0.1
- [ ] 0.3 Document sidecar paths, mapping tables, stable ordering, and intake
      transaction in `contracts/README.md` — **XS**
      **Design decisions**: D1-D5
      **Dependencies**: 0.2
- [ ] Checkpoint: fixture validation green; review the diff and contract scope

## Phase 1 — producer adapters

- [ ] 1.1 Test: bug-scrub maps an eligible finding to a schema-valid stub with stable
      provenance/common priority/exhaustive effort/normalized slug, writes byte-stable
      JSON, and leaves no partial file on validation failure — **S**
      **Spec scenarios**: sw *Bug-scrub promotes a finding*, *Candidate batch validation fails*
      **Design decisions**: D1-D3
      **Dependencies**: 0.1
- [ ] 1.2 Implement bug-scrub candidate projection, CLI/output wiring, and canonical skill documentation — **S**
      **Dependencies**: 0.2, 1.1
- [ ] 1.3 Test: improve-harness maps a ranked gap to a schema-valid stub and retains the
      legacy markdown proposal helper/flag — **S**
      **Spec scenarios**: sw *Improve-harness emits a capability-gap candidate*
      **Design decisions**: D1-D3
      **Dependencies**: 0.1
- [ ] 1.4 Implement improve-harness candidate projection/output, compatibility wrapper, and canonical skill documentation — **S**
      **Dependencies**: 0.2, 1.3
- [ ] 1.5 Test: explore-feature projects only untracked shortlist items, preserves rich
      opportunities, normalizes change-ID prefixes, separates prose blockers from exact
      dependency IDs, validates the sidecar, and skips existing/scaffolded entries — **S**
      **Spec scenarios**: sw *Explore-feature emits shortlist candidates*
      **Design decisions**: D1-D3
      **Dependencies**: 0.1
- [ ] 1.6 Implement explore-feature projection helper and canonical skill output contract — **S**
      **Dependencies**: 0.2, 1.5
- [ ] Checkpoint: all three producer suites green; review cumulative diff and scopes

## Phase 2 — candidate prioritization

- [ ] 2.1 Test: a mixed three-generator batch is validated, ranked exactly once per
      stub on the shared five-band priority scale, retains provenance, safely renders
      inert source text, has stable ties, and fails closed on a malformed member — **S**
      **Spec scenarios**: sw *Mixed producer batch is ranked*, *Mixed batch contains a malformed stub*
      **Design decisions**: D4
      **Dependencies**: 1.2, 1.4, 1.6
- [ ] 2.2 Implement the explicit candidate-work loader/ranker, CLI/report integration, and canonical skill documentation
      in prioritize-proposals — **M**
      **Dependencies**: 2.1
- [ ] Checkpoint: prioritize-proposals suite green; validate mixed fixture twice for stable order

## Phase 3 — approved roadmap intake

- [ ] 3.1 Test: approved stub plus acceptance outcomes maps to one valid new-roadmap item,
      creates the complete roadmap envelope/capability scaffold, preserves exact change
      ID/provenance, and resolves dependencies — **S**
      **Spec scenarios**: ro *Approved stub creates a new-roadmap item*
      **Design decisions**: D5
      **Dependencies**: 0.1
- [ ] 3.2 Test: existing-roadmap intake emits a refine add request; missing acceptance
      outcomes and unresolved dependencies fail before any write; execution priority is
      omitted so refine-roadmap assigns max+1 without a collision — **S**
      **Spec scenarios**: ro *Approved stub targets an existing roadmap*, *Approved stub omits acceptance outcomes*, *Candidate dependency cannot be resolved*
      **Design decisions**: D5, D6
      **Dependencies**: 3.1
- [ ] 3.3 Implement the plan-roadmap candidate intake helper/CLI and canonical skill documentation for
      refine-roadmap/new-roadmap routing — **M**
      **Dependencies**: 0.2, 3.1, 3.2
- [ ] Checkpoint: plan-roadmap/refine-roadmap focused suites green; inspect for direct active-roadmap writes

## Phase 4 — integration and documentation

- [ ] 4.1 Test: exercise representative outputs from all three producers through mixed
      ranking and approved-stub roadmap intake without hand-edited intermediate data — **S**
      **Spec scenarios**: all sw/ro scenarios
      **Dependencies**: 2.2, 3.3
- [ ] 4.2 Run `skills/install.sh` once to sync canonical skill/shared sources into
      generated mirrors; verify no mirror drift or unrelated generated diff — **S**
      **Design decisions**: D1-D6
      **Dependencies**: 4.1
- [ ] 4.3 Run focused suites, full skills suite, ruff, package validation, and strict
      OpenSpec validation; append implementation/validation records; commit and push — **S**
      **Dependencies**: 4.2
- [ ] Checkpoint: all gates green; diff maps only to ri-12; branch is pushed
