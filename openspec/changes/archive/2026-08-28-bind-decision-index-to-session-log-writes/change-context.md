# Change Context: bind-decision-index-to-session-log-writes

Capability: `skill-workflow`. Rows are one-per-scenario, following the convention
`fix-architecture-freshness-evidence` established.

Contract Ref is `---` throughout: `contracts/` holds only `README.md`, which records that
all four sub-types were evaluated and none applies. Per the skill, a contracts directory
containing only a README means "no contracts applicable".

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|---|---|---|---|---|---|---|---|
| sw.1 | specs/skill-workflow/spec.md | All three steps succeed | --- | --- | --- | test_phase_record_write_both.py (existing pin) | --- |
| sw.2 | specs/skill-workflow/spec.md | Coordinator unavailable triggers local-file fallback | --- | --- | --- | test_phase_record_write_both.py (existing pin) | --- |
| sw.3 | specs/skill-workflow/spec.md | Sanitizer failure does not block coordinator write | --- | --- | --- | test_phase_record_write_both.py (existing pin) | --- |
| sw.4 | specs/skill-workflow/spec.md | Markdown append failure does not block coordinator write | --- | --- | --- | test_phase_record_write_both.py (existing pin) | --- |
| sw.5 | specs/skill-workflow/spec.md | Regeneration leaves the decision index current | --- | D1 | --- | test_decision_index_binding.py::test_index_is_current_after_write (1.1) | --- |
| sw.6 | specs/skill-workflow/spec.md | Regeneration failure does not lose the session log | --- | D3 | --- | test_decision_index_binding.py::test_regeneration_failure_keeps_the_log (1.2) | --- |
| sw.7 | specs/skill-workflow/spec.md | Regeneration is skipped when the generator is absent | --- | D3 | --- | test_decision_index_binding.py::test_absent_generator_warns_and_continues (1.3) | --- |
| sw.8 | specs/skill-workflow/spec.md | No worker call site invokes the persistence pipeline | --- | D4 | --- | test_decision_index_binding.py::test_no_worker_call_site (1.6) | --- |
| sw.9 | specs/skill-workflow/spec.md | A hand-edited session log still reports drift | --- | D5 | --- | test_decision_index_binding.py::test_hand_edited_log_still_reports_drift (1.7) | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|---|---|---|---|
| D1 | Regeneration is a fourth step in `write_both()`, not a caller responsibility | Step four runs after the coordinator step | The defect is that regeneration lives where a caller must remember; seven callers relocates it. Running after step one means it derives from what was actually appended |
| D2 | Always on, with no flag | No parameter, no environment variable | 0.06s across 168 changes leaves no cost argument, and an off-by-default correctness step shipped unreachable earlier this same session |
| D3 | Best-effort; the session log outranks the index | Broad catch, warn to stderr, append to `warnings`, never raise | `write_both()` is documented as never raising and four callers rely on it; a stale index is a reported one-command condition |
| D4 | Orchestrator-scoping becomes enforced | Structural test over the skill payload | Step four writes outside every package's `write_allow`; the restriction is real but currently only convention |
| D5 | The gate keeps checking | No change to the producer or its classification | This removes one cause; hand-edits, manual archive moves, and future writers still stale the index |

## Review Findings Summary

| Finding ID | Package | Type | Criticality | Disposition | Resolution |
|---|---|---|---|---|---|

## Coverage Summary

- **Requirements traced**: 0/9
- **Tests mapped**: 9 requirements have at least one test
- **Evidence collected**: 0/9 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
