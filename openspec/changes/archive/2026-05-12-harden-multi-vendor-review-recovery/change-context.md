# Change Context — harden-multi-vendor-review-recovery

**Generated**: 2026-05-09 (validation pass)
**Branch**: openspec/harden-multi-vendor-review-recovery
**Commit at validation**: 374a19b

## Summary

Hardens the multi-vendor review convergence loop with a durable-checkpoint + observability + path-safety pattern. The `converge()` API in `convergence_loop.py` now persists per-vendor findings to disk BEFORE invoking the consensus synthesizer; if synthesis raises, the original exception propagates but the persisted findings remain on disk for postmortem analysis. **This is durability, not automatic recovery** — the proposal does not introduce subprocess fallback. Recovery awaits a separate `consensus_synthesizer.py:59` parser-fix proposal.

The CLI dispatcher (`review_dispatcher.py`) was migrated to the same shared helper (`checkpoint_findings.py`) so both paths share atomic-write semantics, schema-versioned manifests, and path-safety guards. Per-vendor file paths and contents at the CLI dispatcher's call site remain byte-identical for backward compatibility.

## Requirement Traceability Matrix

5 requirements / 22 scenarios across `specs/skill-workflow/spec.md`. Tests live in `skills/tests/parallel-infrastructure/` and `skills/tests/autopilot/`. Evidence column records the short-SHA at which the test was passing (`pass 374a19b`).

| Req | Spec § | Description | Test(s) | Evidence |
|-----|--------|-------------|---------|----------|
| R1.S1 | spec.md:23 | Round-trip preserves vendor findings | `test_checkpoint_findings.py::test_round_trip_single_vendor`, `::test_round_trip_multi_vendor` | pass 374a19b |
| R1.S2 | spec.md:29 | Manifest is sufficient to enumerate vendors | `test_checkpoint_findings.py::test_read_uses_manifest_index_not_glob` | pass 374a19b |
| R1.S3 | spec.md:35 | Manifest preserves existing dispatcher fields | `test_checkpoint_findings.py::test_manifest_has_legacy_fields`, `test_review_dispatcher_migration.py::test_orchestrator_write_manifest_has_legacy_fields`, `::test_orchestrator_write_manifest_has_superset_fields` | pass 374a19b |
| R1.S4 | spec.md:41 | In-process callers without dispatch metadata | `test_checkpoint_findings.py::test_in_process_caller_no_dispatch_metadata` | pass 374a19b |
| R1.S5 | spec.md:47 | quorum_received reflects actual successful vendors | `test_checkpoint_findings.py::test_quorum_received_derived_from_dispatch_success`, `test_convergence_checkpoint.py::test_manifest_records_total_dispatched_as_quorum_requested` | pass 374a19b |
| R1.S6 | spec.md:52 | change_id is optional for CLI dispatcher | `test_checkpoint_findings.py::test_manifest_change_id_optional_null`, `::test_manifest_change_id_present` | pass 374a19b |
| R1.S7 | spec.md:59 | Manifest write is atomic (write→fsync→rename→fsync-parent) | `test_checkpoint_findings.py::test_atomic_write_no_tmp_residue`, `::test_atomic_write_overwrites_existing`, `::test_atomic_write_calls_fsync` | pass 374a19b |
| R1.S8 | spec.md:64 | Concurrent converge calls use distinct cache directories | `test_checkpoint_findings.py::test_concurrent_dirs_isolated` | pass 374a19b |
| R2.S1 | spec.md:73 | Successful synthesis path also writes checkpoints | `test_convergence_checkpoint.py::test_success_path_writes_checkpoint`, `::test_multi_round_writes_separate_checkpoints` | pass 374a19b |
| R2.S2 | spec.md:80 | Synthesis failure leaves checkpoint intact and exception propagates | `test_convergence_checkpoint.py::test_synthesis_failure_preserves_checkpoint`, `test_convergence_durability_integration.py::test_line_range_bug_propagates_with_durable_checkpoint` | pass 374a19b |
| R2.S3 | spec.md:87 | Empty review round still produces a manifest | `test_checkpoint_findings.py::test_empty_round_produces_manifest`, `test_convergence_checkpoint.py::test_empty_round_quorum_lost_no_crash` | pass 374a19b |
| R2.S4 | spec.md:93 | Checkpoint write permission error | `test_convergence_checkpoint.py::test_checkpoint_write_failure_emits_log_and_propagates` | pass 374a19b |
| R3.S1 | spec.md:105 | Existing callers see no behavior change | `test_convergence_result_shape.py::test_existing_caller_pattern_with_full_kwargs`, `::test_no_synthesis_failed_field` | pass 374a19b |
| R3.S2 | spec.md:110 | Recovery-aware callers can locate the checkpoint | `test_convergence_result_shape.py::test_default_checkpoint_dir_is_none`, `::test_checkpoint_dir_accepts_path`, `::test_checkpoint_dir_field_type_annotation` | pass 374a19b |
| R4.S1 | spec.md:128 | Synthesis failure with checkpoint emits structured log entry | `test_convergence_checkpoint.py::test_synthesis_failure_emits_log_entry`, `test_convergence_durability_integration.py::test_line_range_bug_propagates_with_durable_checkpoint` (asserts payload) | pass 374a19b |
| R4.S2 | spec.md:134 | Synthesis success emits no log entry | `test_convergence_checkpoint.py::test_happy_path_no_failure_log` | pass 374a19b |
| R4.S3 | spec.md:138 | Checkpoint write failure emits a different log entry | `test_convergence_checkpoint.py::test_checkpoint_write_failure_emits_log_and_propagates` | pass 374a19b |
| R4.S4 | spec.md:144 | Logging failure does not mask result | `test_checkpoint_findings.py::test_safe_log_error_swallows_handler_exception`, `test_convergence_checkpoint.py::test_handler_failure_does_not_mask_synthesis_exception` | pass 374a19b |
| R5.S1 | spec.md:154 | artifacts_dir is normalized | `test_checkpoint_findings.py::test_artifacts_dir_resolves_relative`, `::test_validate_path_safety_returns_resolved` | pass 374a19b |
| R5.S2 | spec.md:159 | vendor name with path separators is rejected | `test_checkpoint_findings.py::test_vendor_name_rejected[*]` (6 parametrized: `../escape`, `vendor/with/slash`, `vendor with spaces`, `vendor.with.dots`, `<empty>`, `vendor:colon`), `::test_manifest_vendor_entry_name_rejected` | pass 374a19b |
| R5.S3 | spec.md:164 | review_type is constrained to {plan, implementation} | `test_checkpoint_findings.py::test_review_type_rejected[*]` (5 parametrized: `plans`, `Plan`, `implementations`, `<empty>`, `evaluation`), `::test_write_manifest_review_type_rejected` | pass 374a19b |
| R5.S4 | spec.md:169 | Manifest-referenced paths stay within manifest's directory | `test_checkpoint_findings.py::test_read_vendor_findings_rejects_path_traversal`, `::test_write_manifest_rejects_findings_path_with_separator`, `::test_write_manifest_rejects_findings_path_with_traversal`, `::test_write_manifest_rejects_findings_path_non_string` | pass 374a19b |

## Coverage Summary

| Metric | Value |
|--------|-------|
| Requirements traced | 5 / 5 |
| Scenarios traced | 22 / 22 |
| Tests mapped | 85 (proposal-specific, parametrized expansion of ~75 raw functions) |
| Evidence collected | 22 / 22 |
| Gaps | 0 |
| Deferred | 0 |

## Defense-in-Depth Tests Beyond Spec Scenarios

These tests guard schema-version forward-compat, the round-2 IMPL_REVIEW fixes, and the CLI-dispatcher write-shim contract. They are not directly mapped to a numbered scenario but verify properties the spec requires:

- `test_checkpoint_findings.py::test_schema_version_is_one` — pin schema_version constant
- `test_checkpoint_findings.py::test_read_manifest_rejects_unknown_schema_version_v2` — forward-compat: reject manifests this reader can't handle
- `test_checkpoint_findings.py::test_read_manifest_rejects_unknown_schema_version_v0` — same, downgrade direction
- `test_checkpoint_findings.py::test_read_manifest_rejects_missing_schema_version` — schema_version is required
- `test_checkpoint_findings.py::test_read_vendor_findings_propagates_schema_version_error` — schema-version error surfaces through the read path
- `test_review_dispatcher_migration.py::test_write_manifest_rejects_non_canonical_filename` — backward-compat shim must validate `output_path.name == "review-manifest.json"` (round-1 R1-C3 fix)
- `test_checkpoint_findings.py::test_validate_finding_*` (3 tests: required_fields, criticality_enum, disposition_enum) — wrapper-object schema enforcement

## Out-of-Band Verification

Manual integration test in `test_convergence_durability_integration.py::test_line_range_bug_propagates_with_durable_checkpoint`:

1. Feed `line_range: "10-20"` (the malformed string shape that motivated this proposal) to `converge()`
2. Synthesizer raises (the unfixed `consensus_synthesizer.py:59` bug — a separate proposal)
3. Verify checkpoint files exist on disk and contain the original findings
4. Verify the structured log `convergence.synthesis_failed_with_checkpoint` was emitted with all required payload fields
5. The exception propagates to the caller (no fallback)

This is the durability+observability claim end-to-end. Recovery is **not** in scope.

## Quality Gates at Validation Time

| Gate | Result | Notes |
|------|--------|-------|
| `openspec validate --strict` | valid | 0 unchecked tasks after §7.0 reconciliation commit 374a19b |
| Proposal tests | 85/85 pass | `test_checkpoint_findings.py` (50 cases) + `test_review_dispatcher_migration.py` (9) + `test_convergence_result_shape.py` (5) + `test_convergence_checkpoint.py` (9) + `test_convergence_durability_integration.py` (2) + 10 expanded parametrized cases |
| Adjacent test regression | 152 pass / 16 errors (pre-existing) | All errors trace to `openspec/changes/add-prototyping-stage/contracts/schemas/synthesis-plan.schema.json` (different change-id, not on this branch). Confirmed unrelated. |
| ruff | clean | All proposal files |
| mypy --strict | clean | `checkpoint_findings.py`, `convergence_loop.py` |
| Task checkbox drift gate (§7.0) | reconciled | 18→0 unchecked at commit 374a19b |
