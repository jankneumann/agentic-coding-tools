# Tasks: Add deterministic context producer checks

Tests precede behavior changes. Sizes use the plan-feature attention budget;
none are L or XL.

## 1. Consume the canonical producer contract

- [x] 1.1 (S) Write failing contract tests covering four adapter outcomes:
  clean/drifted/failed/not-configured results validate against the installed ri-06
  `ProducerResult`.
  **Spec scenarios**: project-context-refresh.canonical-result, project-context-refresh.actionable-failure, project-context-refresh.optional-unavailable
  **Contracts**: contracts/README.md; add-durable-context-refresh-records/contracts/context-refresh-types.schema.json#/$defs/ProducerResult
  **Design decisions**: D2
  **Dependencies**: ri-06 complete
- [x] 1.2 (S) Implement registry-backed producer invocation by importing
  ri-06 strict result/artifact/validation/remediation models.
  **Spec scenarios**: project-context-refresh.producer-discovery, project-context-refresh.canonical-result
  **Contracts**: contracts/README.md; add-durable-context-refresh-records/contracts/context-refresh-types.schema.json#/$defs/ProducerResult
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.1
- [x] 1.3 (XS) Add fail-closed input/result validation covering invalid
  revisions, unknown modes, duplicate producer IDs, unsafe artifact paths, plus
  schema-invalid adapter results.
  **Spec scenarios**: project-context-refresh.canonical-result, project-context-refresh.actionable-failure
  **Contracts**: contracts/README.md; add-durable-context-refresh-records/contracts/context-refresh-types.schema.json
  **Design decisions**: D1, D2
  **Dependencies**: 1.2

- [x] Checkpoint: run producer-contract tests, review the diff, verify dependency use

## 2. Absorb deterministic documentation generation

- [x] 2.1 (M) Port failing scanner/marker tests covering inventory discovery,
  unbalanced markers, missing anchors, prose preservation, plus repeat rendering.
  **Spec scenarios**: project-context-refresh.preserve-prose, project-context-refresh.repeat-generation
  **Contracts**: contracts/README.md
  **Design decisions**: D3, D4, D5
  **Dependencies**: 1.3
- [x] 2.2 (M) Implement documentation generation/checking with canonical result
  structures for artifacts, validations, remediation, fallbacks, plus safe errors.
  **Spec scenarios**: project-context-refresh.precise-drift, project-context-refresh.preserve-prose, project-context-refresh.canonical-result
  **Contracts**: contracts/README.md; add-durable-context-refresh-records/contracts/context-refresh-types.schema.json#/$defs/ProducerResult
  **Design decisions**: D2, D3, D4, D5
  **Dependencies**: 2.1
- [x] 2.3 (S) Write supersession tests proving
  `add-update-documentation-skill` has no executable tasks/packages or normative
  hook/cleanup/post-merge lifecycle delta.
  **Spec scenarios**: project-context-refresh.documentation-superseded, project-context-refresh.shared-convergence-owner
  **Contracts**: superseded change proposal/tasks/work-packages/spec
  **Design decisions**: D5
  **Dependencies**: 2.2
- [x] 2.4 (S) Finalize the complete supersession record while retaining the old
  marker design as historical rationale.
  **Spec scenarios**: project-context-refresh.documentation-superseded
  **Design decisions**: D5
  **Dependencies**: 2.3

- [x] Checkpoint: run documentation/supersession tests, review the diff, verify scope

## 3. Adapt API and decision owners

- [x] 3.1 (S) Write failing workflow-contract adapter tests covering exact
  affected paths, check-mode isolation, canonical result validation, stable
  ordering, plus remediation.
  **Spec scenarios**: project-context-refresh.precise-drift, project-context-refresh.canonical-result
  **Contracts**: contracts/README.md; add-durable-context-refresh-records/contracts/context-refresh-types.schema.json#/$defs/ProducerResult
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.3
- [x] 3.2 (M) Implement the API/bindings adapter around the canonical contract
  generator/check owner.
  **Spec scenarios**: project-context-refresh.producer-discovery, project-context-refresh.precise-drift
  **Contracts**: contracts/README.md
  **Design decisions**: D1, D2
  **Dependencies**: 3.1
- [x] 3.3 (S) Write failing decision-index adapter tests covering
  archive/session-log inputs, repeat output, check-mode isolation, plus canonical
  result validation.
  **Spec scenarios**: project-context-refresh.repeat-generation, project-context-refresh.canonical-result
  **Contracts**: contracts/README.md
  **Design decisions**: D1, D2, D3
  **Dependencies**: 1.3
- [x] 3.4 (M) Implement the decision adapter around `decision_index.py` while
  retaining `make decisions` as the standalone owner.
  **Spec scenarios**: project-context-refresh.producer-discovery, project-context-refresh.repeat-generation
  **Contracts**: contracts/README.md
  **Design decisions**: D1, D2
  **Dependencies**: 3.3

- [x] Checkpoint: run API/decision adapter tests, review the diff, verify owner boundaries

## 4. Add the OpenSpec projection adapter

- [x] 4.1 (M) Write failing projection tests covering active deltas, canonical
  artifact records, conflicting deltas, plus zero writes to live specs/archives.
  **Spec scenarios**: project-context-refresh.openspec-projection, project-context-refresh.precise-drift
  **Contracts**: contracts/README.md
  **Design decisions**: D2, D3, D6
  **Dependencies**: 1.3
- [x] 4.2 (M) Extract reusable parse/project/compare helpers from `update-specs`
  without weakening its active-agent or main-mutation guard.
  **Spec scenarios**: project-context-refresh.openspec-projection
  **Design decisions**: D6
  **Dependencies**: 4.1
- [x] 4.3 (S) Implement the OpenSpec adapter with canonical result output for
  artifacts, validation, remediation, fallback, plus safe errors.
  **Spec scenarios**: project-context-refresh.openspec-projection, project-context-refresh.canonical-result
  **Contracts**: contracts/README.md; add-durable-context-refresh-records/contracts/context-refresh-types.schema.json#/$defs/ProducerResult
  **Design decisions**: D2, D6
  **Dependencies**: 4.2

- [x] Checkpoint: run OpenSpec projection tests, review the diff, verify canonical specs unchanged

## 5. Integrate and verify

- [x] 5.1 (S) Add registry tests proving all four stable producer IDs resolve to
  their canonical owners with independent execution.
  **Spec scenarios**: project-context-refresh.producer-discovery
  **Design decisions**: D1
  **Dependencies**: 2.4, 3.2, 3.4, 4.3
- [x] 5.2 (S) Prove repeat-run determinism across all producer fixtures; require
  byte-identical output plus a fresh canonical result on the second check.
  **Spec scenarios**: project-context-refresh.repeat-generation, project-context-refresh.canonical-result
  **Contracts**: contracts/README.md; add-durable-context-refresh-records/contracts/context-refresh-types.schema.json#/$defs/ProducerResult
  **Design decisions**: D2, D3, D4
  **Dependencies**: 5.1
- [x] 5.3 (XS) Run the final validation matrix: strict OpenSpec, work packages,
  focused pytest, `git diff --check`, plus `bash skills/install.sh --check`.
  **Spec scenarios**: all
  **Dependencies**: 5.2

- [x] Checkpoint: all suites green, cumulative diff maps to tasks, no scope creep
