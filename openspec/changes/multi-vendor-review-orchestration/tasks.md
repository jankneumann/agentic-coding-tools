# Tasks: Multi-Vendor Review Orchestration

## Task 1: Review Dispatcher Script

**Status**: planned
**Depends on**: —

Create `skills/parallel-implement-feature/scripts/review_dispatcher.py`:

- [ ] `ReviewDispatcher` protocol definition
- [ ] `ReviewerInfo`, `DispatchResult`, `ReviewResult` data classes
- [ ] `discover_reviewers()` — query coordinator discovery, fallback to `which` detection
- [ ] `CodexAdapter` — subprocess dispatch via `codex exec`
- [ ] `GeminiAdapter` — subprocess dispatch via `gemini code`
- [ ] `ClaudeAdapter` — subprocess dispatch via `claude code`
- [ ] `dispatch_all_reviews()` — parallel subprocess spawn
- [ ] `wait_for_results()` — collect results with timeout handling
- [ ] `write_review_manifest()` — emit `reviews/review-manifest.json` with vendor metadata, timing, quorum status
- [ ] Model fallback on 429/capacity errors (retry with fallback model before giving up)
- [ ] Auth error detection and user-facing re-login messages
- [ ] CLI entry point for standalone testing
- [ ] Unit tests for adapter CLI construction, result parsing, error classification

## Task 2: Consensus Synthesizer Script

**Status**: planned
**Depends on**: —

Create `skills/parallel-implement-feature/scripts/consensus_synthesizer.py`:

- [ ] `VendorFindings`, `FindingMatch`, `ConsensusFinding`, `ConsensusReport` data classes
- [ ] `load_findings()` — load and validate per-vendor findings JSON
- [ ] `match_findings()` — cross-vendor finding matching (location + type + similarity)
- [ ] `compute_consensus()` — classify as confirmed/unconfirmed/disagreement
- [ ] `write_report()` — output consensus-report.json
- [ ] CLI entry point for standalone testing
- [ ] Unit tests for matching algorithm with fixture findings

## Task 3: Consensus Report Schema

**Status**: planned
**Depends on**: —

Create `openspec/schemas/consensus-report.schema.json`:

- [ ] Schema definition extending review-findings pattern
- [ ] `reviewers` array with vendor, timing, success metadata
- [ ] `consensus_findings` array with match status, agreed criticality/disposition
- [ ] `quorum_met` boolean
- [ ] `review_manifest` metadata section

## Task 4: Integration Orchestrator Enhancement

**Status**: planned
**Depends on**: Task 1, Task 2, Task 3

Update `skills/parallel-implement-feature/scripts/integration_orchestrator.py`:

- [ ] `record_review_findings()` — accept optional `vendor` parameter
- [ ] `record_consensus()` — new method for consensus reports
- [ ] `check_integration_gate()` — use consensus findings (confirmed block, unconfirmed warn)
- [ ] Update `generate_execution_summary()` to include multi-vendor review section
- [ ] Update existing tests for backward compatibility

## Task 5: Review Dispatch Skill Integration

**Status**: planned
**Depends on**: Task 1, Task 4

Update parallel workflow skills to use review dispatcher:

- [ ] Update `parallel-implement-feature/SKILL.md` Phase C to reference multi-vendor dispatch
- [ ] Add review dispatch step between package completion and integration gate
- [ ] Add consensus synthesis step before integration gate check
- [ ] Update `parallel-review-plan/SKILL.md` to document vendor dispatch usage
- [ ] Update `parallel-review-implementation/SKILL.md` to document vendor dispatch usage

## Task 6: Vendor Adapter Tests

**Status**: planned
**Depends on**: Task 1

- [ ] Mock subprocess tests for each adapter (codex, gemini, claude)
- [ ] Timeout handling tests
- [ ] Invalid JSON output handling tests
- [ ] Missing CLI binary tests (graceful degradation)
- [ ] Discovery fallback tests (coordinator unavailable → `which` detection)

## Task 7: Spec Updates

**Status**: planned
**Depends on**: Task 4, Task 5

- [ ] Add multi-vendor review requirements to `openspec/specs/skill-workflow/spec.md`
- [ ] Document consensus model in parallel development design doc
