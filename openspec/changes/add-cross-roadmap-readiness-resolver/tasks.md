# Tasks: Add Cross-Roadmap Readiness Resolver

## Phase 1 — Shared admission rule

- [ ] 1.1 Write RED characterization and ownership tests for the shared admission rule (S)
  **Spec scenarios**: `roadmap-orchestration.preserve-the-existing-autopilot-admission-contract`, `roadmap-orchestration.use-one-shared-implementation`
  **Contract**: `contracts/readiness-result.schema.json`
  **Design decisions**: D1
  **Dependencies**: None

- [ ] 1.2 Move `_get_ready_items` into roadmap-runtime and rewire autopilot imports (S)
  **Spec scenarios**: `roadmap-orchestration.preserve-the-existing-autopilot-admission-contract`, `roadmap-orchestration.use-one-shared-implementation`
  **Design decisions**: D1
  **Dependencies**: 1.1

- [ ] Checkpoint: run focused tests, review the cumulative diff, verify package scope

## Phase 2 — Repository-wide resolver

- [ ] 2.1 Write RED resolver tests for ranking, effective completion, typed external edges, invalid state, missing checkpoints, source fingerprints, and byte determinism (M)
  **Spec scenarios**: all scenarios in `Canonical Cross-Roadmap Readiness Resolution`, `Checkpoint-Authoritative Cross-Roadmap Edges`, and `Deterministic Readiness Projection`
  **Contract**: `contracts/readiness-result.schema.json`
  **Design decisions**: D2, D3, D4, D5
  **Dependencies**: 1.2

- [ ] 2.2 Implement the checkpoint-aware runtime resolver and read-only JSON command with a source fingerprint (M)
  **Spec scenarios**: `roadmap-orchestration.return-one-globally-ranked-ready-now-list`, all scenarios in `Checkpoint-Authoritative Cross-Roadmap Edges`, `roadmap-orchestration.unchanged-inputs-produce-byte-identical-output`, `roadmap-orchestration.missing-checkpoint-is-a-valid-first-run`
  **Contract**: `contracts/readiness-result.schema.json`
  **Design decisions**: D2, D3, D4, D5
  **Dependencies**: 2.1

- [ ] 2.3 Delegate the supervisor compatibility view to the runtime resolver (S)
  **Spec scenarios**: `roadmap-orchestration.return-one-globally-ranked-ready-now-list`, `roadmap-orchestration.advisory-state-cannot-change-readiness`
  **Design decisions**: D4, D5
  **Dependencies**: 2.2

- [ ] Checkpoint: run focused tests, review the cumulative diff, verify package scope

## Phase 3 — Validation evidence

- [ ] 3.1 Run the focused runtime, autopilot-roadmap, plan-roadmap, and supervise suites (S)
  **Spec scenarios**: all
  **Design decisions**: D1-D5
  **Dependencies**: 2.3

- [ ] 3.2 Run ruff, strict OpenSpec validation, package validation, context-impact validation, and install-payload checks (S)
  **Spec scenarios**: all
  **Design decisions**: D1-D5
  **Dependencies**: 3.1

- [ ] Checkpoint: confirm all task boxes are complete, inspect `main...HEAD`, and record validation evidence

