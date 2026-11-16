# Plan Findings: make-expedite-fail-closed-on-missing-validation

## Iteration 1 (2026-11-15, PR #701 remediation)

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | consistency | high | context-drift-gate failed on #702: wp-expedite changes `SKILL.md` and `docs/mental-models.md`, implying the `documentation` surface. | Surface declared; `validate_context_impact` VALID against #702's changed files. |
| 2 | consistency | high | `TestCli.test_exit_zero_when_ready` and `TestCli.test_json_output_shape` rely on a report-less READY and also flip; they were not listed. | Listed in proposal Impact; task 1.1 rewrites them. |
| 3 | completeness | high | The new keyword-only signature breaks four direct `check_validation_report(report)` callers; no task updated them. | Task 1.3 updates them; proposal lists them. |
| 4 | completeness | medium | No defined behaviour for an explicit nonexistent `--validation-report` path or an unreadable report. | Scenarios `explicit-path-missing`, `unreadable-report-fails`, `override-explicit-missing-path`, `override-not-applied-to-unreadable-report`; tests in 1.1. |
| 5 | testability | medium | "READY regardless of deployable surface" was never exercised with a non-deployable change. | Test `test_ready_non_deployable_spec_only_report` added to 1.1. |
| 6 | testability | medium | Fixture-only drift test misses `skip` added in an unexercised branch. | D4 and task 3.1 add an AST check that `status="skip"` appears only in `check_rework_report`. |
| 7 | consistency | medium | Roadmap ri-02 description still said "a deployable change", contradicting the proposal (all changes block). | Roadmap description corrected. |

## Vendor review remediation (2026-11-15)

Only codex returned findings; the other vendors failed (see the bind-merge-verdicts plan-findings), so this phase is DEGRADED.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| V5 | contract_mismatch | medium | The roadmap proposal still exempted non-deployable changes from the missing-report block, which contradicts ri-02's fail-closed-with-override contract. | The roadmap proposal's capability text and acceptance outcome now match ri-02. |
| V6 | spec_gap | medium | `_probe_paths` uses `is_file()`, so an automatically probed directory reads as "missing" and becomes overridable. | Task 1.3 makes discovery use `exists()` so an invalid candidate is reported as unreadable. Task 1.1 adds `test_probed_directory_candidate_is_unreadable_not_missing`, and the spec scenario covers probed paths. |
