# Tasks: Build structured vendor result channel

> Change ID: `build-structured-vendor-result-channel`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] 1.1 Write envelope parser contract tests (M)
  **Spec scenarios**: structured vendor results, malformed result, async status.
- [x] 1.2 Implement versioned envelope parsing (M)
  **Dependencies**: 1.1.
- [x] 1.3 Write coordinator ledger lifecycle tests (M)
  **Spec scenarios**: async lifecycle and terminal failure.
- [x] Checkpoint: run dispatcher tests, review diff, verify scope.
- [x] 1.4 Wire async CLI lifecycle to submit_work and complete_work (L)
  **Dependencies**: 1.2, 1.3.
- [x] 2.1 Write lock recovery service and API contract tests (M)
  **Spec scenarios**: session end and idempotent release.
- [x] 2.2 Implement list and release-by-agent endpoints plus proxy methods (L)
  **Dependencies**: 2.1.
- [x] Checkpoint: run coordinator lock tests, review diff, verify scope.
- [x] 3.1 Write SDK mode-boundary tests (S)
  **Spec scenarios**: unsupported SDK mode is rejected before network work.
- [x] 3.2 Document SDK dispatch scope and vendor capability matrix (S)
  **Dependencies**: 3.1.
- [ ] 3.3 Run strict OpenSpec, focused suites, lint, and vendor review (M)
  **Dependencies**: 1.4, 2.2, 3.2.
