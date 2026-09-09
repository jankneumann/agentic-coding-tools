# Tasks: Write a Durable State-Artifacts Guide

## Phase 1 - RED documentation contracts

- [x] 1.1 Add the structural contract test at `skills/tests/state-artifacts/test_state_artifacts_guide.py`.
  - **Size**: S
  - **Spec scenarios**: All durable classes are discoverable; Relevant skill documentation is audited; Runtime skill mirrors are installed
  - **Design decisions**: D1-D4
  - **Dependencies**: None
  - **Coverage**: Assert the five-class inventory, required ownership fields, all eight canonical order markers, the six relevant skill references, supervise alignment, changed-skill mirror parity, and archive-safe OpenSpec change resolution.

- [x] 1.2 Capture the expected RED evidence.
  - **Size**: XS
  - **Spec scenarios**: all
  - **Design decisions**: D4
  - **Dependencies**: 1.1
  - **Command**: Run the focused test against the roadmap parent commit and preserve failures caused by the missing guide or links.

- [x] 1.3 Register the structural suite in default CI collection.
  - **Size**: XS
  - **Spec scenarios**: all
  - **Design decisions**: D4
  - **Dependencies**: 1.1
  - **Coverage**: Add `tests/state-artifacts` to `skills/pyproject.toml` testpaths and prove registration with `skills/tests/ci_coverage`.

- [x] Checkpoint: preserve RED output, review the test diff, and verify writes remain inside the declared package scope.

## Phase 2 - GREEN canonical documentation

- [x] 2.1 Write `docs/guides/state-artifacts.md`.
  - **Size**: S
  - **Spec scenarios**: All durable classes are discoverable; Advisory state conflicts with authoritative state; Fresh supervisor session resumes active work; Canonical state is missing
  - **Design decisions**: D1-D3
  - **Dependencies**: 1.2
  - **Coverage**: Include the exact inventory, question-scoped authority, all eight ordered rehydration stages, the first-run checkpoint exception, the bounded recent-learning window without freezing its numeric default, conflict handling, and missing/stale behavior.

- [x] 2.2 Reference the canonical guide from the six workflow skill sources.
  - **Size**: S
  - **Spec scenarios**: Relevant skill documentation is audited
  - **Design decisions**: D1, D4
  - **Dependencies**: 2.1
  - **Coverage**: Reference the guide from the documentation index and the six canonical skill sources while retaining phase-specific commands and gate semantics.

- [x] 2.3 Align the supervise rehydration section.
  - **Size**: S
  - **Spec scenarios**: Fresh supervisor session resumes active work; Canonical state is missing
  - **Design decisions**: D2-D4
  - **Dependencies**: 2.1
  - **Coverage**: Follow the guide's bootstrap and canonical verification order without changing runtime behavior.

- [x] Checkpoint: run focused GREEN tests, inspect guide references, and confirm the guide has not changed runtime behavior.

## Phase 3 - Mirrors and validation

- [x] 3.1 Synchronize changed skill mirrors.
  - **Size**: S
  - **Spec scenarios**: Runtime skill mirrors are installed
  - **Design decisions**: D4
  - **Dependencies**: 2.2, 2.3
  - **Coverage**: Install changed canonical skill sources into `.agents` and `.claude`, then verify byte identity.

- [ ] 3.2 Close archive-stability and reference-form drift gaps.
  - **Size**: XS
  - **Spec scenarios**: all
  - **Design decisions**: D4
  - **Dependencies**: 1.1, 2.2
  - **Coverage**: Synchronize the feature branch with current `main`, then consume the existing `skills/tests/_shared/openspec_paths.py` helper and `skills/tests/openspec_paths/` guard; resolve the design artifact with `change_dir(ROOT, CHANGE_ID)`, preserve the same eight-stage assertion after archival, normalize remaining shared-semantics wording to repository-relative references, and do not create or copy path infrastructure inside this package.

- [ ] 3.3 Run the complete validation matrix.
  - **Size**: S
  - **Spec scenarios**: all
  - **Design decisions**: D4
  - **Dependencies**: 3.1, 3.2
  - **Coverage**: Run focused and affected skill tests, the OpenSpec path-stability and CI test-coverage guards, `bash skills/install.sh --check`, strict OpenSpec, work-package validation, base-relative context-impact validation, documentation-reference checks, scope checks, and diff checks.

- [ ] Checkpoint: review the complete branch diff, reconcile task checkboxes with commit reality, and preserve validation evidence.
