# Tasks: Write a Durable State-Artifacts Guide

## Phase 1 - RED documentation contracts

- [ ] 1.1 Add the structural contract test at `skills/tests/state-artifacts/test_state_artifacts_guide.py`.
  - **Size**: S
  - **Spec scenarios**: All durable classes are discoverable; Relevant skill documentation is audited; Runtime skill mirrors are installed
  - **Design decisions**: D1-D4
  - **Dependencies**: None
  - **Coverage**: Assert the five-class inventory, required ownership fields, canonical order markers, relevant skill links, supervise alignment, and changed-skill mirror parity.

- [ ] 1.2 Capture the expected RED evidence.
  - **Size**: XS
  - **Spec scenarios**: all
  - **Design decisions**: D4
  - **Dependencies**: 1.1
  - **Command**: Run the focused test against the roadmap parent commit and preserve failures caused by the missing guide or links.

- [ ] Checkpoint: preserve RED output, review the test diff, and verify writes remain inside the declared package scope.

## Phase 2 - GREEN canonical documentation

- [ ] 2.1 Write `docs/guides/state-artifacts.md`.
  - **Size**: S
  - **Spec scenarios**: All durable classes are discoverable; Advisory state conflicts with authoritative state; Fresh supervisor session resumes active work; Canonical state is missing
  - **Design decisions**: D1-D3
  - **Dependencies**: 1.2
  - **Coverage**: Include the exact inventory, question-scoped authority, bootstrap locator rule, canonical verification sequence, conflict handling, and missing/stale behavior.

- [ ] 2.2 Link the canonical documentation sources.
  - **Size**: S
  - **Spec scenarios**: Relevant skill documentation is audited
  - **Design decisions**: D1, D4
  - **Dependencies**: 2.1
  - **Coverage**: Link the documentation index and relevant canonical skill sources while retaining phase-specific commands and gate semantics.

- [ ] 2.3 Align the supervise rehydration section.
  - **Size**: S
  - **Spec scenarios**: Fresh supervisor session resumes active work; Canonical state is missing
  - **Design decisions**: D2-D4
  - **Dependencies**: 2.1
  - **Coverage**: Follow the guide's bootstrap and canonical verification order without changing runtime behavior.

- [ ] Checkpoint: run focused GREEN tests, inspect link targets, and confirm the guide has not changed runtime behavior.

## Phase 3 - Mirrors and validation

- [ ] 3.1 Synchronize changed skill mirrors.
  - **Size**: S
  - **Spec scenarios**: Runtime skill mirrors are installed
  - **Design decisions**: D4
  - **Dependencies**: 2.2, 2.3
  - **Coverage**: Install changed canonical skill sources into `.agents` and `.claude`, then verify byte identity.

- [ ] 3.2 Run the complete validation matrix.
  - **Size**: S
  - **Spec scenarios**: all
  - **Design decisions**: D4
  - **Dependencies**: 3.1
  - **Coverage**: Run focused and affected skill tests, strict OpenSpec, work-package validation, context-drift, link checks, scope checks, and diff checks.

- [ ] Checkpoint: review the complete branch diff, reconcile task checkboxes with commit reality, and preserve validation evidence.
