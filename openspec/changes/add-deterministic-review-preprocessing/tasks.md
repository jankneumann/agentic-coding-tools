# Tasks: add-deterministic-review-preprocessing

Sizes follow the plan-feature sizing table. No task is XL; one is L and is
flagged in design D9 as the chained dispatcher work.

## 1. Contracts

- [x] 1.1 Write contract validation tests for the five JSON and markdown contracts (size: S)
  **Spec scenarios**: skill-workflow Review Packet As Default Input (metadata carries selection and rule groups), Per-Vendor Coverage Contract, Diff-Grounded Fact Check Before Synthesis (removal is never silent)
  **Contracts**: `contracts/review-packet.schema.json`, `contracts/review-rules.schema.json`, `contracts/vendor-coverage.schema.json`, `contracts/fact-check-decisions.schema.json`
  **Design decisions**: D1, D5, D6
  **Dependencies**: None
  **Files**: `skills/tests/parallel-infrastructure/test_review_preprocessing_contracts.py`

- [x] 1.2 Repoint the packet metadata contract test to the v2 contract via `openspec_paths.change_dir` (size: XS)
  **Dependencies**: 1.1
  **Files**: `skills/tests/parallel-infrastructure/test_review_packet_schema.py`

- [ ] Checkpoint: run contract tests, review diff, verify scope

## 2. Fact-check pass

- [x] 2.1 Write tests for the fact-check parser, protected-subject veto, and decision file (size: M)
  **Spec scenarios**: skill-workflow Diff-Grounded Fact Check Before Synthesis (all four scenarios)
  **Contracts**: `contracts/fact-check-decisions.schema.json`
  **Design decisions**: D6, D10
  **Dependencies**: 1.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_fact_check.py`

- [x] 2.2 Implement `fact_check.py` with the ported prompt, economy-tier model resolution, veto, and decision writer (size: M)
  **Dependencies**: 2.1
  **Files**: `skills/parallel-infrastructure/scripts/fact_check.py`, `skills/parallel-infrastructure/scripts/prompts/fact_check_system.md`, `skills/parallel-infrastructure/scripts/prompts/fact_check_user.md`

- [x] 2.3 Write tests for the convergence loop calling fact-check after checkpoint and before synthesis, with the `fact_check=False` switch (size: S)
  **Spec scenarios**: review-convergence-safety Terminal vendor results are checkpointed incrementally (checkpoint precedes fact-check removal)
  **Design decisions**: D6
  **Dependencies**: 2.2
  **Files**: `skills/tests/autopilot/test_convergence_fact_check.py`

- [x] 2.4 Wire fact-check into `converge()` and add `fact_check_tokens`, `fact_check`, and `fact_check_removed` to the round manifest writer (size: M)
  **Dependencies**: 2.3
  **Files**: `skills/autopilot/scripts/convergence_loop.py`, `skills/parallel-infrastructure/scripts/checkpoint_findings.py`

- [ ] Checkpoint: run fact-check and convergence tests, review diff, verify scope

## 3. OCR vendor

- [x] 3.1 Write tests for the OCR adapter rewrite and coercion aliases, including zero-line comments and a missing binary (size: S)
  **Spec scenarios**: skill-workflow Optional OCR Reviewer Vendor (all three scenarios), Finding Coercion Before Validation (OCR vocabulary is coerced)
  **Contracts**: `contracts/ocr-adapter.md`
  **Design decisions**: D7
  **Dependencies**: 1.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_ocr_adapter.py`, `skills/tests/parallel-infrastructure/test_finding_coercion.py`

- [x] 3.2 Implement `ocr_adapter.py` (size: M)
  **Dependencies**: 3.1
  **Files**: `skills/parallel-infrastructure/scripts/ocr_adapter.py`

- [x] 3.3 Add OCR aliases to the coercion sidecar and its install_assets mirror (size: XS)
  **Dependencies**: 3.1
  **Files**: `skills/parallel-infrastructure/scripts/finding-coercion.json`, `skills/parallel-infrastructure/install_assets/openspec/schemas/finding-coercion.json`

- [x] 3.4 Write a discovery test asserting `ocr-local` is Tier 3 when the binary is absent (size: XS)
  **Spec scenarios**: skill-workflow Optional OCR Reviewer Vendor (OCR absent leaves dispatch unchanged)
  **Dependencies**: 3.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`

- [x] 3.5 Declare the `ocr-local` agent in `agents.yaml` with review mode only (size: XS)
  **Dependencies**: 3.4
  **Files**: `agent-coordinator/agents.yaml`

- [ ] Checkpoint: run adapter, coercion, and discovery tests, review diff, verify scope

## 4. Packet selection and rule groups

- [x] 4.1 Write tests for `select_files` gate order, reasons, include override, per-file ceiling, and the no-file-without-reason invariant (size: M)
  **Spec scenarios**: skill-workflow Deterministic File Selection Before Packet Rendering (all four scenarios)
  **Contracts**: `contracts/review-packet.schema.json`, `contracts/review-rules.schema.json`
  **Design decisions**: D1, D2
  **Dependencies**: 1.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_file_selection.py`

- [x] 4.2 Implement `file_selection.py` (size: M)
  **Dependencies**: 4.1
  **Files**: `skills/parallel-infrastructure/scripts/file_selection.py`

- [x] 4.3 Write tests for rule resolution order, project-over-default, grouping key, and missing project file (size: S)
  **Spec scenarios**: skill-workflow Path-Glob Rule Groups In The Review Packet (all three scenarios)
  **Contracts**: `contracts/review-rules.schema.json`
  **Design decisions**: D4
  **Dependencies**: 1.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_rules.py`

- [x] 4.4 Implement `review_rules.py` (size: S)
  **Dependencies**: 4.3
  **Files**: `skills/parallel-infrastructure/scripts/review_rules.py`

- [x] 4.5 Author the embedded `review-rules.json` for this repository's file classes plus its install_assets mirror (size: S)
  **Dependencies**: 4.4
  **Files**: `skills/parallel-infrastructure/scripts/review-rules.json`, `skills/parallel-infrastructure/install_assets/openspec/schemas/review-rules.json`

- [ ] Checkpoint: run selection and rules tests, review diff, verify scope

- [x] 4.6 Write tests for packet building with selection meta, rule groups, truncated list, v2 metadata, and preview parity (size: M)
  **Spec scenarios**: skill-workflow Review Packet As Default Input (all four scenarios), Preview Parity For File Selection
  **Contracts**: `contracts/review-packet.schema.json`
  **Design decisions**: D1, D2, D4
  **Dependencies**: 4.2, 4.4
  **Files**: `skills/tests/parallel-infrastructure/test_review_packet.py`

- [x] 4.7 Integrate selection and rule groups into `review_packet.py` with a `preview` entry point (size: M)
  **Dependencies**: 4.6
  **Files**: `skills/parallel-infrastructure/scripts/review_packet.py`

- [ ] Checkpoint: run packet tests, review diff, verify scope

## 5. Snippet anchor and line resolver

- [x] 5.1 Write tests for hunk parsing, new-side, old-side, full-file, unresolved, and vendor-range precedence (size: M)
  **Spec scenarios**: skill-workflow Ingest-Time Line Resolution From Verbatim Snippet (all four scenarios)
  **Contracts**: `contracts/vendor-coverage.schema.json` (finding fragment)
  **Design decisions**: D3
  **Dependencies**: 1.2
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_line_resolver.py`

- [x] 5.2 Implement `line_resolver.py` (size: M)
  **Dependencies**: 5.1
  **Files**: `skills/parallel-infrastructure/scripts/line_resolver.py`

- [x] 5.3 Write schema tests for optional `existing_code`, `line_resolution`, and `coverage` on canonical, mirror, and sentinel-derived copies (size: S)
  **Spec scenarios**: skill-workflow Review Findings Schema Extension (snippet and coverage are optional; schema copies stay identical)
  **Dependencies**: 1.2
  **Files**: `skills/tests/parallel-infrastructure/test_review_findings_schema.py`

- [x] 5.4 Add the optional fields to the canonical schema and its install_assets mirror (size: XS)
  **Dependencies**: 5.3
  **Files**: `openspec/schemas/review-findings.schema.json`, `skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`

- [ ] Checkpoint: run resolver and schema tests, review diff, verify scope

- [ ] 5.5 Write dispatcher tests for resolution after validation and the `unanchored_findings` manifest count (size: S)
  **Spec scenarios**: skill-workflow Finding Coercion Before Validation (line resolution runs after validation), Review Manifest Generation
  **Design decisions**: D3
  **Dependencies**: 5.2, 5.4, 2.4
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`

- [ ] 5.6 Call the resolver from `_ingest_stdout` after validation and report unanchored counts (size: S)
  **Dependencies**: 5.5
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`, `skills/parallel-infrastructure/scripts/checkpoint_findings.py`

- [ ] Checkpoint: run dispatcher tests, review diff, verify scope

## 6. Matching and ledger on snippets

- [ ] 6.1 Write tests for the snippet-equality match band and axis gate precedence (size: S)
  **Spec scenarios**: skill-workflow Cross-Vendor Finding Matching (equal snippets match despite drifted lines)
  **Design decisions**: D3
  **Dependencies**: 5.6
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_consensus_synthesizer.py`

- [ ] 6.2 Add the snippet band to `match_score` (size: XS)
  **Dependencies**: 6.1
  **Files**: `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`

- [ ] 6.3 Write tests for snippet fingerprint stability, token fallback, and compact by snippet presence (size: S)
  **Spec scenarios**: skill-workflow Gate-Time Review Ledger (snippet fingerprint is stable across rewording), Compact Before New Hunt (snippet presence decides for anchored items)
  **Dependencies**: 5.6
  **Files**: `skills/tests/parallel-infrastructure/test_review_ledger.py`

- [ ] 6.4 Update `fingerprint` and `compact` in `review_ledger.py` (size: S)
  **Dependencies**: 6.3
  **Files**: `skills/parallel-infrastructure/scripts/review_ledger.py`

- [ ] Checkpoint: run synthesizer and ledger tests, review diff, verify scope

## 7. Per-vendor coverage

- [ ] 7.1 Write tests for coverage rate, partial eligibility, unreported default, and skipped-reason fill (size: S)
  **Spec scenarios**: skill-workflow Per-Vendor Coverage Contract (all three scenarios), Review Manifest Generation (manifest carries selection and per-vendor quality fields)
  **Contracts**: `contracts/vendor-coverage.schema.json`
  **Design decisions**: D5
  **Dependencies**: 6.2, 6.4
  **Files**: `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`, `skills/parallel-infrastructure/scripts/tests/test_consensus_synthesizer.py`, `skills/tests/parallel-infrastructure/test_checkpoint_findings.py`

- [ ] 7.2 Compute coverage in the dispatcher, honor partial eligibility in the synthesizer's quorum count, and write coverage fields to the manifest (size: L, flagged: three files in one chained package; splitting would separate the eligibility producer from its consumer and lose the round-trip test)
  **Dependencies**: 7.1
  **Files**: `skills/parallel-infrastructure/scripts/review_dispatcher.py`, `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`, `skills/parallel-infrastructure/scripts/checkpoint_findings.py`

- [ ] 7.3 Add the coverage request to the schema-derived prompt contract block (size: XS)
  **Dependencies**: 7.2
  **Files**: `skills/parallel-infrastructure/scripts/review_findings_schema.py`

- [ ] Checkpoint: run coverage tests, review diff, verify scope

## 8. Fixture set

- [ ] 8.1 Write the fixture-driven tests for fact-check precision against a recorded transcript and for the line-resolution floor (size: S)
  **Spec scenarios**: skill-workflow Labeled Review Fixture Set (both scenarios)
  **Design decisions**: D8
  **Dependencies**: 2.4, 5.6
  **Files**: `skills/tests/parallel-infrastructure/test_fact_check_fixture.py`, `skills/tests/parallel-infrastructure/test_line_resolver_fixture.py`

- [ ] 8.2 Author the labeled fixture manifest from real diffs with at least ten findings (size: M)
  **Dependencies**: 8.1
  **Files**: `skills/tests/parallel-infrastructure/fixtures/review-fixtures/manifest.json`, `skills/tests/parallel-infrastructure/fixtures/review-fixtures/*.diff`, `skills/tests/parallel-infrastructure/fixtures/review-fixtures/*.findings.json`, `skills/tests/parallel-infrastructure/fixtures/review-fixtures/fact-check-transcript.json`

- [ ] Checkpoint: run fixture tests, review diff, verify scope

## 9. Integration

- [ ] 9.1 Run the full parallel-infrastructure and autopilot suites plus `skills/install.sh --check` (size: S)
  **Dependencies**: 2.4, 3.5, 4.7, 6.4, 7.3, 8.2
  **Files**: none

- [ ] 9.2 Document the selection gate, rule sidecar, coverage, fact-check, and OCR vendor in the parallel-infrastructure and autopilot skill docs (size: S)
  **Dependencies**: 9.1
  **Files**: `skills/parallel-infrastructure/SKILL.md`, `skills/autopilot/SKILL.md`, `docs/guides/workflow.md`

- [ ] 9.3 Record the live fact-check precision and token delta in the validation report (size: S)
  **Dependencies**: 9.1
  **Files**: `openspec/changes/add-deterministic-review-preprocessing/validation-report.md`

- [ ] Checkpoint: run full suites, review diff, verify scope
