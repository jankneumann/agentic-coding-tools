# Change Context: add-decision-index

<!-- 3-phase incremental artifact:
     Phase 1 (pre-implementation): Req ID, Spec Source, Description, Contract Ref, Design Decision,
       Test(s) planned. Files Changed = "---". Evidence = "---".
     Phase 2 (implementation): Files Changed populated. Tests pass (GREEN).
     Phase 3 (validation): Evidence filled with "pass <SHA>", "fail <SHA>", or "deferred <reason>". -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | `specs/skill-workflow/spec.md` | Phase Entries support optional inline `architectural:` tag on Decision bullets | --- | D1 (inline backtick over YAML sidecar) | `skills/session-log/SKILL.md`, `skills/explore-feature/scripts/decision_index.py` | `test_decision_index.py::TestExtractDecisions::test_extract_single_tagged_decision` | pass 816dc13 |
| skill-workflow.2 | `specs/skill-workflow/spec.md` | Tag syntax: `` `architectural: <kebab-case>` `` — backtick span, literal key, kebab-case identifier matching capability dir | --- | D1 | `skills/session-log/SKILL.md`, `skills/explore-feature/scripts/decision_index.py` | `test_decision_index.py::TestExtractDecisions::test_extract_multiple_capabilities_in_phase` | pass 816dc13 |
| skill-workflow.3 | `specs/skill-workflow/spec.md` | Only first `architectural:` occurrence per bullet is counted (deterministic extraction) | --- | D2 (per-bullet precision) | `skills/explore-feature/scripts/decision_index.py` | `test_decision_index.py::TestExtractDecisions::test_first_occurrence_only_per_bullet` | pass 816dc13 |
| skill-workflow.4 | `specs/skill-workflow/spec.md` | Untagged Decisions remain valid and MUST NOT be required to carry a tag | --- | D2 | `skills/session-log/SKILL.md`, `skills/explore-feature/scripts/decision_index.py` | `test_decision_index.py::TestExtractDecisions::test_untagged_decision_excluded` | pass 816dc13 |
| skill-workflow.5 | `specs/skill-workflow/spec.md` | Sanitizer preserves tagged Decisions unredacted (no changes to `sanitize_session_log.py` required) | --- | D1 (sanitizer compatibility) | `skills/explore-feature/tests/test_decision_index.py` (verifies, no sanitizer code change) | `test_decision_index.py::TestSanitizerPreservesTags::test_sanitizer_preserves_tagged_decisions` | pass 816dc13 |
| software-factory-tooling.1 | `specs/software-factory-tooling/spec.md` | Emitter extracts tagged Decisions from every indexed session-log and writes per-capability markdown | --- | D4 (emitter pass over standalone walker) | `skills/explore-feature/scripts/decision_index.py`, `skills/explore-feature/scripts/archive_index.py` | `test_decision_index.py::TestEmitDecisionIndex::test_aggregates_by_capability_reverse_chronological` | pass 816dc13 |
| software-factory-tooling.2 | `specs/software-factory-tooling/spec.md` | Each Decision record: title, rationale, change-id, phase name/date, back-ref, status | --- | D6 (capability files) | `skills/explore-feature/scripts/decision_index.py` | `test_decision_index.py::TestEmitDecisionIndex::test_decision_record_fields_complete` | pass 816dc13 |
| software-factory-tooling.3 | `specs/software-factory-tooling/spec.md` | Supersession via `` `supersedes:` `` marker: mark earlier `superseded`, emit bidirectional Supersedes/Superseded by links, preserve earlier entry | --- | D3 (explicit supersession) | `skills/explore-feature/scripts/decision_index.py`, `skills/session-log/SKILL.md` | `test_decision_index.py::TestEmitDecisionIndex::test_supersession_chain_preserved` | pass 816dc13 |
| software-factory-tooling.4 | `specs/software-factory-tooling/spec.md` | Emitter is incremental: re-runs update only affected capability files | --- | D4 | `skills/explore-feature/scripts/decision_index.py`, `skills/explore-feature/scripts/archive_index.py` | `test_decision_index.py::TestEmitDecisionIndex::test_new_capability_file_auto_created`, `test_byte_identical_on_rerun` | pass 816dc13 |
| software-factory-tooling.5 | `specs/software-factory-tooling/spec.md` | Emitter produces deterministic output: twice-run yields byte-identical files | --- | D4 | `skills/explore-feature/scripts/decision_index.py`, `Makefile`, `.github/workflows/ci.yml` | `test_decision_index.py::TestEmitDecisionIndex::test_byte_identical_on_rerun` | pass 816dc13 |
| software-factory-tooling.6 | `specs/software-factory-tooling/spec.md` | Emitter generates `docs/decisions/README.md` explaining purpose, generation, and how to read the timeline | --- | D7 (generated README) | `skills/explore-feature/scripts/decision_index.py`, `docs/decisions/README.md` | `test_decision_index.py::TestEmitReadme::test_generated_readme_listing_capabilities` | pass 816dc13 |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Inline backtick tags | Sanitizer-compatible, write-once economy | `decision_index.py:extract_decisions` regex; no changes to `sanitize_session_log.py` | YAML sidecars double the write surface and risk prose/structured drift. Backtick spans pass the sanitizer's existing kebab-case allowlist and non-scanning-of-backticks rule. |
| D2 — Per-bullet tags | Multi-capability phases need per-bullet precision | Extraction anchors on the `1. **Title** \`architectural: <cap>\`` pattern; one `TaggedDecision` per matching bullet | Per-phase tags force one-capability-per-phase (unnatural) or ambiguous "multiple phase tags" schema. |
| D3 — Explicit supersession | Inferred supersession is wrong-but-confident and damages trust | `decision_index.py` resolves `supersedes:` markers by change-id#phase/index; annotates both directions in output | Heuristic "later decision in same capability touching same topic" will miscategorize often enough to poison the index. |
| D4 — Extend archive-intelligence emitter | One source of truth for archive contents | New emitter pass invoked after existing archive-index walk; respects existing incremental checkpoint | Parallel walker duplicates discovery + incremental logic and risks seeing different change sets. |
| D5 — Heuristic + agent review backfill | Miscategorizations on day one would kill adoption | `backfill_decision_tags.py` emits JSON proposals with confidence scores; agent reviews ambiguous cases before committing edits | Pure heuristic poisons trust; pure manual (30+ session-logs × multiple Decisions) is too much unaided human work. |
| D6 — Capability files (one per `openspec/specs/<cap>/`) | Questions are asked per-capability | Emitter writes `docs/decisions/<capability>.md` per spec capability | Scrolling a monolithic index doesn't serve "how did we get to X?" queries. |
| D7 — Generated README | Capability set changes over time | `emit_readme()` regenerates README on every `make decisions` run | Hand-maintained README diverges as new capabilities are added. |

## Coverage Summary

- **Requirements traced**: 11/11
- **Tests mapped**: 11/11 requirements have at least one test
- **Evidence collected**: 11/11 requirements have pass evidence at commit `816dc13` (iteration 1 HEAD); 54 tests pass at that commit including 6 regression tests added for the multi-vendor-review findings
- **Gaps identified**: none
- **Deferred items**:
    - 133 backfill proposals remain in `backfill-proposals.json` for subsequent human review — per D5 + proposal §3, goal is coverage of pivotal decisions, not exhaustive labeling
    - Accepted-as-low iteration findings: `_SUPERSEDES_REF` regex could be tightened to kebab-only; no-logging on missing session-log; CI failure message could include a diff preview; em-dash-in-rationale edge case. All documented in review-findings.json at `accept` disposition.
